#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.verify_single_report_output

用途：
  验收“提供 --json-out 时，只产出一份报告文件”的规则是否被遵守。
  这是一个通用脚本：给定一个 glob（默认 llm_probe_report_*.json），它会检查当前目录是否出现默认报告文件。

使用：
  # 运行 probe（示例）
  python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed/build_reports/llm_probe.json

  # 立刻验证当前目录没有生成默认文件
  python -m tools.verify_single_report_output --glob "llm_probe_report_*.json"

退出码：
  0：PASS（未发现匹配文件）
  2：FAIL（发现了匹配文件）
"""

from __future__ import annotations

import argparse
from pathlib import Path
import glob as _glob

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="llm_probe_report_*.json", help="检查当前目录中不应出现的默认报告文件匹配模式")
    args = ap.parse_args()

    found = [Path(p) for p in _glob.glob(args.glob)]
    if found:
        print("[FAIL] default report file(s) found (should be none when --json-out is provided):")
        for p in found[:20]:
            print("  -", p)
        return 2

    print("[PASS] no default report files found.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
