---
title: list_chroma_collections.py 使用说明（列出 Chroma 集合）
version: v1.0
last_updated: 2026-01-16
tool_id: list_chroma_collections

impl:
  module: mhy_ai_rag_data.tools.list_chroma_collections
  wrapper: tools/list_chroma_collections.py

entrypoints:
  - python tools/list_chroma_collections.py
  - python -m mhy_ai_rag_data.tools.list_chroma_collections

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# list_chroma_collections.py 使用说明


> 目标：列出指定 Chroma DB 下所有 collection，并可选检查目标 collection 是否存在，用于验证向量库同步成功。

## 快速开始

```cmd
python tools\list_chroma_collections.py --db chroma_db --expect rag_chunks
```

期望输出：
```
db_path=f:\zhiz-c++\zhiz-llm-rag\chroma_db
collections:
- name='rag_chunks'
STATUS: OK (found collection 'rag_chunks')
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--expect` | *(空)* | 期望的 collection 名称（可选） |

## 退出码

- `0`：成功（若指定 `--expect` 且存在，也返回 0）
- `2`：失败（DB 打不开或 expect 不存在）

## 示例

### 1) 列出所有 collections
```cmd
python tools\list_chroma_collections.py --db chroma_db
```

### 2) 检查特定 collection 是否存在
```bash
python tools/list_chroma_collections.py \
  --db chroma_db \
  --expect rag_chunks
```

### 3) CI 中验证
```cmd
python tools\list_chroma_collections.py --db chroma_db --expect rag_chunks
if %ERRORLEVEL% neq 0 (echo Collection not found! & exit /b 2)
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/list_chroma_collections.py`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `list_chroma_collections`
> entrypoints: `python tools/list_chroma_collections.py`, `python -m mhy_ai_rag_data.tools.list_chroma_collections`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--db` | — | 'chroma_db' | Chroma persistent directory |
| `--expect` | — | None | Expected collection name |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
