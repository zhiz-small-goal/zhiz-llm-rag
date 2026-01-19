#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

check_mypy.py

Purpose
  Run mypy with repo exit-code contract.

Usage
  python tools/check_mypy.py
  python tools/check_mypy.py --root .
  python tools/check_mypy.py --strict

Switches
  --strict / --no-strict     Enable/disable mypy strict mode
  Env: RAG_MYPY_STRICT=1     Enable strict mode (overridden by CLI flags)

Exit codes
  0: PASS
  2: FAIL  (type check violations)
  3: ERROR (tool/runtime failure)
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
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


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


_MYPY_LOC_RE = re.compile(r"^(?P<path>(?:[A-Za-z]:[/\\\\][^:]+|[^:]+)):(?P<line>\d+):(.*)$")


def _normalize_loc_lines(text: str) -> str:
    if not text:
        return text
    out: List[str] = []
    for line in text.splitlines():
        m = _MYPY_LOC_RE.match(line)
        if not m:
            out.append(line)
            continue
        path = m.group("path").replace("\\\\", "/")
        rest = line[m.end("line") + 1 :]
        line_no = m.group("line")
        out.append(f"{path}:{line_no}:{rest}")
    return "\n".join(out)


def _tool_python_prefix(root: Path) -> List[str]:
    """Return argv prefix to run `-m mypy ...`.

    - If mypy is importable in current interpreter: use current interpreter.
    - Else: delegate to tools/rag_python.py to locate a repo venv python.

    This makes `python tools/check_mypy.py` work in a fresh cmd shell, as long as
    a repo venv exists (or RAG_PYTHON is set).
    """

    if _module_available("mypy"):
        return [sys.executable]

    wrapper = root / "tools" / "rag_python.py"
    if not wrapper.is_file():
        return [sys.executable]

    return [sys.executable, str(wrapper)]


def _run(argv: List[str], cwd: Path) -> int:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        print(f"[ERROR] failed to run: {argv}\n{e}", file=sys.stderr)
        return 3

    if proc.stdout:
        out = _normalize_loc_lines(proc.stdout)
        print(out, end="" if out.endswith("\n") else "\n")
    if proc.stderr:
        err = _normalize_loc_lines(proc.stderr)
        print(err, end="" if err.endswith("\n") else "\n", file=sys.stderr)

    return _map_rc(int(proc.returncode))


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run mypy with repo exit-code contract.")
    ap.add_argument("--root", default=".", help="Repo root (default: .)")
    ap.add_argument("--strict", dest="strict", action="store_true", help="Enable mypy strict mode")
    ap.add_argument("--no-strict", dest="strict", action="store_false", help="Disable mypy strict mode")
    ap.add_argument("--config", default="", help="Optional config path (default: pyproject.toml)")
    ap.set_defaults(strict=None)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[ERROR] --root does not exist: {root}", file=sys.stderr)
        return 3

    if args.strict is None:
        strict_mode = _env_bool("RAG_MYPY_STRICT", False)
    else:
        strict_mode = bool(args.strict)

    config_path = Path(args.config) if args.config else (root / "pyproject.toml")
    if not config_path.exists():
        print(f"[ERROR] config not found: {config_path}", file=sys.stderr)
        return 3

    py_prefix = _tool_python_prefix(root)
    cmd = [*py_prefix, "-m", "mypy", "--show-column-numbers", "--show-error-codes"]
    cmd += ["--config-file", str(config_path)]
    if strict_mode:
        cmd.append("--strict")

    print("[check_mypy] cmd:", " ".join(cmd))
    rc = _run(cmd, root)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
