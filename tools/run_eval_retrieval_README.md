---
title: "`run_eval_retrieval.py` 使用说明（Stage-2：检索侧回归 hit@k + 分桶回归）"
version: v1.0
last_updated: 2026-01-20
tool_id: run_eval_retrieval

impl:
  module: mhy_ai_rag_data.tools.run_eval_retrieval
  wrapper: tools/run_eval_retrieval.py

entrypoints:
  - python tools/run_eval_retrieval.py
  - python -m mhy_ai_rag_data.tools.run_eval_retrieval

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# `run_eval_retrieval.py` 使用说明（Stage-2：检索侧回归 hit@k + 分桶回归）


> **适用日期**：2026-01-05  
> **脚本位置建议**：`tools/run_eval_retrieval.py`（根目录 wrapper）  
> **权威实现**：`src/mhy_ai_rag_data/tools/run_eval_retrieval.py`  
> **输出位置**：默认写入 `data_processed/build_reports/eval_retrieval_report.json`

## 目录
- [`run_eval_retrieval.py` 使用说明（Stage-2：检索侧回归 hit@k + 分桶回归）](#run_eval_retrievalpy-使用说明stage-2检索侧回归-hitk--分桶回归)
  - [目录](#目录)
  - [1. 目的与适用场景](#1-目的与适用场景)
  - [2. 输入：eval_cases.jsonl（新增 bucket/pair_id 概念）](#2-输入eval_casesjsonl新增-bucketpair_id-概念)
  - [3. 用法（命令行）](#3-用法命令行)
  - [4. 输出：eval_retrieval_report.json（schema_version=2）](#4-输出eval_retrieval_reportjsonschema_version2)
  - [5. 指标解读（overall + buckets）](#5-指标解读overall--buckets)
  - [6. 退出码与常见故障](#6-退出码与常见故障)
  - [7. 实时观测（stream/progress）](#7-实时观测streamprogress)
    - [7.1 开启流式事件输出（JSONL / json-seq）](#71-开启流式事件输出jsonl--json-seq)
    - [7.2 Windows 下实时观察（PowerShell / CMD）](#72-windows-下实时观察powershell--cmd)
    - [7.3 控制台节流进度（不刷屏）](#73-控制台节流进度不刷屏)
    - [7.4 事件记录类型（简述）](#74-事件记录类型简述)

---

## 1. 目的与适用场景

该脚本只评估“检索侧”是否稳定：对每条评测 query 执行 **embedding → Chroma topK 查询**，判断 topK 的来源是否命中 `expected_sources`。

它用于回答两类问题：

- **召回是否退化？**（overall hit@k 是否下降）
- **口语 vs 官方术语**的回归是否改善？（`buckets.oral` 的 hit@k 是否改善/是否退化）
- 退化发生在“检索层”还是“生成层”？（如果检索 hit 稳定但端到端不稳，问题更多在 LLM/prompt/context）

---

## 2. 输入：eval_cases.jsonl（新增 bucket/pair_id 概念）

每行一个 JSON 对象（JSONL），既兼容旧格式，也支持新增字段：

**必填字段（保持不变）**
- `id`: 用例唯一标识（字符串）
- `query`: 用户问题
- `expected_sources`: 期望命中文档路径片段（相对 root；支持多个）
- `must_include`: 生成答案应包含的关键词/短语（用于轻量断言；本脚本不使用，但 `validate_eval_cases.py` 会校验）
- `tags`: 标签（可选）

**新增可选字段（用于“口语 vs 术语断桥”分桶回归）**
- `bucket`: `official|oral|ambiguous`；缺省会被视为 `official`（同时在报告 `warnings` 里记录缺省行为）
- `pair_id`: 绑定口语/术语的“同概念对照组”（建议 oral 与 official 用同一个 pair_id）
- `concept_id`: 概念分组 ID（可选）

示例（推荐写法）：
```json
{"id":"map_boundary_oral","bucket":"oral","pair_id":"map_boundary","concept_id":"map_boundary","query":"如何设定地图边界？","expected_sources":["data_raw/.../xx.md"],"must_include":["..."],"tags":["retrieval","oral"]}
{"id":"map_boundary_official","bucket":"official","pair_id":"map_boundary","concept_id":"map_boundary","query":"如何设置场景生效范围？","expected_sources":["data_raw/.../xx.md"],"must_include":["..."],"tags":["retrieval","official"]}
```

---

## 3. 用法（命令行）

```bash
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 20 --embed-backend auto --embed-model BAAI/bge-m3 --device cpu --out data_processed/build_reports/eval_retrieval_report.json
```

---

## 4. 输出：eval_retrieval_report.json（schema_version=2）

输出文件包含：

- `schema_version`: `"2"`（用于区分旧报告格式）
- `metrics`: overall 指标（cases/hit_cases/hit_rate），与旧版兼容
- `buckets`: 分桶指标（按 `bucket` 聚合）
- `warnings`: 缺省 bucket、非法 bucket 等结构性问题的提示（建议在 CI 里先做“可生成 + 可读”，再逐步收紧门禁）
- `cases[]`: 每条用例结果（保留旧字段，并新增 bucket/pair_id/concept_id/must_include）
- `cases[].debug`: 预留调试结构（dense/keyword/fusion/expansion_trace 占位），为后续引入 QueryNormalizer / Hybrid / RRF 做契约铺垫

---

## 5. 指标解读（overall + buckets）

- `metrics.hit_rate`：overall 命中率（hit_cases / cases）
- `buckets.oral.hit_rate`：口语桶命中率（重点观察）
- `buckets.official.hit_rate`：术语桶命中率（通常更稳定）
- 若 `buckets.oral` 退化而 overall 不退化，说明整体指标被 official 桶“稀释”，此时应以 oral 桶为准推进修复。

---

## 6. 退出码与常见故障

- `0`：成功完成并写出报告
- `2`：cases/db 缺失、chromadb/embedding 初始化失败等

常见问题：

1) `embedder init failed`  
- 原因：未安装 FlagEmbedding / sentence_transformers，或模型名不可用  
- 处理：按仓库依赖说明安装；确保 `--embed-model` 与索引构建一致

2) `chromadb import failed`  
- 原因：未安装 `chromadb`  
- 处理：安装最小 rag 依赖或使用项目提供的 venv/requirements

---

## 7. 实时观测（events/progress）

> 背景：最终报告 `eval_retrieval_report.json` 依旧在跑完整个用例集后一次性写出；为缩短反馈环路，可开启 **items 事件流** 与 **控制台进度** 两类旁路信号。

### 7.1 开启 items 事件流（JSONL）

```bash
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 5   --out data_processed/build_reports/eval_retrieval_report.json   --events-out data_processed/build_reports/eval_retrieval_report.events.jsonl   --progress on --progress-min-interval-ms 500
```

说明：
- `--events-out` 写出 JSONL（每行一个 v2 `item`），用于实时查看与中断后重放。
- `--progress` 输出到 stderr；`--progress-min-interval-ms` 用于节流。

### 7.2 Windows 下实时观察（PowerShell）

```powershell
Get-Content -Path data_processeduild_reports\eval_retrieval_report.events.jsonl -Wait
```

### 7.3 事件记录语义（简述）

events 文件每行是一个“report v2 item”（同最终报告的 `items[]` 结构）；字段解释见：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md` 的 items 章节，以及 `src/mhy_ai_rag_data/tools/report_events.py` 的模块注释。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--cases` | — | 'data_processed/eval/eval_cases.jsonl' | eval cases jsonl (relative to root) |
| `--collection` | — | 'rag_chunks' | collection name |
| `--db` | — | 'chroma_db' | chroma db dir (relative to root) |
| `--dense-topk` | — | 0 | type=int；dense candidate pool for fusion; 0 means use --k |
| `--device` | — | 'cpu' | cpu\|cuda |
| `--embed-backend` | — | 'auto' | auto\|flagembedding\|sentence-transformers |
| `--embed-model` | — | 'BAAI/bge-m3' | embed model name |
| `--events-out` | — | 'auto' | item events output (jsonl): auto\|off\|<path> (relative to root). Used for recovery/rebuild. |
| `--fusion-method` | — | 'rrf' | fusion method for hybrid retrieval (currently: rrf) |
| `--k` | — | 5 | type=int；topK for retrieval |
| `--keyword-topk` | — | 0 | type=int；keyword candidate pool for fusion; 0 means use --k |
| `--md-out` | — | '' | optional report.md path (relative to root); default: <out>.md |
| `--meta-field` | — | 'source_uri\|source\|path\|file' | metadata field(s) for source path (use \| to separate) |
| `--out` | — | 'data_processed/build_reports/eval_retrieval_report.json' | output json (relative to root) |
| `--progress` | — | 'auto' | runtime progress feedback to stderr: auto\|on\|off |
| `--progress-min-interval-ms` | — | 200 | type=int；min progress update interval in ms (throttling) |
| `--retrieval-mode` | — | 'hybrid' | retrieval strategy: dense\|hybrid (dense + keyword via RRF) |
| `--root` | — | '.' | project root |
| `--rrf-k` | — | 60 | type=int；RRF k parameter (rank bias) |
| `--skip-if-missing` | — | — | action=store_true；if inputs/deps missing, emit WARN and exit 0 (for gate integration) |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
