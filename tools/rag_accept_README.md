---
title: rag_accept.py 使用说明（RAG 一键验收工具）
version: v1.0
last_updated: 2026-01-16
tool_id: rag_accept

impl:
  module: mhy_ai_rag_data.tools.rag_accept
  wrapper: tools/rag_accept.py

entrypoints:
  - python tools/rag_accept.py
  - python -m mhy_ai_rag_data.tools.rag_accept

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# rag_accept.py 使用说明


> 目标：一键验收入口，默认跑核心序列（stamp → check → snapshot → rag-status --strict），可选开启 verify/Stage-2 评测。

## 快速开始

```cmd
python tools\rag_accept.py --root .
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | *(auto)* | 项目根目录 |
| `--profile` | *(auto)* | 构建 profile JSON |
| `--verify-stage1` | *(flag)* | 运行 verify_stage1_pipeline |
| `--stage2` | *(flag)* | 运行 Stage-2 检索评测 |
| `--stage2-full` | *(flag)* | 运行 Stage-2 检索+RAG 评测（需 LLM）|

## 退出码

- `0`：PASS
- `2`：FAIL
- `3`：ERROR

## 示例

```cmd
rem 基础验收
python tools\rag_accept.py --root .

rem 包含 Stage-1 验证
python tools\rag_accept.py --root . --verify-stage1

rem 完整验收（含 Stage-2）
python tools\rag_accept.py --root . --verify-stage1 --stage2-full
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/rag_accept.py`。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--base-url` | — | 'http://localhost:8000/v1' | OpenAI-compatible base URL |
| `--cases` | — | None | eval cases jsonl (override default) |
| `--collection` | — | None | collection name (override profile/default) |
| `--connect-timeout` | — | 10.0 | type=float；HTTP connect timeout seconds |
| `--context-max-chars` | — | 12000 | type=int；max context chars for rag eval |
| `--db` | — | None | chroma db path (override profile/default) |
| `--device` | — | None | cpu\|cuda:0 |
| `--embed-backend` | — | None | auto\|flagembedding\|sentence-transformers |
| `--embed-model` | — | None | embed model name |
| `--k` | — | 5 | type=int；topK for eval (Stage-2) |
| `--llm-model` | — | 'auto' | LLM model id; default auto: run-time resolve via GET /models |
| `--max-tokens` | — | 256 | type=int；max tokens for rag eval |
| `--plan` | — | None | chunk_plan.json path (override profile/default) |
| `--profile` | — | None | build profile json (optional) |
| `--reports-dir` | — | None | build_reports dir (override profile/default) |
| `--root` | — | None | project root (auto-detect if omitted) |
| `--stage2` | — | — | action=store_true；run Stage-2 retrieval eval (stable default) |
| `--stage2-full` | — | — | action=store_true；run Stage-2 retrieval + RAG eval (requires LLM) |
| `--state-root` | — | None | index_state root (override profile/default) |
| `--temperature` | — | 0.0 | type=float；temperature for rag eval |
| `--timeout` | — | 300.0 | type=float；HTTP read timeout seconds |
| `--trust-env` | — | 'auto' | trust env proxies |
| `--verify-llm` | — | — | action=store_true；enable LLM probe in verify_stage1_pipeline |
| `--verify-stage1` | — | — | action=store_true；run verify_stage1_pipeline |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
