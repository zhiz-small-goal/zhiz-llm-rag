---
title: verify_single_report_output.py 使用说明
version: v1.0
last_updated: 2026-01-16
---

# verify_single_report_output.py 使用说明

> 目标：检查当前目录是否存在不应出现的默认报告文件（用于验证工具正确使用了 `--json-out` 参数）。

## 快速开始

```cmd
python tools\verify_single_report_output.py
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--glob` | `llm_probe_report_*.json` | 文件匹配模式，检查是否存在匹配的文件 |

## 功能

- 使用 glob 模式搜索当前目录
- 如果找到匹配文件，说明工具未正确使用 `--json-out` 参数
- 用于 CI 中验证报告输出位置是否规范

## 退出码

- `0`：PASS（未找到默认报告文件）
- `2`：FAIL（找到默认报告文件，说明工具使用不规范）

## 使用场景

- CI 中检查工具是否正确指定了输出路径
- 避免报告文件散落在各个目录

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/verify_single_report_output.py`。
