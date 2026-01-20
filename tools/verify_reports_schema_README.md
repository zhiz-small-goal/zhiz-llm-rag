---
title: verify_reports_schema.py 使用说明
version: v1.0
last_updated: 2026-01-16
tool_id: verify_reports_schema

impl:
  module: mhy_ai_rag_data.tools.verify_reports_schema
  wrapper: tools/verify_reports_schema.py

entrypoints:
  - python tools/verify_reports_schema.py
  - python -m mhy_ai_rag_data.tools.verify_reports_schema

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# verify_reports_schema.py 使用说明


> 目标：验证单个 JSON 报告文件的格式和必需字段，可选地使用 JSON Schema 进行严格验证。

## 快速开始

```cmd
python tools\verify_reports_schema.py --report data_processed\build_reports\check.json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--report` | *(required)* | 报告文件路径 |
| `--step` | *(空)* | 可选的预期 step 名称 |
| `--schema` | *(空)* | 可选的 JSON Schema 文件路径 |

## 功能

- 检查 JSON 可解析性
- 验证必需顶层字段：`status`、`step`、`inputs`、`metrics`、`errors`、`generated_at`
- 验证 `status` 值在允许范围内（PASS/WARN/FAIL/ERROR/SKIP 等）
- 可选：使用 `--schema` 进行完整 JSON Schema 验证

## 退出码

- `0`：PASS（所有报告符合 schema）
- `2`：FAIL（存在不符合 schema 的报告）

## 输出示例

```
[PASS] check.json conforms to schema
[FAIL] eval_report.json: 'status' is a required property
STATUS: FAIL (1/2 reports invalid)
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/verify_reports_schema.py`。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--report` | true | — | JSON report path |
| `--schema` | — | '' | Optional JSON Schema path for jsonschema validation |
| `--step` | — | '' | Optional expected tool name (legacy flag name) |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
