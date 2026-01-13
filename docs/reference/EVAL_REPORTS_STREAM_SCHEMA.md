---
title: Eval 报告流式事件（stream）schema
version: 1
last_updated: 2026-01-06
timezone: America/Los_Angeles
---

# Eval 报告流式事件（stream）schema


> 目标：为长任务提供可增量消费的“事件流”工件（jsonl/json-seq），用于实时观测与事后审计。该工件是旁路，不替代最终汇总报告 JSON。

## 目录
- [1. 背景与格式选择](#1-背景与格式选择)
- [2. 文件命名与并存规则](#2-文件命名与并存规则)
- [3. 通用字段](#3-通用字段)
- [4. 记录类型](#4-记录类型)
- [5. 消费端建议（容错与对账）](#5-消费端建议容错与对账)
- [6. 引用](#6-引用)

---

## 1. 背景与格式选择

- final JSON 文件在写完之前通常不构成合法 JSON text，因此不适合边写边看。
- 为支持增量写入/读取，需要“记录序列”格式。

两种可选格式：
- **JSONL（默认）**：每行一个 JSON 对象。工程惯例，最适合命令行/PowerShell 实时观察。
- **json-seq（可选）**：RFC 7464 JSON Text Sequences，RS(0x1E) + JSON + LF，标准化的可增量序列格式。

## 2. 文件命名与并存规则

- 判定真源（SoT，保持不变）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- 观测旁路（新增）：
  - `data_processed/build_reports/eval_retrieval_report.events.jsonl`（或 `.events.json-seq`）
  - `data_processed/build_reports/eval_rag_report.events.jsonl`（或 `.events.json-seq`）

约束：
- 任何消费端门禁（如 `rag_accept.py`）只读 final JSON，不读 stream。
- stream 仅用于：实时观测、诊断、以及与 final 的对账。

## 3. 通用字段

所有记录 **建议** 包含以下字段（缺失时消费端需容错）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `record_type` | string | 是 | `meta` / `case` / `error` / `summary` |
| `run_id` | string | 是 | 本次运行唯一标识（同一 run 内所有记录一致） |
| `ts_ms` | int | 建议 | 毫秒时间戳 |
| `tool` | string | meta 建议 | 例如 `run_eval_retrieval` / `run_eval_rag` |
| `schema_version` | string|int | meta 建议 | stream schema 版本（本文件为 v1） |

## 4. 记录类型

### 4.1 `meta`

用于标识一次运行的开始/环境/参数（至少写 1 条）。

最小示例：
```json
{"record_type":"meta","run_id":"eval_retrieval-<RUN_ID>","tool":"run_eval_retrieval","schema_version":1,"argv":["<ARGV>"],"k":5}
```

### 4.2 `case`

每完成 1 条用例追加 1 条记录。

- retrieval 侧建议字段：
  - `case_id` / `bucket` / `query` / `expected_sources` / `hit_at_k` / `topk` / `elapsed_ms`
- rag 侧建议字段：
  - `case_id` / `passed` / `llm_call_ok` / `missing` / `context_chars` / `elapsed_ms`
  - `answer_snippet`（可选，建议截断，避免 IO 过大）
  - `error`（可选）：简短错误字符串（用于快速扫一眼）
  - `error_detail`（可选）：结构化错误详情（建议仅在 `llm_call_ok=false` 时出现）
    - 典型字段：`status_code` / `cause` / `url` / `timeout` / `response_snippet`（截断）

### 4.3 `error`

当脚本在运行中遇到 **脚本级异常**（通常会导致提前退出或无法继续处理后续 case）时追加。

说明：
- **用例级失败**（例如 `LLMHTTPError`、单条 case 的 must-include 不通过）应当用 `record_type=case` 表达，并在 `case` 记录里通过 `llm_call_ok=false`、`error`、`error_detail` 等字段承载诊断信息。
- 因此，即使某次运行“所有 case 都失败”，只要脚本能跑完整个用例集并写出 `summary`，也可能 **不会出现任何 `record_type=error` 记录**。

示例：
```json
{"record_type":"error","run_id":"<RUN_ID>","message":"RuntimeError: <MESSAGE>","traceback":"<TRACEBACK>"}
```

### 4.4 `summary`

结束时写 1 条汇总，便于实时消费端快速得到总体结论。

建议字段：
- `metrics`：例如 `cases_total / hit_cases / hit_rate` 或 `passed_cases / pass_rate`
- `elapsed_ms_total`
- `final_report_path`（若可得）

## 5. 消费端建议（容错与对账）

- **容错**：尾部半写行/半写记录要忽略（尤其是进程意外中断时）。
- **对账**（运行结束后）：
  - `summary.metrics.cases_total` 与 final JSON `metrics.cases` 一致
  - `hit_cases/passed_cases` 等关键计数一致
  - 若不一致，应优先检查：是否使用了不同的 `k`/不同的用例集/不同的输出路径（版本与口径不一致是首因）。

## 6. 引用

- JSON text 定义：
  - URL: https://www.rfc-editor.org/rfc/rfc8259.txt
  - 日期/版本: 2017-12 (RFC 8259)
  - 来源类型: Primary（标准）
  - 定位: §2 JSON Grammar

- JSON Text Sequences（增量序列格式）：
  - URL: https://www.rfc-editor.org/rfc/rfc7464.txt
  - 日期/版本: 2015-02 (RFC 7464)
  - 来源类型: Primary（标准）
  - 定位: §1 Introduction and Motivation
