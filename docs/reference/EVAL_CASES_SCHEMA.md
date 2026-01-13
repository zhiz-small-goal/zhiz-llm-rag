---
title: Stage-2 评测契约：eval_cases.jsonl 与 eval_retrieval_report.json
version: v1.0
last_updated: 2026-01-13
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

---

## 1. 背景与边界

Stage-2 的核心目标是：在固定索引与固定检索配置下，持续验证“检索侧候选窗”是否稳定，避免因为数据/代码/配置漂移导致 topK 漏召回。

本契约覆盖：
- 用例输入：`data_processed/eval/eval_cases.jsonl`
- 检索回归输出：`data_processed/build_reports/eval_retrieval_report.json`

不覆盖：
- 端到端 RAG（由 `run_eval_rag.py` 单独负责）
- rerank / hybrid 的具体算法实现（这里只预留字段占位）

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
- `topk: list[{rank,source,distance}]`：dense-only topK 结果（当前实现）
- `debug: object`：调试占位（`dense_topk/keyword_topk/fusion_topk/expansion_trace`）

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
