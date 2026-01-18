---
title: Getting Started（教程）：跑通 Stage-1 + PR/CI Lite 回归
version: v1.0
last_updated: 2026-01-13
---

# Getting Started（教程）：跑通 Stage-1 + PR/CI Lite 回归


> 目标：在不下载大模型、不构建 Chroma 的前提下，跑通一次可复现的 PASS 基线（Golden Path）。

## 目录
- [Getting Started（教程）：跑通 Stage-1 + PR/CI Lite 回归](#getting-started教程跑通-stage-1--prci-lite-回归)
  - [目录](#目录)
  - [1) 前置条件](#1-前置条件)
  - [2) 安装（Stage-1 + CI 工具集）](#2-安装stage-1--ci-工具集)
  - [3) 运行 PR/CI Lite 门禁（必须 PASS）](#3-运行-prci-lite-门禁必须-pass)
  - [4) 跑一遍最小数据链路（inventory → units → validate）](#4-跑一遍最小数据链路inventory--units--validate)
  - [5) 你现在可以做什么（下一步）](#5-你现在可以做什么下一步)

## 1) 前置条件
- embed 需 Python 3.12, 见[embed所需版本详情](../howto/OPERATION_GUIDE.md#step-0环境与依赖安装core-vs-embed避免在-python-313-及以上误装-stage-2)
- Windows / Linux 均可；仓库基线 Python >= 3.11，推荐 Python 3.12
- 在仓库根目录执行（与 `pyproject.toml` 同级）

## 2) 安装（Stage-1 + CI 工具集）
### 2.1 Windows CMD 一键（推荐：不易误用）
> 说明：该脚本会在仓库根目录下自动创建/复用 `.venv_ci`，先跑 `pyproject` preflight，
> 再安装 `.[ci]` 并执行 PR/CI Lite 门禁；任何一步失败都会立刻停止。

```cmd
tools\run_ci_gates.cmd
```

### 2.2 手动安装（如果你想分步观察输出）
```cmd
python tools\check_pyproject_preflight.py --ascii-only
python -m venv .venv_ci
.\.venv_ci\Scripts\activate
python -m pip install -U pip
pip install -e ".[ci]"
```

## 3) 运行 PR/CI Lite 门禁（必须 PASS）
```cmd
python tools\check_cli_entrypoints.py
python tools\check_md_refs_contract.py
pytest -q
```
验收口径：
- entrypoints 门禁输出包含 `[PASS]`
- pytest 输出 `1 passed`（或更多，但必须全通过）

## 4) 跑一遍最小数据链路（inventory → units → validate）
> 说明：如果你本地没有 `data_raw/` 或资料为空，此步骤可跳过；Golden Path 的关键是上面的门禁可复现 PASS。

```cmd
python make_inventory.py
python extract_units.py
python validate_rag_units.py --max-samples 50
```

## 5) 你现在可以做什么（下一步）
- 进入日常操作指南：[`howto/OPERATION_GUIDE.md`](../howto/OPERATION_GUIDE.md)
  - Stage-2（embed/build/check/eval）的主线也在这里；从 Step 4（plan）开始逐步跑到 Step 6（check）。
- 迷路/换机时先跑：`rag-status`，快速判断当前进度与下一步命令（详见：[`howto/rag_status.md`](../howto/rag_status.md)）。
- **旧库迁移提示**：如果你已有 `chroma_db/`（旧版本构建）且 `rag-status` 反复提示 Step6 为 STALE，先补写一次 `data_processed/index_state/db_build_stamp.json`，再重跑一次 `rag-check`（契约详见：[`reference/index_state_and_stamps.md`](../reference/index_state_and_stamps.md)）。

- 查看排障手册：[`docs/howto/TROUBLESHOOTING.md`](../howto/TROUBLESHOOTING.md)
- 查阅契约与参考：[`docs/reference/REFERENCE.md`](../reference/REFERENCE.md)
- 了解报告输出规范（SSOT）：[`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`](../reference/REPORT_OUTPUT_ENGINEERING_RULES.md)
