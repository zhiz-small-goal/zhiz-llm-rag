---
title: How-to：本地 pre-commit 使用指南
version: v1.2
last_updated: 2026-01-14
---

# How-to：本地 pre-commit 使用指南

> 目标：在提交前用 pre-commit 运行本仓库门禁，并保持与 CI 口径一致。

## 目录
- [1) 适用场景](#1-适用场景)
- [2) 前置条件](#2-前置条件)
- [3) 安装 pre-commit](#3-安装-pre-commit)
- [4) 本仓库推荐流程（.venv_ci）](#4-本仓库推荐流程venv_ci)
- [4.1 PowerShell（推荐）](#41-powershell推荐)
- [4.2 Windows CMD](#42-windows-cmd)
- [5) 运行方式（手动 / 提交前钩子）](#5-运行方式手动--提交前钩子)
- [6) 环境变量设置（PowerShell / CMD / 用户变量）](#6-环境变量设置powershell--cmd--用户变量)
- [6.1 PowerShell（当前会话）](#61-powershell当前会话)
- [6.2 Windows CMD（当前会话）](#62-windows-cmd当前会话)
- [6.3 持久化到用户变量（Windows）](#63-持久化到用户变量windows)
- [6.4 查看当前值](#64-查看当前值)
- [7) 解释器选择与环境变量含义](#7-解释器选择与环境变量含义)
- [8) 常见问题](#8-常见问题)
- [9) 相关文档](#9-相关文档)
- [10) 参考](#10-参考)

## 1) 适用场景
- 本地提交前希望自动拦截 gate / ruff / mypy 等失败。
- 多台设备需要稳定选中同一解释器与依赖环境。
- 如需在 VSCode GUI 提交时生效, 采用环境变量设置最省事[环境变量](#6-环境变量设置powershell--cmd--用户变量)

## 2) 前置条件
- 仓库已启用 Git，并且你在仓库根目录操作。
- Python 版本满足本仓库要求（>= 3.11）。
- 运行本仓库门禁所需依赖已安装（推荐 `pip install -e ".[ci]"`）。

## 3) 安装 pre-commit
以下做法按官方文档整理，选择一种即可：

### 方法 A：在本仓库 venv 内安装（推荐）
```powershell
python -m venv .venv_ci
.\.venv_ci\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[ci]"
pip install pre-commit
```

### 方法 B：加入依赖清单（如你使用 requirements）
将 `pre-commit` 加入 `requirements.txt` 或 `requirements-dev.txt` 后再统一安装。

### 方法 C：zipapp（不落地安装）
从 pre-commit 的 GitHub Releases 下载 `.pyz`，使用：
```bash
python pre-commit-#.#.#.pyz --version
```
后续把 `pre-commit` 命令替换为 `python pre-commit-#.#.#.pyz ...`。

## 4) 本仓库推荐流程（.venv_ci）
推荐在 `.venv_ci` 中安装依赖，并显式指定 `RAG_PYTHON`。

### 4.1 PowerShell（推荐）
```powershell
python -m venv .venv_ci
.\.venv_ci\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[ci]"
pip install pre-commit

pre-commit install
$env:RAG_PYTHON = "$PWD\\.venv_ci\\Scripts\\python.exe"
pre-commit run --all-files
```

### 4.2 Windows CMD
```cmd
python -m venv .venv_ci
.\.venv_ci\Scripts\activate.bat
python -m pip install -U pip
pip install -e ".[ci]"
pip install pre-commit

pre-commit install
set "RAG_PYTHON=%CD%\\.venv_ci\\Scripts\\python.exe"
pre-commit run --all-files
```

说明：
- `pre-commit install` 会把 git hook 安装到 `.git/hooks/pre-commit`。
- `RAG_PYTHON` 用于固定解释器，避免多 venv 场景下误选。

## 5) 运行方式（手动 / 提交前钩子）
- 自动触发：执行一次 `pre-commit install`，以后 `git commit` 会自动触发。
- 手动触发：在仓库根目录执行 `pre-commit run --all-files`，用于全量检查。

## 6) 环境变量设置（PowerShell / CMD / 用户变量）
本仓库 hooks 通过 `tools/rag_python.py` 中转，以下示例以 `RAG_PYTHON` 为主。

### 6.1 PowerShell（当前会话）
```powershell
$env:RAG_PYTHON = "$PWD\\.venv_ci\\Scripts\\python.exe"
$env:RAG_VENV_PICK = "first"
$env:RAG_VENV_GLOBS = "**/.venv_ci/Scripts/python.exe;**/venv_*/Scripts/python.exe"
```

### 6.2 Windows CMD（当前会话）
```cmd
set "RAG_PYTHON=%CD%\\.venv_ci\\Scripts\\python.exe"
set "RAG_VENV_PICK=first"
set "RAG_VENV_GLOBS=**/.venv_ci/Scripts/python.exe;**/venv_*/Scripts/python.exe"
```

### 6.3 持久化到用户变量（Windows）
CMD（写入用户变量，需新开终端生效）：
```cmd
setx RAG_PYTHON "%CD%\\.venv_ci\\Scripts\\python.exe"
```

PowerShell（写入用户变量，需新开终端生效）：
```powershell
[Environment]::SetEnvironmentVariable(
  "RAG_PYTHON",
  "$PWD\\.venv_ci\\Scripts\\python.exe",
  "User"
)
```

> 注意：持久化设置不影响当前会话，如需立即生效，请同时在当前会话里用 `set` / `$env:` 赋值一次。

### 6.4 查看当前值/验证是否生效
PowerShell：
```powershell
$env:RAG_PYTHON
Get-Item Env:RAG_PYTHON
```

CMD：
```cmd
echo %RAG_PYTHON%
```

## 7) 解释器选择与环境变量含义
- `RAG_PYTHON`：显式指定解释器路径（绝对或相对仓库根）。
- `VIRTUAL_ENV` / `CONDA_PREFIX`：若已激活 venv/conda，会优先使用对应解释器。
- `RAG_VENV_GLOBS`：自定义查找范围（`;` 或 `:` 分隔）。
- `RAG_VENV_PICK`：多候选时的策略（`error` 或 `first`）。

## 8) 常见问题
- 找不到解释器：先确认 `.venv_ci` 是否存在，再设置 `RAG_PYTHON`。
- 找到多个解释器：设置 `RAG_PYTHON`，或临时设 `RAG_VENV_PICK=first`。
- 提交时未拦截：确认已运行 `pre-commit install` 且仓库有 `.pre-commit-config.yaml`。
- setx / SetEnvironmentVariable 后无效：新开终端再试。

## 9) 相关文档
- [PR/CI Lite 门禁（快速回归）](ci_pr_gates.md)
- [Preflight Checklist（重构/换机/换环境后必跑）](PREFLIGHT_CHECKLIST.md)
- [rag_python.py 作为 pre-commit 入口中转](../../tools/rag_python.md)

## 10) 参考
- pre-commit 官方文档（Installation / Quick start）：https://pre-commit.com/#install
- pre-commit 官方文档（Run against all files）：https://pre-commit.com/#4-optional-run-against-all-the-files
- Windows CMD `set` 命令（环境变量）：https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/set_1
- Windows CMD `setx` 命令（持久化用户/系统变量）：https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setx
- PowerShell `about_Environment_Variables`：https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_environment_variables?view=powershell-7.4
