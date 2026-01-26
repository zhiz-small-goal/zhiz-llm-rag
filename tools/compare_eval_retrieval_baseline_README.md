---
title: "`compare_eval_retrieval_baseline.py` 使用说明（Stage-2 基线对比门禁：不退化）"
version: v1.0
last_updated: 2026-01-25
tool_id: compare_eval_retrieval_baseline

impl:
  module: mhy_ai_rag_data.tools.compare_eval_retrieval_baseline
  wrapper: tools/compare_eval_retrieval_baseline.py

entrypoints:
  - python tools/compare_eval_retrieval_baseline.py
  - python -m mhy_ai_rag_data.tools.compare_eval_retrieval_baseline

contracts:
  output: report-output-v2

timezone: America/Los_Angeles
cli_framework: argparse
---
# `compare_eval_retrieval_baseline.py` 使用说明（Stage-2 基线对比门禁：不退化）

> **适用范围**：Stage-2 retrieval（`run_eval_retrieval.py` 的输出）
>
> 该工具把“当前 Stage-2 report”与“已固化 baseline”进行对比，并输出 report v2 items 作为 gate 的裁决依据。

## 1. 对比做什么

- **指标对比**：默认对比 overall `hit_rate`，并可对分桶（official/oral/ambiguous）分别裁决；
- **配置一致性**：默认至少要求 `k` 与 `retrieval_mode` 一致（避免对比口径不一致导致误判）；
- **可选严格一致性**：开启 `--strict-config` 后，会把 `embed_model/device/collection/pool_k/fusion_method/rrf_k` 等也纳入一致性校验。

## 2. 快速开始（推荐：不允许下降）

```bash
python tools/compare_eval_retrieval_baseline.py --root . \
  --baseline data_processed/baselines/eval_retrieval_baseline.json \
  --report data_processed/build_reports/eval_retrieval_report.json \
  --allowed-drop 0.0 --bucket-allowed-drop 0.0 \
  --out data_processed/build_reports/eval_retrieval_baseline_compare_report.json
```

输出：
- `data_processed/build_reports/eval_retrieval_baseline_compare_report.json`
- 可选：`--md-out` 生成 Markdown 版（便于人工阅读与 code review）

## 3. 常见 FAIL 与处理

1) `baseline_missing`
- 触发：baseline 文件不存在
- 处理：先运行 `snapshot_eval_retrieval_baseline.py` 固化 baseline

2) `config_mismatch`
- 触发：baseline 与 current 的关键配置字段不同（默认检查 `k/retrieval_mode`）
- 处理：先确认是否“有意变更口径”。若是有意升级（例如 dense→hybrid），先重新 snapshot baseline；若不是有意变更，修复当前配置回到 baseline。

3) `metric_drop` / `bucket_drop`
- 触发：当前 `hit_rate` 低于 baseline 超过阈值
- 处理：优先用 report 中的 FAIL 用例与 `topk/debug` 定位（embedding/分块/索引/查询侧），必要时先恢复上一版口径再逐步引入变更。

## 4. 参数（摘要）

- `--allowed-drop`：overall `hit_rate` 允许下降的绝对值（例如 0.02 表示允许下降 2 个百分点）
- `--bucket-allowed-drop`：每个 bucket 的允许下降
- `--strict-config`：把更多 config 字段纳入一致性校验
- `--skip-if-missing`：用于 gate/CI，当 report 缺失或被标记为跳过时，以 WARN 退出 0（但 baseline 缺失仍会 FAIL）

## 5. 退出码

- `0`：对比完成（可能包含 WARN/FAIL items；以 report v2 的 items 为准）
- `2`：参数/IO 错误等导致工具自身失败（非“指标退化”）
