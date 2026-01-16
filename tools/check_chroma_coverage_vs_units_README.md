---
title: check_chroma_coverage_vs_units.py 使用说明（检查 Chroma 覆盖率）
version: v1.0
last_updated: 2026-01-16
---

# check_chroma_coverage_vs_units.py 使用说明


> 目标：快速判断 Chroma 索引覆盖率，用于"中断恢复/是否需要重跑"的决策依据，避免不必要的全量重建。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [原理](#原理)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [示例](#示例)
- [常见问题](#常见问题)
- [相关文档](#相关文档)

## 目的

本工具用于快速判断 Chroma索引构建进度：

- **重新计算期望 chunk IDs**：从 `text_units.jsonl` 按 chunking 口径（doc_id:chunk_index）生成期望 ID 列表
- **批量查询 Chroma**：检查这些 IDs 是否在 collection 中存在
- **输出覆盖率**：`present/missing/coverage_percent`，用于决策是否需要重跑

## 适用场景

- **进程中断后**：判断 Chroma 构建进度，决定是否需要全量重建
- **断电恢复**：快速检查缺口比例
- **CI 验证**：确认 build 后索引是否完整

## 原理

本项目使用 upsert 且 chunk_id 可复现（`doc_id:chunk_index`），因此：

- **重跑不会产生重复记录**（同 ID 覆盖写入）
- **但会重复计算 embedding**（成本高）
- **本脚本帮助你判断缺口比例**，再决定是否值得重跑

### 计算流程

1. 读取 `text_units.jsonl`
2. 按与 `build_chroma_index.py` 相同的口径（include_media_stub / chunk_conf）生成所有期望 chunk IDs
3. 批量查询 Chroma collection（`coll.get(ids=...)`）
4. 统计 present/missing/coverage%

## 快速开始

```cmd
python tools\check_chroma_coverage_vs_units.py ^
  --root . ^
  --units data_processed\text_units.jsonl ^
  --db chroma_db ^
  --collection rag_chunks
```

期望输出：
```
expected_chunks=5234
include_media_stub=True
chunk_conf=chunk_chars:1200 overlap_chars:120 min_chunk_chars:200
present=5234
missing=0
coverage_percent=100.00
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--units` | `data_processed/text_units.jsonl` | 文本单元输入文件 |
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--collection` | `rag_chunks` | Collection 名称 |
| `--include-media-stub` | `true` | 是否索引媒体 stub（需与 build 时一致） |
| `--chunk-chars` | `1200` | 单个 chunk 最大字符数 |
| `--overlap-chars` | `120` | 重叠字符数 |
| `--min-chunk-chars` | `200` | 最小 chunk 字符数 |
| `--batch` | `200` | 批量查询大小 |

> **重要**：`--include-media-stub` 和 chunk_conf 参数必须与构建时一致，否则期望 IDs 不准确。

## 退出码

- `0`：成功输出覆盖率（无论覆盖率高低）
- `2`：失败（输入文件缺失/collection 不可读）

## 示例

### 1) 检查覆盖率
```cmd
python tools\check_chroma_coverage_vs_units.py --root .
```

### 2) 不包含媒体 stub
```cmd
python tools\check_chroma_coverage_vs_units.py ^
  --root . ^
  --include-media-stub false
```

### 3) 自定义 chunk 配置
```cmd
python tools\check_chroma_coverage_vs_units.py ^
  --root . ^
  --chunk-chars 800 ^
  --overlap-chars 80 ^
  --min-chunk-chars 100
```

### 4) 决策示例
```bash
# 检查覆盖率
python tools/check_chroma_coverage_vs_units.py --root .
# 输出：coverage_percent=85.50

# 决策：
# - 如果 coverage >= 95%，可以增量补齐
# - 如果 coverage < 80%，建议全量重建
```

## 常见问题

### 1) coverage_percent 不是 100%，但构建明明跑完了
**可能原因**：
- chunk_conf 参数与构建时不一致
- include-media-stub 参数与构建时不一致
- text_units.jsonl 在构建后又更新了

**处理**：
1. 确认参数一致：
   ```bash
   # 查看构建时的参数（从 build 命令历史或 index_state.json）
   cat data_processed/index_state/rag_chunks/*/index_state.json
   ```

2. 使用相同参数检查：
   ```cmd
   python tools\check_chroma_coverage_vs_units.py ^
     --root . ^
     --chunk-chars <构建时的值> ^
     --include-media-stub <构建时的值>
   ```

### 2) 报错：`[FATAL] collection not found`
**原因**：collection 名称错误或 Chroma DB 路径错误

**处理**：
```bash
# 列出所有 collections
python tools/list_chroma_collections.py --db chroma_db
```

### 3) 覆盖率很低（<50%），是否需要重跑？
**建议**：
- 使用 `--sync-mode incremental` 增量补齐（只 embedding 缺失的部分）
- 或者 `--on-missing-state reset` 全量重建（如果时间允许）

### 4) 批量查询很慢
调大 `--batch`：
```cmd
python tools\check_chroma_coverage_vs_units.py ^
  --root . ^
  --batch 1000
```

## 相关文档

- [tools/build_chroma_index_flagembedding_README.md](build_chroma_index_flagembedding_README.md) - 构建索引
- [tools/check_chroma_embeddings_sample_README.md](check_chroma_embeddings_sample_README.md) - 检查 embedding 质量
-[tools/list_chroma_collections_README.md](list_chroma_collections_README.md) - 列出 collections


---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/check_chroma_coverage_vs_units.py`。推荐使用 `python -m mhy_ai_rag_data.tools.check_chroma_coverage_vs_units`。
