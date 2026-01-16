---
title: write_db_build_stamp.py 使用说明（写入数据库构建戳）
version: v1.0
last_updated: 2026-01-16
---

# write_db_build_stamp.py 使用说明

> 目标：写入 db_build_stamp.json，记录数据库构建时间戳和元数据，为 rag-status 提供稳定的 freshness 判定基础。

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
