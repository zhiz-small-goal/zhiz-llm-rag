#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rag_status.py

目标：
- 解决“多机/重复构建后忘记进度”的痛点：基于**本地真实产物 + 报告**，给出当前状态与下一步建议。
- 默认只读：不触发 embedding / 不访问网络 / 不修改 Chroma / 不写任何产物（除非显式 --json-out）。

输出：
- 人类可读：按步骤列出 OK/MISS/STALE/FAIL，并给出 NEXT 建议命令。
- 机器可读（可选）：遵循 docs/reference/REFERENCE.md 的 report 契约（schema_version=1）。

推荐用法（与 docs/howto/OPERATION_GUIDE.md 对齐）：
  rag-status
  rag-status --profile build_profile_schemeB.json
  rag-status --profile build_profile_schemeB.json --strict --json-out data_processed/build_reports/status.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from mhy_ai_rag_data.project_paths import find_project_root
from mhy_ai_rag_data.tools.reporting import add_error, build_base, status_to_rc, write_report

# Optional: index_state is pure-stdlib in this repo; keep import guarded in case of partial installs.
try:
    from mhy_ai_rag_data.tools import index_state as index_state_mod
except Exception:  # noqa: BLE001
    index_state_mod = None  # type: ignore


@dataclass(frozen=True)
class CheckItem:
    key: str
    label: str
    kind: str  # "file" | "json" | "dir" | "report_v1" | "stage1_verify" | "stage1_snapshot"
    path: Path
    inputs: Tuple[Path, ...] = ()
    freshness: Optional[Path] = None  # optional: use this path's mtime as freshness basis
    optional: bool = False


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    kb = n / 1024.0
    if kb < 1024:
        return f"{kb:.1f} KiB"
    mb = kb / 1024.0
    if mb < 1024:
        return f"{mb:.1f} MiB"
    gb = mb / 1024.0
    return f"{gb:.2f} GiB"


