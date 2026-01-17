#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO-GENERATED WRAPPER

Compatibility entrypoint: allow `python tools/view_report.py ...`.

SSOT: src/mhy_ai_rag_data/tools/view_report.py
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent
    if root.name == "tools":
        root = root.parent
    src = root / "src"
    if src.exists():
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    runpy.run_module("mhy_ai_rag_data.tools.view_report", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
