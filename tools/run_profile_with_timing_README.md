---
title: run_profile_with_timing.py 使用说明（带时间统计的性能分析）
version: v1.0
last_updated: 2026-01-16
tool_id: run_profile_with_timing

impl:
  module: mhy_ai_rag_data.tools.run_profile_with_timing
  wrapper: tools/run_profile_with_timing.py

entrypoints:
  - python tools/run_profile_with_timing.py
  - python -m mhy_ai_rag_data.tools.run_profile_with_timing

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# run_profile_with_timing.py 使用说明

> 目标：运行 build profile 并记录每步耗时，生成性能报告。

## 快速开始

```cmd
python tools\run_profile_with_timing.py --profile build_profile_schemeB.json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--profile` | `build_profile_schemeB.json` | Profile JSON 路径 |
| `--smoke` | *(flag)* | 烟雾模式（快速验证）|

## 退出码

- `0`：PASS
- `2`：FAIL

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/run_profile_with_timing.py`。
