---
title: check_readme_code_sync.py 使用说明（tools/ README ↔ 源码对齐门禁）
version: v0.3
last_updated: 2026-01-21
tool_id: check_readme_code_sync

impl:
  module: mhy_ai_rag_data.tools.check_readme_code_sync
  wrapper: tools/check_readme_code_sync.py

entrypoints:
  - python tools/check_readme_code_sync.py
  - python -m mhy_ai_rag_data.tools.check_readme_code_sync

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---

# check_readme_code_sync.py 使用说明


> 目标：对 `tools/` 下 README 与对应源码进行一致性门禁检查，重点解决“参数/说明滞后于源码”与“自动生成区块漂移”。

## 输入（SSOT）

- `docs/reference/readme_code_sync.yaml`：一致性规则（required frontmatter keys / AUTO block markers / 默认 enforce 列表）。
- `docs/reference/readme_code_sync_index.yaml`：README ↔ 工具实现映射（tool_id / impl.module / contracts.output 等）。
- `docs/reference/readme_code_sync_exceptions.yaml`：例外登记（仅允许显式跳过 options/output-contract/artifacts 的校验；需 reason/owner/review.trigger）。

## 检查内容（`--check`）

- YAML frontmatter 必须存在，且包含 SSOT 中声明的 required keys。
- AUTO block markers（BEGIN/END）配对与顺序合法。
- 当 README 中出现 AUTO blocks（`options` / `output-contract` / `artifacts`）时：`--check` 会对这些区块做一致性校验；不一致会 FAIL，并提供 diff（用于 review）。
- 当 README 的代码块中出现以 entrypoints 开头的示例命令时：校验示例中使用的 `--flags` 必须存在于源码 argparse 定义（未知 flag 直接 FAIL）。
- 若 `contracts.output == report-output-v2`：至少在 frontmatter 或正文中可见 `report-output-v2` 信号（迁移期的最小信号约束）。

约定：
- AUTO markers 必须为**独立行**（避免 README 用反引号/代码块展示 marker 字符串时误触发）。


## 用法

```bash
# 默认读取 SSOT 与 index，并输出 report-output-v2 JSON
python tools/check_readme_code_sync.py --root .

# 指定输出路径（相对 repo root）
python tools/check_readme_code_sync.py --root . --out data_processed/build_reports/readme_code_sync_report.json

# 不落盘 JSON（只输出 console）
python tools/check_readme_code_sync.py --root . --out ""

# 生成/刷新 README AUTO blocks（会就地改写 tools/*README*.md）
python tools/check_readme_code_sync.py --root . --write
```

## 退出码

- 0：全部通过
- 2：存在契约违反（FAIL）
- 3：脚本异常（ERROR）

## 典型失败与定位

- `frontmatter_missing`：README 顶部缺少 `--- ... ---`。
- `frontmatter_required_keys_missing`：缺少 `title/version/last_updated` 等 required keys。
- `auto_block_marker_invalid`：AUTO block begin/end 不成对或顺序错。
- `options_block_mismatch`：AUTO options block 内容与生成器输出不一致（用 `--write` 刷新）。
- `options_help_snapshot_failed`：`generation.options=help-snapshot` 但无法获取稳定的 help 快照（考虑改用 `static-ast` / 补齐 wrapper / 或登记例外）。
- `output_contract_block_mismatch`：AUTO output-contract block 内容与生成器输出不一致（用 `--write` 刷新）。
- `artifacts_block_mismatch`：AUTO artifacts block 内容与生成器输出不一致（用 `--write` 刷新）。
- `exceptions_invalid`：例外文件结构不合法（缺 reason/owner/review.trigger 或 skip check 名不受支持）。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--check` | — | — | action=store_true；Only check consistency (default). |
| `--config` | — | 'docs/reference/readme_code_sync.yaml' | SSOT config path |
| `--index` | — | 'docs/reference/readme_code_sync_index.yaml' | Mapping index path |
| `--out` | — | DEFAULT_OUT | nargs='?'；Write report-output-v2 JSON to this path (relative to repo root). Empty -> no JSON. |
| `--root` | — | '.' | Repo root |
| `--write` | — | — | action=store_true；Rewrite/insert deterministic AUTO blocks. |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 默认输出: `data_processed/build_reports/readme_code_sync_report.json`（JSON） + `data_processed/build_reports/readme_code_sync_report.md`（Markdown）
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
- artifacts（registry）：
  - `data_processed/build_reports/readme_code_sync_report.json`
  - `data_processed/build_reports/readme_code_sync_report.md`
<!-- AUTO:END artifacts -->
