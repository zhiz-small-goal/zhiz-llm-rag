#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_report_tools_contract

Report Output v2 工具覆盖面与自描述一致性门禁：

1) 静态对账（registry <-> REPORT_TOOL_META）
   - registry: docs/reference/report_tools_registry.toml
   - REPORT_TOOL_META: 通过 AST 提取（不 import、不执行模块副作用）

2) 动态自检（tool --selftest）
   - 运行 tools/<tool_id>.py --selftest
   - 校验 report.json 通过 verify_report_output_contract
   - 校验 stdout == render_console(report)
   - 校验 report.md == render_markdown(report)
   - 对 high_cost 工具：校验 report.events.jsonl 至少 2 行可解析 JSON

本工具自身也输出 v2 report bundle（report.json + report.md + stdout 渲染）。
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_render import render_console, render_markdown
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args
from mhy_ai_rag_data.tools.verify_report_output_contract import verify as verify_report


REPORT_TOOL_META = {
    "id": "check_report_tools_contract",
    "kind": "VERIFY_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/check_report_tools_contract.py",
}


_ALLOWED_KINDS: Set[str] = {
    "CHECK_REPORT",
    "INDEX_REPORT",
    "STATE_REPORT",
    "EVAL_REPORT",
    "GATE_REPORT",
    "VERIFY_REPORT",
    "RENDER_REPORT",
}

_ALLOWED_CHANNELS: Set[str] = {"console", "file", "events", "checkpoint"}


