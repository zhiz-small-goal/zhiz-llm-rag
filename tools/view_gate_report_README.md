---
title: view_gate_report.py 使用说明
version: v1.0
last_updated: 2026-01-12
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
把 `gate_report.json` 生成一份人类可读的 Markdown 摘要，便于快速定位 FAIL/ERROR 的 step 与日志路径。

## 适用场景
- PR/CI Lite 跑完 gate 后，需要快速扫一眼整体状态与关键步骤。
- 需要给 Review 或 Handoff 提供更易读的汇总页面。

## 快速开始
```bash
python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md
```

## 参数说明
- `--root`：仓库根目录（默认 `.`）。
- `--report`：`gate_report.json` 路径（相对 `--root`，默认 `data_processed/build_reports/gate_report.json`）。
- `--md-out`：可选，输出 Markdown 文件路径（相对 `--root`）。
- `--max-findings`：每个 step 里展示的 findings 上限（默认 8）。

## 输出与产物
- 标准输出：Markdown 文本摘要（含 summary、results、warnings、findings）。
- 可选落盘：`--md-out` 指定的 Markdown 文件（例如 `data_processed/build_reports/gate_report.md`）。

## 退出码
- `0`：成功生成摘要。
- `2`：找不到报告文件或 JSON 无法解析。
- `3`：脚本异常（Python 运行时错误）。

## 常见问题
1) **提示 missing or invalid report**
- 原因：`gate_report.json` 不存在或格式错误。
- 处理：先运行 `python tools/gate.py --profile ci --root .` 生成报告，再执行本脚本。

2) **findings 为空**
- 说明：`findings` 为可选字段，只有 gate step 明确写入才会展示。
