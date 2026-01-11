---
title: Policy（Conftest / Rego）使用说明（流程与配置不变量）
version: v1.1
last_updated: 2026-01-11
---

# Policy（Conftest / Rego）使用说明

> 目标：把“仓库契约/工作流不变量”写成 **policy-as-code**，在 CI/门禁中可重复执行。

## 目录
- [描述](#描述)
- [适用范围](#适用范围)
- [前置条件](#前置条件)
- [安装 conftest](#安装-conftest)
- [快速开始](#快速开始)
- [输入与输出](#输入与输出)
- [常见失败与处理](#常见失败与处理)
- [关联文档](#关联文档)

## 描述

本目录包含 Conftest(Rego) 策略，主要约束两类内容：

1) **SSOT 与契约不变量**（`docs/reference/reference.yaml`）
   - 例如：退出码常量、报告路径、schema 路径、policy 输入集等。
2) **CI 工作流不变量**（`.github/workflows/ci.yml`）
   - 例如：必须包含 gate runner step；必须上传 `gate_report.json` 作为工件。

策略设计原则：
- **确定性**：只读输入文件，不依赖网络、不依赖 embedding/chroma。
- **primary-first**：以仓库内 SSOT/config/workflow 作为事实来源。
- **低耦合**：仅做“流程/契约”的最小强约束，不把业务逻辑塞进 policy。

注意：Conftest v0.60+ 默认使用 Rego v1。策略文件使用 `import rego.v1`。

## 适用范围

- CI：强制执行，防止门禁口径/工作流被悄悄改坏。
- 本地：可选执行；若未安装 conftest，gate runner 会 SKIP（本地不阻断）。

## 前置条件

- 参考 SSOT：`docs/reference/reference.yaml`
  - `policy.conftest.version` 为推荐版本（CI 会按此版本安装）。

## 安装 conftest

> 推荐：**优先使用“Release 二进制 / Go install（可固定版本）”**，确保与 SSOT 的 `policy.conftest.version` 一致。
> 
> 说明：Homebrew / Scoop 通常安装“最新版本”，可能与 SSOT 不一致（不影响使用，但可能导致 CI 与本地行为差异）。

### 本地安装指引: [本地安装](../docs/howto/offline_conftest.md)

### 方式 A：Release 二进制（推荐：可固定版本）

- **Linux（与 CI 同口径）**

```bash
# 例：固定安装 v0.61.0（请以 docs/reference/reference.yaml 为准）
VERSION="0.61.0"
SYSTEM="$(uname -s)"   # Linux
ARCH="$(uname -m)"     # x86_64 / aarch64
curl -fsSL -o conftest.tar.gz \
  "https://github.com/open-policy-agent/conftest/releases/download/v${VERSION}/conftest_${VERSION}_${SYSTEM}_${ARCH}.tar.gz"
tar xzf conftest.tar.gz conftest
sudo mv conftest /usr/local/bin/conftest
conftest --version
```

- **macOS**
  - 与 Linux 同方法；注意 `SYSTEM` 为 `Darwin`。

- **Windows（PowerShell）**
  - 推荐做法：从 GitHub Releases 下载对应 `vX.Y.Z` 的 Windows 资产并放入 PATH。
  - 如果你希望脚本化安装：请先在 Releases 页面确认资产文件名（不同架构可能不同）。

### 方式 B：Homebrew（macOS / Linux）

```bash
brew install conftest
conftest --version
```

### 方式 C：Scoop（Windows）

```powershell
scoop install conftest
conftest --version
```

### 方式 D：Docker（无需本机安装）

```bash
docker run --rm -v "${PWD}:/project" \
  openpolicyagent/conftest test /project/docs/reference/reference.yaml /project/.github/workflows/ci.yml -p /project/policy
```

### 方式 E：Go install（可固定版本）

```bash
# 例：固定安装 v0.61.0（请以 docs/reference/reference.yaml 为准）
go install github.com/open-policy-agent/conftest@v0.61.0
conftest --version
```

## 快速开始

### 1) 直接运行 conftest（本地/CI 通用）

```bash
conftest test docs/reference/reference.yaml .github/workflows/ci.yml -p policy
```

### 2) 通过 gate runner 触发（推荐主线）

```bash
python tools/gate.py --profile ci --root .
```

说明：
- 当 SSOT 中 `policy.enabled=true` 且系统能找到 `conftest` 时，gate runner 会执行 policy。
- 若找不到 conftest：policy step 会标记为 SKIP（默认不阻断本地）。

## 输入与输出

### Inputs

按 SSOT（`docs/reference/reference.yaml`）定义：
- `docs/reference/reference.yaml`
- `.github/workflows/ci.yml`

### Outputs

- conftest 输出到 stdout。
- 通过 gate runner 运行时，日志写入：
  - `data_processed/build_reports/gate_logs/policy_conftest.log`

## 常见失败与处理

1) **conftest 未安装（本地）**
- 现象：gate 中 policy step 显示 `SKIP note=conftest_missing`。
- 处理：这不是失败；若你希望本地也强制执行，安装 conftest 后复跑。

2) **policy deny（FAIL）**
- 现象：conftest 输出 `FAIL - ...`；gate 汇总为 FAIL。
- 原因：CI 工作流缺少 gate step、未上传 gate_report，或 SSOT 中关键字段被改动。
- 处理：按输出信息修复对应文件；policy 的目标是强制“流程不变量”。

3) **policy 输入集无效（ERROR）**
- 现象：`policy.conftest.inputs missing or invalid`。
- 处理：修复 `docs/reference/reference.yaml` 的 `policy.conftest.inputs`。

## 关联文档

- [Gate runner](../tools/gate_README.md)
- [PR/CI Lite 门禁主线](../docs/howto/ci_pr_gates.md)
- [SSOT（机器可读）](../docs/reference/reference.yaml)
