---
title: plan_chunks_from_units.py 使用说明（从文本单元规划分块）
version: v1.0
last_updated: 2026-01-16
tool_id: plan_chunks_from_units

impl:
  module: mhy_ai_rag_data.tools.plan_chunks_from_units
  wrapper: tools/plan_chunks_from_units.py

entrypoints:
  - python tools/plan_chunks_from_units.py
  - python -m mhy_ai_rag_data.tools.plan_chunks_from_units

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# plan_chunks_from_units.py 使用说明


> 目标：Dry-run chunk 规划，从 text_units.jsonl 按与 build 相同的口径计算预期 chunks 数量，生成 chunk_plan.json，用于验收时对齐 expected==count。

## 快速开始

```cmd
python tools\plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub true --out data_processed\chunk_plan.json
```

输出：
```
=== CHUNK PLAN ===
units_read=500
units_indexed=450
units_skipped=50
planned_chunks=2340
include_media_stub=False
chunk_conf=chunk_chars:1200 overlap_chars:120 min_chunk_chars:200
out=f:\zhiz-c++\zhiz-llm-rag\data_processed\chunk_plan.json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--units` | `data_processed/text_units.jsonl` | 文本单元文件 |
| `--chunk-chars` | `1200` | 单个 chunk 最大字符数 |
| `--overlap-chars` | `120` | 重叠字符数 |
| `--min-chunk-chars` | `200` | 最小 chunk 字符数 |
| `--include-media-stub` | `false` | 是否索引媒体 stub（需与 build 一致） |
| `--out` | `data_processed/chunk_plan.json` | 输出 JSON 路径 |

## 退出码

- `0`：成功
- `2`：失败（units 不存在等）

## 输出报告

```json
{
  "root": "f:\\zhiz-c++\\zhiz-llm-rag",
  "units_path": "...",
  "planned_chunks": 2340,
  "units_read": 500,
  "units_indexed": 450,
  "units_skipped": 50,
  "chunk_conf": {...},
  "include_media_stub": false,
  "type_breakdown": {
    "markdown": {"indexed": 300, "skipped": 0, "chunks": 1500},
    "video": {"indexed": 0, "skipped": 50, "chunks": 0}
  }
}
```

## 示例

### 1) 生成 chunk 计划
```bash
python tools/plan_chunks_from_units.py小
```

### 2) 包含媒体 stub
```cmd
python tools\plan_chunks_from_units.py --root . --include-media-stub true
```

### 3) 自定义分块参数
```cmd
python tools\plan_chunks_from_units.py --chunk-chars 800 --overlap-chars 80 --min-chunk-chars 100
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/plan_chunks_from_units.py`。**重要**：plan 参数必须与 build 保持一致，否则验收会失败。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `plan_chunks_from_units`
> entrypoints: `python tools/plan_chunks_from_units.py`, `python -m mhy_ai_rag_data.tools.plan_chunks_from_units`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--chunk-chars` | — | 1200 | type=int |
| `--include-media-stub` | — | 'false' | Whether to index media stubs (true/false). Must match build step. |
| `--min-chunk-chars` | — | 200 | type=int |
| `--out` | — | 'data_processed/chunk_plan.json' | Output json path (relative to root) |
| `--overlap-chars` | — | 120 | type=int |
| `--root` | — | '.' | Project root |
| `--units` | — | 'data_processed/text_units.jsonl' | Units JSONL path (relative to root) |
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
  - `data_processed/chunk_plan.json`
  - `data_processed/build_reports/chunk_plan_report.json`
  - `data_processed/build_reports/chunk_plan_report.md`
<!-- AUTO:END artifacts -->
