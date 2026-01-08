#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO-GENERATED WRAPPER

兼容入口：允许在仓库根目录下继续使用 `python prompt_rag.py ...`。

权威实现位于：src/mhy_ai_rag_data/prompt_rag.py
推荐用法：
- pip install -e .
- 使用 console scripts: rag-*
- 或 python -m mhy_ai_rag_data.prompt_rag ...
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent
    # tools/*.py 在 tools 目录下，需要回到 repo root
    if root.name == 'tools':
        root = root.parent
    src = root / 'src'
    if src.exists():
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    runpy.run_module('mhy_ai_rag_data.prompt_rag', run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
