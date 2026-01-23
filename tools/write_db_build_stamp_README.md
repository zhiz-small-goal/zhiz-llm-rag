---
title: write_db_build_stamp.py 使用说明（写入数据库构建戳）
version: v1.0
last_updated: 2026-01-16
tool_id: write_db_build_stamp

impl:
  module: mhy_ai_rag_data.tools.write_db_build_stamp
  wrapper: tools/write_db_build_stamp.py

entrypoints:
  - python tools/write_db_build_stamp.py
  - python -m mhy_ai_rag_data.tools.write_db_build_stamp

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
owner: "zhiz"
status: "active"
---
# write_db_build_stamp.py 使用说明



## 目录

- [SSOT 与口径入口](#ssot-与口径入口)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [示例](#示例)
- [输出](#输出)
- [自动生成区块（AUTO）](#自动生成区块auto)

> 目标：写入 db_build_stamp.json，记录数据库构建时间戳和元数据，为 rag-status 提供稳定的 freshness 判定基础。


## SSOT 与口径入口

- **文档体系 SSOT**：`docs/reference/DOC_SYSTEM_SSOT.md`
- **WAL/续跑术语表**：`docs/reference/GLOSSARY_WAL_RESUME.md`
- **build CLI/日志真相表**：`docs/reference/build_chroma_cli_and_logs.md`

> 约束：本文仅保留“怎么做/怎么排障”的最短路径；参数默认值与字段解释以真相表为准。

## 快速开始

```cmd
python tools\write_db_build_stamp.py --root . --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --writer manual
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--db` | `chroma_db` | Chroma DB 目录 |
| `--collection` | `rag_chunks` | Collection 名称 |
| `--state-root` | `data_processed/index_state` | State 根目录 |
| `--plan` | `data_processed/chunk_plan.json` | chunk_plan.json 路径 |
| `--writer` | `manual` | 写入者标识 |
| `--count` | *(空)* | 可选：覆盖 collection_count（跳过打开 chroma）|
| `--out` | *(空)* | 输出路径（默认：`<state-root>/db_build_stamp.json`）|

## 退出码

- `0`：PASS
- `2`：FAIL

## 示例

```cmd
rem 手动补写构建戳
python tools\write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --writer manual
```

## 输出

写入到：`data_processed\index_state\db_build_stamp.json`

```json
{
  "collection": "rag_chunks",
  "collection_count": 2340,
  "schema_hash": "abc123...",
  "updated_at": "2026-01-16T00:00:00Z",
  "writer": "manual"
}
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/write_db_build_stamp.py`。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--collection` | — | 'rag_chunks' | — |
| `--collection-count` | — | None | optional: provide collection.count snapshot to avoid opening Chroma (int) |
| `--db` | — | 'chroma_db' | — |
| `--out` | — | None | output path (default: <state_root>/db_build_stamp.json) |
| `--plan` | — | None | — |
| `--root` | — | '.' | — |
| `--schema-hash` | — | None | — |
| `--state-root` | — | 'data_processed/index_state' | — |
| `--writer` | — | 'manual' | — |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
- artifacts（registry）：
  - `data_processed/index_state/db_build_stamp.json`
<!-- AUTO:END artifacts -->
