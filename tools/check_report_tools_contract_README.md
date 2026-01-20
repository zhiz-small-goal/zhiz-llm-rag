---
title: check_report_tools_contract.py 使用说明（report tools registry 合规性）
version: v0.1
last_updated: 2026-01-20
tool_id: check_report_tools_contract

impl:
  module: mhy_ai_rag_data.tools.check_report_tools_contract
  wrapper: tools/check_report_tools_contract.py

entrypoints:
  - python tools/check_report_tools_contract.py
  - python -m mhy_ai_rag_data.tools.check_report_tools_contract

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_report_tools_contract.py 使用说明


> 目标：校验 report-output-v2 工具的 registry（`report_tools_registry.toml`）与工具自描述（`REPORT_TOOL_META`）一致性，并可选运行各工具 `--selftest` 以验证产物、stdout、markdown 渲染等与契约一致。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [退出码](#退出码)
- [自动生成参考（README↔代码对齐）](#自动生成参考readme代码对齐)

## 目的
- 防止 registry 与代码中的 `REPORT_TOOL_META` 出现偏差（id/kind/channels/contract_version/entrypoint/high_cost/selftest 支持）。
- 校验工具自检产物：`report.json/.md`、`render_console`/`render_markdown` 一致性；高成本工具还校验 events/checkpoint。
- 提供统一的 report-output-v2 报告产物，便于 gate/CI 汇总。

## 适用场景
- CI/gate：确保新增或修改的报告类工具遵循 registry 契约。
- 本地回归：在修改 report 渲染逻辑或 registry 时，快速发现契约回归。
- 高成本工具：确认自检产物完整（events、checkpoint）。

## 快速开始
```bash
# 仅做静态检查（registry ↔ REPORT_TOOL_META）
python tools/check_report_tools_contract.py --root . --mode static

# 仅运行自检（按 registry 中 supports_selftest 的工具执行 --selftest）
python tools/check_report_tools_contract.py --root . --mode selftest --scope all

# 全量：静态 + 自检
python tools/check_report_tools_contract.py --root . --mode all --scope changed --timeout-s 120
```

## 退出码
- `0`：PASS
- `2`：FAIL（契约违反或自检失败）
- `3`：ERROR（脚本异常）

## 自动生成参考（README↔代码对齐）

> 本节为派生内容：优先改源代码/SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 回写。
> tool_id: `check_report_tools_contract`
> entrypoints: `python tools/check_report_tools_contract.py`, `python -m mhy_ai_rag_data.tools.check_report_tools_contract`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--mode` | — | 'static' | static: only static checks; selftest: only run tool --selftest; all: both |
| `--out` | — | 'data_processed/build_reports/check_report_tools_contract.json' | Output report.json path (relative to --root) |
| `--registry` | — | 'docs/reference/report_tools_registry.toml' | Registry TOML path (relative to --root) |
| `--root` | — | '.' | Repo root |
| `--scan-dir` | — | 'src/mhy_ai_rag_data/tools' | Directory to scan for REPORT_TOOL_META (relative to --root) |
| `--scope` | — | 'all' | Which tools to run selftest for |
| `--strict` | — | — | action=store_true；Treat verify warnings as failures |
| `--timeout-s` | — | 90 | type=int；Per-tool selftest timeout |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
- artifacts（registry）：
  - `data_processed/build_reports/check_report_tools_contract.json`
  - `data_processed/build_reports/check_report_tools_contract.md`
<!-- AUTO:END artifacts -->
