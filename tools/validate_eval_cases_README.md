---
title: "`validate_eval_cases.py` 使用说明（校验 eval_cases.jsonl：结构 + 可执行性 + 分桶字段）"
version: v1.1
last_updated: 2026-01-25
tool_id: validate_eval_cases

impl:
  module: mhy_ai_rag_data.tools.validate_eval_cases
  wrapper: tools/validate_eval_cases.py

entrypoints:
  - python tools/validate_eval_cases.py
  - python -m mhy_ai_rag_data.tools.validate_eval_cases

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# `validate_eval_cases.py` 使用说明（校验 eval_cases.jsonl：结构 + 可执行性 + 分桶字段）


> **适用日期**：2026-01-05  
> **脚本位置建议**：`tools/validate_eval_cases.py`  
> **权威实现**：`src/mhy_ai_rag_data/tools/validate_eval_cases.py`  
> **输出**：`data_processed/build_reports/eval_cases_validation.json`

## 目录
- [1. 目的与适用场景](#1-目的与适用场景)
- [2. 校验范围（必填字段 + bucket/pair_id 规则）](#2-校验范围必填字段--bucketpair_id-规则)
- [3. 用法（命令行）](#3-用法命令行)
- [4. 输出报告字段](#4-输出报告字段)
- [5. 工程化建议](#5-工程化建议)

---

## 1. 目的与适用场景

该脚本用于把 `eval_cases.jsonl` 的“手工维护风险”压到最低，避免因为格式/字段/路径错误导致回归结果不可用或被噪声污染。

常见问题包括：

- JSONL 某行格式坏了，评测脚本直接崩
- `id` 重复导致统计错乱
- `expected_sources` 指向不存在路径（或路径写法不一致）
- `must_include` 写了答案不可能包含的锚点词，导致评测大量假 FAIL
- **口语桶用例缺少 bucket/pair_id**，导致“口语 vs 术语回归”无法聚合分析

---

## 2. 校验范围（必填字段 + bucket/pair_id 规则）

**必填字段（缺失 → FAIL）**
- `id`（非空、唯一）
- `query`（长度基本合法）
- `expected_sources`（list 且非空）
- `must_include`（list 且非空）

**bucket 字段（可选，但强烈建议补齐）**
- `bucket` 允许：`official|oral|ambiguous`
- 缺省 bucket → **warning**（默认视为 `official`，并在报告里记录）
- 非法 bucket → **FAIL**（防止拼写错误导致分桶统计失真）

**pair_id 字段（可选，但推荐用于对照组绑定）**
- 当 bucket 为 `oral` 或 `official` 时：
  - 缺少 `pair_id` → **warning**（建议补齐，用于“同概念口语/术语对照”）
- 空字符串 `pair_id` → warning

**concept_id 字段**
- 为空字符串 → warning（通常意味着手工填充遗漏）

---

## 3. 用法（命令行）

```bash
python tools/validate_eval_cases.py --root . --cases data_processed/eval/eval_cases.jsonl --check-sources-exist --out data_processed/build_reports/eval_cases_validation.json
```

说明：
- `--skip-if-missing` 用于 gate/CI：当 cases 文件缺失时，以 WARN 退出 0（避免在“未准备用例”阶段阻断其它门禁）。

---

## 4. 输出报告字段

- `overall`：`PASS|FAIL`
- `errors[]`：会导致 FAIL 的问题（解析错误、缺字段、id 重复、非法 bucket、路径不存在等）
- `warnings[]`：潜在问题（bucket 缺省、pair_id 缺失、must_include 质量问题、锚点未出现在期望文档等）
- `counts.*`：统计信息（lines/cases/errors/warnings）

---

## 5. 工程化建议

- 建议在任何 Stage-2 回归之前先跑一次 `validate_eval_cases.py`，确保输入数据“可执行、可审计”。
- 当你开始正式治理“口语 vs 官方术语断桥”时，建议把：
  1) `bucket` 缺省从 warning 升级为 error（在你补齐历史用例之后）
  2) 对 oral/official 的 `pair_id` 缺失从 warning 升级为 error（当你明确要做对照评测之后）

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--cases` | — | 'data_processed/eval/eval_cases.jsonl' | eval cases jsonl (relative to root) |
| `--check-must-include-in-sources` | — | — | action=store_true；check each must_include appears in at least one expected_source file (only for file paths) |
| `--check-sources-exist` | — | — | action=store_true；check that expected_sources path exists under root |
| `--md-out` | — | '' | optional report.md path (relative to root); default: <out>.md |
| `--out` | — | 'data_processed/build_reports/eval_cases_validation.json' | output report json (relative to root) |
| `--root` | — | '.' | project root |
| `--skip-if-missing` | — | — | action=store_true；if cases missing, emit WARN and exit 0 (for gate integration) |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
