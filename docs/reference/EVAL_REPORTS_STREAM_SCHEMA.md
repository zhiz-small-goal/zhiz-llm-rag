---
title: Eval 报告 items 事件流（events.jsonl）schema
version: 2
last_updated: 2026-01-21
timezone: America/Los_Angeles
---

# Eval 报告 items 事件流（events.jsonl）schema


> 目标：为长任务提供“即时落盘 + 中断可恢复”的 **items 事件流** 工件（JSONL），用于实时观测与事后审计。该工件是旁路，不替代最终汇总报告 JSON（判定真源/SoT）。

## 目录
- [1. 定义与定位](#1-定义与定位)
- [2. 文件命名与并存规则](#2-文件命名与并存规则)
- [3. 记录语义](#3-记录语义)
- [4. 写入与容错建议](#4-写入与容错建议)
- [5. 引用](#5-引用)

---

## 1. 定义与定位

- events 文件格式：**JSONL**（每行一个 JSON object）。
- 每行语义：**report-output-v2 的一个 `item`**（与最终报告 `items[]` 同结构）。
- 不承载运行时“进度条/Spinner”（进度必须走 stderr 或其它旁路，不写入 events）。

实现位置（SoT）：
- 写入器：`src/mhy_ai_rag_data/tools/report_events.py`（`ItemEventsWriter`）
- 工程规则：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`（items/排序/loc_uri 等）

---

## 2. 文件命名与并存规则

- 判定真源（SoT，保持不变）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- 观测旁路（events）：
  - `data_processed/build_reports/eval_retrieval_report.events.jsonl`
  - `data_processed/build_reports/eval_rag_report.events.jsonl`

约束：
- 任何消费端门禁只读 final JSON，不读 events。
- events 用于：实时观测、诊断、以及运行中断后的“重放/恢复”输入。

---

## 3. 记录语义

### 3.1 最小字段

每行至少应满足：
- 是一个 JSON object
- 具备 report v2 item 的核心字段之一（例如：`status_label`/`severity_level`/`message`）。

写入器会在缺失时补充：
- `ts_ms`：毫秒时间戳（int）

> 说明：items 的完整字段集合以 `REPORT_OUTPUT_ENGINEERING_RULES.md` 为准；events 只是把 items 逐条 append 写出。

### 3.2 与最终报告的关系

- final 报告：包含 `summary` + `items[]` + `data`。
- events：只包含 **items 的增量序列**，不包含 `summary`（summary 需要全量聚合）。

推断：
- 若要在运行中展示“已处理条数/当前失败数”等聚合指标，需要消费端对 events 做增量聚合，或由工具另行输出进度摘要到 stderr。（该聚合不应反向影响 final 口径。）

---

## 4. 写入与容错建议

- 写入：append-only；建议一开始 truncate 旧文件（同一次 run 内保持单一序列）。
- 容错：消费端应忽略空行/解析失败行（中断时可能出现半行）。
- 对账：运行结束后，以 final JSON 为准；若需要一致性校验，应对比 “events 行数/状态计数” 与 final `summary.counts`（注意 final 可能包含非 events 来源的 items，例如启动阶段校验项）。

---

## 5. 引用

- JSON text 定义：
  - URL: https://www.rfc-editor.org/rfc/rfc8259.txt
  - 日期/版本: 2017-12 (RFC 8259)
  - 来源类型: Primary（标准）
  - 定位: §2 JSON Grammar
