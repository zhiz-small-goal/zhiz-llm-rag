#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

check_exit_code_contract.py

Purpose
  Reduce exit-code drift by statically flagging disallowed exit patterns.

Contract
  This repo standardizes on process exit codes {0, 2, 3}.
  - 0: PASS
  - 2: FAIL (gate / precondition / contract violation)
  - 3: ERROR (unexpected exception)

What this tool checks
  Python (.py)
    - sys.exit(<literal int>) where <literal int> NOT IN {0,2,3}
    - exit(<literal int>) where <literal int> NOT IN {0,2,3}
    - SystemExit(<literal int>) where <literal int> NOT IN {0,2,3}
    - Any of the above with a *string literal* or *f-string* argument
      (Python maps SystemExit(str) / sys.exit(str) to rc=1)

  Batch (.cmd/.bat)
    - exit /b 1  (and variants like: exit   /b   01)

Notes
  - The checks are deliberately conservative to keep false positives low.
  - Only literal arguments are flagged; dynamic values are not interpreted.

Usage
  python tools/check_exit_code_contract.py
  python tools/check_exit_code_contract.py --root .

Exit codes
  0: PASS
  2: FAIL (violations found)
  3: ERROR (tool failure)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


ALLOWED_INT_EXIT_CODES = {0, 2, 3}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    col: int
    rule_id: str
    message: str
    snippet: str


def _repo_root(cli_root: str) -> Path:
    return Path(cli_root).resolve()


def _iter_files(root: Path) -> Tuple[List[Path], List[Path]]:
    """Return (py_files, cmd_files) under root.

    Keep this deterministic and avoid scanning transient / large directories.
    """
    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "site-packages",
        "node_modules",
        "chroma_db",
        "data_processed",
    }

    py_files: List[Path] = []
    cmd_files: List[Path] = []

    # Root-level scripts
    for p in root.glob("*.py"):
        if p.is_file():
            py_files.append(p)

    for p in root.glob("*.cmd"):
        if p.is_file():
            cmd_files.append(p)
    for p in root.glob("*.bat"):
        if p.is_file():
            cmd_files.append(p)

    # Conventional dirs
    for d in (root / "tools", root / "src"):
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if any(part in skip_dirs for part in p.parts):
                continue
            if p.suffix.lower() == ".py":
                py_files.append(p)
            elif p.suffix.lower() in {".cmd", ".bat"}:
                cmd_files.append(p)

    # Avoid self-scanning cycles due to duplicated folders in some environments.
    # Deterministic dedup.
    py_files = sorted(set(py_files))
    cmd_files = sorted(set(cmd_files))
    return py_files, cmd_files


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _get_line(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].rstrip("\n")
    return ""


