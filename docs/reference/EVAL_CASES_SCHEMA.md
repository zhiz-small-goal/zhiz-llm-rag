---
title: Stage-2 评测契约：eval_cases.jsonl 与 eval_retrieval_report.json
version: v1.1
last_updated: 2026-01-25
---

# Stage-2 评测契约：`eval_cases.jsonl` 与 `eval_retrieval_report.json`


> 适用日期：2026-01-05  
> 目标：把 Stage-2 的输入/输出定义成“可版本化契约”，支持口语 vs 官方术语的分桶回归与可解释证据落盘。

## 目录
- [1. 背景与边界](#1-背景与边界)
- [2. `eval_cases.jsonl` 行级 schema](#2-eval_casesjsonl-行级-schema)
- [3. `eval_retrieval_report.json` schema_version=2](#3-eval_retrieval_reportjson-schema_version2)
- [4. 分桶约定（bucket）](#4-分桶约定bucket)
- [5. 对照组约定（pair_id）](#5-对照组约定pair_id)
- [6. 向后兼容原则](#6-向后兼容原则)

**相关文档**：[报告输出契约与工程规则（SSOT）](REPORT_OUTPUT_ENGINEERING_RULES.md) - 所有报告工具的统一输出规范（schema_version=2, items/summary, 排序规则, loc_uri, events 等）

---

## 1. 背景与边界

Stage-2 的核心目标是：在固定索引与固定检索配置下，持续验证“检索侧候选窗”是否稳定，避免因为数据/代码/配置漂移导致 topK 漏召回。

本契约覆盖：
- 用例输入：`data_processed/eval/eval_cases.jsonl`
- 检索回归输出：`data_processed/build_reports/eval_retrieval_report.json`

不覆盖：
- 端到端 RAG（由 `run_eval_rag.py` 单独负责）
- rerank 的具体算法实现（本契约不规定 rerank 逻辑，只规定可审计字段）

---

## 2. `eval_cases.jsonl` 行级 schema

每行一个 JSON 对象。

### 2.1 必填字段（缺失应视为 FAIL）
- `id: str`：唯一标识
- `query: str`：用户查询
- `expected_sources: list[str]`：期望来源（相对 root 的路径片段；支持多个）
- `must_include: list[str]`：轻量锚点（用于端到端评测或质量门禁）

### 2.2 可选字段（建议补齐）
- `bucket: str`：`official|oral|ambiguous`
- `pair_id: str|null`：口语/术语对照组绑定
- `concept_id: str|null`：概念分组（可选）
- `tags: list[str]`：标签（可选）
- 其他自定义字段允许存在，但建议以下划线前缀标识“非契约字段”。

---

## 3. `eval_retrieval_report.json` schema_version=2

顶层字段（关键字段）：
- `schema_version: "2"`
- `timestamp: str`
- `run_meta: object`：包含 `python/platform/argv` 等可追溯信息
- `metrics: object`：overall 指标（`cases/hit_cases/hit_rate`）
- `buckets: object`：分桶指标（同上）
- `warnings: list[object]`：结构性缺省/异常提示（例如缺省 bucket、非法 bucket 被标记为 unknown）
- `cases: list[object]`：逐 case 结果明细

每条 `cases[i]`（关键字段）：
- `id/query/expected_sources/must_include`
- `bucket/pair_id/concept_id`
- `hit_at_k: bool|null`
- `topk: list[{rank,source,distance,...}]`：topK 结果。`retrieval_mode=dense` 时为 dense topK；`retrieval_mode=hybrid` 时为 dense+keyword 融合 topK（RRF）。
- `debug: object`：调试字段（可用于“dense vs hybrid”对照与失败定位）：
  - `retrieval_mode`: `dense|hybrid`
  - `dense_topk`: dense topK（截断到 k）
  - `keyword_topk`: keyword topK（截断到 k；hybrid 才有）
  - `fusion_topk`: 融合 topK（hybrid 才有）
  - `hit_at_k_dense`: dense-only 的命中结果（用于对照）
  - `fusion_method` / `rrf_k`: 融合参数
  - `expansion_trace`: 预留（当前为 null）

---

## 4. 分桶约定（bucket）

- `official`：官方术语/规范问法
- `oral`：口语化/非规范表达（重点风险面）
- `ambiguous`：歧义表达（可选，用于单独观测）

建议做法：同一个概念至少有两条用例（oral + official），以便观察“断桥是否被修复”。

---

## 5. 对照组约定（pair_id）

- `pair_id` 用于把同一概念的“口语/术语”用例绑定为一组对照数据。
- 推荐：`pair_id` 与 `concept_id` 同值（除非你想把多个口语变体绑定到一个 concept 下）。

---

## 6. 向后兼容原则

- 工具必须允许旧用例（缺省 `bucket`）继续运行，但应在报告 `warnings` 明确记录缺省行为。
- 新字段应“可空”，读取端必须容错；当你决定收紧门禁时，再把 warning 升级为 error。


---

## 7. 基线对比（baseline compare）

Stage-2 的门禁闭环通常由 `compare_eval_retrieval_baseline.py` 完成：
- baseline 固化：`snapshot_eval_retrieval_baseline.py` 将 `metrics/buckets/config` 写入 `data_processed/baselines/eval_retrieval_baseline.json`；
- 对比裁决：默认至少校验 `k` 与 `retrieval_mode` 一致；如需把 `embed_model/device/dense_pool_k/keyword_pool_k` 等也纳入一致性，可在 compare 里启用 `--strict-config`。

`config_mismatch` 常见原因是 baseline 版本旧（字段缺失或含义变更）；处理方式是更新 baseline（重新 snapshot），而不是直接放宽 `allowed-drop`。
