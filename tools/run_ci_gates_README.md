---
title: run_ci_gates.cmd 使用说明
version: v1.0
last_updated: 2026-01-10
---

# run_ci_gates.cmd 使用说明

## 目录
- [描述](#描述)
- [适用范围](#适用范围)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [参数与用法](#参数与用法)
- [执行流程](#执行流程)
- [退出码与判定](#退出码与判定)
- [产物与副作用](#产物与副作用)
- [常见失败与处理](#常见失败与处理)
- [关联文档](#关联文档)


## 描述

`tools/run_ci_gates.cmd` 是 Windows CMD 下的 PR/CI Lite 一键门禁脚本，目标是：
- 以 fail-fast 方式跑完“入口点/契约/最小集成”回归。
- 用最少依赖（仅 Python + pip）完成自检。
- 统一退出码为 {0,2,3}，与项目门禁契约一致。

脚本会自动定位仓库根目录、创建或复用虚拟环境，并按固定顺序执行各个门禁项。

## 适用范围
- Windows 开发环境（CMD 或 PowerShell）。
- 重构后快速自检入口点与契约是否回归。
- PR 前本地快跑，或 CI 中作为轻量门禁入口。

## 前置条件
- Windows 终端可用 `cmd.exe`。
- 已安装 Python 3.11+，并保证 `py` 或 `python` 在 PATH 中。
- 允许访问依赖源（pip install 需要网络或可用的镜像）。
- 如使用 `--with-embed`，建议 Python 3.12，并确保 embed 依赖可安装。
- 如使用 `--no-install`，请先在同一虚拟环境内完成 `pip install -e ".[ci]"`（以及可选的 `.[embed]`）。

## 快速开始

```cmd
tools\run_ci_gates.cmd
```

可选示例：

```cmd
tools\run_ci_gates.cmd --with-embed
tools\run_ci_gates.cmd --no-install
tools\run_ci_gates.cmd --venv .venv_ci_py312
```

PowerShell 里也可直接运行 `.cmd`，或显式用 `cmd /c`：

```powershell
cmd /c tools\run_ci_gates.cmd
```

## 参数与用法

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--with-embed` | 关闭 | 额外安装 `.[embed]` 依赖（用于 Stage-2 相关依赖）。 |
| `--no-install` | 关闭 | 跳过所有 pip install 步骤，仅运行门禁。 |
| `--venv <path>` | `.venv_ci` | 虚拟环境目录（相对路径相对于仓库根目录）。 |

注意：传入未知参数会直接报错并退出（exit code=2）。

## 执行流程

1) 切换到仓库根目录（脚本会以 `tools/` 的上级目录作为根目录）。
2) 检查虚拟环境：
   - 若 `VENV\Scripts\python.exe` 不存在，则自动创建 venv。
   - 查找 base Python 的顺序为：`py -3.12` → `py -3.11` → `py -3` → `python`。
3) 预检门禁（在任何 pip install 之前执行）：
   - `tools/check_pyproject_preflight.py --ascii-only`  
     预检 pyproject/打包基础约束，确保基础元数据可用。
   - `tools/gen_tools_wrappers.py --check`  
     校验受管 wrapper 是否与模板一致。
   - `tools/check_tools_layout.py --mode fail`  
     检查 tools 布局契约与命名冲突。
   - `tools/check_exit_code_contract.py --root .`  
     约束脚本退出码只能落在 {0,2,3}。
4) 依赖安装（可通过 `--no-install` 跳过）：
   - `pip install -U pip`
   - `pip install -e ".[ci]"`
   - 可选：`pip install -e ".[embed]"`
5) 正式门禁：
   - `tools/check_cli_entrypoints.py`
   - `tools/check_md_refs_contract.py`
   - `pytest -q`
6) 全部通过后输出 `[PASS] CI/PR Lite gates OK` 并退出 0。

## 退出码与判定

脚本对所有门禁的退出码做统一归一化：

| 退出码 | 含义 | 说明 |
|---:|---|---|
| 0 | PASS | 所有门禁通过。 |
| 2 | FAIL | 契约/测试失败等“门禁失败”。 |
| 3 | ERROR | 环境或执行异常（依赖、解释器、意外异常）。 |

归一化规则（`gate` 子程序）：
- 0 → 0  
- 2/3 → 原样传递  
- 1 → 2（例如 pytest 失败）  
- ≥4 → 3  
- 其余非预期返回码 → 2

## 产物与副作用
- 可能创建或复用虚拟环境目录（默认 `.venv_ci`）。
- 会在虚拟环境内更新 pip、安装 `.[ci]`（以及可选的 `.[embed]`）。
- 一般不修改仓库文件；如使用传统 editable 安装器，可能产生 `*.egg-info`。
- pytest 会在系统临时目录生成测试临时文件。

## 常见失败与处理

- `[FAIL] unknown arg`  
  参数拼写错误或顺序不正确；按 “参数与用法” 重新传参。

- `[ERROR] cannot find a base Python to create venv`  
  安装 Python 3.11+，确保 `py` 或 `python` 在 PATH。

- `pip install` 失败  
  检查网络/代理；或先在可用网络环境安装依赖，再用 `--no-install` 复用。

- `check_cli_entrypoints` 失败  
  通常是未安装 `.[ci]` 或使用了错误的 venv；确认 `--venv` 指向正确环境。

- `check_tools_layout` / `check_exit_code_contract` 失败  
  根据对应工具的输出定位违反契约的脚本或调用点。

- `pytest -q` 失败  
  查看 pytest 输出定位失败用例，必要时单独运行指定测试进行排查。

## 关联文档
- [PR/CI Lite 门禁（快速回归）](../docs/howto/ci_pr_gates.md)
- [日常操作(详细)](../docs/howto/OPERATION_GUIDE.md)
- [参考与契约（口径、产物、架构）](../docs/reference/REFERENCE.md)
