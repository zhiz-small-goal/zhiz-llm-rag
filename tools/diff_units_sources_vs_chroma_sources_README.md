---
title: diff_units_sources_vs_chroma_sources.py 使用说明（对比文本单元与 Chroma 源）
version: v1.0
last_updated: 2026-01-16
tool_id: diff_units_sources_vs_chroma_sources

impl:
  module: mhy_ai_rag_data.tools.diff_units_sources_vs_chroma_sources
  wrapper: tools/diff_units_sources_vs_chroma_sources.py

entrypoints:
  - python tools/diff_units_sources_vs_chroma_sources.py
  - python -m mhy_ai_rag_data.tools.diff_units_sources_vs_chroma_sources

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# diff_units_sources_vs_chroma_sources.py 使用说明


> 目标：对比 text_units.jsonl 的 source_uri 集合与 Chroma collection 中的 source_uri 集合，解释"为什么库里 unique_source_uri 比 units 少"现象。

## 目的

本工具用于：

- **解释覆盖率差异**：为什么 Chroma 中的 unique_source_uri 比 text_units.jsonl 少
- **验证媒体索引**：确认引入 `--include-media-stub` 或 OCR/ASR 后，媒体文件是否按预期入库
- **调试过滤逻辑**：查看哪些 source_type 被构建阶段过滤掉

## 快速开始

```cmd
python tools\diff_units_sources_vs_chroma_sources.py --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks
```

期望输出：
```
units_unique_sources=1500
chroma_unique_sources=1200
skipped_sources(units_only)=300
added_sources(chroma_only)=0

Skipped extensions (top 15):
  .mp4: 150
  .mp3: 100
  .png: 50

Skipped sample:
  docs/video/intro.mp4
  docs/audio/demo.mp3
  ...
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--units` | `data_processed/text_units.jsonl` | 文本单元文件 |
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--collection` | `rag_chunks` | Collection 名称 |
| `--max-sample` | `20` | 输出样本最大数量 |

## 退出码

- `0`：成功（无论是否存在差异）
- `2`：失败（文件/库无法读取）

## 示例

### 1) 查看差异
```cmd
python tools\diff_units_sources_vs_chroma_sources.py --root .
```

### 2) 查看更多样本
```cmd
python tools\diff_units_sources_vs_chroma_sources.py --root . --max-sample 50
```

## 常见现象解释

### 1) skipped_sources 很多，都是媒体文件
**原因**：构建时未使用 `--include-media-stub`

**处理**：重建时加上 `--include-media-stub`
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --include-media-stub
```

### 2) added_sources 不为 0
**原因**：Chroma 中存在 text_units.jsonl 没有的源（通常是旧数据残留）

**处理**：重置 Chroma DB 后重建
```cmd
python tools\reset_chroma_db.py --db chroma_db
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/diff_units_sources_vs_chroma_sources.py`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `diff_units_sources_vs_chroma_sources`
> entrypoints: `python tools/diff_units_sources_vs_chroma_sources.py`, `python -m mhy_ai_rag_data.tools.diff_units_sources_vs_chroma_sources`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--collection` | — | 'rag_chunks' | — |
| `--db` | — | 'chroma_db' | — |
| `--max-sample` | — | 20 | type=int |
| `--root` | — | '.' | — |
| `--units` | — | 'data_processed/text_units.jsonl' | — |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
