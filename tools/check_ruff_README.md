---
title: check_ruff.py 使用说明
version: v1.4
last_updated: 2026-01-14
tool_id: check_ruff

impl:
  wrapper: tools/check_ruff.py

entrypoints:
  - python tools/check_ruff.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_ruff.py 使用说明


## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [最小可用指令（拷贝即用）](#最小可用指令拷贝即用)
- [参数说明](#参数说明)
- [环境变量开关](#环境变量开关)
- [输出与退出码](#输出与退出码)
- [备注与常见问题](#备注与常见问题)
- [与 Ruff 命令的区别](#与-ruff-命令的区别)
- [常用诊断/修复命令](#常用诊断修复命令)

## 目的
用仓库统一退出码契约（0/2/3）执行 Ruff lint，并可选执行 `ruff format --check`。

## 适用场景
- PR/CI Lite 门禁中的静态检查步骤
- 本地自检代码规范与潜在错误（例如未使用变量、语法问题）

## 快速开始
```bash
python tools/check_ruff.py --root .
python tools/check_ruff.py --root . --format
python tools/check_ruff.py --root . --format src/mhy_ai_rag_data/rag_config.py

# 需要自动修复格式时（会修改文件, 以下指令任选其一）
python -m ruff format .
ruff format .
```

## 最小可用指令（拷贝即用）
Windows（建议用于 CI Lite 自检，含格式检查）：
```cmd
python -m venv .venv_ci
.\.venv_ci\Scripts\activate
pip install -e ".[ci]"
python tools\check_ruff.py --root . --format
```

**自动修复 lint 与格式（会改文件）**：
1. `python -m ruff check --fix .`
作用：检查并自动修复代码质量问题（linting issues）

修复内容示例：
- ❌ 移除未使用的导入 import os
- ❌ 移除未使用的变量
- ❌ 自动排序导入语句
- ❌ 修复简单的语法问题（如 == None → is None）
- ❌ 移除重复的导入
不会改变：代码的格式（空格、换行、缩进等）

2. `python -m ruff format .`
作用：自动格式化代码外观（formatting）

修复内容示例：
- ✨ 统一缩进（4 个空格）
- ✨ 调整行长度（自动换行）
- ✨ 统一引号风格（单引号/双引号）
- ✨ 调整空行数量
- ✨ 格式化括号、逗号后的空格
不会改变：代码逻辑或移除/添加任何语句

```cmd
python -m ruff check --fix .
python -m ruff format .
```

## 参数说明
- `--root`：仓库根目录（默认 `.`，会进行 `resolve()`）
- `--format` / `--no-format`：启用/关闭 `ruff format --check`
- `--output-format`：Ruff lint 输出格式（默认 `concise`）
- `--config`：可选配置路径（默认 Ruff 自动发现配置文件）
- `files...`：可选文件列表（如 pre-commit 传入的暂存文件）

## 环境变量开关
- `RAG_RUFF_FORMAT=1`：当未指定 CLI 开关时，启用 `ruff format --check`

## 输出与退出码
- `0`：PASS（lint/format 全部通过或未启用 format）
- `2`：FAIL（lint/format 存在违规；Ruff 的退出码 1 会被映射为 2）
- `3`：ERROR（Ruff 命令异常或退出码 >1；例如配置错误、崩溃）

## 备注与常见问题
- 脚本不会修改文件，只做检查：lint 使用 `ruff check`，格式使用 `ruff format --check`。
- 未使用导入等问题属于 lint（`ruff check`），不是 format；要修复需显式运行 `ruff check --fix`，本脚本不带 `--fix`。
- 格式检查只在启用 `--format` 或 `RAG_RUFF_FORMAT=1` 时执行；否则跳过并提示。
- 文件列表默认为 `.`，但可传入具体文件（如 pre-commit 传入暂存文件）以缩小范围。
- lint/format 输出会把 Windows 路径归一为 `/`，格式为 `path:line:col: message` 便于 VS Code 跳转。
- 默认读取 `pyproject.toml` 的 Ruff 配置；需要覆盖时用 `--config <path>`。

## 与 Ruff 命令的区别
- 退出码映射：Ruff 的 `0/1/2` 分别被映射为 `0/2/3` 以符合仓库门禁契约。
- 格式检查仅做 `--check`，不会改动源文件；本脚本不提供自动修复。
- 输出位置归一化：标准化 Windows 路径，方便 IDE 点击跳转。

## 常用诊断/修复命令
仅检查（与门禁一致）：
```bash
python tools/check_ruff.py --root .
python tools/check_ruff.py --root . --format
```

检查 + 自动修复 lint（未使用导入等）：
```bash
python -m ruff check --fix .
ruff check --fix src/mhy_ai_rag_data/tools/snapshot_stage1_baseline.py
```

自动修复格式（会改文件, 比如统一单引号改为双引号；与本脚本的 format --check 不同）：
```bash
python -m ruff format .
ruff format src/mhy_ai_rag_data/tools/snapshot_stage1_baseline.py
```

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_ruff`
> entrypoints: `python tools/check_ruff.py`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--config` | — | '' | Optional config path (default: auto-discovery) |
| `--format` | — | — | action=store_true；Enable ruff format --check |
| `--no-format` | — | — | action=store_false；Disable ruff format --check |
| `--output-format` | — | 'concise' | Ruff lint output format (default: concise) |
| `--root` | — | '.' | Repo root (default: .) |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
