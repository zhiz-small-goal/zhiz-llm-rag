---
title: check_readme_code_sync.py 使用说明（tools/ README ↔ 源码对齐门禁）
version: v0.1
last_updated: 2026-01-20
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

## 检查内容（Step3：只做 --check）

- YAML frontmatter 必须存在，且包含 SSOT 中声明的 required keys。
- AUTO block markers（BEGIN/END）配对与顺序合法。
- 当 README 中出现 `<!-- AUTO:BEGIN options --> ... <!-- AUTO:END options -->` 时：
  - 读取映射到的 `impl.module` 源码文件（`src/.../*.py`）
  - 静态抽取 `argparse` 的 `add_argument("--flag")` 形态的长参数
  - 对比 AUTO options block 内出现的 `--flag` 集合（多/少都会报 FAIL）。
- 若 `contracts.output == report-output-v2`：至少在 frontmatter 或正文中可见 `report-output-v2` 信号（Step4 再加强为 output-contract AUTO block）。

## 用法

```bash
# 默认读取 SSOT 与 index，并输出 report-output-v2 JSON
python tools/check_readme_code_sync.py --root .

# 指定输出路径（相对 repo root）
python tools/check_readme_code_sync.py --root . --out data_processed/build_reports/readme_code_sync_report.json

# 不落盘 JSON（只输出 console）
python tools/check_readme_code_sync.py --root . --out ""
```

## 退出码

- 0：全部通过
- 2：存在契约违反（FAIL）
- 3：脚本异常（ERROR）

## 典型失败与定位

- `frontmatter_missing`：README 顶部缺少 `--- ... ---`。
- `frontmatter_required_keys_missing`：缺少 `title/version/last_updated` 等 required keys。
- `auto_block_marker_invalid`：AUTO block begin/end 不成对或顺序错。
- `options_mismatch`：AUTO options block 内出现的 `--flag` 与源码静态抽取结果不一致。