def _callee_kind(node: ast.AST) -> Optional[str]:
    """Return one of {sys.exit, exit, SystemExit} if node matches, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "sys" and node.attr == "exit":
            return "sys.exit"
    if isinstance(node, ast.Name):
        if node.id == "exit":
            return "exit"
        if node.id == "SystemExit":
            return "SystemExit"
    return None


def _arg_kind(arg0: ast.AST) -> Tuple[str, Optional[int]]:
    """Return (kind, int_value_if_any).

    kind in {none, int, str, fstr, other}
    """
    if isinstance(arg0, ast.Constant):
        if arg0.value is None:
            return "none", None
        if isinstance(arg0.value, bool):
            # bool is int subclass; treat as other to avoid weirdness
            return "other", None
        if isinstance(arg0.value, int):
            return "int", int(arg0.value)
        if isinstance(arg0.value, str):
            return "str", None
        return "other", None
    if isinstance(arg0, ast.JoinedStr):
        return "fstr", None
    return "other", None


def _scan_py(path: Path, root: Path) -> Tuple[List[Finding], Optional[str]]:
    """Return (findings, fatal_error_message_if_any)."""
    try:
        text = _read_text(path)
    except Exception as e:
        return [], f"cannot read {path}: {e}"

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as e:
        return [], f"syntax error in {path}: {e.msg}"
    except Exception as e:
        return [], f"cannot parse {path}: {e}"

    findings: List[Finding] = []
    for node in ast.walk(tree):
        # We flag both direct calls and raise SystemExit(...) forms.
        if isinstance(node, ast.Call):
            kind = _callee_kind(node.func)
            if not kind:
                continue

            # No args -> ok (defaults to rc=0)
            if not node.args:
                continue

            arg0 = node.args[0]
            arg_kind, int_value = _arg_kind(arg0)

            if arg_kind in {"str", "fstr"}:
                rule = "ECS003" if kind in {"sys.exit", "exit"} else "ECS001"
                msg = f"{kind} with string/f-string literal can map to rc=1; use rc in {sorted(ALLOWED_INT_EXIT_CODES)}"
                line = getattr(node, "lineno", 1)
                col = getattr(node, "col_offset", 0) + 1
                findings.append(Finding(path, line, col, rule, msg, _get_line(text, line)))
                continue

            if arg_kind == "int" and int_value is not None and int_value not in ALLOWED_INT_EXIT_CODES:
                rule = "ECS011" if kind == "SystemExit" else ("ECS012" if kind == "sys.exit" else "ECS013")
                msg = f"{kind}({int_value}) is outside allowed exit codes {sorted(ALLOWED_INT_EXIT_CODES)}"
                line = getattr(node, "lineno", 1)
                col = getattr(node, "col_offset", 0) + 1
                findings.append(Finding(path, line, col, rule, msg, _get_line(text, line)))

        if isinstance(node, ast.Raise):
            exc = node.exc
            if isinstance(exc, ast.Call):
                kind = _callee_kind(exc.func)
                if kind != "SystemExit":
                    continue
                if not exc.args:
                    continue
                arg0 = exc.args[0]
                arg_kind, int_value = _arg_kind(arg0)
                if arg_kind in {"str", "fstr"}:
                    line = getattr(node, "lineno", 1)
                    col = getattr(node, "col_offset", 0) + 1
                    findings.append(
                        Finding(
                            path,
                            line,
                            col,
                            "ECS001",
                            f"raise SystemExit with string/f-string literal can map to rc=1; use rc in {sorted(ALLOWED_INT_EXIT_CODES)}",
                            _get_line(text, line),
                        )
                    )
                elif arg_kind == "int" and int_value is not None and int_value not in ALLOWED_INT_EXIT_CODES:
                    line = getattr(node, "lineno", 1)
                    col = getattr(node, "col_offset", 0) + 1
                    findings.append(
                        Finding(
                            path,
                            line,
                            col,
                            "ECS011",
                            f"raise SystemExit({int_value}) is outside allowed exit codes {sorted(ALLOWED_INT_EXIT_CODES)}",
                            _get_line(text, line),
                        )
                    )

    return findings, None


_RE_EXIT_B = re.compile(r"\bexit\s*/b\s*(?P<code>\d+)\b", re.IGNORECASE)
_RE_COMMENT = re.compile(r"^\s*(rem\b|::)", re.IGNORECASE)


def _scan_cmd(path: Path) -> Tuple[List[Finding], Optional[str]]:
    try:
        text = _read_text(path)
    except Exception as e:
        return [], f"cannot read {path}: {e}"

    findings: List[Finding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\n")
        if _RE_COMMENT.search(raw):
            continue
        m = _RE_EXIT_B.search(raw)
        if not m:
            continue
        try:
            code = int(m.group("code"), 10)
        except Exception:
            continue
        if code == 1:
            col = (m.start("code") + 1) if m.start("code") >= 0 else 1
            findings.append(
                Finding(
                    path,
                    idx,
                    col,
                    "ECS101",
                    "batch exits with rc=1; prefer 2=FAIL or 3=ERROR",
                    raw,
                )
            )

    return findings, None


def _print_findings(root: Path, findings: Sequence[Finding]) -> None:
    for f in findings:
        try:
            rel = f.path.relative_to(root)
        except Exception:
            rel = f.path
        # VS Code clickable diagnostics: file:line:col
        print(f"{rel}:{f.line}:{f.col} [FAIL] {f.rule_id}: {f.message}\n    {f.snippet}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Static checks to reduce exit-code drift")
    ap.add_argument("--root", default=".", help="Repo root (default: .)")
    args = ap.parse_args(argv)

    root = _repo_root(args.root)
    if not root.exists():
        print(f"[ERROR] --root does not exist: {root}", file=sys.stderr)
        return 3

    py_files, cmd_files = _iter_files(root)
    findings: List[Finding] = []

    fatal_errors: List[str] = []

    for p in py_files:
        # Ignore this tool itself (not required, but avoids any future recursion patterns)
        if p.name == "check_exit_code_contract.py":
            continue
        f, err = _scan_py(p, root)
        findings.extend(f)
        if err:
            fatal_errors.append(err)

    for p in cmd_files:
        f, err = _scan_cmd(p)
        findings.extend(f)
        if err:
            fatal_errors.append(err)

    if fatal_errors:
        for e in fatal_errors[:20]:
            print(f"[ERROR] {e}", file=sys.stderr)
        if len(fatal_errors) > 20:
            print(f"[ERROR] ... ({len(fatal_errors) - 20} more)", file=sys.stderr)
        return 3

    if findings:
        _print_findings(root, findings)
        print(f"[FAIL] exit-code contract violations: {len(findings)}", file=sys.stderr)
        return 2

    print("[PASS] exit-code contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
