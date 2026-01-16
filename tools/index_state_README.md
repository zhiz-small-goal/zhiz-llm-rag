---
title: index_state.py 使用说明（索引状态管理模块）
version: v1.0
last_updated: 2026-01-16
---

# index_state.py 使用说明


> 目标：为增量构建 + 强一致验收提供最小状态文件（manifest）管理，记录每个文档的 doc_id、content_sha256、n_chunks，支持新增/变更/删除判定。

## 目的

本模块是工具库模块（非命令行工具），提供：

- **schema_hash 计算**：embed_model/chunk_conf/include_media_stub 变化时生成新hash
- **状态文件读写**：index_state.json 原子写入
- **LATEST 指针管理**：跟踪最新 schema_hash

## 主要API

### 1) compute_schema_hash
```python
from mhy_ai_rag_data.tools.index_state import compute_schema_hash

schema_hash = compute_schema_hash(
    embed_model="BAAI/bge-m3",
    chunk_conf={"chunk_chars": 1200, "overlap_chars": 120, "min_chunk_chars": 200},
    include_media_stub=True,
    id_strategy_version=1
)
```

### 2) load_index_state / save_json_atomic
```python
from mhy_ai_rag_data.tools.index_state import load_index_state, save_json_atomic

state = load_index_state(state_file)
if state is None:
    # 首次构建
    pass

# 更新后保存
save_json_atomic(state_file, new_state)
```

### 3) read_latest_pointer /write_latest_pointer
```python
from mhy_ai_rag_data.tools.index_state import read_latest_pointer, write_latest_pointer

latest = read_latest_pointer(state_root, collection)
write_latest_pointer(state_root, collection, schema_hash)
```

## 状态文件结构

```json
{
  "schema_version": 1,
  "schema_hash": "abc123...",
  "embed_model": "BAAI/bge-m3",
  "chunk_conf": {...},
  "include_media_stub": false,
  "updated_at": "2026-01-16T00:00:00Z",
  "docs": {
    "path/to/doc.md": {
      "doc_id": "md_abc123",
      "source_uri": "path/to/doc.md",
      "content_sha256": "def456...",
      "n_chunks": 5,
      "updated_at": "2026-01-16T00:00:00Z"
    }
  }
}
```

## 目录布局

```
data_processed/index_state/
├── rag_chunks/
│   ├── LATEST (指针文件，内容为最新 schema_hash)
│   ├── abc123.../
│   │   └── index_state.json
│   └── def456.../
│       └── index_state.json
```

---

**注意**：本模块是**工具库模块**，通常被其他工具（如 `build_chroma_index_flagembedding.py`）导入使用，不直接作为命令行工具运行。
