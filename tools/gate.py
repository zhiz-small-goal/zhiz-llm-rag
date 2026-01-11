#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

gate.py

单一入口：PR/CI Lite 门禁执行器（跨平台）。

核心能力
- 读取 `reference.yaml` 中的 gate_profiles（机器可读 SSOT）。
- 按 profile 顺序执行各个门禁步骤（默认 fail-fast）。
- 产出单一 JSON report（默认写到 reference.yaml 指定路径）。

退出码（仓库统一口径）
- 0: PASS
- 2: FAIL（门禁不通过）
- 3: ERROR（脚本异常）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ALLOWED_RC = {0, 2, 3}


def _ensure_src_on_path() -> None:
    # 允许在未 editable install 的情况下导入 src 侧模块
    repo = Path(__file__).resolve().parent
    if repo.name == "tools":
        repo = repo.parent
    src = repo / "src"
    if src.exists():
        sys.path.insert(0, str(src))


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _tail(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[-max_chars:]


def _normalize_rc(rc: int) -> int:
    # Defensive: map any unexpected rc to {0,2,3}
    if rc in ALLOWED_RC:
        return rc
    if rc == 1:
        return 2
    if rc < 0:
        return 3
    if rc >= 4:
        return 3
    return 2


def _load_reference_yaml(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        return None, f"PyYAML not available: {type(e).__name__}: {e}"

    if not path.exists():
        return None, f"reference file not found: {path}"

    try:
        obj = yaml.safe_load(_read_text(path))
    except Exception as e:  # noqa: BLE001
        return None, f"yaml parse error: {type(e).__name__}: {e}"

    if not isinstance(obj, dict):
        return None, "reference.yaml root is not a mapping"
    return obj, None


def _repo_root(cli_root: str) -> Path:
    return Path(cli_root).resolve()


def _cmd_map(root: Path) -> Dict[str, List[str]]:
    py = sys.executable
    return {
        "pyproject_preflight": [py, "tools/check_pyproject_preflight.py", "--ascii-only"],
        "wrappers_check": [py, "tools/gen_tools_wrappers.py", "--check"],
        "tools_layout": [py, "tools/check_tools_layout.py", "--mode", "fail"],
        "exit_code_contract": [py, "tools/check_exit_code_contract.py", "--root", str(root)],
        "public_release_hygiene": [
            py,
            "tools/check_public_release_hygiene.py",
            "--repo",
            str(root),
            "--history",
            "0",
        ],
        "cli_entrypoints": [py, "tools/check_cli_entrypoints.py"],
        "md_refs_contract": [py, "tools/check_md_refs_contract.py"],
        "pytest": [py, "-m", "pytest", "-q"],
    }


def _run_step(cmd: List[str], *, cwd: Path, timeout_s: int) -> Tuple[int, str, str, float]:
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        dt = time.time() - t0
        return p.returncode, p.stdout, p.stderr, dt
    except FileNotFoundError:
        dt = time.time() - t0
        return 127, "", f"command not found: {cmd[0]}", dt
    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        return 124, "", f"timeout after {timeout_s}s: {' '.join(cmd)}", dt


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PR/CI Lite gates runner (single entry).")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--ref", default="reference.yaml", help="Reference YAML path (relative to repo root)")
    ap.add_argument(
        "--profile",
        default="fast",
        choices=["fast", "ci", "full"],
        help="Gate profile defined in reference.yaml gate_profiles",
    )
    ap.add_argument("--json-out", default="", help="Override JSON report output path")
    ap.add_argument("--timeout", type=int, default=900, help="Per-step timeout seconds")
    ap.add_argument("--keep-going", action="store_true", help="Run all steps even after failures")
    ap.add_argument("--stdout-tail", type=int, default=8000, help="Max chars of stdout kept in report")
    ap.add_argument("--stderr-tail", type=int, default=8000, help="Max chars of stderr kept in report")
    ap.add_argument("--list", action="store_true", help="List profiles/steps and exit")
    args = ap.parse_args(argv)

    root = _repo_root(args.root)
    if not root.exists():
        print(f"[ERROR] --root does not exist: {root}", file=sys.stderr)
        return 3

    _ensure_src_on_path()

    # Import here (after sys.path tweak) to keep tool runnable in repo-only mode.
    try:
        from mhy_ai_rag_data.tools import reporting
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] cannot import reporting module: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    ref_path = (root / args.ref).resolve() if not Path(args.ref).is_absolute() else Path(args.ref).resolve()
    ref, ref_err = _load_reference_yaml(ref_path)

    # Always create a report skeleton (even if reference.yaml is broken)
    report = reporting.build_base(
        step="gate",
        inputs={
            "root": str(root),
            "ref": str(ref_path),
            "profile": args.profile,
            "timeout_s": int(args.timeout),
            "keep_going": bool(args.keep_going),
        },
    )

    # Resolve output path early
    out_path = ""
    try:
        if args.json_out:
            out_path = args.json_out
        else:
            if isinstance(ref, dict):
                reports = ref.get("reports")
                if isinstance(reports, dict):
                    gp = reports.get("gate_report")
                    if isinstance(gp, str) and gp.strip():
                        out_path = str((root / gp).resolve())
        if not out_path:
            # Fallback: keep consistent with docs/reference/REFERENCE.md
            out_path = str((root / "data_processed" / "build_reports" / "gate_report.json").resolve())
    except Exception:
        out_path = str((root / "data_processed" / "build_reports" / "gate_report.json").resolve())

    if args.list:
        print("[gate] known steps:")
        for k in sorted(_cmd_map(root).keys()):
            print(f"  - {k}")
        if isinstance(ref, dict):
            gp = ref.get("gate_profiles")
            if isinstance(gp, dict):
                print("\n[gate] profiles (from reference.yaml):")
                for name, seq in gp.items():
                    if isinstance(seq, list):
                        print(f"  - {name}: {seq}")
        report["metrics"]["list_mode"] = True
        report["status"] = "PASS"
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
        return 0

    if ref_err:
        reporting.add_error(report, "REF_LOAD", "Failed to load reference.yaml", detail=ref_err)
        report["status"] = "ERROR"
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
        return 3

    assert isinstance(ref, dict)
    profiles = ref.get("gate_profiles")
    if not isinstance(profiles, dict):
        reporting.add_error(report, "REF_SCHEMA", "reference.yaml missing gate_profiles mapping")
        report["status"] = "ERROR"
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
        return 3

    seq = profiles.get(args.profile)
    if not isinstance(seq, list) or not seq:
        reporting.add_error(report, "REF_PROFILE", f"profile not found or empty: {args.profile}")
        report["status"] = "ERROR"
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
        return 3

    cmd_map = _cmd_map(root)
    unknown = [str(x) for x in seq if str(x) not in cmd_map]
    if unknown:
        reporting.add_error(report, "REF_UNKNOWN_STEP", "Unknown step(s) in profile", detail=unknown)
        report["status"] = "ERROR"
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
        return 3

    steps_out: List[Dict[str, Any]] = []
    report["metrics"]["profile"] = args.profile
    report["metrics"]["steps"] = steps_out

    overall = "PASS"

    for name in [str(x) for x in seq]:
        cmd = cmd_map[name]
        print("\n" + "=" * 80)
        print(f"[gate] step={name}")
        print("$ " + " ".join(cmd))

        rc_raw, out, err, dt = _run_step(cmd, cwd=root, timeout_s=int(args.timeout))
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")

        rc = _normalize_rc(int(rc_raw))
        status = "PASS" if rc == 0 else ("FAIL" if rc == 2 else "ERROR")

        steps_out.append(
            {
                "name": name,
                "cmd": cmd,
                "rc_raw": int(rc_raw),
                "rc": int(rc),
                "status": status,
                "duration_ms": int(dt * 1000),
                "stdout_tail": _tail(out, int(args.stdout_tail)),
                "stderr_tail": _tail(err, int(args.stderr_tail)),
            }
        )

        if rc != 0:
            # Keep a compact error list for report consumers
            reporting.add_error(
                report,
                code=f"STEP_{name}",
                message=f"step failed: {name}",
                detail={"rc_raw": int(rc_raw), "rc": int(rc)},
            )

            if rc == 3:
                overall = "ERROR"
            elif overall != "ERROR":
                overall = "FAIL"

            if not args.keep_going:
                break

    report["status"] = overall

    try:
        reporting.write_report(report, json_out=out_path, default_name="gate_report.json")
        print(f"[gate] report={out_path}")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] cannot write report: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    return reporting.status_to_rc(overall)


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt", file=sys.stderr)
        return 3
    except SystemExit:
        raise
    except Exception:
        print("[ERROR] unhandled exception", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(_entry())
