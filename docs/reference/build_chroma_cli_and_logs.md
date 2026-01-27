---
title: build_chroma_index_flagembedding CLI 与日志真相表（SSOT）
version: v1.1
last_updated: 2026-01-27
timezone: America/Los_Angeles
owner: zhiz
status: active
---

# build_chroma_index_flagembedding CLI 与日志真相表（SSOT）

> 目的：以源码为基线，收敛 `build_chroma_index_flagembedding.py` 的参数默认值、组合语义、`--resume-status` 字段与关键日志解释，避免 README/howto 中出现漂移。  
> 裁决：若本文与运行输出不一致，以源码为准，并在本文更新（同日修订 version）。

## 目录

- [1. CLI 参数与默认值（build 子命令）](#1-cli-参数与默认值build-子命令)
- [2. 组合语义（关键因果规则）](#2-组合语义关键因果规则)
- [3. `--resume-status` 输出字段（只读预检）](#3---resume-status-输出字段只读预检)
- [4. 关键日志与含义（含两条 WARN 与 writer lock）](#4-关键日志与含义含两条-warn-与-writer-lock)
- [5. 最小用法（Windows CMD）](#5-最小用法windows-cmd)
- [6. 与其它契约的关系（state/WAL 文件语义）](#6-与其它契约的关系statewal-文件语义)

---

## 1. CLI 参数与默认值（build 子命令）

以下列表来源于 `src/mhy_ai_rag_data/tools/build_chroma_index_flagembedding.py` 的 argparse 定义（截至 2026-01-23）。

### 基础路径
- `--root`：默认 `"."`
- `--units`：默认 `"data_processed/text_units.jsonl"`
- `--db`：默认 `"chroma_db"`
- `--collection`：默认 `"rag_chunks"`
- `--plan`：默认 `None`（仅用于 stamp/可追溯，不影响写库逻辑）

### Embedding/Chunk
- `--embed-model`：默认 `"BAAI/bge-m3"`
- `--device`：默认 `"cpu"`
- `--embed-batch`：默认 `32`
- `--upsert-batch`：默认 `256`
- `--chunk-chars`：默认 `1200`
- `--overlap-chars`：默认 `120`
- `--min-chunk-chars`：默认 `200`
- `--include-media-stub`：默认 `false`
- `--hnsw-space`：默认 `"cosine"`（写入 collection metadata）

### Sync/State
- `--sync-mode`：默认 `"incremental"`；choices：`none|delete-stale|incremental`
- `--state-root`：默认 `"data_processed/index_state"`
- `--on-missing-state`：默认 `"fail"`；choices：`reset|fail|full-upsert`（`reset` 为破坏性：delete+recreate）
- `--schema-change`：默认 `"fail"`；choices：`reset|fail`（`reset` 为破坏性：delete+recreate）
- `--delete-batch`：默认 `5000`
- `--strict-sync`：默认 `"true"`（字符串；运行时按 bool 解析）
- `--write-state`：默认 `"true"`（成功完成后写 `index_state.json`）

### WAL/Resume/Lock
- `--wal`：默认 `"on"`；choices：`on|off`
- `--resume`：默认 `"auto"`；choices：`auto|off|force`
- `--resume-status`：默认 `false`（只读预检并退出）
- `--wal-fsync`：默认 `"off"`；choices：`off|doc|interval`
- `--wal-fsync-interval`：默认 `200`
- `--keep-wal`：默认 `false`（成功后保留 WAL）
- `--writer-lock`：默认 `"true"`（创建 `writer.lock` 互斥锁）

---

## 2. 组合语义（关键因果规则）

1) **`--resume-status` 只读**：不会加载 embedding 模型，不写入 collection，不写 WAL，不创建 writer lock；用于低成本预检。  
   - 注意：`schema_hash` 由 `embed_model/chunk_conf/include_media_stub` 等口径参数计算；`--resume-status` 也会基于“当前命令行参数”计算 `schema_hash`。若你漏带 `--include-media-stub`（默认 false），就会得到不同 `schema_hash`，可能触发 `[FATAL] [SCHEMA] LATEST != current`。  
2) **State 缺失 + collection 非空**：会打印一条“默认评估”WARN：`index_state missing ... policy=<on-missing-state>`。  
3) **WAL 可续跑覆盖 reset**：若 WAL 表示可续跑（`resume_active=true`），会追加第二条 WARN：`WAL indicates resumable progress; ignore on-missing-state=reset and continue with resume.`，并进入 resume 路径。  
4) **resume=force**：若无可续跑 WAL，则直接 FATAL 退出。  
5) **writer lock exists**：若 `--wal=on` 且 `--writer-lock=true`，会在 state_dir 下创建互斥锁；若锁已存在则 FATAL，避免并发写入/WAL 交叉污染。  
6) **strict-sync=true 的验收语义**：build 结束后要求 `collection.count == expected_chunks`，否则以 FAIL 退出（用于阻止 silent drift）。

