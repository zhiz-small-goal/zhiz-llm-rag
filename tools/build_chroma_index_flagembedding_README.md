---
title: build_chroma_index_flagembedding.py 使用说明（FlagEmbedding 构建 Chroma 索引）
version: v1.1
last_updated: 2026-01-22
tool_id: build_chroma_index_flagembedding

impl:
  module: mhy_ai_rag_data.tools.build_chroma_index_flagembedding
  wrapper: tools/build_chroma_index_flagembedding.py

entrypoints:
  - python tools/build_chroma_index_flagembedding.py
  - python -m mhy_ai_rag_data.tools.build_chroma_index_flagembedding

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# build_chroma_index_flagembedding.py 使用说明


> 目标：使用 FlagEmbedding (BGE-M3) 构建/更新 Chroma 向量索引，支持增量同步（incremental）、删除过期（delete-stale）等策略，并提供强一致验收（expected_chunks == collection.count）。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [依赖与前置条件](#依赖与前置条件)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [同步模式说明](#同步模式说明)
- [状态文件（manifest）](#状态文件manifest)
- [退出码](#退出码)
- [示例](#示例)
- [常见问题](#常见问题)
- [相关文档](#相关文档)

## 目的

本工具使用 FlagEmbedding (BGE-M3) 模型为 Chroma PersistentClient 构建向量索引，辅助 RAG 检索场景。核心特性：

- **支持增量构建**：基于 content_sha256 对比，只对新增/变更文档重新 embedding
- **状态管理**：维护 index_state.json manifest，记录每个文档的 doc_id、content_sha256、n_chunks
- **强一致验收**：构建后检查 `expected_chunks == collection.count()`，防止不可见错误
- **schema 版本化**：embed_model/chunk_conf/include_media_stub 变化时生成新 schema_hash，自动处理 schema 变更

## 适用场景

- 首次构建 Chroma 向量库
- 文档内容更新后增量刷新索引
- 从其他 embedding 模型迁移到 FlagEmbedding
- 需要可追溯的索引构建历史

## 依赖与前置条件

必需依赖：
- `chromadb`：向量存储
- `FlagEmbedding`：BGE-M3 embedding 模型
- 输入文件：`data_processed/text_units.jsonl`（由 `extract_units.py` 生成）

安装：
```bash
pip install -e ".[embed]"
```

## 快速开始

### 1) 首次构建（增量模式）
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks --embed-model BAAI/bge-m3 --device cpu --sync-mode incremental
```

### 2) 使用 CUDA 加速
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --embed-model BAAI/bge-m3 --device cuda --embed-batch 64
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| **输入/输出** |||
| `--root` | `.` | 项目根目录 |
| `--units` | `data_processed/text_units.jsonl` | 文本单元输入文件 |
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--collection` | `rag_chunks` | Collection 名称 |
| `--plan` | *(空)* | chunk_plan.json 路径（可选，用于 db_build_stamp 追溯） |
| **Embedding** |||
| `--embed-model` | `BAAI/bge-m3` | FlagEmbedding 模型名 |
| `--device` | `cpu` | 设备（cpu/cuda） |
| `--embed-batch` | `32` | Embedding 批大小 |
| `--upsert-batch` | `256` | Upsert 批大小 |
| **分块配置** |||
| `--chunk-chars` | `1200` | 单个 chunk 最大字符数 |
| `--overlap-chars` | `120` | 重叠字符数 |
| `--min-chunk-chars` | `200` | 最小 chunk 字符数（小于此值丢弃） |
| `--include-media-stub` | *(flag)* | 是否索引媒体 stub |
| `--hnsw-space` | `cosine` | HNSW 距离（cosine/l2/ip） |
| **同步/状态** |||
| `--sync-mode` | `incremental` | 同步模式（none/delete-stale/incremental） |
| `--state-root` | `data_processed/index_state` | 状态文件根目录 |
| `--on-missing-state` | `reset` | 状态缺失时策略（reset/fail/full-upsert） |
| `--schema-change` | `reset` | schema 变更时策略（reset/fail） |
| `--delete-batch` | `5000` | 删除操作批大小 |
| `--strict-sync` | `true` | 是否强制检查 count == expected_chunks |
| `--write-state` | `true` | 是否写入 index_state.json |
| **断点续跑/WAL** |||
| `--wal` | `on` | 是否写入进度/WAL：`index_state.stage.jsonl` |
| `--resume` | `auto` | 断点续跑（auto/off/force）：auto=按 WAL 自动续跑；off=禁用；force=无可续跑 WAL 则失败 |
| `--resume-status` | *(flag)* | 只读输出 WAL/状态概览并退出 |
| `--wal-fsync` | `off` | WAL fsync 策略（off/doc/interval） |
| `--wal-fsync-interval` | `200` | wal-fsync=interval 时，每 N 个 WAL 事件 fsync |
| `--keep-wal` | *(flag)* | 成功且写入 state 后仍保留 WAL |
| `--writer-lock` | `true` | 是否在 state dir 创建单写入者锁（writer.lock） |

## 同步模式说明

| 模式 | 说明 | 性能 | 推荐场景 |
|---|---|---|---|
| `none` | 只 upsert，不删除过期 chunk | 快 | 仅用于测试/调试 |
| `delete-stale` | 删除变更/删除文档的旧 chunks，全量 upsert | 中 | 数据集不大且需要完全重建 |
| `incremental` | 删除变更/删除文档的旧 chunks，只对新增/变更文档 embedding | 最快 ⭐ | 生产推荐（O(Δ) embedding） |

## 状态文件（manifest）

### 位置
```
data_processed/index_state/<collection>/<schema_hash>/index_state.json
data_processed/index_state/<collection>/<schema_hash>/index_state.stage.jsonl  # 进度/WAL（默认成功+写 state 后清理；可用 --keep-wal 保留）
data_processed/index_state/<collection>/LATEST
```

### 结构
```json
{
  "schema_version": 1,
  "schema_hash": "abc123...",
  "embed_model": "BAAI/bge-m3",
  "chunk_conf": {"chunk_chars": 1200, ...},
  "include_media_stub": false,
  "updated_at": "2026-01-16T00:00:00Z",
  "docs": {
    "path/to/doc1.md": {
      "doc_id": "md_abc123",
      "source_uri": "path/to/doc1.md",
      "content_sha256": "def456...",
      "n_chunks": 5,
      "updated_at": "2026-01-16T00:00:00Z"
    }
  }
}
```

## 退出码

- `0`：PASS（构建成功且通过 strict-sync 检查）
- `2`：FAIL（输入文件缺失、schema 变更策略为 fail、strict-sync 不通过等）
- `3`：ERROR（脚本异常/未捕获异常）

## 示例

### 1) 首次构建
```cmd
python tools\build_chroma_index_flagembedding.py build --root .
```

### 2) 增量更新（只处理变化的文档）
```cmd
rem 修改了某些文档后，再次运行相同命令 → 自动增量
python tools\build_chroma_index_flagembedding.py build --root .
```

### 3) 包含媒体 stub
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --include-media-stub
```

### 4) Schema 变更（切换 embedding 模型）
```cmd
rem schema_hash 会变化，自动重置 collection 后重建
python tools\build_chroma_index_flagembedding.py build --root . --embed-model BAAI/bge-large-zh-v1.5 --schema-change reset
```

## 常见问题

### 1) 报错：`FAIL (sync mismatch; expected_chunks=100 got=95)`
**原因**：增量模式下 collection 中残留了之前的 chunk IDs

**处理**：
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --on-missing-state reset
```


### 1.5) 断点续跑：写入过程中中断后如何恢复
**现象**：首次构建或大批量增量更新时，进程被中断（CTRL+C / 机器重启），希望不重复处理已成功写入的文档。

**机制**：默认 `--resume auto` 会在 `index_state.json` 同目录写入 `index_state.stage.jsonl`（JSONL 事件流）。每个文档在完成 upsert + flush 后记录 `DOC_COMMITTED`；下次启动若检测到同一 `db_path + collection + schema_hash` 的 WAL 且 collection 非空，会跳过 `content_sha256` 相同的已完成文档。

**操作**：
```cmd
rem 1) 正常运行（默认会生成 WAL）
python tools\build_chroma_index_flagembedding.py build --root . --db chroma_db --collection rag_chunks

rem 2) 中断后，直接重复执行同命令 → 自动跳过已完成文档，继续剩余部分
python tools\build_chroma_index_flagembedding.py build --root . --db chroma_db --collection rag_chunks

rem 3) 如需完全禁用 WAL（保持旧行为 / 更少 IO）
python tools\build_chroma_index_flagembedding.py build --root . --resume off
```

**注意**：
- WAL 仅在同一 schema_hash 下安全复用；embed_model/chunk_conf/include_media_stub 变化会导致 schema_hash 变化，WAL 不会用于跳过。
- WAL 依赖 collection 中已存在数据；若手动清空 DB 或切换 db_path/collection，请删除对应 WAL 文件或使用 `--resume off` 再跑一次全量。

### 2) FlagEmbedding 找不到模型
**处理**：确认模型已下载到 Hugging Face cache 或指定本地路径
```cmd
set HF_HOME=D:\models
python tools\build_chroma_index_flagembedding.py build --root .
```

### 3) 切换 chunk_conf 后报 schema 不匹配
这是预期行为。chunk_conf 变化 → schema_hash 变化 → 需要重建索引

### 4) CUDA out of memory
降低 `--embed-batch` 和 `--upsert-batch`：
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --device cuda --embed-batch 16 --upsert-batch 128
```

## 相关文档

- [tools/check_chroma_coverage_vs_units_README.md](check_chroma_coverage_vs_units_README.md) - 检查索引覆盖率
- [tools/index_state_README.md](index_state_README.md) - 状态文件管理
- [docs/reference/index_state_and_stamps.md](../docs/reference/index_state_and_stamps.md) - Index State 设计文档


---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/build_chroma_index_flagembedding.py`。推荐使用 console script `rag-*` 或 `python -m mhy_ai_rag_data.tools.build_chroma_index_flagembedding`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `build_chroma_index_flagembedding`
> entrypoints: `python tools/build_chroma_index_flagembedding.py`, `python -m mhy_ai_rag_data.tools.build_chroma_index_flagembedding`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--chunk-chars` | — | 1200 | type=int |
| `--collection` | — | 'rag_chunks' | — |
| `--db` | — | 'chroma_db' | — |
| `--delete-batch` | — | 5000 | type=int；Batch size for collection.delete(ids=...). |
| `--device` | — | 'cpu' | — |
| `--embed-batch` | — | 32 | type=int |
| `--embed-model` | — | 'BAAI/bge-m3' | — |
| `--hnsw-space` | — | 'cosine' | cosine/l2/ip (stored in collection metadata) |
| `--include-media-stub` | — | — | action=store_true；index media stubs too |
| `--keep-wal` | — | — | action=store_true；Do not delete WAL on success. |
| `--min-chunk-chars` | — | 200 | type=int |
| `--on-missing-state` | — | 'reset' | If state missing but collection is non-empty: reset collection / fail / proceed with full upsert (may keep stale). |
| `--overlap-chars` | — | 120 | type=int |
| `--plan` | — | None | Optional: chunk_plan.json path used only for db_build_stamp traceability. |
| `--resume` | — | 'auto' | Resume behavior when WAL exists: auto/off/force. |
| `--resume-status` | — | — | action=store_true；Inspect state/WAL and exit (read-only). |
| `--root` | — | '.' | Project root |
| `--root` | — | '.' | Project root |
| `--schema-change` | — | 'reset' | If schema_hash differs from LATEST pointer: reset collection (recommended) or fail. |
| `--state-root` | — | 'data_processed/index_state' | Directory to store index_state/manifest (relative to root). |
| `--strict-sync` | — | 'true' | true/false: fail if collection.count != expected_chunks after build. |
| `--sync-mode` | — | 'incremental' | Sync semantics: none/upsert-only; delete-stale=delete old per-doc then full upsert; incremental=delete old per-doc and only embed changed docs. |
| `--units` | — | 'data_processed/text_units.jsonl' | — |
| `--upsert-batch` | — | 256 | type=int |
| `--wal` | — | 'on' | Write progress WAL (index_state.stage.jsonl) during build. |
| `--wal-fsync` | — | 'off' | WAL fsync policy: off/doc/interval. |
| `--wal-fsync-interval` | — | 200 | type=int；When wal-fsync=interval, fsync every N WAL events. |
| `--write-state` | — | 'true' | true/false: write index_state.json after successful build. |
| `--writer-lock` | — | 'true' | true/false: create an exclusive writer lock in the state dir. |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
- artifacts（registry）：
  - `data_processed/index_state/<collection>/<schema_hash>/index_state.json`
  - `data_processed/index_state/db_build_stamp.json`
<!-- AUTO:END artifacts -->
