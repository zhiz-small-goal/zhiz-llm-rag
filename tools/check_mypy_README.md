---
title: check_mypy.py 使用说明
version: v1.1
last_updated: 2026-01-12
tool_id: check_mypy

impl:
  wrapper: tools/check_mypy.py

entrypoints:
  - python tools/check_mypy.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_mypy.py 使用说明


## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [环境变量开关](#环境变量开关)
- [输出与退出码](#输出与退出码)
- [备注与常见问题](#备注与常见问题)

## 目的
用仓库统一退出码契约（0/2/3）执行 mypy 类型检查，并可选启用 strict 模式。

## 适用场景
- PR/CI Lite 门禁中的类型检查步骤
- 本地提前发现类型不一致、缺注解或推断失败等问题

## 快速开始
```bash
python tools/check_mypy.py --root .
python tools/check_mypy.py --root . --strict
```

## 参数说明
- `--root`：仓库根目录（默认 `.`，会进行 `resolve()`）
- `--strict` / `--no-strict`：启用/关闭严格模式
- `--config`：可选配置路径（默认使用 `<root>/pyproject.toml`）

## 环境变量开关
- `RAG_MYPY_STRICT=1`：当未指定 CLI 开关时，启用 strict 模式

## 输出与退出码
- `0`：PASS（类型检查通过）
- `2`：FAIL（类型检查失败）
- `3`：ERROR（工具运行失败或异常）

## 备注与常见问题
- 脚本不会修改文件，仅做检查。
- mypy 会读取 `pyproject.toml` 的 `[tool.mypy]` 配置（例如 `files=["src"]`）。
- 诊断输出包含列号，格式为 `file:line:col`，便于 VS Code 跳转。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_mypy`
> entrypoints: `python tools/check_mypy.py`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--config` | — | '' | Optional config path (default: pyproject.toml) |
| `--no-strict` | — | — | action=store_false；Disable mypy strict mode |
| `--root` | — | '.' | Repo root (default: .) |
| `--strict` | — | — | action=store_true；Enable mypy strict mode |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
