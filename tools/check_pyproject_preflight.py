#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

Preflight: verify pyproject.toml is UTF-8 + sane ASCII-ish, and parseable TOML.

Rationale
- TOML v1.0 requires UTF-8 documents; non-UTF8 or invisible unicode often causes pip/PEP 517 failure.
- This repo sets requires-python >= 3.11, so stdlib tomllib is always available.

Exit codes
- 0: PASS
- 2: FAIL
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import unicodedata
import tomllib


_SUSPECT_CODEPOINTS = {
    # Smart quotes
    0x2018,
    0x2019,
    0x201C,
    0x201D,
    # Dashes/minus variants
    0x2010,
    0x2011,
    0x2012,
    0x2013,
    0x2014,
    0x2212,
    0xFF0D,
    # Spaces / invisibles
    0x00A0,  # NBSP
    0x200B,  # ZWSP
    0x200C,
    0x200D,  # ZWNJ/ZWJ
    0x2060,  # Word joiner
    0xFEFF,  # BOM / ZWNBSP
}


def _scan_unicode(text: str, ascii_only: bool) -> list[dict]:
    issues: list[dict] = []
    for idx, ch in enumerate(text):
        cp = ord(ch)
        if ascii_only and cp > 0x7F:
            issues.append(
                {
                    "kind": "non-ascii",
                    "codepoint": f"U+{cp:04X}",
                    "char": ch,
                    "name": unicodedata.name(ch, "UNKNOWN"),
                    "index": idx,
                }
            )
            continue
        if cp in _SUSPECT_CODEPOINTS:
            issues.append(
                {
                    "kind": "suspect",
                    "codepoint": f"U+{cp:04X}",
                    "char": ch,
                    "name": unicodedata.name(ch, "UNKNOWN"),
                    "index": idx,
                }
            )
    return issues


def _idx_to_line_col(text: str, idx: int) -> tuple[int, int]:
    # 1-based line/col
    line = text.count("\n", 0, idx) + 1
    last_nl = text.rfind("\n", 0, idx)
    col = idx - last_nl
    return line, col


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="pyproject.toml", help="Path to TOML (default: pyproject.toml)")
    ap.add_argument("--ascii-only", action="store_true", help="Fail if any non-ASCII character exists")
    args = ap.parse_args(argv)

    def _print_hint() -> None:
        """Print actionable guidance for beginners.

        This tool intentionally stays single-purpose (preflight only) and communicates
        success/failure via exit code. To make the workflow harder to misuse in Windows
        interactive CMD, recommend a fail-fast runner or "&&" chaining.
        """
        print(
            "[HINT] Windows CMD interactive mode does not stop after failures. "
            'Use "&&" to chain commands, or run tools\\run_ci_gates.cmd.'
        )

    p = Path(args.path).resolve()
    print(f"[INFO] pyproject_path = {p}")

    if not p.exists():
        print("[FATAL] pyproject file not found")
        _print_hint()
        return 2

    raw = p.read_bytes()

    # 1) UTF-8 strict decode (TOML v1.0 requirement)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        print(f"[FATAL] not UTF-8 (strict decode failed): {e}")
        _print_hint()
        return 2

    # 2) Unicode scan (invisible / risky chars)
    issues = _scan_unicode(text, ascii_only=bool(args.ascii_only))
    if issues:
        print("[FAIL] suspicious characters detected:")
        for it in issues[:200]:
            line, col = _idx_to_line_col(text, int(it["index"]))
            # VS Code Ctrl+Click: ABS_PATH:LINE:COL: ...
            # NOTE: f-string expressions cannot contain backslashes in older parsers
            # (e.g., Python 3.11 grammar). Use single quotes in dict indexing.
            print(f"{p}:{line}:{col}: [FAIL] {it['kind']}  {it['codepoint']}  {it['name']}  repr={it['char']!r}")
        if len(issues) > 200:
            print(f"  ... ({len(issues) - 200} more)")
        _print_hint()
        return 2

    # 3) TOML parse (stdlib tomllib, TOML 1.0.0)
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        msg = str(e)
        m = re.search(r"\(at line (\d+), column (\d+)\)", msg)
        if m:
            line = int(m.group(1))
            col = int(m.group(2))
            # VSCode clickable: path:line:col
            print(f"{p}:{line}:{col}: [FATAL] TOML parse failed: {msg}")
        else:
            print(f"{p}: [FATAL] TOML parse failed: {msg}")
        _print_hint()
        return 2

    print("[PASS] pyproject.toml preflight OK (UTF-8 + sane chars + TOML parse)")
    _print_hint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
