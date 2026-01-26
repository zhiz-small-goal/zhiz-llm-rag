---
title: "`snapshot_eval_retrieval_baseline.py` 使用说明（Stage-2 基线固化：metrics/buckets/config）"
version: v1.0
last_updated: 2026-01-25
tool_id: snapshot_eval_retrieval_baseline

impl:
  module: mhy_ai_rag_data.tools.snapshot_eval_retrieval_baseline
  wrapper: tools/snapshot_eval_retrieval_baseline.py

entrypoints:
  - python tools/snapshot_eval_retrieval_baseline.py
  - python -m mhy_ai_rag_data.tools.snapshot_eval_retrieval_baseline

contracts:
  output: report-output-v2

timezone: America/Los_Angeles
cli_framework: argparse
---
# `snapshot_eval_retrieval_baseline.py` 使用说明（Stage-2 基线固化：metrics/buckets/config）

> **适用范围**：Stage-2 retrieval（`run_eval_retrieval.py` 的输出）
> 
> 该工具用于把某次 Stage-2 的结果固化为 baseline（用于后续 compare 门禁）。它会：
> 1) 写出 **baseline 文件**：`data_processed/baselines/eval_retrieval_baseline.json`
> 2) 同时写出一份 **report v2**：`data_processed/build_reports/eval_retrieval_baseline_snapshot_report.json`（用于 gate/view 统一消费）

## 1. 何时使用

- 你已经跑过 `run_eval_retrieval.py`，并且认可当前 `metrics/buckets` 作为新的“可接受基线”；
- 你准备把 Stage-2 纳入 gate，并需要一个可审计的 baseline 文件作为对比输入；
- 你从旧版 Stage-2 升级（例如切换到 `--retrieval-mode hybrid`）后，需要重建 baseline，避免 compare 报 `config_mismatch`。

## 2. 快速开始

在项目根目录运行：

```bash
python tools/snapshot_eval_retrieval_baseline.py --root . \
  --report data_processed/build_reports/eval_retrieval_report.json \
  --baseline-out data_processed/baselines/eval_retrieval_baseline.json
```

成功后你会得到：
- baseline：`data_processed/baselines/eval_retrieval_baseline.json`
- 报告：`data_processed/build_reports/eval_retrieval_baseline_snapshot_report.json`（以及可选 md）

## 3. 输出说明

### 3.1 baseline 文件（给 compare 使用）

baseline 文件的核心结构为：
- `baseline.config`：从 Stage-2 report 中抽取的检索配置（例如 `k/retrieval_mode/dense_pool_k/keyword_pool_k/...`）
- `baseline.metrics`：overall 指标（cases/hit_cases/hit_rate）
- `baseline.buckets`：分桶指标（official/oral/ambiguous）

### 3.2 snapshot report（report-output-v2）

snapshot report 用于统一日志/汇总：
- items 中会记录：输入 report 路径、baseline 输出路径、抽取到的 config/metrics/buckets 等信息
- 如输入 report 缺失/不可解析，会产生 FAIL item

## 4. 参数（摘要）

- `--report`：Stage-2 report.json（默认 `data_processed/build_reports/eval_retrieval_report.json`）
- `--baseline-out`：baseline 输出文件（默认 `data_processed/baselines/eval_retrieval_baseline.json`）
- `--out`：snapshot report 输出（默认 `data_processed/build_reports/eval_retrieval_baseline_snapshot_report.json`）
- `--md-out`：可选 md 输出；不填则默认 `<out>.md`

## 5. 退出码与常见问题

- `0`：成功写出 baseline 与 report
- `2`：输入 report 缺失/不可解析/写出失败

常见问题：
- **baseline 文件写出成功但 compare 仍提示 config_mismatch**：请确认 compare 的 `--strict-config` 是否启用；若启用，需要确保 embedding/collection/pool_k 等也与 baseline 一致。
