#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.gate

Single-entry gate runner (Schema + Policy + deterministic report).

Design goals
- Single entrypoint for CI/PR lite gates.
- SSOT-driven (docs/reference/reference.yaml).
- Deterministic artifacts:
  - data_processed/build_reports/gate_report.json
  - data_processed/build_reports/gate_logs/<step_id>.log

Exit codes (contract)
- 0: PASS
- 2: FAIL  (gate violation / tests failed)
- 3: ERROR (setup/runtime error)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = yaml.safe_load(f)
    if not isinstance(obj, dict):
        raise ValueError("SSOT yaml must be a mapping/object")
    return obj


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_text(p: Path, s: str) -> None:
    _ensure_dir(p.parent)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    _ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _norm_status(rc: int) -> str:
    if rc == 0:
        return "PASS"
    if rc == 2:
        return "FAIL"
    if rc == 3:
        return "ERROR"
    # unexpected rc -> treat as ERROR (but keep original rc in report)
    return "ERROR"


@dataclass
class StepResult:
    id: str
    argv: List[str]
    rc: int
    status: str
    elapsed_ms: int
    log_path: Optional[str] = None
    note: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None


def _run_step(repo: Path, step_id: str, argv_tail: List[str], logs_dir: Path) -> StepResult:
    start = _iso_now()
    t0 = time.time()

    argv = [shutil.which("python") or "python"]
    # Prefer current interpreter (more deterministic in venv/CI)
    argv[0] = os.environ.get("PYTHON", "") or shutil.which("python") or "python"
    try:
        argv[0] = os.environ.get("PYTHON", "") or os.environ.get("PY") or os.sys.executable
    except Exception:
        pass
    argv = [argv[0]] + argv_tail

    log_path = logs_dir / f"{step_id}.log"
    try:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        out = proc.stdout or ""
        _write_text(log_path, out)
        rc = int(proc.returncode)
    except Exception as e:
        _write_text(log_path, f"[ERROR] exception while running step: {e}\nargv={argv}\n")
        rc = 3

    elapsed_ms = int((time.time() - t0) * 1000)
    end = _iso_now()
    return StepResult(
        id=step_id,
        argv=argv,
        rc=rc,
        status=_norm_status(rc),
        elapsed_ms=elapsed_ms,
        log_path=str(log_path.as_posix()),
        start_ts=start,
        end_ts=end,
    )


def _canon_system_arch() -> Tuple[str, str]:
    """Return canonical (system, arch) for vendored binaries.

    system: windows|linux|darwin
    arch:   amd64|arm64
    """
    if os.name == "nt" or sys.platform.startswith("win"):
        system = "windows"
    elif sys.platform == "darwin":
        system = "darwin"
    else:
        system = "linux"

    m = (platform.machine() or "").lower()
    if m in {"x86_64", "amd64", "x64"}:
        arch = "amd64"
    elif m in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        # best-effort fallback; keep stable string for logs
        arch = m or "unknown"
    return system, arch