def _iso_local(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _safe_stat(p: Path) -> Optional[os.stat_result]:
    try:
        return p.stat()
    except Exception:  # noqa: BLE001
        return None


def _dir_latest_mtime(d: Path, *, max_entries: int = 2000) -> Optional[float]:
    if not d.exists():
        return None
    try:
        # Use a bounded walk to avoid pathological huge dirs.
        n = 0
        latest = None
        for root, _, files in os.walk(d):
            for fn in files:
                n += 1
                if n > max_entries:
                    return latest  # best effort
                p = Path(root) / fn
                st = _safe_stat(p)
                if not st:
                    continue
                mt = st.st_mtime
                if latest is None or mt > latest:
                    latest = mt
        if latest is not None:
            return latest
        st = _safe_stat(d)
        return st.st_mtime if st else None
    except Exception:  # noqa: BLE001
        st = _safe_stat(d)
        return st.st_mtime if st else None


def _mtime(p: Path) -> Optional[float]:
    st = _safe_stat(p)
    if not st:
        return None
    return st.st_mtime


def _is_stale(out_path: Path, inputs: Sequence[Path], *, freshness_path: Optional[Path] = None) -> bool:
    """Return True if any input is newer than output.

    freshness_path:
      Some items (notably the Chroma DB dir) have unstable mtimes on Windows/SQLite even in read-only flows.
      When provided and exists, we use its mtime as the 'output' freshness basis, while still displaying out_path.
    """
    if not inputs:
        return False

    basis = freshness_path if (freshness_path is not None and freshness_path.exists()) else out_path
    out_mt = _dir_latest_mtime(basis) if basis.is_dir() else _mtime(basis)
    if out_mt is None:
        return False

    for inp in inputs:
        inp_mt = _dir_latest_mtime(inp) if inp.is_dir() else _mtime(inp)
        if inp_mt is None:
            continue
        if inp_mt > out_mt:
            return True
    return False


def _read_json(p: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj, None
        return None, "json_root_not_object"
    except Exception as e:  # noqa: BLE001
        return None, f"json_parse_error: {e!r}"


def _git_head_short(root: Path) -> Optional[str]:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        s = (p.stdout or "").strip()
        return s or None
    except Exception:  # noqa: BLE001
        return None


def _load_profile(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    obj, err = _read_json(path)
    if err:
        return None, err
    # minimal sanity
    if obj is None:
        return None, "profile_not_object"
    return obj, None


def _resolve_path(root: Path, p: str) -> Path:
    x = Path(p)
    return (root / x).resolve() if not x.is_absolute() else x.resolve()


def _default_commands(*, profile_path: Optional[Path]) -> Dict[str, List[str]]:
    # Prefer profile-based wrappers when available; otherwise fall back to rag-* entrypoints.
    prof = str(profile_path) if profile_path else "build_profile_schemeB.json"
    return {
        "inventory": ["rag-inventory", "python make_inventory.py"],
        "extract_units": ["rag-extract-units", "python extract_units.py"],
        "validate_units": [
            "rag-validate-units --json-out data_processed/build_reports/units.json",
            "python validate_rag_units.py --json-out data_processed/build_reports/units.json",
        ],
        "plan": [
            "rag-plan",
            "python tools/plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl --out data_processed/chunk_plan.json",
        ],
        "build_profile": [
            f"python tools/run_build_profile.py --profile {prof}",
            "rag-build  # (不推荐默认：更适合无 profile 的简单构建)",
        ],
        "build_with_timing": [f"python tools/run_profile_with_timing.py --profile {prof} --smoke"],
        "stamp": [
            "rag-stamp --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json",
            "python tools/write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json --writer manual",
        ],
        "check": [
            "rag-check --json-out data_processed/build_reports/check.json",
            "python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json --json-out data_processed/build_reports/check.json",
        ],
        "probe_llm": [
            "rag-probe-llm --base http://localhost:8000/v1 --timeout 10 --json-out data_processed/build_reports/llm_probe.json",
            "python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed/build_reports/llm_probe.json",
        ],
        "verify_stage1": [
            "python -m tools.verify_stage1_pipeline --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --timeout 10",
            "python -m mhy_ai_rag_data.tools.verify_stage1_pipeline --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --timeout 10",
        ],
        "snapshot_stage1": [
            "python -m tools.snapshot_stage1_baseline --root . --out data_processed/build_reports/stage1_baseline_snapshot.json",
            "python -m mhy_ai_rag_data.tools.snapshot_stage1_baseline --root . --out data_processed/build_reports/stage1_baseline_snapshot.json",
        ],
    }


def _make_checks(
    *,
    root: Path,
    profile: Optional[Dict[str, Any]],
    db: Path,
    collection: str,
    units: Path,
    plan: Path,
    reports_dir: Path,
    state_root: Optional[Path],
) -> List[CheckItem]:
    inv = root / "inventory.csv"
    chroma_dir = db

    units_report = reports_dir / "units.json"
    check_report = reports_dir / "check.json"
    llm_report = reports_dir / "llm_probe.json"
    stage1_verify = reports_dir / "stage1_verify.json"
    stage1_snapshot = reports_dir / "stage1_baseline_snapshot.json"

    # A stable DB freshness basis (updated only on successful write-to-db operations).
    state_dir = state_root if state_root is not None else (root / "data_processed" / "index_state")
    stamp_path = state_dir / "db_build_stamp.json"
    stamp_exists = stamp_path.exists()

    items: List[CheckItem] = [
        CheckItem("inventory", "inventory.csv（资料清单）", "file", inv, optional=True),
        CheckItem("units", "text_units.jsonl（抽取产物）", "file", units, inputs=(inv,)),
        CheckItem(
            "units_report", "units.json（validate 报告）", "report_v1", units_report, inputs=(units,), optional=True
        ),
        CheckItem("plan", "chunk_plan.json（chunk 计划）", "json", plan, inputs=(units,)),
        # NOTE: DB mtime is unstable on Windows/SQLite in some read flows; prefer stamp_path when available.
        CheckItem(
            "db",
            f"Chroma DB（{collection}）",
            "dir",
            chroma_dir,
            inputs=(plan,),
            freshness=stamp_path if stamp_exists else None,
        ),
        CheckItem("db_stamp", "db_build_stamp.json（DB 构建戳）", "json", stamp_path, optional=True),
        CheckItem(
            "check_report",
            "check.json（强校验报告）",
            "report_v1",
            check_report,
            inputs=(plan, stamp_path) if stamp_exists else (plan, chroma_dir),
            optional=True,
        ),
        CheckItem("llm_probe", "llm_probe.json（LLM 探测报告）", "report_v1", llm_report, optional=True),
        CheckItem(
            "stage1_verify", "stage1_verify.json（Stage-1 一键验收）", "stage1_verify", stage1_verify, optional=True
        ),
        CheckItem(
            "stage1_snapshot",
            "stage1_baseline_snapshot.json（Stage-1 基线快照）",
            "stage1_snapshot",
            stage1_snapshot,
            optional=True,
        ),
    ]

    # Index-state (incremental sync) is profile-driven; report as optional info.
    if state_root is not None:
        items.append(CheckItem("index_state", "index_state（增量同步状态）", "dir", state_root, optional=True))
    return items


def _evaluate_item(it: CheckItem) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "key": it.key,
        "label": it.label,
        "path": str(it.path),
        "kind": it.kind,
        "exists": it.path.exists(),
        "optional": it.optional,
        "status": "MISS",
        "detail": {},
        "stale": False,
    }

    if not it.path.exists():
        out["status"] = "MISS"
        return out

    # stat
    if it.path.is_file():
        st = _safe_stat(it.path)
        if st:
            out["detail"]["size"] = st.st_size
            out["detail"]["size_h"] = _fmt_bytes(st.st_size)
            out["detail"]["mtime"] = st.st_mtime
            out["detail"]["mtime_h"] = _iso_local(st.st_mtime)
        if st and st.st_size == 0:
            out["status"] = "FAIL"
            out["detail"]["reason"] = "empty_file"
            return out
    else:
        mt = _dir_latest_mtime(it.path)
        if mt is not None:
            out["detail"]["mtime"] = mt
            out["detail"]["mtime_h"] = _iso_local(mt)

    # stale
    out["stale"] = _is_stale(it.path, it.inputs, freshness_path=it.freshness)

    if it.kind == "file":
        out["status"] = "OK"
        if out["stale"]:
            out["status"] = "STALE"
        return out

    if it.kind == "dir":
        # consider non-empty dir for OK
        any_file = False
        try:
            for _ in it.path.rglob("*"):
                any_file = True
                break
        except Exception:  # noqa: BLE001
            any_file = True
        out["status"] = "OK" if any_file else "FAIL"
        if not any_file:
            out["detail"]["reason"] = "empty_dir"
        if out["stale"] and out["status"] == "OK":
            out["status"] = "STALE"
        return out

    if it.kind == "json":
        obj, err = _read_json(it.path)
        if err:
            out["status"] = "FAIL"
            out["detail"]["reason"] = err
            return out
        out["status"] = "OK"
        # small hints
        if obj is not None:
            if "chunks" in obj and isinstance(obj["chunks"], list):
                out["detail"]["chunks"] = len(obj["chunks"])
            if "n_chunks" in obj and isinstance(obj["n_chunks"], int):
                out["detail"]["n_chunks"] = obj["n_chunks"]
            # db_build_stamp.json / other helper jsons
            if "collection_count" in obj and isinstance(obj.get("collection_count"), int):
                out["detail"]["collection_count"] = int(obj["collection_count"])
            if "schema_hash" in obj and isinstance(obj.get("schema_hash"), str):
                out["detail"]["schema_hash"] = str(obj["schema_hash"])
        if out["stale"]:
            out["status"] = "STALE"
        return out

    if it.kind == "report_v1":
        obj, err = _read_json(it.path)
        if err:
            out["status"] = "FAIL"
            out["detail"]["reason"] = err
            return out
        if obj is None:
            out["status"] = "FAIL"
            out["detail"]["reason"] = "report_not_object"
            return out
        # Support both v1 and v2 reports (v2: schema_version=2 with summary)
        sv = obj.get("schema_version")
        if sv not in (1, 2):
            out["status"] = "FAIL"
            out["detail"]["reason"] = f"unsupported_schema_version: {sv}"
            return out
        # Extract status: v1 uses top-level "status", v2 uses "summary.overall_status_label"
        if sv == 1:
            report_status = str(obj.get("status") or "INFO").upper()
            out["detail"]["step"] = obj.get("step")
        else:  # sv == 2
            summary = obj.get("summary", {})
            report_status = str(summary.get("overall_status_label") or "INFO").upper()
            out["detail"]["total_items"] = summary.get("total_items", 0)
            out["detail"]["max_severity"] = summary.get("max_severity_level", 0)
        out["detail"]["report_status"] = report_status
        if report_status == "PASS":
            out["status"] = "OK"
        elif report_status in ("FAIL", "ERROR"):
            out["status"] = "FAIL"
            out["detail"]["errors"] = obj.get("errors", [])
        else:
            out["status"] = "OK"  # INFO/WARN: treat as ok for progress
        if out["stale"] and out["status"] == "OK":
            out["status"] = "STALE"
        return out

    if it.kind == "stage1_verify":
        obj, err = _read_json(it.path)
        if err or obj is None:
            out["status"] = "FAIL"
            out["detail"]["reason"] = err or "report_not_object"
            return out
        overall = str(obj.get("overall") or "UNKNOWN").upper()
        out["detail"]["overall"] = overall
        out["status"] = "OK" if overall == "PASS" else "FAIL"
        if out["stale"] and out["status"] == "OK":
            out["status"] = "STALE"
        return out

    if it.kind == "stage1_snapshot":
        obj, err = _read_json(it.path)
        if err:
            out["status"] = "FAIL"
            out["detail"]["reason"] = err
            return out
        out["status"] = "OK"
        if obj is not None:
            out["detail"]["keys"] = sorted(list(obj.keys()))[:20]
        if out["stale"]:
            out["status"] = "STALE"
        return out

    out["status"] = "OK"
    return out


def _pick_next(evals: Dict[str, Dict[str, Any]], cmds: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    A deterministic "resume" policy:

    Order (aligned with docs/howto/OPERATION_GUIDE.md):
    - inventory -> extract_units -> validate_units -> plan -> build -> check -> probe_llm -> verify_stage1 -> snapshot_stage1

    Rules:
    - If a required artifact is MISS/FAIL/STALE: pick it as NEXT.
    - Optional items do not block progress, but are suggested when nearby.
    """
    order = [
        ("inventory", "Step 3（inventory）", "inventory"),
        ("units", "Step 3（extract units）", "extract_units"),
        ("units_report", "Step 3（validate units）", "validate_units"),
        ("plan", "Step 4（plan）", "plan"),
        ("db", "Step 5（build）", "build_with_timing"),
        ("db_stamp", "Step 5.5（db stamp）", "stamp"),
        ("check_report", "Step 6（check）", "check"),
        ("llm_probe", "Step 8（probe llm）", "probe_llm"),
        ("stage1_verify", "Step 9（verify stage1）", "verify_stage1"),
        ("stage1_snapshot", "Step 10（snapshot stage1）", "snapshot_stage1"),
    ]

    # inventory is optional unless units missing
    # If units MISS, and inventory MISS: prioritize inventory.
    if evals.get("units", {}).get("status") == "MISS" and evals.get("inventory", {}).get("status") == "MISS":
        return {
            "stage": "inventory",
            "why": "units 缺失且 inventory.csv 不存在；需要先生成资料清单。",
            "commands": cmds["inventory"],
        }

    for key, step_label, cmd_key in order:
        st = evals.get(key, {}).get("status")
        opt = bool(evals.get(key, {}).get("optional"))
        if opt and key in (
            "inventory",
            "units_report",
            "db_stamp",
            "check_report",
            "llm_probe",
            "stage1_verify",
            "stage1_snapshot",
        ):
            # optional items don't block unless FAIL/STALE and downstream depends
            if key == "units_report":
                # recommend validate even if optional when units exists
                if evals.get("units", {}).get("status") in ("OK", "STALE") and st in ("MISS", "FAIL", "STALE"):
                    return {
                        "stage": key,
                        "why": f"{step_label}：units 已存在，但 validate 报告缺失/失败/过期；建议跑一次硬校验以避免后续漂移。",
                        "commands": cmds[cmd_key],
                    }
                continue
            if key == "db_stamp":
                # 若库存在但 stamp 缺失：建议先补 stamp，避免后续 check 被误判为 STALE。
                if evals.get("db", {}).get("status") in ("OK", "STALE") and st in ("MISS", "FAIL"):
                    return {
                        "stage": key,
                        "why": f"{step_label}：检测到 DB 已存在，但 db_build_stamp.json 缺失/不可读；建议补写构建戳以获得稳定的 freshness 判定（避免只读评测刷新 DB mtime 导致误 STALE）。",
                        "commands": cmds[cmd_key],
                    }
                continue
            if key == "check_report":
                # if db ok but check missing/fail/stale, recommend check
                if evals.get("db", {}).get("status") in ("OK", "STALE") and st in ("MISS", "FAIL", "STALE"):
                    return {
                        "stage": key,
                        "why": f"{step_label}：库已存在，但强校验报告缺失/失败/过期；建议跑 check 以确认 expected==count。",
                        "commands": cmds[cmd_key],
                    }
                continue
            if key in ("llm_probe", "stage1_verify", "stage1_snapshot"):
                # keep optional by default: only suggest when explicitly missing AND all prior core steps ok
                pass

        if st in ("MISS", "FAIL", "STALE"):
            return {"stage": key, "why": f"{step_label}：检测到 {key}={st}。", "commands": cmds[cmd_key]}

    return {
        "stage": "complete",
        "why": "核心产物已齐全（含 plan/db/check 等）；可进入 Stage-2 评测或继续做质量回归。",
        "commands": ["rag-check-all", "python -m tools.view_stage2_reports  # 若你已跑过 Stage-2"],
    }


def _print_human(root: Path, cfg: Dict[str, Any], evals: Dict[str, Dict[str, Any]], next_: Dict[str, Any]) -> None:
    print("== RAG STATUS ==")
    print("time   :", _iso_local(time.time()))
    print("root   :", root)
    if cfg.get("profile"):
        print("profile:", cfg["profile"])
    if cfg.get("git"):
        print("git    :", cfg["git"])
    print("python :", sys.executable)
    print("py_ver :", platform.python_version())
    print("os     :", f"{platform.system()} {platform.release()} ({platform.machine()})")
    print("db     :", cfg.get("db"))
    print("col    :", cfg.get("collection"))
    if cfg.get("reports_dir"):
        print("reports:", cfg.get("reports_dir"))
    if cfg.get("state_root"):
        print("state  :", cfg.get("state_root"))
    if cfg.get("db_stamp"):
        print("stamp  :", cfg.get("db_stamp"))
    print("-" * 72)

    # stable order
    keys = [
        "inventory",
        "units",
        "units_report",
        "plan",
        "db",
        "db_stamp",
        "check_report",
        "llm_probe",
        "stage1_verify",
        "stage1_snapshot",
        "index_state",
    ]
    for k in keys:
        if k not in evals:
            continue
        e = evals[k]
        st = e["status"]
        label = e["label"]
        path = e["path"]
        detail = e.get("detail", {})
        line = f"[{st:<5}] {label:<28}  {path}"
        print(line)
        # compact details
        extra: List[str] = []
        if "size_h" in detail:
            extra.append(f"size={detail['size_h']}")
        if "mtime_h" in detail:
            extra.append(f"mtime={detail['mtime_h']}")
        if "collection_count" in detail:
            extra.append(f"count={detail['collection_count']}")
        if "report_status" in detail:
            extra.append(f"report={detail['report_status']}")
        if "overall" in detail:
            extra.append(f"overall={detail['overall']}")
        if "chunks" in detail:
            extra.append(f"chunks={detail['chunks']}")
        if "collection_count" in detail:
            extra.append(f"count={detail['collection_count']}")
        if "schema_hash" in detail:
            extra.append(f"schema={detail['schema_hash']}")
        if extra:
            print(" " * 8 + "; ".join(extra))
        if st == "FAIL" and detail.get("errors"):
            errs = detail["errors"]
            # show at most 3
            for x in errs[:3]:
                code = x.get("code")
                msg = x.get("message")
                print(" " * 8 + f"- {code}: {msg}")
            if len(errs) > 3:
                print(" " * 8 + f"... ({len(errs)} errors)")
    print("-" * 72)
    print("NEXT :", next_.get("stage"))
    print("WHY  :", next_.get("why"))
    print("CMDS :")
    for c in next_.get("commands", []):
        print("  -", c)


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG status / resume helper (project-specific).")
    ap.add_argument("--root", default=None, help="项目根目录（默认自动向上查找）")
    ap.add_argument("--profile", default=None, help="构建 profile JSON（推荐，用于对齐 db/units/reports/state_root）")
    ap.add_argument("--db", default=None, help="Chroma DB 目录（可覆盖 profile）")
    ap.add_argument("--collection", default=None, help="collection 名（可覆盖 profile）")
    ap.add_argument("--units", default=None, help="text_units.jsonl 路径（可覆盖 profile）")
    ap.add_argument("--plan", default=None, help="chunk_plan.json 路径（可覆盖 profile 或默认）")
    ap.add_argument("--reports-dir", default=None, help="build_reports 目录（可覆盖 profile 或默认）")
    ap.add_argument("--state-root", default=None, help="index_state 根目录（可覆盖 profile）")
    ap.add_argument("--strict", action="store_true", help="严格模式：任何 MISS/FAIL/STALE 都返回非 0（FAIL）")
    ap.add_argument("--json-out", default=None, help="JSON 报告输出路径（提供则只写这一份）")
    ap.add_argument("--json-stdout", action="store_true", help="将 JSON 报告输出到 stdout（不落盘）")
    args = ap.parse_args()

    root = find_project_root(args.root)
    profile_path = _resolve_path(root, args.profile) if args.profile else None
    profile: Optional[Dict[str, Any]] = None
    if profile_path:
        prof, err = _load_profile(profile_path)
        if err:
            print(f"[WARN] failed to load profile: {profile_path} ({err})")
        else:
            profile = prof

    # Resolve config (priority: explicit args > profile > defaults)
    def pick(key: str, default: Any) -> Any:
        v = getattr(args, key.replace("-", "_"), None)
        if v:
            return v
        if profile and key in profile and profile[key] not in (None, ""):
            return profile[key]
        return default

    collection = str(pick("collection", "rag_chunks"))
    db = _resolve_path(root, str(pick("db", "chroma_db")))
    units = _resolve_path(root, str(pick("units", "data_processed/text_units.jsonl")))
    plan = _resolve_path(root, str(pick("plan", "data_processed/chunk_plan.json")))
    reports_dir = _resolve_path(root, str(pick("reports_dir", "data_processed/build_reports")))
    state_root_val = pick("state_root", "data_processed/index_state")
    state_root = _resolve_path(root, str(state_root_val)) if state_root_val else None

    cmds = _default_commands(profile_path=profile_path)
    items = _make_checks(
        root=root,
        profile=profile,
        db=db,
        collection=collection,
        units=units,
        plan=plan,
        reports_dir=reports_dir,
        state_root=state_root if state_root else None,
    )

    evals: Dict[str, Dict[str, Any]] = {}
    for it in items:
        evals[it.key] = _evaluate_item(it)

    next_ = _pick_next(evals, cmds)

    # Optional: index_state pointer info (best effort)
    if index_state_mod is not None and state_root is not None:
        try:
            latest = index_state_mod.read_latest_pointer(state_root, collection)
            if latest:
                evals.setdefault("index_state", {}).setdefault("detail", {})["latest_schema"] = latest
        except Exception:  # noqa: BLE001
            pass

    stamp_path = (
        state_root if state_root is not None else (root / "data_processed" / "index_state")
    ) / "db_build_stamp.json"

    cfg = {
        "profile": str(profile_path) if profile_path else None,
        "git": _git_head_short(root),
        "db": str(db),
        "collection": collection,
        "units": str(units),
        "plan": str(plan),
        "reports_dir": str(reports_dir),
        "state_root": str(state_root) if state_root else None,
        "db_stamp": str(stamp_path),
    }
    _print_human(root, cfg, evals, next_)

    # JSON report
    report = build_base("status", inputs=cfg)
    report["metrics"]["checks"] = evals
    report["metrics"]["next"] = next_

    # Decide report status
    if args.strict:
        bad = [k for k, v in evals.items() if v.get("status") in ("MISS", "FAIL", "STALE") and not v.get("optional")]
        # optional but important reports: treat FAIL as bad in strict
        bad += [k for k, v in evals.items() if v.get("status") == "FAIL" and v.get("optional")]
        if bad:
            report["status"] = "FAIL"
            add_error(report, "STATUS_STRICT_FAIL", "missing/failing/stale items", detail={"items": bad, "next": next_})
        else:
            report["status"] = "PASS"
    else:
        report["status"] = "INFO"

    if args.json_out:
        out_path = write_report(report, json_out=args.json_out, default_name="status_report.json")
        print(f"Wrote report: {out_path}")
    if args.json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return status_to_rc(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
