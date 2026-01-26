---
title: How-to：建立“口语 vs 官方术语”检索回归（防止 topK 漏召回）
version: v1.1
last_updated: 2026-01-25
---

# How-to：建立“口语 vs 官方术语”检索回归（防止 topK 漏召回）


> 适用日期：2026-01-05  
> 适用范围：Stage-2 retrieval（`run_eval_retrieval.py`），目标是把“表达断桥”变成可回归指标与可解释证据。

## 目录
- [1. 你要达成的验收目标](#1-你要达成的验收目标)
- [2. Step 1 生成/补齐用例（bucket + pair_id）](#2-step-1-生成补齐用例bucket--pair_id)
- [3. Step 2 先过门禁：validate_eval_cases](#3-step-2-先过门禁validate_eval_cases)
- [4. Step 3 跑检索回归：run_eval_retrieval（看 buckets）](#4-step-3-跑检索回归run_eval_retrieval看-buckets)
- [5. Step 4 读报告与定位断桥位置](#5-step-4-读报告与定位断桥位置)
- [6. Step 5 把分桶指标接入 CI/日常回归](#6-step-5-把分桶指标接入-ci日常回归)

---

## 1. 你要达成的验收目标

你要解决的问题是：用户口语表达与文档官方术语不一致，导致候选窗（dense 或 hybrid 融合 topK）里没有目标 chunk，从而出现漏召回。

因此验收目标应以 **oral 分桶**为主：

- `buckets.oral.hit_rate` 不低于基线（或持续改善）
- 在同一 `pair_id` 下，`official` 命中但 `oral` 不命中的差距逐步缩小
- 报告可解释：每条失败用例能看到 topK 来源列表，并可定位到“预期文档是否完全没进入候选窗”

---

## 2. Step 1 生成/补齐用例（bucket + pair_id）

### 2.1 用 `suggest_eval_case.py` 生成初稿（推荐）

**详细文档**: [使用说明（半自动生成 eval case：expected_sources + must_include + bucket/pair_id）](../../tools/suggest_eval_case_README.md)
口语桶（示例）：

```bash
python tools/suggest_eval_case.py --root . --query "如何设定地图边界？" --bucket oral --pair-id map_boundary --concept-id map_boundary --append-to data_processed/eval/eval_cases.jsonl
```

然后再为同一概念补一条 official 用例（对照组）：

```bash
python tools/suggest_eval_case.py --root . --query "如何设置场景生效范围？" --bucket official --pair-id map_boundary --concept-id map_boundary --append-to data_processed/eval/eval_cases.jsonl
```

### 2.2 人工补齐 expected_sources 与 must_include
`expected_sources` 与 `must_include` 是评测稳定性的关键输入：必须指向可长期存在的文档路径，并选择“答案中稳定出现”的锚点词（命令、参数、文件名等优先）。

---

## 3. Step 2 先过门禁：validate_eval_cases

**相关文档**: [使用说明（校验 eval_cases.jsonl：结构 + 可执行性 + 分桶字段）](../../tools/validate_eval_cases_README.md)

```bash
python tools/validate_eval_cases.py --root . --cases data_processed/eval/eval_cases.jsonl --out data_processed/build_reports/eval_cases_validation.json
```

关注：
- `overall` 是否 PASS
- `warnings` 中是否出现 `missing_bucket_default`、`missing_pair_id`（建议逐步补齐后再收紧门禁）

---

## 4. Step 3 跑检索回归：run_eval_retrieval（看 buckets）

**相关文档**: [使用说明（Stage-2：检索侧回归 hit@k + 分桶回归）](../../tools/run_eval_retrieval_README.md)

```bash
# 诊断：只看向量召回（隔离 keyword 侧变量）
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 20 --retrieval-mode dense --embed-backend auto --embed-model BAAI/bge-m3 --device auto --out data_processed/build_reports/eval_retrieval_report.dense.json

# 常规：hybrid（dense + keyword；RRF 融合；用于门禁与日常回归）
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 20 --retrieval-mode hybrid --dense-topk 50 --keyword-topk 50 --fusion-method rrf --rrf-k 60 --embed-backend auto --embed-model BAAI/bge-m3 --device auto --out data_processed/build_reports/eval_retrieval_report.json
```

输出重点：
- `metrics.hit_rate`（overall）
- `buckets.oral.hit_rate`（关键）
- `cases[]` 中失败用例的 `topk[]`（定位候选窗是否缺失预期来源）

---

## 5. Step 4 读报告与定位断桥位置

定位口语断桥时，你优先回答三件事：

1) 预期来源文档是否完全没进 topK？  
- 是：优先考虑“口语→术语映射（QueryNormalizer）/ hybrid（BM25 兜底）”  
- 否：更像排序问题，可考虑 rerank

2) 是否只在 oral 桶失败而 official 桶稳定？  
- 是：问题与表达分布相关，应把 oral 指标作为触发器

3) `warnings` 是否提示 bucket 缺省或 unknown？  
- 是：先修复用例数据质量，避免误判系统退化

---

## 6. Step 5 把分桶指标接入 CI/日常回归

建议分两阶段推进：

- 阶段 A（先保证“可生成 + 可解释”）：CI 只要求报告生成成功、schema_version 正确、可计算 buckets。  
- 阶段 B（再收紧阈值）：对 `buckets.oral.hit_rate` 设置“不低于基线”的门禁；失败时输出 fail cases 列表以便定位。

当 oral 桶长期低于目标或修复收益停滞，再触发引入更高成本方案（hybrid / rerank / 引擎升级）。


补充（基线对比与 gate 闭环）：

- 当你认可某次 Stage-2 结果作为新基线时，用 `snapshot_eval_retrieval_baseline.py` 固化：
  - `python tools/snapshot_eval_retrieval_baseline.py --root . --report data_processed/build_reports/eval_retrieval_report.json --baseline-out data_processed/baselines/eval_retrieval_baseline.json`
- 日常回归/CI 用 `compare_eval_retrieval_baseline.py` 做门禁：
  - `python tools/compare_eval_retrieval_baseline.py --root . --baseline data_processed/baselines/eval_retrieval_baseline.json --report data_processed/build_reports/eval_retrieval_report.json --allowed-drop 0.0 --bucket-allowed-drop 0.0`

这一步的 `config_mismatch` 常见原因是 baseline 版本旧（例如 baseline 未记录 `retrieval_mode`）；处理方式是重新 snapshot baseline，而不是调整 GPU/CPU 设备。