@dataclass(frozen=True)
class RegistryTool:
    id: str
    module: str
    kind: str
    contract_version: int
    entrypoint: str
    channels: Tuple[str, ...]
    high_cost: bool
    supports_selftest: bool


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _as_bool(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


def _as_int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


def _read_toml(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if tomllib is None:
        return None, "tomllib_unavailable"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None, "toml_root_not_object"
        return data, None
    except Exception as e:  # noqa: BLE001
        return None, f"toml_parse_error: {type(e).__name__}: {e}"


def _extract_report_tool_meta(module_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extract REPORT_TOOL_META dict without importing the module."""

    try:
        src = module_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return None, f"read_error: {type(e).__name__}: {e}"

    try:
        tree = ast.parse(src, filename=str(module_path))
    except SyntaxError as e:
        return None, f"syntax_error: {e.msg}"

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "REPORT_TOOL_META":
                try:
                    val = ast.literal_eval(node.value)
                except Exception as e:  # noqa: BLE001
                    return None, f"meta_not_literal: {type(e).__name__}: {e}"
                if isinstance(val, dict):
                    return val, None
                return None, "meta_not_dict"

    return None, "meta_missing"


def _load_registry(
    registry_path: Path, *, repo_root: Path
) -> Tuple[Dict[str, RegistryTool], List[Dict[str, Any]], List[Dict[str, Any]]]:
    items: List[Dict[str, Any]] = []

    if not registry_path.exists():
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "registry_missing",
                    "title": "registry missing",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": f"missing registry file: {registry_path}",
                    "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1"
                    if registry_path.is_absolute()
                    else "docs/:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return {}, items, []

    data, err = _read_toml(registry_path)
    if err or not data:
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "registry_parse_failed",
                    "title": "registry parse failed",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": err or "unknown error",
                    "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return {}, items, []

    raw_list = data.get("tool")
    if not isinstance(raw_list, list):
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "registry_bad_schema",
                    "title": "registry schema invalid",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": "expected top-level key 'tool' as an array of tables ([[tool]])",
                    "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return {}, items, []

    by_id: Dict[str, RegistryTool] = {}
    normalized_raw: List[Dict[str, Any]] = []

    for i, t in enumerate(raw_list, start=1):
        if not isinstance(t, dict):
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_entry_not_object:{i}",
                        "title": "registry entry invalid",
                        "status_label": "ERROR",
                        "severity_level": 4,
                        "message": f"registry entry #{i} is not an object",
                        "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        tid = _as_str(t.get("id"))
        module = _as_str(t.get("module"))
        kind = _as_str(t.get("kind")).upper()
        entrypoint = _as_str(t.get("entrypoint"))
        cv = _as_int(t.get("contract_version"))
        channels_raw = t.get("channels")
        channels = tuple(_as_str(x) for x in channels_raw) if isinstance(channels_raw, list) else tuple()
        high_cost = bool(t.get("high_cost") is True)
        supports_selftest = bool(t.get("supports_selftest") is True)

        normalized_raw.append(dict(t))

        problems: List[str] = []
        if not tid:
            problems.append("id missing")
        if not module:
            problems.append("module missing")
        if kind not in _ALLOWED_KINDS:
            problems.append(f"kind invalid: {kind or '(empty)'}")
        if cv != 2:
            problems.append(f"contract_version invalid: {cv}")
        if not entrypoint:
            problems.append("entrypoint missing")
        if not channels:
            problems.append("channels missing")
        else:
            bad_ch = [c for c in channels if c not in _ALLOWED_CHANNELS]
            if bad_ch:
                problems.append(f"channels invalid: {bad_ch}")

        if tid and tid in by_id:
            problems.append(f"duplicate id: {tid}")

        if problems:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_entry_invalid:{tid or i}",
                        "title": "registry entry invalid",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "\n".join(problems),
                        "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                        "detail": {"entry": t},
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        by_id[tid] = RegistryTool(
            id=tid,
            module=module,
            kind=kind,
            contract_version=int(cv or 2),
            entrypoint=entrypoint,
            channels=channels,
            high_cost=high_cost,
            supports_selftest=supports_selftest,
        )

    return by_id, items, normalized_raw


def _scan_meta(*, repo_root: Path, scan_dir: Path) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    items: List[Dict[str, Any]] = []
    metas: Dict[str, Dict[str, Any]] = {}

    if not scan_dir.exists():
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "scan_dir_missing",
                    "title": "scan directory missing",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": f"scan_dir not found: {scan_dir}",
                    "loc": f"{scan_dir.relative_to(repo_root).as_posix()}:1:1"
                    if scan_dir.is_absolute()
                    else "src/:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return {}, items

    for p in sorted(scan_dir.rglob("*.py")):
        if p.name.startswith("__"):
            continue

        meta, err = _extract_report_tool_meta(p)
        if err == "meta_missing":
            continue
        if err or meta is None:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_parse_failed:{p.relative_to(repo_root).as_posix()}",
                        "title": "REPORT_TOOL_META parse failed",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": err or "unknown error",
                        "loc": f"{p.relative_to(repo_root).as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        tid = _as_str(meta.get("id"))
        if not tid:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_missing_id:{p.relative_to(repo_root).as_posix()}",
                        "title": "REPORT_TOOL_META missing id",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "REPORT_TOOL_META.id missing/invalid",
                        "loc": f"{p.relative_to(repo_root).as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        if tid in metas:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_duplicate_id:{tid}",
                        "title": "REPORT_TOOL_META duplicate id",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"duplicate tool id: {tid}",
                        "loc": f"{p.relative_to(repo_root).as_posix()}:1:1",
                        "detail": {
                            "previous": metas[tid].get("path"),
                            "current": p.relative_to(repo_root).as_posix(),
                        },
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        metas[tid] = {"meta": meta, "path": p.relative_to(repo_root).as_posix()}

    return metas, items


def _compare_registry_vs_meta(reg: RegistryTool, meta: Mapping[str, Any]) -> List[str]:
    mism: List[str] = []

    meta_kind = _as_str(meta.get("kind")).upper()
    meta_cv = _as_int(meta.get("contract_version"))
    meta_channels_raw = meta.get("channels")
    meta_channels = tuple(_as_str(x) for x in meta_channels_raw) if isinstance(meta_channels_raw, list) else tuple()
    meta_high_cost = bool(meta.get("high_cost") is True)
    meta_supports_selftest = bool(meta.get("supports_selftest") is True)
    meta_entrypoint = _as_str(meta.get("entrypoint"))

    if meta_kind != reg.kind:
        mism.append(f"kind mismatch: registry={reg.kind} meta={meta_kind}")
    if meta_cv != reg.contract_version:
        mism.append(f"contract_version mismatch: registry={reg.contract_version} meta={meta_cv}")

    if set(meta_channels) != set(reg.channels):
        mism.append(f"channels mismatch: registry={list(reg.channels)} meta={list(meta_channels)}")

    if meta_high_cost != reg.high_cost:
        mism.append(f"high_cost mismatch: registry={reg.high_cost} meta={meta_high_cost}")

    if meta_supports_selftest != reg.supports_selftest:
        mism.append(f"supports_selftest mismatch: registry={reg.supports_selftest} meta={meta_supports_selftest}")

    if meta_entrypoint and meta_entrypoint != reg.entrypoint:
        mism.append(f"entrypoint mismatch: registry={reg.entrypoint} meta={meta_entrypoint}")

    return mism


def _git_changed_paths(repo_root: Path) -> Set[str]:
    """Return a set of repo-relative paths that are changed (best-effort)."""

    def _run(args: Sequence[str]) -> List[str]:
        try:
            out = subprocess.check_output(args, cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL)
            return [ln.strip() for ln in out.splitlines() if ln.strip()]
        except Exception:
            return []

    changed = set(_run(["git", "diff", "--name-only"]))
    changed |= set(_run(["git", "diff", "--name-only", "--cached"]))
    changed |= set(_run(["git", "ls-files", "-m"]))
    changed |= set(_run(["git", "ls-files", "-o", "--exclude-standard"]))
    return set(p.replace("\\", "/") for p in changed)


def _tool_paths_for_registry_entry(tool: RegistryTool) -> Set[str]:
    out: Set[str] = set()
    out.add(f"tools/{tool.id}.py")
    # module -> src path
    mod = tool.module.strip()
    if mod.startswith("mhy_ai_rag_data.tools."):
        fn = mod.split(".")[-1] + ".py"
        out.add(f"src/mhy_ai_rag_data/tools/{fn}")
    return out


def _select_tool_ids(*, scope: str, registry: Mapping[str, RegistryTool], changed: Set[str]) -> List[str]:
    ids = sorted(registry.keys())
    if scope == "all":
        return ids
    if scope != "changed":
        return ids
    if not changed:
        return []

    selected: List[str] = []
    for tid, tool in registry.items():
        if _tool_paths_for_registry_entry(tool) & changed:
            selected.append(tid)
    return sorted(set(selected))


def _parse_out_token(stderr: str) -> Tuple[Optional[Path], Optional[str]]:
    """Parse the canonical stderr token.

    Returns (path, warning_message).
    """

    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("out = "):
            continue
        path_str = line[len("out = ") :].strip()
        if not path_str:
            return None, "out token path empty"
        if i + 1 < len(lines):
            pure = lines[i + 1].strip()
            if pure and pure != path_str:
                return None, "out token path mismatch between token line and next-line path"
        return Path(path_str), None
    return None, "out token not found"


def _run_tool_selftest(*, repo_root: Path, tool: RegistryTool, artifacts_root: Path, timeout_s: int) -> Dict[str, Any]:
    wrapper = repo_root / "tools" / f"{tool.id}.py"
    if not wrapper.exists():
        return {"ok": False, "error": f"missing wrapper: {wrapper}"}

    cmd: List[str] = [
        sys.executable,
        str(wrapper),
        "--selftest",
        "--root",
        str(repo_root),
        "--artifacts",
        str(artifacts_root),
    ]

    if tool.high_cost:
        cmd += ["--durability-mode", "fsync", "--fsync-interval-ms", "1"]

    try:
        p = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_s)),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout_s}s", "cmd": cmd}

    out_path, warn = _parse_out_token(p.stderr)
    return {
        "ok": p.returncode == 0,
        "rc": int(p.returncode),
        "stdout": p.stdout,
        "stderr": p.stderr,
        "out_path": str(out_path) if out_path else "",
        "out_warn": warn or "",
        "cmd": cmd,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Any]:
    out: List[Any] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s:
            continue
        out.append(json.loads(s))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Check report-output-v2 tools registry vs REPORT_TOOL_META")
    add_selftest_args(ap)

    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument(
        "--registry",
        default="docs/reference/report_tools_registry.toml",
        help="Registry TOML path (relative to --root)",
    )
    ap.add_argument(
        "--scan-dir",
        default="src/mhy_ai_rag_data/tools",
        help="Directory to scan for REPORT_TOOL_META (relative to --root)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/check_report_tools_contract.json",
        help="Output report.json path (relative to --root)",
    )

    ap.add_argument(
        "--mode",
        default="static",
        choices=["static", "selftest", "all"],
        help="static: only static checks; selftest: only run tool --selftest; all: both",
    )
    ap.add_argument(
        "--scope",
        default="all",
        choices=["all", "changed"],
        help="Which tools to run selftest for",
    )
    ap.add_argument("--timeout-s", type=int, default=90, help="Per-tool selftest timeout")
    ap.add_argument("--strict", action="store_true", help="Treat verify warnings as failures")

    args = ap.parse_args()

    # tool-level selftest
    repo_root = Path(getattr(args, "root", ".")).resolve()
    loc = Path(__file__).resolve()
    try:
        loc = loc.relative_to(repo_root)
    except Exception:
        pass

    rc = maybe_run_selftest_from_args(args=args, meta=REPORT_TOOL_META, repo_root=repo_root, loc_source=loc)
    if rc is not None:
        return int(rc)

    registry_path = (repo_root / str(args.registry)).resolve()
    scan_dir = (repo_root / str(args.scan_dir)).resolve()
    out_path = (repo_root / str(args.out)).resolve()

    items: List[Dict[str, Any]] = []

    # -------- static checks --------
    reg_by_id: Dict[str, RegistryTool] = {}
    reg_raw: List[Dict[str, Any]] = []
    if args.mode in {"static", "all"}:
        reg_by_id, reg_items, reg_raw = _load_registry(registry_path, repo_root=repo_root)
        items.extend(reg_items)

        metas_by_id, meta_items = _scan_meta(repo_root=repo_root, scan_dir=scan_dir)
        items.extend(meta_items)

        # registry -> meta
        for tid, reg in sorted(reg_by_id.items()):
            meta_entry = metas_by_id.get(tid)
            if not meta_entry:
                items.append(
                    ensure_item_fields(
                        {
                            "tool": "check_report_tools_contract",
                            "key": f"missing_meta_for_registry:{tid}",
                            "title": "missing REPORT_TOOL_META for registry tool",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"tool id {tid} exists in registry but not found in scan_dir",
                            "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                        },
                        tool_default="check_report_tools_contract",
                    )
                )
                continue

            mismatches = _compare_registry_vs_meta(reg, meta_entry.get("meta") or {})
            if mismatches:
                items.append(
                    ensure_item_fields(
                        {
                            "tool": "check_report_tools_contract",
                            "key": f"registry_vs_meta_mismatch:{tid}",
                            "title": "registry vs REPORT_TOOL_META mismatch",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "\n".join(mismatches),
                            "loc": f"{meta_entry.get('path')}:1:1",
                        },
                        tool_default="check_report_tools_contract",
                    )
                )

        # meta -> registry missing
        for tid, meta_entry in sorted(metas_by_id.items()):
            if tid not in reg_by_id:
                items.append(
                    ensure_item_fields(
                        {
                            "tool": "check_report_tools_contract",
                            "key": f"missing_registry_for_meta:{tid}",
                            "title": "missing registry entry for REPORT_TOOL_META",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"tool id {tid} exists in REPORT_TOOL_META but not in registry",
                            "loc": f"{meta_entry.get('path')}:1:1",
                        },
                        tool_default="check_report_tools_contract",
                    )
                )

    # -------- dynamic selftests --------
    if args.mode in {"selftest", "all"}:
        if not reg_by_id:
            reg_by_id, reg_items, reg_raw = _load_registry(registry_path, repo_root=repo_root)
            items.extend(reg_items)

        artifacts_root = Path(
            str(getattr(args, "artifacts", "data_processed/build_reports/_selftest_artifacts"))
        ).resolve()
        artifacts_root.mkdir(parents=True, exist_ok=True)

        changed = _git_changed_paths(repo_root)
        tool_ids = _select_tool_ids(scope=str(args.scope), registry=reg_by_id, changed=changed)

        if not tool_ids:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": "dynamic_scope_empty",
                        "title": "dynamic selftest scope empty",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"no tools selected for scope={args.scope} (changed files: {len(changed)})",
                        "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
        else:
            for tid in tool_ids:
                tool = reg_by_id[tid]
                if not tool.supports_selftest:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_skip_no_selftest:{tid}",
                                "title": "tool does not support selftest",
                                "status_label": "WARN",
                                "severity_level": 2,
                                "message": "supports_selftest=false in registry",
                                "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )
                    continue

                res = _run_tool_selftest(
                    repo_root=repo_root,
                    tool=tool,
                    artifacts_root=artifacts_root,
                    timeout_s=int(args.timeout_s),
                )

                if not bool(res.get("ok")):
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_selftest_failed:{tid}",
                                "title": "tool selftest execution failed",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": _as_str(res.get("error")) or "non-zero return code",
                                "loc": f"tools/{tid}.py:1:1",
                                "detail": {
                                    "rc": res.get("rc"),
                                    "cmd": res.get("cmd"),
                                    "stdout": res.get("stdout"),
                                    "stderr": res.get("stderr"),
                                },
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )
                    continue

                # locate report bundle
                out_path_str = _as_str(res.get("out_path"))
                expected = (artifacts_root / tid / "report.json").resolve()
                report_json = Path(out_path_str).resolve() if out_path_str else expected

                if report_json != expected:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_report_path_unexpected:{tid}",
                                "title": "selftest report path unexpected",
                                "status_label": "WARN",
                                "severity_level": 2,
                                "message": f"stderr out path {report_json} != expected {expected}",
                                "loc": f"tools/{tid}.py:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )

                report_md = (expected.with_suffix(".md")).resolve()
                events_path = (expected.parent / "report.events.jsonl").resolve()
                checkpoint_path = (expected.parent / "checkpoint.json").resolve()

                if not report_json.exists():
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_missing_report_json:{tid}",
                                "title": "missing report.json",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": f"expected {report_json}",
                                "loc": f"tools/{tid}.py:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )
                    continue

                report_obj = _read_json(report_json)
                vr = verify_report(
                    report=report_obj,
                    report_path=report_json,
                    repo_root=repo_root,
                    strict=True,
                )

                if not vr.ok:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_contract_violation:{tid}",
                                "title": "tool selftest violates report output contract",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": "\n".join(list(vr.errors)[:50]),
                                "loc": f"tools/{tid}.py:1:1",
                                "detail": {"warnings": vr.warnings, "out_warn": res.get("out_warn", "")},
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )
                    continue

                # stdout exact match
                expected_console = render_console(report_obj, title=str(report_obj.get("tool") or tid))
                got_stdout = str(res.get("stdout") or "")
                if got_stdout != expected_console:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_stdout_mismatch:{tid}",
                                "title": "stdout != render_console(report)",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": "tool stdout did not match render_console(report)",
                                "loc": f"tools/{tid}.py:1:1",
                                "detail": {
                                    "expected_first_200": expected_console[:200],
                                    "got_first_200": got_stdout[:200],
                                },
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )

                # markdown exact match
                if not report_md.exists():
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_missing_md:{tid}",
                                "title": "missing report.md",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": f"expected {report_md}",
                                "loc": f"tools/{tid}.py:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )
                else:
                    got_md = report_md.read_text(encoding="utf-8", errors="replace")
                    expected_md = render_markdown(
                        report_obj,
                        report_path=report_json,
                        root=repo_root,
                        title=str(report_obj.get("tool") or tid),
                    )
                    if got_md != expected_md:
                        items.append(
                            ensure_item_fields(
                                {
                                    "tool": "check_report_tools_contract",
                                    "key": f"dynamic_md_mismatch:{tid}",
                                    "title": "report.md != render_markdown(report)",
                                    "status_label": "FAIL",
                                    "severity_level": 3,
                                    "message": "tool report.md did not match render_markdown(report)",
                                    "loc": f"tools/{tid}.py:1:1",
                                },
                                tool_default="check_report_tools_contract",
                            )
                        )

                # high_cost extras: events
                if tool.high_cost:
                    if not events_path.exists():
                        items.append(
                            ensure_item_fields(
                                {
                                    "tool": "check_report_tools_contract",
                                    "key": f"dynamic_missing_events:{tid}",
                                    "title": "missing events jsonl",
                                    "status_label": "FAIL",
                                    "severity_level": 3,
                                    "message": f"expected {events_path}",
                                    "loc": f"tools/{tid}.py:1:1",
                                },
                                tool_default="check_report_tools_contract",
                            )
                        )
                    else:
                        try:
                            ev = _read_jsonl(events_path)
                            if len(ev) < 2:
                                items.append(
                                    ensure_item_fields(
                                        {
                                            "tool": "check_report_tools_contract",
                                            "key": f"dynamic_events_too_few:{tid}",
                                            "title": "events file too short",
                                            "status_label": "FAIL",
                                            "severity_level": 3,
                                            "message": f"events lines={len(ev)} (<2)",
                                            "loc": f"tools/{tid}.py:1:1",
                                        },
                                        tool_default="check_report_tools_contract",
                                    )
                                )
                        except Exception as e:  # noqa: BLE001
                            items.append(
                                ensure_item_fields(
                                    {
                                        "tool": "check_report_tools_contract",
                                        "key": f"dynamic_events_parse_failed:{tid}",
                                        "title": "events jsonl parse failed",
                                        "status_label": "FAIL",
                                        "severity_level": 3,
                                        "message": repr(e),
                                        "loc": f"tools/{tid}.py:1:1",
                                    },
                                    tool_default="check_report_tools_contract",
                                )
                            )

                    # checkpoint: 当前规范不强制，但 selftest_utils 会生成；此处以 WARN 记录缺失。
                    if not checkpoint_path.exists():
                        items.append(
                            ensure_item_fields(
                                {
                                    "tool": "check_report_tools_contract",
                                    "key": f"dynamic_missing_checkpoint:{tid}",
                                    "title": "missing checkpoint.json",
                                    "status_label": "WARN",
                                    "severity_level": 2,
                                    "message": f"expected {checkpoint_path}",
                                    "loc": f"tools/{tid}.py:1:1",
                                },
                                tool_default="check_report_tools_contract",
                            )
                        )

                if args.strict and vr.warnings:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_warnings_strict:{tid}",
                                "title": "warnings treated as failures",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": "\n".join(list(vr.warnings)[:50]),
                                "loc": f"tools/{tid}.py:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )

                if not vr.warnings:
                    items.append(
                        ensure_item_fields(
                            {
                                "tool": "check_report_tools_contract",
                                "key": f"dynamic_selftest_pass:{tid}",
                                "title": "tool selftest ok",
                                "status_label": "PASS",
                                "severity_level": 0,
                                "message": "selftest generated valid report bundle",
                                "loc": f"tools/{tid}.py:1:1",
                            },
                            tool_default="check_report_tools_contract",
                        )
                    )

    if not items:
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "ok",
                    "title": "contract ok",
                    "status_label": "PASS",
                    "severity_level": 0,
                    "message": "no mismatches found",
                    "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": "check_report_tools_contract",
        "root": str(repo_root.as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "data": {
            "mode": str(args.mode),
            "scope": str(args.scope),
            "strict": bool(args.strict),
            "artifacts": str(Path(getattr(args, "artifacts", "")).resolve()),
        },
    }

    normalized = write_report_bundle(
        report=report,
        report_json=out_path,
        repo_root=repo_root,
        console_title="check_report_tools_contract",
        emit_console=True,
    )

    return int((normalized.get("summary") or {}).get("overall_rc") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
