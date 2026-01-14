#!/usr/bin/env python3
"""
rag_python.py

A cross-platform launcher to run project scripts using a *project venv* Python,
while allowing pre-commit to invoke a stable entry command.

Typical pre-commit usage (Windows/Linux/macOS):

    entry: python
    args: [tools/rag_python.py, tools/gate.py, --profile, fast, --root, .]

This wrapper will:
1) Determine repository root (git toplevel if available, else walk up for .git).
2) Resolve the "target python" interpreter:
   - If env RAG_PYTHON is set -> use it (absolute/relative path allowed).
   - Else if the current terminal has an activated environment (VIRTUAL_ENV/CONDA_PREFIX) -> use it.
   - Else search for venv interpreters using glob patterns (supports venv_*).
3) Exec the target python with the remaining argv (script/module args + filenames).

Environment variables:
- RAG_PYTHON:
    Explicit interpreter path to use. Highest priority.
    Example (Windows):
      set RAG_PYTHON=D:\repo\venv_embed\Scripts\python.exe
- VIRTUAL_ENV:
    If your shell has activated a venv, this points to the environment prefix.
    The wrapper will try <prefix>/Scripts/python.exe (Windows) or <prefix>/bin/python (POSIX).
- CONDA_PREFIX:
    Best-effort support for conda activation; treated as an environment prefix.
- RAG_VENV_GLOBS:
    Optional. Semicolon-separated glob patterns (relative to repo root).
    Defaults include:
      **/venv_*/Scripts/python.exe
      **/.venv/Scripts/python.exe
      **/venv_*/bin/python
      **/venv_*/bin/python3
      **/.venv/bin/python
      **/.venv/bin/python3
- RAG_VENV_PICK:
    What to do if multiple interpreters are found:
      "error" (default) -> list candidates and exit 2
      "first"           -> pick lexicographically smallest path (stable but may surprise)
- RAG_PY_DEBUG:
    "1" to print debug info to stderr.

External environment variables (observed, not owned by this script):
- VIRTUAL_ENV: set by venv activation scripts; points to the env prefix.
- CONDA_PREFIX: often set by conda activation; points to the env prefix.

Exit codes:
- 2: configuration / selection error (no venv found, ambiguous, bad args)
- otherwise: exit code from the invoked python process
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_GLOBS = [
    "**/venv_*/Scripts/python.exe",
    "**/.venv/Scripts/python.exe",
    "**/venv_*/bin/python",
    "**/venv_*/bin/python3",
    "**/.venv/bin/python",
    "**/.venv/bin/python3",
]


def _python_from_prefix(prefix: Path) -> Optional[Path]:
    """Resolve the interpreter path inside an environment prefix.

    Supports venv and (best-effort) conda-style layouts.
    """
    # Windows venv layout: <prefix>\Scripts\python.exe
    candidates = [
        prefix / "Scripts" / "python.exe",
        # POSIX venv layout: <prefix>/bin/python
        prefix / "bin" / "python",
        prefix / "bin" / "python3",
        # Conda (Windows) often uses <prefix>\python.exe
        prefix / "python.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p.resolve()
    return None


def _python_from_active_terminal_env(root: Path) -> Optional[Path]:
    """Prefer the Python from an *already activated* environment.

    Primary signal: VIRTUAL_ENV (set by venv activation scripts).
    Secondary (best-effort): CONDA_PREFIX.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        pref = Path(venv)
        if not pref.is_absolute():
            pref = (root / pref).resolve()
        py = _python_from_prefix(pref)
        if py:
            _debug(f"python (VIRTUAL_ENV) = {py}")
            return py

        # Fallback: if PATH has a python under VIRTUAL_ENV, use it.
        which_py = shutil.which("python")
        if which_py:
            wp = Path(which_py).resolve()
            try:
                if str(wp).lower().startswith(str(pref).lower()):
                    _debug(f"python (PATH under VIRTUAL_ENV) = {wp}")
                    return wp
            except Exception:
                pass

    conda_pref = os.environ.get("CONDA_PREFIX")
    if conda_pref:
        pref = Path(conda_pref)
        if not pref.is_absolute():
            pref = (root / pref).resolve()
        py = _python_from_prefix(pref)
        if py:
            _debug(f"python (CONDA_PREFIX) = {py}")
            return py

    return None


def _debug(msg: str) -> None:
    if os.environ.get("RAG_PY_DEBUG") == "1":
        print(f"[rag_python] {msg}", file=sys.stderr)


