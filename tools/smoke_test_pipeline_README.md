---
title: smoke_test_pipeline.py 使用说明（烟雾测试管道）
version: v1.0
last_updated: 2026-01-16
tool_id: smoke_test_pipeline

impl:
  module: mhy_ai_rag_data.tools.smoke_test_pipeline
  wrapper: tools/smoke_test_pipeline.py

entrypoints:
  - python tools/smoke_test_pipeline.py
  - python -m mhy_ai_rag_data.tools.smoke_test_pipeline

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# smoke_test_pipeline.py 使用说明

> 目标：快速烟雾测试管道，验证核心流程可用性。

## 快速开始

```cmd
python tools\smoke_test_pipeline.py --root .
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |

## 退出码

- `0`：PASS
- `2`：FAIL

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/smoke_test_pipeline.py`。