---

## 3. `--resume-status` 输出字段（只读预检）

输出以“键=值”形式逐行打印，字段含义如下：

- `db_path`：Chroma DB 目录（posix 形式用于稳定展示）
- `collection`：目标 collection 名
- `schema_hash`：构建口径指纹（用于定位 state/WAL 路径）
- `collection_count`：当前 collection.count
- `state_file` + `state_present`：完成态 `index_state.json` 路径与是否存在
- `wal_path` + `wal_present` + `wal_on`：WAL 路径、是否存在、wal 开关
- `wal_run_id`：WAL 记录的 run_id
- `wal_finished_ok`：WAL 是否已标记成功完成
- `wal_last_event`：WAL 最后一条事件类型
- `wal_truncated_tail_ignored`：是否检测到末尾截断并忽略（审计字段）
- `wal_docs_committed`：WAL 中已 committed 的 doc 数
- `wal_committed_batches`：累计 committed 批次数
- `wal_upsert_rows_committed_total`：累计 committed 的 upsert 行数
- `resume_mode`：用户意图（auto/off/force）
- `resume_active`：最终生效决策（是否进入 resume）

---

## 4. 关键日志与含义（含两条 WARN 与 writer lock）

### 4.1 State 缺失但库非空（默认评估）
- 日志：`[WARN] index_state missing but collection.count=... policy=reset`
- 含义：这是在“无法定位多余 ids”的前提下，对 `--on-missing-state` 的默认分支评估；不是最终决策。

### 4.2 WAL 覆盖 reset（最终生效）
- 日志：`[WARN] WAL indicates resumable progress; ignore on-missing-state=reset and continue with resume.`
- 含义：WAL 表示存在可恢复进度，因此最终决策进入 resume；此时不会执行 reset（避免重复写入与无谓重置）。

### 4.3 writer lock exists（互斥保护）
- 日志：`[FATAL] writer lock exists: .../writer.lock`
- 含义：检测到 state_dir 互斥锁；常见原因是上次中断遗留锁文件或并发运行。推荐先 `--resume-status` 读取 WAL/状态，再按 runbook 处置。

---

## 5. 最小用法（Windows CMD）

只读预检（推荐作为 runbook 第一步）：
```cmd
rem 注意：要检查“哪套索引口径”，就要带上同口径参数（尤其 --include-media-stub）
rem Scheme B（include_media_stub=true）：
python tools\build_chroma_index_flagembedding.py build --collection rag_chunks --resume-status --include-media-stub

rem 文本-only（include_media_stub=false，默认）：
python tools\build_chroma_index_flagembedding.py build --collection rag_chunks --resume-status
```

正常 build（示例：默认增量 + WAL）：
```cmd
python tools\build_chroma_index_flagembedding.py build --collection rag_chunks --sync-mode incremental --wal on --resume auto
```

显式禁用 resume（即便 WAL 存在也不续跑）：
```cmd
python tools\build_chroma_index_flagembedding.py build --collection rag_chunks --resume off
```

---

## 6. 与其它契约的关系（state/WAL 文件语义）

- 文件语义与路径：`docs/reference/index_state_and_stamps.md`  
- 术语定义：`docs/reference/GLOSSARY_WAL_RESUME.md`  
- 文档层级与裁决规则：`docs/reference/DOC_SYSTEM_SSOT.md`
