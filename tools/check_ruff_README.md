---
title: check_ruff.py 使用说明
version: v1.2
last_updated: 2026-01-12
---

# check_ruff.py 使用说明


## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [环境变量开关](#环境变量开关)
- [输出与退出码](#输出与退出码)
- [备注与常见问题](#备注与常见问题)

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
- `2`：FAIL（lint/format 存在违规）
- `3`：ERROR（工具运行失败或异常）

## 备注与常见问题
- 脚本不会修改文件，仅做检查。
- lint 输出使用 `file:line:col` 形式，便于 VS Code 跳转。
- 默认使用 `pyproject.toml` 中的 Ruff 配置；如需覆盖，使用 `--config`。