def _repo_root(start: Path) -> Path:
    """
    Try git toplevel first; fallback to walking upwards for a .git directory;
    fallback to current working directory.
    """
    try:
        # Use git if available. This works even if invoked from subdir.
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            root = Path(out)
            _debug(f"repo root (git) = {root}")
            return root
    except Exception:
        pass

    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            _debug(f"repo root (.git) = {p}")
            return p

    cwd = Path.cwd().resolve()
    _debug(f"repo root (cwd) = {cwd}")
    return cwd


def _split_globs(raw: Optional[str]) -> List[str]:
    if not raw:
        return DEFAULT_GLOBS.copy()
    # Allow both ';' and ':' as separators (Windows / POSIX friendly).
    parts: List[str] = []
    for chunk in raw.replace(":", ";").split(";"):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts or DEFAULT_GLOBS.copy()


def _normalize_pattern(pat: str) -> str:
    """
    pathlib.Path.rglob(pattern) is already recursive, so leading '**/' is redundant.
    Keep the rest as-is.
    """
    pat = pat.strip().replace("\\", "/")
    while pat.startswith("**/"):
        pat = pat[3:]
    return pat


def _candidate_interpreters(root: Path, globs: Iterable[str]) -> List[Path]:
    candidates: List[Path] = []
    for g in globs:
        pat = _normalize_pattern(g)
        # rglob expects patterns using '/' regardless of platform; pathlib handles it.
        for p in root.rglob(pat):
            if p.is_file():
                candidates.append(p.resolve())
    # de-dup and stable order
    uniq = sorted({c for c in candidates}, key=lambda x: str(x).lower())
    return uniq


def _resolve_explicit_python(root: Path, raw: str) -> Optional[Path]:
    p = Path(raw)
    if not p.is_absolute():
        p = (root / p).resolve()
    if p.exists() and p.is_file():
        return p
    return None


def _choose_python(root: Path) -> Path:
    explicit = os.environ.get("RAG_PYTHON")
    if explicit:
        resolved = _resolve_explicit_python(root, explicit)
        if resolved is None:
            raise RuntimeError(
                f"RAG_PYTHON is set but not found: {explicit!r} (resolved under {root})"
            )
        _debug(f"python (RAG_PYTHON) = {resolved}")
        return resolved

    # Prefer the interpreter from an already-activated terminal environment
    # (e.g., VS Code integrated terminal auto-activation).
    active = _python_from_active_terminal_env(root)
    if active is not None:
        return active

    globs = _split_globs(os.environ.get("RAG_VENV_GLOBS"))
    candidates = _candidate_interpreters(root, globs)
    _debug(f"glob patterns = {globs}")
    _debug(f"found {len(candidates)} candidates")

    if not candidates:
        raise RuntimeError(
            "No venv python interpreter found.\n"
            f"Searched under: {root}\n"
            "Tried globs:\n  - " + "\n  - ".join(globs) + "\n"
            "You can set RAG_PYTHON to explicitly point to the interpreter."
        )

    if len(candidates) == 1:
        _debug(f"python (unique) = {candidates[0]}")
        return candidates[0]

    pick = (os.environ.get("RAG_VENV_PICK") or "error").strip().lower()
    if pick == "first":
        _debug(f"python (first) = {candidates[0]}")
        return candidates[0]

    # default: error
    listing = "\n".join(f"  - {p}" for p in candidates)
    raise RuntimeError(
        "Multiple venv python interpreters found; selection is ambiguous.\n"
        f"Searched under: {root}\n"
        f"Candidates:\n{listing}\n"
        "Set RAG_PYTHON to one of the paths above, or set RAG_VENV_PICK=first."
    )


def _usage() -> str:
    return (
        "Usage:\n"
        "  python tools/rag_python.py <script.py | -m module> [args...] [filenames...]\n\n"
        "Examples:\n"
        "  python tools/rag_python.py tools/gate.py --profile fast --root .\n"
        "  python tools/rag_python.py -m mypkg.cli --help\n"
    )


def main(argv: List[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(_usage(), file=sys.stderr)
        return 2

    start = Path(__file__).resolve().parent
    root = _repo_root(start)
    try:
        py = _choose_python(root)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3

    # Pass-through: everything after this wrapper is given to target python.
    cmd = [str(py), *argv]

    _debug(f"exec: {cmd!r}")
    try:
        proc = subprocess.run(cmd, cwd=str(root))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
