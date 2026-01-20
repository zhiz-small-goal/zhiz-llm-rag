---
title: Index State 与 Stamps 契约
version: v1.1
last_updated: 2026-01-18
---

# Index State 与 Stamps 契约


> 目的：把“增量同步状态（index_state）”与“写库完成戳（stamps）”写成可核验契约，避免把 DB 目录 mtime 当成上游输入，从而降低 `rag-status` 的误报与漂移。

## 目录
- [Index State 与 Stamps 契约](#index-state-与-stamps-契约)
  - [目录](#目录)
  - [1) 产物清单与职责边界](#1-产物清单与职责边界)
  - [2) db_build_stamp.json（写库完成戳）](#2-db_build_stampjson写库完成戳)
  - [3) index_state（增量同步状态）](#3-index_state增量同步状态)
  - [4) 与 rag-status / rag-check 的依赖关系](#4-与-rag-status--rag-check-的依赖关系)
  - [5) 迁移与兼容策略](#5-迁移与兼容策略)
  - [6) 原子写与并发约束](#6-原子写与并发约束)

---

## 1) 产物清单与职责边界

本仓库把“DB 的语义变化”拆成两个层面：

- **语义输入（plan）**：`data_processed/chunk_plan.json`
  - 定义：同参数（chunk_conf / include_media_stub 等）下，预计写入的 `planned_chunks` 与 type breakdown。
  - 规则：任何参数变化都必须重新生成 plan，并以该 plan 驱动 check。

- **语义写入（stamp）**：`data_processed/index_state/db_build_stamp.json`
  - 定义：仅在 build/upsert/sync 等“写库成功”后更新的稳定信号。
  - 规则：query/eval/retriever 等“读库行为”不应更新该文件。
  - 报告契约：**该文件为“状态元数据报告”**，遵循 `schema_version=2` 报告契约（见 `src/mhy_ai_rag_data/tools/report_contract.py`）。

- **增量状态（index_state）**：`data_processed/index_state/<collection>/<schema_hash>/index_state.json`（以及 `LATEST` 指针）
  - 定义：用于增量同步（manifest / schema hash / 已处理 doc_id / source_uri 等）的状态记录。
  - 规则：属于实现细节，但可用于复盘“为什么某次只处理了增量”。
  - 报告契约：**该文件同样为“状态元数据报告”**，遵循 `schema_version=2` 报告契约。

---

## 2) db_build_stamp.json（写库完成戳）

### 2.1 位置（path）
- 固定路径：`data_processed/index_state/db_build_stamp.json`

### 2.2 生成时机（producer）
- 必须在 **build/upsert/sync 成功并完成落盘** 后写入。
- 失败/中断时不得写入（否则会把失败态伪装成最新）。

### 2.3 字段（schema 最小集合）

`db_build_stamp.json` 是一个 `schema_version=2` 的**报告对象**：顶层必须包含 `schema_version/generated_at/tool/root/summary/items`；同时允许附加“状态字段”（例如 db/collection/plan 快照），供消费者读取。

示例（字段精简，实际输出允许更多扩展字段）：

```json
{
  "schema_version": 2,
  "generated_at": "2026-01-18T10:00:00Z",
  "tool": "db_build_stamp",
  "root": "D:/repo/zhiz-llm-rag",
  "summary": {
    "overall_status_label": "PASS",
    "overall_rc": 0,
    "max_severity_level": 2,
    "counts": {"PASS": 1, "WARN": 1},
    "total_items": 2
  },
  "items": [
    {
      "tool": "db_build_stamp",
      "title": "db_build_stamp written",
      "status_label": "PASS",
      "severity_level": 0,
      "message": "wrote D:/repo/zhiz-llm-rag/data_processed/index_state/db_build_stamp.json (collection=rag_chunks)",
      "detail": {"collection": "rag_chunks", "schema_hash": "..."}
    }
  ],

  "updated_at": "2026-01-18T18:00:00+0800",
  "writer": "manual|build|sync",
  "db": "D:/repo/zhiz-llm-rag/chroma_db",
  "collection": "rag_chunks",
  "schema_hash": "optional",
  "collection_count": 3693,
  "count_error": null,
  "plan": {
    "path": "D:/repo/zhiz-llm-rag/data_processed/chunk_plan.json",
    "sha256": "hex...",
    "planned_chunks": 3693,
    "read_error": null
  },
  "note": "Updated only by successful write-to-db operations (build/upsert/sync) or explicit manual stamp."
}
```

字段解释（要点）：
- `generated_at/tool/root/summary/items`：统一报告契约；用于 `verify_report_output_contract`、统一渲染与排序。
- `updated_at`：写入时间（本地时区 ISO 字符串），用于人类阅读与粗略排序（保留 legacy 习惯）。
- `writer`：写入者标签（例如 `manual`/`build_*`/`sync_*`），用于追溯是谁更新了 stamp。
- `db/collection`：绑定具体库与 collection，避免多库场景误用。
- `collection_count/count_error`：可选 DB count 快照与错误原因（若读取失败会记录 error）。
- `plan.path/plan.sha256/plan.planned_chunks`：把 plan 绑定进 stamp，防止“换 plan 但 stamp 还旧”；其中 `sha256` 便于离线审计，`planned_chunks` 便于快速对齐 expected。

### 2.4 读取语义（consumer）
- `rag-status` 应以 stamp 作为 DB 的“freshness basis”，而不是 DB 目录 mtime。
- `rag-check` 若用于“新旧判定”，应以 `plan + stamp` 作为上游输入。

---

## 3) index_state（增量同步状态）

### 3.1 位置（path）
- 根目录：`data_processed/index_state/`
- 典型结构（示意）：`data_processed/index_state/<collection>/<schema_hash>/index_state.json`
- 指针：`data_processed/index_state/<collection>/LATEST`

### 3.2 生成时机（producer）
- 仅在启用增量同步模式的 build/sync 时更新。
- schema 变化（embed_model/chunk_conf/include_media_stub）通常会触发 schema_hash 变化（建议视为“新索引版本”）。

### 3.3 字段（最小集合）

`index_state.json` 是一个 `schema_version=2` 的**状态元数据报告**：
- 顶层具备 v2 报告 envelope 字段（用于统一渲染/验收）。
- 同时携带实现态字段：`schema_hash/docs/last_build/...`（用于增量同步与复盘）。

建议消费者读取的关键字段：
- `schema_hash`：chunk_conf/include_media_stub/embed_model 的稳定指纹。
- `docs`：以 `source_uri` 为 key 的 manifest（`doc_id/content_sha256/n_chunks/...`）。
- `last_build`：本轮 build 的计数与模式（sync_mode / expected_chunks / collection_count 等）。

---

## 4) 与 rag-status / rag-check 的依赖关系

### 4.1 rag-check（强校验）
- 输入：`chunk_plan.json` + DB（count）
- 输出：`data_processed/build_reports/check.json`
- 核心不变量：`collection.count == planned_chunks`

### 4.2 rag-status（进度自检）
- 目标：对“关键产物是否齐全、是否需要下一步行动”给出稳定导航。
- 规则（与本契约绑定）：
  - DB 的新旧：比较 `chunk_plan.json.mtime` 与 `db_build_stamp.json.mtime`。
  - check 的新旧：比较 `check.json.mtime` 与 `max(chunk_plan.json.mtime, db_build_stamp.json.mtime)`。
  - 当 stamp 缺失：提示“需要补写构建戳”，并给出 `rag-stamp`/脚本命令。

---

## 5) 迁移与兼容策略

### 5.1 旧库（缺 stamp）
- 一次性补写（写出的文件为 `schema_version=2`）：
  - `rag-stamp --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json`
  - 或 `python tools/write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json`
- 补写后建议重跑一次 `rag-check`，生成与 stamp 同步的新 check 报告。

### 5.2 多库/多 collection
- 建议为每个库/collection 独立维护 stamp（字段中应写入 db/collection）。
- `rag-status` 在读取配置/参数时，应避免把 A 库的 stamp 用到 B 库。

---

## 6) 原子写与并发约束

- **原子写**：写 stamp/状态文件时，先写临时文件（`.tmp`），再用原子替换（rename/replace），避免中断导致半写 JSON。
- **单写入者**：同一时刻不应有两个 build 作业写入同一 `db + collection + index_state`，否则状态会互相覆盖并导致不可复核。
