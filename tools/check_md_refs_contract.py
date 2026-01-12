#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

check_md_refs_contract.py

Purpose
  Gate the stability of the md_refs API contract and its call sites.

Why this exists
  - High-frequency regression: ref extractor signature drift + positional args binding.
  - Manual checking is unreliable (refactors can silently break runtime).

Checks (FAIL => exit code 2)
  1) Signature: extract_refs_from_md(md_path, md_text, project_root, preset=...)
  2) Smoke-call: the function can be called using keyword arguments.
  3) Call sites: all calls to extract_refs_from_md in this repo use keyword args
     for md_path/md_text/project_root (positional args are disallowed).

Usage
  python tools/check_md_refs_contract.py
  python tools/check_md_refs_contract.py --root .

Exit codes
  0 PASS
  2 FAIL (contract violation)
  3 ERROR (script exception)
"""

from __future__ import annotations

import argparse
import ast
import inspect
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


REQ_PARAMS = ("md_path", "md_text", "project_root")


def _repo_root(cli_root: Optional[str]) -> Path:
    if cli_root:
        return Path(cli_root).resolve()
    # tools/ is at repo root in this project layout
    return Path(__file__).resolve().parent.parent


def _fail(msg: str) -> int:
    print("[FAIL]", msg)
    return 2


def _pass(msg: str) -> int:
    print("[PASS]", msg)
    return 0


def _iter_py_files(root: Path) -> Iterable[Path]:
    # Keep it deterministic and avoid scanning transient/large folders.
    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "chroma_db",
        "data_processed",
    }
    for p in root.rglob("*.py"):
        if any(part in skip_dirs for part in p.parts):
            continue
        # Skip any nested git checkouts (vendored copies / old snapshots).
        # This avoids false alarms when the repo accidentally contains another repo.
        # Heuristic: if a parent (other than repo root) contains a .git directory, skip.
        try:
            rel = p.relative_to(root)
        except Exception:
            rel = None
        if rel is not None:
            cur = root
            for part in rel.parts[:-1]:
                cur = cur / part
                if cur != root and (cur / ".git").is_dir():
                    break
            else:
                yield p
            continue
        yield p


def _call_uses_positional_args(call: ast.Call) -> bool:
    # Any positional args -> disallow.
    return len(call.args) > 0


def _kw_names(call: ast.Call) -> set:
    out = set()
    for kw in call.keywords:
        if kw.arg is None:
            # **kwargs - cannot reliably validate; treat as OK (escape hatch).
            continue
        out.add(kw.arg)
    return out


def _is_target_call(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id == "extract_refs_from_md"
    if isinstance(f, ast.Attribute):
        return f.attr == "extract_refs_from_md"
    return False


def _check_signature() -> Tuple[bool, str]:
    try:
        from mhy_ai_rag_data.md_refs import extract_refs_from_md  # type: ignore
    except Exception as e:
        return False, f"cannot import mhy_ai_rag_data.md_refs.extract_refs_from_md: {e!r}"

    sig = inspect.signature(extract_refs_from_md)
    params = list(sig.parameters.values())
    names = [p.name for p in params]

    missing = [n for n in REQ_PARAMS if n not in names]
    if missing:
        return False, f"signature missing required params: {missing}; actual={names}"

    # Ensure required params are POSITIONAL_OR_KEYWORD or KEYWORD_ONLY
    bad_kind = []
    for n in REQ_PARAMS:
        p = sig.parameters[n]
        if p.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            bad_kind.append((n, str(p.kind)))
    if bad_kind:
        return False, f"required params must be keyword-callable; bad={bad_kind}; sig={sig}"

    # Smoke-call with keyword args
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        md_path = root / "x.md"
        md_text = "# hello\n\nno links\n"
        md_path.write_text(md_text, encoding="utf-8")
        try:
            _ = extract_refs_from_md(md_path=md_path, md_text=md_text, project_root=root, preset="commonmark")
        except Exception as e:
            return False, f"smoke call failed: {e!r}"

    return True, f"signature OK: {sig}"


def _check_callsites(root: Path) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for py in _iter_py_files(root):
        try:
            src = py.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src, filename=str(py))
        except Exception:
            # Ignore parse errors from non-source artifacts.
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_target_call(node):
                continue

            if _call_uses_positional_args(node):
                issues.append(f"{py.as_posix()}: positional args are not allowed for extract_refs_from_md")
                continue

            kw = _kw_names(node)
            # If **kwargs was used, we cannot assert coverage; accept.
            if any(k.arg is None for k in node.keywords):
                continue
            missing = [n for n in REQ_PARAMS if n not in kw]
            if missing:
                issues.append(f"{py.as_posix()}: missing keywords {missing} for extract_refs_from_md")

    ok = len(issues) == 0
    return ok, issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate md_refs.extract_refs_from_md signature + callsites.")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect from this script location)")
    args = ap.parse_args()

    root = _repo_root(args.root)
    print("[INFO] repo_root =", root)

    try:
        ok_sig, sig_msg = _check_signature()
        print("[INFO]", sig_msg)
        if not ok_sig:
            return _fail("md_refs signature/behavior gate failed")

        ok_calls, issues = _check_callsites(root)
        if not ok_calls:
            print("[INFO] callsite issues:")
            for x in issues[:50]:
                print("  -", x)
            if len(issues) > 50:
                print(f"  ... ({len(issues) - 50} more)")
            return _fail("md_refs callsites gate failed")

        return _pass("md_refs contract appears stable")

    except SystemExit:
        raise
    except Exception as e:
        print("[ERROR]", repr(e))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
