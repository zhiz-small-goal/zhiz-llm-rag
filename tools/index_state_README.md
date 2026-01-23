---
title: index_state.py 使用说明（索引状态管理模块）
version: v1.3
last_updated: 2026-01-23
tool_id: index_state

impl:
  module: mhy_ai_rag_data.tools.index_state
  wrapper: tools/index_state.py

entrypoints:
  - python tools/index_state.py
  - python -m mhy_ai_rag_data.tools.index_state
entrypoints_note: "兼容/调试入口：用于 README↔源码对齐与开发自检；不保证提供稳定 CLI（运行通常等同导入）。"

contracts:
  output: report-output-v2

generation:
  options: help-snapshot
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: other
owner: "zhiz"
status: "active"
---
# index_state.py 使用说明



## 目录

- [SSOT 与口径入口](#ssot-与口径入口)
- [目的](#目的)
- [运行入口（entrypoints）说明（非稳定 CLI）](#运行入口entrypoints说明非稳定-cli)
- [与断点续跑（WAL）的关系](#与断点续跑wal的关系)
- [主要API](#主要api)
  - [1) compute_schema_hash](#1-compute_schema_hash)
  - [2) load_index_state（兼容 v1 -> v2）](#2-load_index_state兼容-v1-v2)
  - [3) write_index_state_report（v2 写入推荐入口）](#3-write_index_state_reportv2-写入推荐入口)
  - [4) read_latest_pointer / write_latest_pointer](#4-read_latest_pointer-write_latest_pointer)
- [状态文件结构（v2 示例）](#状态文件结构v2-示例)
- [目录布局](#目录布局)
- [关联自检](#关联自检)
- [自动生成区块（AUTO）](#自动生成区块auto)

> 目标：为增量构建 + 强一致验收提供最小状态文件（manifest）管理，记录每个文档的 doc_id、content_sha256、n_chunks，支持新增/变更/删除判定。


## SSOT 与口径入口

- **文档体系 SSOT**：`docs/reference/DOC_SYSTEM_SSOT.md`
- **WAL/续跑术语表**：`docs/reference/GLOSSARY_WAL_RESUME.md`
- **build CLI/日志真相表**：`docs/reference/build_chroma_cli_and_logs.md`

> 约束：本文仅保留“怎么做/怎么排障”的最短路径；参数默认值与字段解释以真相表为准。

## 目的

> 相关 SSOT：`docs/reference/index_state_and_stamps.md`、`docs/reference/build_chroma_cli_and_logs.md`、`docs/reference/GLOSSARY_WAL_RESUME.md`。


本模块是工具库模块（非命令行工具），提供：

<!-- ENTRYPOINTS-NONCLI-NOTE -->
## 运行入口（entrypoints）说明（非稳定 CLI）

本 README 顶部与“自动生成参考”里列出的 `entrypoints`，主要用途是 **兼容入口/调试入口**：用于在 repo 根目录下通过 wrapper 触发模块导入、以及让 `check_readme_code_sync` 能识别 README 里的示例命令块并做一致性校验。它不表示该模块对外提供“可长期依赖的命令行接口”。

- **行为边界**：运行 `python tools/index_state.py` 或 `python -m mhy_ai_rag_data.tools.index_state` 的主要效果是“导入模块并完成定义加载”，通常不会产生业务输出；传入参数也不会被消费（除非未来明确加入 CLI）。
- **正确使用方式**：请把它当作库模块，在 Python 里 `import` 后调用下方 API；需要执行索引构建/校验等动作时，优先使用项目内的具体 CLI 工具（例如 `tools/build_chroma_index_flagembedding.py`、`tools/verify_stage1_pipeline.py`、`tools/check_inventory_build.py` 等）。


- **schema_hash 计算**：embed_model/chunk_conf/include_media_stub 变化时生成新 hash
- **状态文件读写**：index_state.json 原子写入（tmp -> replace）
- **LATEST 指针管理**：跟踪最新 schema_hash
- **Report v2 兼容读取**：读取 legacy v1（缺 schema_version）时，在内存中转换为 `schema_version=2` 的 v2 envelope


## 与断点续跑（WAL）的关系

- 本模块管理 `index_state.json`（完成态 manifest）的读写与兼容；当前策略是 only-on-success 写入，因此中断时 `index_state.json` 可能缺失。
- build 工具为断点续跑引入了 `index_state.stage.jsonl`（WAL）与 `writer.lock`（互斥锁）；它们不由本模块负责写入，但与 manifest 存在协作关系。
- 若你要判断是否可续跑，请使用：
  ```cmd
  python tools\build_chroma_index_flagembedding.py build --collection <name> --resume-status
  ```

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

### 2) load_index_state（兼容 v1 -> v2）
```python
from mhy_ai_rag_data.tools.index_state import load_index_state

state = load_index_state(state_file, root=repo_root)
if state is None:
    # 首次构建
    pass

# state 是 dict；当输入为 v1 时会被规整为 v2 report（schema_version=2）
```

### 3) write_index_state_report（v2 写入推荐入口）
```python
from mhy_ai_rag_data.tools.index_state import write_index_state_report

out = write_index_state_report(
    root=repo_root,
    state_root=repo_root / "data_processed/index_state",
    collection="rag_chunks",
    schema_hash=schema_hash,
    db=repo_root / "chroma_db",
    embed_model="BAAI/bge-m3",
    chunk_conf={"chunk_chars": 1200, "overlap_chars": 120, "min_chunk_chars": 200},
    include_media_stub=False,
    docs={},
    last_build={"sync_mode": "full", "expected_chunks": 0, "collection_count": 0},
    items=[{"tool": "index_state", "title": "index_state written", "status_label": "PASS", "severity_level": 0, "message": "wrote"}],
)
print(out)
```

### 4) read_latest_pointer / write_latest_pointer
```python
from mhy_ai_rag_data.tools.index_state import read_latest_pointer, write_latest_pointer

latest = read_latest_pointer(state_root, collection)
write_latest_pointer(state_root, collection, schema_hash)
```

## 状态文件结构（v2 示例）

```json
{
  "schema_version": 2,
  "generated_at": "2026-01-19T00:00:00Z",
  "tool": "index_state",
  "root": "/abs/path/to/repo",
  "summary": {"overall_label": "PASS", "overall_rc": 0, "counts": {"PASS": 1, "INFO": 0, "WARN": 0, "FAIL": 0, "ERROR": 0}},
  "items": [
    {"tool": "index_state", "key": "state_written", "title": "index_state written", "status_label": "PASS", "severity_level": 0, "message": "..."}
  ],

  "schema_hash": "abc123...",
  "db": "data_processed/chroma_db",
  "collection": "rag_chunks",
  "embed_model": "BAAI/bge-m3",
  "chunk_conf": {"chunk_chars": 1200, "overlap_chars": 120, "min_chunk_chars": 200},
  "include_media_stub": false,
  "updated_at": "2026-01-19T00:00:00Z",

  "docs": {
    "path/to/doc.md": {
      "doc_id": "md_abc123",
      "source_uri": "path/to/doc.md",
      "content_sha256": "def456...",
      "n_chunks": 5,
      "updated_at": "2026-01-19T00:00:00Z"
    }
  },
  "last_build": {"sync_mode": "upsert", "expected_chunks": 5, "collection_count": 5, "build_seconds": 0.2}
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

## 关联自检

如果需要对 index_state / db_build_stamp 这类“状态元数据报告”的 v2 契约进行固定样例校验，可运行：

- `python tools/verify_state_reports_samples.py`

---

**注意**：本模块是工具库模块，通常被其他工具导入使用；不建议把 `tools/index_state.py` 视作稳定的命令行接口。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
_(no long flags detected by help-snapshot)_
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->