def _find_conftest(repo: Path, ssot: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Locate conftest binary.

    Search order (privacy/offline friendly):
    1) $CONFTEST_BIN (absolute/relative path)
    2) vendored: third_party/conftest/v<version>/<system>_<arch>/conftest(.exe)
    3) PATH (shutil.which)

    Returns: (path_or_none, note)
    """
    env_bin = os.environ.get("CONFTEST_BIN", "").strip()
    if env_bin:
        p = (repo / env_bin).resolve() if not Path(env_bin).is_absolute() else Path(env_bin)
        if p.exists() and p.is_file():
            return (str(p.as_posix()), "conftest.env")

    conftest_cfg = (ssot.get("policy") or {}).get("conftest") or {}
    version = str(conftest_cfg.get("version") or "").strip()
    system, arch = _canon_system_arch()
    exe = "conftest.exe" if system == "windows" else "conftest"
    # default vendor location
    vendor_dir = Path(repo) / "third_party" / "conftest"
    # allow override for monorepo/enterprise layout
    override_vendor = str(conftest_cfg.get("vendor_dir") or "").strip()
    if override_vendor:
        vendor_dir = (repo / override_vendor).resolve() if not Path(override_vendor).is_absolute() else Path(override_vendor)

    if version:
        candidate = vendor_dir / f"v{version}" / f"{system}_{arch}" / exe
        if candidate.exists() and candidate.is_file():
            return (str(candidate.as_posix()), "conftest.vendored")

    path_bin = shutil.which("conftest")
    if path_bin:
        return (path_bin, "conftest.path")
    return (None, "conftest_missing")


def _run_conftest(repo: Path, ssot: Dict[str, Any], logs_dir: Path) -> StepResult:
    start = _iso_now()
    t0 = time.time()
    log_path = logs_dir / "policy_conftest.log"

    enabled = bool(((ssot.get("policy") or {}).get("enabled")))
    if not enabled:
        _write_text(log_path, "[SKIP] policy.enabled=false\n")
        return StepResult(
            id="policy_conftest",
            argv=["conftest", "test", "..."],
            rc=0,
            status="SKIP",
            elapsed_ms=0,
            log_path=str(log_path.as_posix()),
            note="policy.disabled",
            start_ts=start,
            end_ts=_iso_now(),
        )

    conftest_cfg = (ssot.get("policy") or {}).get("conftest") or {}
    conftest_bin, locate_note = _find_conftest(repo=repo, ssot=ssot)
    if not conftest_bin:
        required = bool(conftest_cfg.get("required"))
        _write_text(
            log_path,
            "[WARN] conftest not found; skipping policy checks.\n"
            "       Tip: vendor conftest under third_party/conftest/ or set CONFTEST_BIN.\n"
        )
        return StepResult(
            id="policy_conftest",
            argv=["conftest", "test", "..."],
            rc=3 if required else 0,
            status="ERROR" if required else "SKIP",
            elapsed_ms=0,
            log_path=str(log_path.as_posix()),
            note="conftest_missing_required" if required else locate_note,
            start_ts=start,
            end_ts=_iso_now(),
        )

    _write_text(log_path, f"[INFO] conftest={conftest_bin} source={locate_note}\n")

    policy_dir = Path(repo) / str(conftest_cfg.get("policy_dir") or "policy")
    inputs = conftest_cfg.get("inputs") or []
    if not isinstance(inputs, list) or not inputs:
        _write_text(log_path, "[ERROR] policy.conftest.inputs missing or invalid\n")
        rc = 3
        elapsed_ms = int((time.time() - t0) * 1000)
        return StepResult(
            id="policy_conftest",
            argv=[conftest_bin, "test"],
            rc=rc,
            status=_norm_status(rc),
            elapsed_ms=elapsed_ms,
            log_path=str(log_path.as_posix()),
            note="invalid_policy_inputs",
            start_ts=start,
            end_ts=_iso_now(),
        )

    argv = [conftest_bin, "test"] + [str(Path(repo)/p) for p in inputs] + ["-p", str(policy_dir)]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        _write_text(log_path, proc.stdout or "")
        rc_raw = int(proc.returncode)
        # conftest uses 0 pass, 1 fail, 2 error (varies). Map nonzero to FAIL/ERROR.
        rc = 2 if rc_raw == 1 else (3 if rc_raw != 0 else 0)
    except Exception as e:
        _write_text(log_path, f"[ERROR] conftest exception: {e}\nargv={argv}\n")
        rc = 3

    elapsed_ms = int((time.time() - t0) * 1000)
    end = _iso_now()
    return StepResult(
        id="policy_conftest",
        argv=argv,
        rc=rc,
        status=_norm_status(rc),
        elapsed_ms=elapsed_ms,
        log_path=str(log_path.as_posix()),
        start_ts=start,
        end_ts=end,
    )




def _step_result_to_dict(r: StepResult) -> Dict[str, Any]:
    """Serialize StepResult to JSON-friendly dict.

    Important: omit keys whose value is None.
    This keeps optional fields (e.g., note) absent instead of `null`,
    matching JSON Schema expectations.
    """
    return {k: v for k, v in r.__dict__.items() if v is not None}


def _overall_rc(results: List[StepResult]) -> Tuple[str, int]:
    any_error = any(r.status == "ERROR" for r in results if r.status != "SKIP")
    any_fail = any(r.status == "FAIL" for r in results if r.status != "SKIP")
    if any_error:
        return ("ERROR", 3)
    if any_fail:
        return ("FAIL", 2)
    return ("PASS", 0)


def _validate_self_schema(repo: Path, ssot: Dict[str, Any], gate_report_path: Path) -> Optional[Dict[str, Any]]:
    """Return warning object on validation failure; None on success."""
    try:
        import jsonschema  # type: ignore
    except Exception as e:
        return {"code": "schema_validator_missing", "message": "jsonschema not installed; skip gate_report schema validation", "detail": repr(e)}

    schema_rel = ((ssot.get("schemas") or {}).get("gate_report")) or "schemas/gate_report_v1.schema.json"
    schema_path = repo / str(schema_rel)

    try:
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        with gate_report_path.open("r", encoding="utf-8") as f:
            inst = json.load(f)
        jsonschema.validate(instance=inst, schema=schema)
        return None
    except Exception as e:
        return {"code": "gate_report_schema_invalid", "message": "gate_report does not match JSON Schema", "detail": repr(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Repo gate runner (SSOT-driven).")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--profile", default="ci", choices=["fast", "ci", "release"], help="Gate profile")
    ap.add_argument("--ssot", default="docs/reference/reference.yaml", help="SSOT yaml path (relative to root)")
    ap.add_argument("--json-out", default="", help="Override gate report output path")
    args = ap.parse_args()

    repo = Path(args.root).resolve()
    ssot_path = (repo / args.ssot).resolve()

    try:
        ssot = _load_yaml(ssot_path)
    except Exception as e:
        print(f"[ERROR] failed to load SSOT: {ssot_path} :: {e}")
        return 3

    report_dir = Path(repo) / str(((ssot.get("paths") or {}).get("report_dir")) or "data_processed/build_reports")
    gate_logs_dir = Path(repo) / str(((ssot.get("paths") or {}).get("gate_logs_dir")) or "data_processed/build_reports/gate_logs")
    gate_report_name = str(((ssot.get("paths") or {}).get("gate_report")) or "gate_report.json")

    out_path = Path(args.json_out) if args.json_out else (report_dir / gate_report_name)
    if not out_path.is_absolute():
        out_path = (repo / out_path).resolve()

    _ensure_dir(report_dir)
    _ensure_dir(gate_logs_dir)

    profile_steps = (((ssot.get("gates") or {}).get("profiles") or {}).get(args.profile)) or []
    steps_cfg = ((ssot.get("gates") or {}).get("steps") or {})

    results: List[StepResult] = []
    warnings: List[Dict[str, Any]] = []

    for step_id in profile_steps:
        step_cfg = steps_cfg.get(step_id, {})
        # builtin step (policy)
        if isinstance(step_cfg, dict) and step_cfg.get("builtin") == "conftest":
            results.append(_run_conftest(repo, ssot, gate_logs_dir))
            continue

        argv_tail = []
        if isinstance(step_cfg, dict) and isinstance(step_cfg.get("argv"), list):
            argv_tail = [str(x) for x in step_cfg.get("argv")]
        else:
            # allow step id to be directly an argv list in future
            warnings.append({"code": "unknown_step", "message": f"unknown step_id in profile: {step_id}"})
            results.append(StepResult(id=step_id, argv=[], rc=3, status="ERROR", elapsed_ms=0, note="unknown_step"))
            continue

        results.append(_run_step(repo, step_id, argv_tail, gate_logs_dir))

    overall_status, overall_rc = _overall_rc(results)

    counts = {
        "pass": sum(1 for r in results if r.status == "PASS"),
        "fail": sum(1 for r in results if r.status == "FAIL"),
        "error": sum(1 for r in results if r.status == "ERROR"),
        "skip": sum(1 for r in results if r.status == "SKIP"),
        "total": len(results),
    }

    report: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "tool": "rag-gate",
        "root": str(repo),
        "profile": args.profile,
        "ssot_path": str(ssot_path.relative_to(repo)) if ssot_path.is_relative_to(repo) else str(ssot_path),
        "summary": {"overall_status": overall_status, "overall_rc": overall_rc, "counts": counts},
        "results": [_step_result_to_dict(r) for r in results],
    }
    if warnings:
        report["warnings"] = warnings

    _write_json(out_path, report)

    # Self schema validation (adds warning, but does not change PASS->FAIL unless already failing)
    warn = _validate_self_schema(repo, ssot, out_path)
    if warn:
        report.setdefault("warnings", []).append(warn)
        _write_json(out_path, report)
        # if schema is broken, treat as ERROR (this is a contract failure)
        overall_rc = 3
        overall_status = "ERROR"
        report["summary"]["overall_status"] = overall_status
        report["summary"]["overall_rc"] = overall_rc
        _write_json(out_path, report)

    print(f"[gate] profile={args.profile} status={overall_status} rc={overall_rc} report={out_path}")
    return int(overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
