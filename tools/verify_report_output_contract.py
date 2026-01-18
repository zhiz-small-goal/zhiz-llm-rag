#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO-GENERATED WRAPPER

Generated-By: tools/gen_tools_wrappers.py
Target-Module: mhy_ai_rag_data.tools.verify_report_output_contract
SSOT: src/mhy_ai_rag_data/tools/verify_report_output_contract.py

兼容入口：允许运行 `python tools/<name>.py ...`，但真实实现固定在 src（SSOT）。
不要手工修改本文件；请运行：python tools/gen_tools_wrappers.py --write
"""

from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path


def _ensure_src_on_path() -> None:
    # 保证在未 editable install 的情况下也能导入 src 侧实现
    repo = Path(__file__).resolve().parent
    if repo.name == "tools":
        repo = repo.parent
    src = repo / "src"
    if src.exists():
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    runpy.run_module("mhy_ai_rag_data.tools.verify_report_output_contract", run_name="__main__")
    return 0


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt", file=sys.stderr)
        return 3
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(f"[ERROR] SystemExit: {code}", file=sys.stderr)
        return 3
    except Exception:
        print("[ERROR] unhandled exception", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(_entry())
