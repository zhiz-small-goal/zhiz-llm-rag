#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

check_ruff.py

Purpose
  Run Ruff lint (and optional format --check) with repo exit-code contract.

Usage
  python tools/check_ruff.py
  python tools/check_ruff.py --root .
  python tools/check_ruff.py --format

Switches
  --format / --no-format     Enable/disable format --check
  Env: RAG_RUFF_FORMAT=1     Enable format --check (overridden by CLI flags)

Exit codes
  0: PASS
  2: FAIL  (lint/format violations)
  3: ERROR (tool/runtime failure)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _map_rc(rc: int) -> int:
    if rc == 0:
        return 0
    if rc == 1:
        return 2
    return 3


def _run(argv: List[str], cwd: Path) -> int:
    try:
        proc = subprocess.run(argv, cwd=str(cwd), check=False)
    except Exception as e:
        print(f"[ERROR] failed to run: {argv}\n{e}", file=sys.stderr)
        return 3
    return _map_rc(int(proc.returncode))


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Ruff lint/format checks with repo exit-code contract.")
    ap.add_argument("--root", default=".", help="Repo root (default: .)")
    ap.add_argument("--format", dest="format_check", action="store_true", help="Enable ruff format --check")
    ap.add_argument("--no-format", dest="format_check", action="store_false", help="Disable ruff format --check")
    ap.add_argument("--output-format", default="concise", help="Ruff lint output format (default: concise)")
    ap.add_argument("--config", default="", help="Optional config path (default: auto-discovery)")
    ap.set_defaults(format_check=None)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[ERROR] --root does not exist: {root}", file=sys.stderr)
        return 3

    if args.format_check is None:
        format_check = _env_bool("RAG_RUFF_FORMAT", False)
    else:
        format_check = bool(args.format_check)

    base = [sys.executable, "-m", "ruff"]
    lint_cmd = base + ["check", "."]
    if args.output_format:
        lint_cmd += ["--output-format", str(args.output_format)]
    if args.config:
        lint_cmd += ["--config", str(args.config)]

    print("[check_ruff] lint:", " ".join(lint_cmd))
    lint_rc = _run(lint_cmd, root)

    format_rc = 0
    if format_check:
        fmt_cmd = base + ["format", "--check", "."]
        if args.config:
            fmt_cmd += ["--config", str(args.config)]
        print("[check_ruff] format:", " ".join(fmt_cmd))
        format_rc = _run(fmt_cmd, root)
    else:
        print("[check_ruff] format: SKIP (enable with --format or RAG_RUFF_FORMAT=1)")

    if 3 in {lint_rc, format_rc}:
        return 3
    if 2 in {lint_rc, format_rc}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
