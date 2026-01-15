#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_tools_layout

Audit tools/ layout: wrappers vs repo-only tools.

Markers (marker-first contract):
- AUTO-GENERATED WRAPPER
- REPO-ONLY TOOL

Rules:
- If tools/<name>.py has a same-named peer in src/mhy_ai_rag_data/tools/<name>.py,
  then tools/<name>.py MUST be a wrapper (SSOT is in src/).
- Every tools/*.py MUST declare exactly one marker; otherwise it is classified as unknown.

Output:
- Text summary to stdout.
- Optional JSON report.

Exit codes:
- 0: PASS (or WARN when --mode warn)
- 2: FAIL (when --mode fail and issues exist)
- 3: ERROR (unhandled exception)
"""

from __future__ import annotations

import argparse
import time
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mhy_ai_rag_data.tools.report_order import write_json_report

MARK_WRAPPER = "AUTO-GENERATED WRAPPER"
MARK_REPO_ONLY = "REPO-ONLY TOOL"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_head(path: Path, max_bytes: int = 32 * 1024) -> str:
    """Read the first N bytes as best-effort UTF-8 text."""
    try:
        data = path.read_bytes()[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def classify_tool(path: Path) -> Tuple[str, List[str]]:
    """Return (kind, reasons) where kind in {wrapper, repo_only, unknown}."""
    text = read_head(path)
    reasons: List[str] = []

    if MARK_WRAPPER in text:
        reasons.append(f"marker:{MARK_WRAPPER}")
        return "wrapper", reasons

    if MARK_REPO_ONLY in text:
        reasons.append(f"marker:{MARK_REPO_ONLY}")
        return "repo_only", reasons

    return "unknown", reasons


def wrapper_sane(text: str) -> bool:
    # Heuristic: wrappers in this repo should forward to mhy_ai_rag_data.tools.* via runpy.
    return ("runpy.run_module(" in text) and ("mhy_ai_rag_data.tools." in text)


def iter_tools_py(tools_dir: Path, recursive: bool) -> List[Path]:
    if not tools_dir.exists():
        return []
    if recursive:
        paths = [p for p in tools_dir.rglob("*.py") if p.is_file()]
    else:
        paths = [p for p in tools_dir.glob("*.py") if p.is_file()]

    ignore = {"__init__.py", "__main__.py"}
    paths = [p for p in paths if p.name not in ignore]
    return sorted(paths)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit tools/ layout contract (wrappers vs repo-only tools).")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--mode", default="warn", choices=["warn", "fail"], help="warn: exit 0; fail: exit 2 on issues")
    ap.add_argument("--recursive", action="store_true", help="Scan tools/ recursively")
    ap.add_argument(
        "--out",
        default="",
        help="Write JSON report to this path (relative to repo root). Empty -> no JSON.",
    )
    args = ap.parse_args()

    repo = Path(args.root).resolve()
    tools_dir = repo / "tools"
    src_tools_dir = repo / "src" / "mhy_ai_rag_data" / "tools"

    tools_py = iter_tools_py(tools_dir, recursive=bool(args.recursive))

    wrappers: List[str] = []
    repo_only: List[str] = []
    unknown: List[str] = []

    wrapper_warnings: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []

    for p in tools_py:
        rel = str(p.relative_to(repo))
        kind, reasons = classify_tool(p)

        if kind == "wrapper":
            wrappers.append(rel)
            head = read_head(p)
            if not wrapper_sane(head):
                wrapper_warnings.append(
                    {
                        "type": "wrapper_sanity",
                        "file": rel,
                        "detail": "Wrapper marker found but runpy.run_module forwarding pattern not detected (heuristic).",
                    }
                )
        elif kind == "repo_only":
            repo_only.append(rel)
        else:
            unknown.append(rel)

        src_peer = src_tools_dir / p.name
        if src_peer.exists() and kind != "wrapper":
            issues.append(
                {
                    "type": "name_conflict_tools_vs_src",
                    "file": rel,
                    "src_peer": str(src_peer.relative_to(repo)),
                    "kind": kind,
                    "reasons": reasons,
                    "detail": "Same-named file exists in src/, but tools-side file is not a wrapper.",
                }
            )

        if kind == "unknown":
            issues.append(
                {
                    "type": "unknown_tool_kind",
                    "file": rel,
                    "detail": f"Missing markers: add '{MARK_WRAPPER}' (wrapper) or '{MARK_REPO_ONLY}' (repo-only).",
                }
            )

    report: Dict[str, Any] = {
        "timestamp": now_iso(),
        "root": str(repo),
        "inputs": {
            "tools_dir": str(tools_dir),
            "src_tools_dir": str(src_tools_dir),
            "recursive": bool(args.recursive),
            "mode": args.mode,
            "mark_wrapper": MARK_WRAPPER,
            "mark_repo_only": MARK_REPO_ONLY,
        },
        "summary": {
            "tools_py": len(tools_py),
            "wrappers": len(wrappers),
            "repo_only": len(repo_only),
            "unknown": len(unknown),
            "wrapper_warnings": len(wrapper_warnings),
            "issues": len(issues),
        },
        "groups": {"wrappers": wrappers, "repo_only": repo_only, "unknown": unknown},
        "warnings": wrapper_warnings,
        "issues": issues,
    }

    print(
        f"[check_tools_layout] tools_py={report['summary']['tools_py']} wrappers={report['summary']['wrappers']} "
        f"repo_only={report['summary']['repo_only']} unknown={report['summary']['unknown']}"
    )

    if wrapper_warnings:
        print(f"[WARN] wrapper_sanity_warnings={len(wrapper_warnings)} (heuristic; marker-first contract)")
        for w in wrapper_warnings[:10]:
            print(f"  - {w['file']}: {w['detail']}")
        if len(wrapper_warnings) > 10:
            print("  - ...")

    if issues:
        print(f"[ISSUES] count={len(issues)}")
        for it in issues[:50]:
            if it.get("type") == "name_conflict_tools_vs_src":
                print(f"  - {it['file']}  <->  {it['src_peer']}  kind={it['kind']}")
            else:
                print(f"  - {it['file']}: {it.get('detail', '')}")
        if len(issues) > 50:
            print("  - ...")

    status = "PASS"
    exit_code = 0
    if issues:
        if args.mode == "fail":
            status = "FAIL"
            exit_code = 2
        else:
            status = "WARN"
            exit_code = 0

    if args.out:
        out_path = (repo / args.out).resolve()
        ensure_dir(out_path.parent)
        write_json_report(out_path, report)
        print(f"[check_tools_layout] report={out_path}")

    print(f"\nSTATUS: {status}")
    return exit_code


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
