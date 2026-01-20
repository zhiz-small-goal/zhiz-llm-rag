---
title: "`suggest_eval_case.py` 使用说明（半自动生成 eval case：expected_sources + must_include + bucket/pair_id）"
version: v1.0
last_updated: 2026-01-20
tool_id: suggest_eval_case

impl:
  module: mhy_ai_rag_data.tools.suggest_eval_case
  wrapper: tools/suggest_eval_case.py

entrypoints:
  - python tools/suggest_eval_case.py
  - python -m mhy_ai_rag_data.tools.suggest_eval_case

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# `suggest_eval_case.py` 使用说明（半自动生成 eval case：expected_sources + must_include + bucket/pair_id）


> **适用日期**：2026-01-05  
> **脚本位置建议**：`tools/suggest_eval_case.py`  
> **权威实现**：`src/mhy_ai_rag_data/tools/suggest_eval_case.py`

## 目录
- [1. 为什么需要它](#1-为什么需要它)
- [2. 典型用法](#2-典型用法)
- [3. 输出 JSON 字段说明](#3-输出-json-字段说明)
- [4. 关键参数说明（新增 bucket/pair-id/concept-id）](#4-关键参数说明新增-bucketpair-idconcept-id)
- [5. 追加到 eval_cases.jsonl](#5-追加到-eval_casesjsonl)

---

## 1. 为什么需要它

当你对资料内容不熟时，手工写 `eval_cases.jsonl` 常见两个难点：

1) **expected_sources 不好选**：你不知道这条问题应该绑定哪篇文档/哪段排障记录。  
2) **must_include 不好定**：你不知道答案应出现哪些“稳定锚点”，容易写成泛词、同义词或“答案里可能不会出现”的词，导致评测误判。

该工具把这两件事改成“先让检索给你证据，再从证据里抽锚点”，并且允许你为用例附加 `bucket/pair_id`，用于后续“口语 vs 术语”的分桶回归。

---

## 2. 典型用法

仅打印建议的 JSON（不写文件）：

```bash
python tools/suggest_eval_case.py --root . --query "如何检查 Chroma 向量库是否构建完整？" --k 5
```

为“口语桶”生成用例（同时写入文件）：

```bash
python tools/suggest_eval_case.py --root . --query "如何设定地图边界？" --bucket oral --pair-id map_boundary --concept-id map_boundary --append-to data_processed/eval/eval_cases.jsonl
```

---

## 3. 输出 JSON 字段说明

输出对象可直接粘贴到 `eval_cases.jsonl`（每行一个 JSON）：

- `id/query/expected_sources/must_include/tags`：原有字段
- `bucket`: `official|oral|ambiguous`（新增）
- `pair_id`: 绑定口语/术语对照组（新增，推荐）
- `concept_id`: 概念分组（新增，可选）
- `_suggest_meta`: 本次建议生成的证据（topK 来源与距离等），便于人工审查与追溯

---

## 4. 关键参数说明（新增 bucket/pair-id/concept-id）

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--bucket` | `official` | 用例分桶：`official/oral/ambiguous` |
| `--pair-id` | 空 | 绑定口语/术语对照组（推荐同概念两条用例用同一 pair-id） |
| `--concept-id` | 空 | 概念分组 ID（可选） |

---

## 5. 追加到 eval_cases.jsonl

```bash
python tools/suggest_eval_case.py --root . --query "..." --append-to data_processed/eval/eval_cases.jsonl
```

建议你在追加后立刻跑一次：

```bash
python tools/validate_eval_cases.py --root . --cases data_processed/eval/eval_cases.jsonl
```

确保 bucket/pair_id 等字段可被稳定消费。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--append-to` | — | '' | append suggested case to an existing jsonl file (optional) |
| `--bucket` | — | 'official' | case bucket: official/oral/ambiguous |
| `--collection` | — | 'rag_chunks' | chroma collection name |
| `--concept-id` | — | '' | concept grouping id (optional) |
| `--db` | — | 'chroma_db' | chroma db directory relative to root |
| `--device` | — | 'cpu' | embedding device: cpu/cuda (backend dependent) |
| `--embed-backend` | — | 'auto' | embedding backend |
| `--embed-model` | — | 'BAAI/bge-m3' | embedding model name (should match index) |
| `--k` | — | 5 | type=int；topK for retrieval |
| `--max-terms` | — | 8 | type=int；max must_include candidates |
| `--meta-field` | — | 'source_uri\|source\|path\|file' | metadata source field priority, separated by \| |
| `--out` | — | '' | write the suggested case json to this path (optional) |
| `--pair-id` | — | '' | bind oral vs official variants (optional, recommended) |
| `--pick-sources` | — | 2 | type=int；how many top sources to include into expected_sources |
| `--query` | true | — | user query to build eval case |
| `--root` | — | '.' | project root |
| `--tags` | — | 'suggested' | comma separated tags |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
