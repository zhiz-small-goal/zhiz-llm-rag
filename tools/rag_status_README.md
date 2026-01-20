---
title: rag_status.py 使用说明（RAG 状态/新鲜度检查）
version: v1.0
last_updated: 2026-01-16
tool_id: rag_status

impl:
  module: mhy_ai_rag_data.tools.rag_status
  wrapper: tools/rag_status.py

entrypoints:
  - python tools/rag_status.py
  - python -m mhy_ai_rag_data.tools.rag_status

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# rag_status.py 使用说明

> 目标：基于本地真实产物+报告，给出当前状态与下一步建议，解决"多机/重复构建后忘记进度"的痛点。

## 快速开始

```cmd
python tools\rag_status.py --root .
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | *(auto)* | 项目根目录 |
| `--profile` | *(auto)* | 构建 profile JSON |
| `--strict` | *(flag)* | 严格模式（任何 MISS/FAIL/STALE 返回 FAIL）|
| `--json-out` | *(空)* | JSON 报告输出路径 |

## 退出码

- `0`：PASS（strict 模式下无 MISS/FAIL/STALE）或 INFO（非 strict）
- `2`：FAIL（strict 模式下有问题）

## 示例

```cmd
rem 查看状态
python tools\rag_status.py --root .

rem 严格模式（用于 CI）
python tools\rag_status.py --root . --strict --json-out data_processed\build_reports\status.json
```

## 报告兼容性

**自身输出格式**: `schema_version=1`（保持向后兼容）

**检查能力**: 兼容检查 `schema_version=1` 和 `schema_version=2` 的报告
- v1 报告：从顶层 `status` 字段读取状态
- v2 报告：从 `summary.overall_status_label` 读取状态，并记录 `total_items` 和 `max_severity_level`

rag_status 定位为"状态检查工具"而非"诊断报告工具"，因此其自身输出保持简单的 v1 格式，但能够检查其他工具生成的 v1 或 v2 报告。

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/rag_status.py`。
