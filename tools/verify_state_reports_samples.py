#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO-GENERATED WRAPPER

兼容入口：允许在仓库根目录下继续使用 `python tools/verify_state_reports_samples.py`。

权威实现位于：src/mhy_ai_rag_data/tools/verify_state_reports_samples.py
推荐用法：
- pip install -e .
- 或 python -m mhy_ai_rag_data.tools.verify_state_reports_samples
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
    runpy.run_module("mhy_ai_rag_data.tools.verify_state_reports_samples", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
