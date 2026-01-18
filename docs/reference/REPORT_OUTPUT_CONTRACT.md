---
title: 报告输出契约（compat alias）
version: v2
last_updated: 2026-01-18
timezone: America/Los_Angeles
---

# 报告输出契约（compat alias）

本文档不再作为输出契约的单一真源（SSOT）。

- **SSOT**：[`REPORT_OUTPUT_ENGINEERING_RULES.md`](REPORT_OUTPUT_ENGINEERING_RULES.md)
- 本文件仅作为兼容入口保留，避免旧链接失效。

> 若你在实现/修改任何会产出 `schema_version=2` 报告的工具，请以 SSOT 文档为准：
> - 文件输出（JSON/Markdown）
> - 控制台输出（stdout）
> - VS Code 可点击定位（loc/loc_uri）
> - 长跑任务（progress + `*.events.jsonl` + 恢复）

