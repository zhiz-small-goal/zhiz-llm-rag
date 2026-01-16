---
title: 观测长任务（实时进度与事件流）
version: 1
last_updated: 2026-01-06
timezone: America/Los_Angeles
---

# 观测长任务（实时进度与事件流）


> 目标：当评测/构建步骤运行时间较长时，做到“跑的过程中就能看到是否在正确推进”，避免等最终 JSON 落盘后才发现偏差。

## 目录
- [观测长任务（实时进度与事件流）](#观测长任务实时进度与事件流)
  - [目录](#目录)
  - [1. 背景与约束](#1-背景与约束)
  - [2. 推荐做法（旁路 stream + 保留 final）](#2-推荐做法旁路-stream--保留-final)
  - [3. run\_eval\_retrieval：实时观测示例](#3-run_eval_retrieval实时观测示例)
  - [4. run\_eval\_rag：实时观测示例](#4-run_eval_rag实时观测示例)
  - [5. Windows 观测命令（PowerShell/CMD）](#5-windows-观测命令powershellcmd)
  - [6. 常见问题与裁决](#6-常见问题与裁决)

---

## 1. 背景与约束

- 约束 1：最终汇总报告（`*_report.json`）必须保持 **合法 JSON**，且尽量保持既有消费链路不变（例如 `view_stage2_reports.py`、`rag_accept.py` 只读 final）。
- 约束 2：单个 JSON 文件在“未写完”前通常不是合法 JSON text；对外部工具来说不可增量解析。RFC 8259 将 JSON text 定义为“单一序列化值”，因此未完成的 JSON 无法被当作合法 JSON text 消费。\
  引用：https://www.rfc-editor.org/rfc/rfc8259.txt | 日期=2017-12 | 来源类型=Primary（标准） | 定位=§2 JSON Grammar

因此：**实时观测不应依赖“边写同一个 final JSON 文件”。**

---

## 2. 推荐做法（旁路 stream + 保留 final）

- final（判定真源 / SoT）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- stream（观测旁路 / 可增量消费）：
  - `*.events.jsonl`（默认）或 `*.events.json-seq`（可选）

选择 jsonl 作为默认 stream 的理由：
- 本仓库已有 JSONL 使用习惯（`eval_cases.jsonl`），且 Windows 下 `Get-Content -Wait` / `tail -f` 体验最好。
- 若你需要标准化的增量序列格式，可选 RFC 7464 JSON Text Sequences（json-seq）。RFC 7464 设计目标就是“可以增量生产/消费一系列 JSON 文本”。\
  引用：https://www.rfc-editor.org/rfc/rfc7464.txt | 日期=2015-02 | 来源类型=Primary（标准） | 定位=§1 Introduction and Motivation

---

## 3. run_eval_retrieval：实时观测示例

```bash
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 5 --out data_processed/build_reports/eval_retrieval_report.json --stream-out data_processed/build_reports/eval_retrieval_report.events.jsonl --stream-format jsonl --progress-every-seconds 10
```

你会得到两类信号：
- 控制台：每 10 秒打印一次 `cases_done/hit_cases/hit_rate/elapsed_s`。
- 文件：`eval_retrieval_report.events.jsonl` 每处理完 1 条 case 追加 1 行 JSON（`record_type=case`），结束追加 `record_type=summary`。

---

## 4. run_eval_rag：实时观测示例

```bash
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --k 5 --out data_processed/build_reports/eval_rag_report.json --stream-out data_processed/build_reports/eval_rag_report.events.jsonl --stream-format jsonl --progress-every-seconds 10 --print-case-errors --stream-answer-chars 200
```

说明：

- `--stream-answer-chars` 默认 0（不写答案片段）。当你需要在长跑过程中快速判断“回答是否明显跑偏”时，可以写一个截断片段（例如 200 字），避免 stream 体积过大。
- `--print-case-errors`：当某条 case 失败时，在控制台立即输出一行简要错误（含 status/cause 截断）；用于“边跑边判因”。默认关闭，避免刷屏。

补充：
- 当 LLM 调用失败（`llm_call_ok=false`）时，events 的 `case` 记录会包含 `error`（短字符串）以及 `error_detail`（结构化详情，含 `status_code/cause/response_snippet` 截断），便于你在长跑中直接判因。

---

## 5. Windows 观测命令（PowerShell/CMD）

PowerShell（推荐）：

```powershell
# 实时查看 jsonl 事件流
Get-Content -Wait data_processed\build_reports\eval_retrieval_report.events.jsonl

# 如果是 json-seq（RFC 7464），可先去掉 RS 分隔符再看
Get-Content -Wait data_processed\build_reports\eval_retrieval_report.events.json-seq | % { $_ -replace "\x1e", "" }
```

CMD：
- CMD 原生对 “follow file” 支持不如 PowerShell；建议优先用 PowerShell。

---

## 6. 常见问题与裁决

1) **stream 文件存在，但最终 report.json 还没生成**
- 现象：events 已有大量 case 记录，但 final 还未写出。
- 裁决：这是预期行为（final 仍在等待全量汇总）。你要看的“是否正确推进”，以 stream + 控制台为准。

2) **stream 与 final 指标不一致**
- 现象：summary 的 cases_total / hit / pass 与 final 的 metrics 不一致。
- 裁决：优先以 final 为准（SoT）。不一致通常来自：脚本异常中断、某些 case 在 final 统计里被过滤、或 stream 写入未 flush。建议把“不一致对账”做成单独的 verify 脚本门禁（先 warning，后收紧）。

3) **events 文件体积增长太快**
- 现象：jsonl 写入包含大量 answer/context，磁盘增长快。
- 裁决：默认保持 stream 轻量，只写关键字段；需要答案片段时用 `--stream-answer-chars` 截断。