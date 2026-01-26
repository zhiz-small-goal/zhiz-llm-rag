---
title: 观测长任务（进度与 items 事件流）
version: 3
last_updated: 2026-01-25
timezone: America/Los_Angeles
---

# 观测长任务（进度与 items 事件流）


> 目标：当评测/构建步骤运行时间较长时，在运行过程中获得可用信号（stderr 进度 + events.jsonl），避免只在最终 JSON 落盘后才发现偏差。

## 目录
- [1. 背景与约束](#1-背景与约束)
- [2. 推荐做法（events + progress，final 仍为 SoT）](#2-推荐做法events--progressfinal-仍为-sot)
- [3. run_eval_retrieval：观测示例](#3-run_eval_retrieval观测示例)
- [4. run_eval_rag：观测示例](#4-run_eval_rag观测示例)
- [5. Windows 观测命令（PowerShell）](#5-windows-观测命令powershell)
- [6. 常见问题与裁决](#6-常见问题与裁决)

---

## 1. 背景与约束

- 约束 1：最终汇总报告（`*_report.json`）必须保持 **合法 JSON**，且保持既有消费链路不变（例如 gate/view 脚本只读 final）。
- 约束 2：单个 JSON 文件在未写完前通常不是合法 JSON text；因此实时观测不应依赖“边写同一个 final JSON 文件”。

引用（JSON text 语法）：
- URL: https://www.rfc-editor.org/rfc/rfc8259.txt
- 日期/版本: 2017-12 (RFC 8259)
- 来源类型: Primary（标准）
- 定位: §2 JSON Grammar

---

## 2. 推荐做法（events + progress，final 仍为 SoT）

- final（判定真源 / SoT）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- events（观测旁路 / 可增量消费）：
  - `*.events.jsonl`（每行一个 report v2 item）
- progress（控制台旁路）：
  - `--progress`（stderr 输出），配合 `--progress-min-interval-ms` 做节流。

events 的结构来源：`src/mhy_ai_rag_data/tools/report_events.py`；完整 items 字段与排序规则来源：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`。

---

## 3. run_eval_retrieval：观测示例

```bash
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 5 --retrieval-mode hybrid --dense-topk 50 --keyword-topk 50 --fusion-method rrf --rrf-k 60 --out data_processed/build_reports/eval_retrieval_report.json   --events-out data_processed/build_reports/eval_retrieval_report.events.jsonl   --progress on --progress-min-interval-ms 500
```

你会得到两类信号：
- stderr：节流后的进度摘要（由 `--progress*` 控制）
- 文件：`eval_retrieval_report.events.jsonl`（items 事件流）

---

## 4. run_eval_rag：观测示例

```bash
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --k 5   --out data_processed/build_reports/eval_rag_report.json   --events-out data_processed/build_reports/eval_rag_report.events.jsonl   --progress on --progress-min-interval-ms 500   --print-case-errors
```

说明：
- `--print-case-errors` 仅用于运行中快速判因（stderr 一行摘要）；最终裁决仍以 report.json 为准。

---

## 5. Windows 观测命令（PowerShell）

```powershell
# 实时查看 jsonl items 事件流
Get-Content -Wait data_processed\build_reports\eval_retrieval_report.events.jsonl

Get-Content -Wait data_processed\build_reports\eval_rag_report.events.jsonl
```

---

## 6. 常见问题与裁决

1) **events 文件存在，但最终 report.json 还没生成**
- 现象：events 已有大量 item，但 final 还未写出。
- 裁决：预期行为（final 需要全量汇总）。运行中以 events + stderr 进度判断“是否在推进”。

2) **events 与 final 指标不一致**
- 现象：你在运行中增量统计得到的计数，与 final `summary.counts` 不一致。
- 裁决：优先以 final 为准；不一致常见原因：脚本异常中断导致 final 未完成、消费端对 events 的聚合规则与 final 不同、或 final 除了 case items 还包含启动/校验项等非 case items。

3) **events 文件体积增长太快**
- 现象：jsonl 写入过多 detail 字段导致 IO 压力。
- 裁决：events 设计为 items 级别的增量记录；若某工具的 item.detail 过大，可通过工具侧在 detail 中做截断/摘要（保持最终 report.json 仍可审计）。
