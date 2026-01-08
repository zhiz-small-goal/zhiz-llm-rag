#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

check_cli_entrypoints.py

Purpose
- Diagnose and gate common "command not found" issues for rag-* console scripts on Windows.
- Validate that console_scripts entry points exist in package metadata and are reachable via PATH.

Why this exists
- Key invariant: without the CLI entrypoints, the pipeline cannot run.
- High reuse: multi-machine setups frequently hit PATH/venv mismatch.
- Manual checking is error-prone (shell PATH caching, multiple Python installs).

Exit codes
- 0: PASS (expected entrypoints present and reachable)
- 2: FAIL (missing entrypoints or PATH cannot reach scripts dir)

Usage
  python tools/check_cli_entrypoints.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple

try:
    import importlib.metadata as im
except Exception:  # pragma: no cover
    import importlib_metadata as im  # type: ignore


def _fail(msg: str) -> int:
    print("[FAIL]", msg)
    return 2


def _pass(msg: str) -> int:
    print("[PASS]", msg)
    return 0


def _scripts_dir() -> Path:
    # Console-script wrappers typically live next to the interpreter.
    # - Windows: <venv>/Scripts
    # - POSIX:   <venv>/bin
    # NOTE: do NOT resolve symlinks here; venvs on POSIX commonly symlink
    # <venv>/bin/python -> /usr/bin/pythonX, while wrappers live in <venv>/bin.
    return Path(sys.executable).parent


def _path_entries() -> List[str]:
    return [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]


def _in_path(dir_path: Path) -> bool:
    d = str(dir_path).lower().rstrip("\\/")
    return any(str(p).lower().rstrip("\\/") == d for p in _path_entries())


def _list_rag_wrappers(scripts_dir: Path) -> List[str]:
    if not scripts_dir.exists():
        return []
    names = []
    for p in scripts_dir.iterdir():
        if not p.is_file():
            continue
        n = p.name.lower()
        if not n.startswith("rag-"):
            continue
        # Windows: wrappers are typically *.exe/*.cmd/*.bat.
        # POSIX: wrappers are typically extension-less executable files.
        if os.name == "nt":
            if n.endswith((".exe", ".cmd", ".bat")):
                names.append(p.name)
        else:
            # Be permissive: some environments may generate "rag-foo" or "rag-foo.py".
            if n.endswith((".exe", ".cmd", ".bat")):
                continue
            names.append(p.name)
    return sorted(names)


def _list_rag_entrypoints() -> List[str]:
    # Read installed console_scripts entry points (package metadata)
    eps = im.entry_points()
    # Repo baseline is Py3.11+: importlib.metadata.entry_points() returns EntryPoints with .select()
    if hasattr(eps, "select"):
        cs = eps.select(group="console_scripts")
    else:
        cs = eps.get("console_scripts", [])
    names = sorted([ep.name for ep in cs if ep.name.startswith("rag-")])
    return names


def _expect_names(entrypoints: List[str]) -> Tuple[List[str], List[str]]:
    # We don't hardcode a strict list (project may evolve).
    # But inventory + units are considered baseline for this repo.
    must_have = ["rag-extract-units", "rag-validate-units"]
    nice_to_have = ["rag-make-inventory", "rag-inventory"]
    missing_must = [n for n in must_have if n not in entrypoints]
    missing_any_inventory = [n for n in nice_to_have if n in entrypoints]
    # missing_any_inventory is "present inventory commands"; if empty, inventory cli is absent.
    return missing_must, missing_any_inventory


def main() -> int:
    scripts_dir = _scripts_dir()
    print("[INFO] sys.executable =", sys.executable)
    print("[INFO] scripts_dir    =", scripts_dir)

    entrypoints = _list_rag_entrypoints()
    wrappers = _list_rag_wrappers(scripts_dir)

    print("[INFO] rag console_scripts entrypoints (metadata):")
    if entrypoints:
        for n in entrypoints:
            print("  -", n)
    else:
        print("  (none found)")

    print("[INFO] rag wrappers in scripts_dir:")
    if wrappers:
        for n in wrappers:
            print("  -", n)
    else:
        print("  (none found)")

    in_path = _in_path(scripts_dir)
    print("[INFO] scripts_dir on PATH:", "YES" if in_path else "NO")

    missing_must, any_inventory_present = _expect_names(entrypoints)
    if missing_must:
        print("[INFO] missing baseline entrypoints:", missing_must)
        return _fail("baseline rag-* entrypoints missing (reinstall package into this venv)")

    if not any_inventory_present:
        # It might be named rag-inventory (new) or rag-make-inventory (old). If neither exists, that's a problem.
        return _fail("no inventory CLI found (expected rag-inventory or rag-make-inventory). Check your installed package version/pyproject entry points.")

    if not in_path:
        return _fail("venv scripts_dir is not on PATH for this shell. Re-activate venv or open a new shell.")

    # Optional consistency check: metadata entrypoints should usually have wrappers
    # (best-effort, not strict because wrappers may be generated differently).
    return _pass("rag-* entrypoints appear installed and reachable")

if __name__ == "__main__":
    raise SystemExit(main())
