---
title: view_gate_report.py 使用说明
version: v1.1
last_updated: 2026-01-16
tool_id: view_gate_report

impl:
  module: mhy_ai_rag_data.tools.view_gate_report
  wrapper: tools/view_gate_report.py

entrypoints:
  - python tools/view_gate_report.py
  - python -m mhy_ai_rag_data.tools.view_gate_report

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# view_gate_report.py 使用说明


## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [输出与产物](#输出与产物)
- [退出码](#退出码)
- [常见问题](#常见问题)

## 目的

把 schema v2 的 gate 报告渲染为：
- **控制台视图**（stdout）：detail 按严重度从轻到重，summary 在末尾，并以 `\n\n` 结束。
- **Markdown 人类入口**（可选落盘）：summary 顶部，detail 按严重度从重到轻，定位字段以 `[loc](loc_uri)` 形式可点击跳转。

同时支持 **中断恢复模式**：直接从 `gate_report.events.jsonl` 重建/查看。

## 适用场景
- 本地或 CI 跑完 gate 后，需要快速扫一眼整体状态与关键步骤。
- gate 运行中断/崩溃，只剩 `gate_report.events.jsonl`，希望重建 `gate_report.md`。

## 快速开始

### 1) 从最终 JSON 渲染

```bash
python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md
```

### 2) 从 events.jsonl（中断恢复）渲染

```bash
python tools/view_gate_report.py --root . --events data_processed/build_reports/gate_report.events.jsonl --md-out data_processed/build_reports/gate_report.md
```

## 参数说明
- `--root`：仓库根目录（默认 `.`）。
- `--report`：`gate_report.json` 路径（相对 `--root`，默认 `data_processed/build_reports/gate_report.json`）。
- `--events`：可选，事件流 `*.events.jsonl` 路径（相对 `--root`）。提供后优先使用该文件渲染。
- `--md-out`：可选，输出 Markdown 文件路径（相对 `--root`）。

## 输出与产物
- 标准输出：控制台视图（包含 detail 与 summary；滚屏友好）。
- 可选落盘：`--md-out` 指定的 Markdown 文件（例如 `data_processed/build_reports/gate_report.md`）。

## 退出码
- `0`：成功渲染。
- `2`：找不到报告文件或 JSON 无法解析。
- `3`：脚本异常（Python 运行时错误）。

## 常见问题

1) **提示 missing or invalid report**
- 原因：`gate_report.json` 不存在/格式错误，且未提供 `--events`。
- 处理：先运行 `python tools/gate.py --profile ci --root .` 生成最终报告；或改用 `--events` 指向事件流文件。

2) **定位链接不可点击**
- 说明：`loc_uri` 以 `vscode://file/...` 形式渲染，依赖本机安装 VS Code 并允许该 scheme 打开。
- 处理：确认 VS Code 已安装；或在 Markdown 中复制 `loc`（纯文本 `path:line:col`）手动跳转。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--events` | — | '' | optional: item events jsonl to render (relative to root); used for recovery/rebuild |
| `--md-out` | — | '' | optional markdown output path (relative to root) |
| `--report` | — | 'data_processed/build_reports/gate_report.json' | gate_report.json path (relative to root) |
| `--root` | — | '.' | project root |
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
