---
title: gate.py / rag-gate 使用说明（单入口 Gate：Schema + Policy + 可审计报告）
version: v1.2
last_updated: 2026-01-12
---

# gate.py / rag-gate 使用说明（单入口 Gate）

> 目标：用**一条命令**跑完 PR/CI Lite 门禁，并生成**确定性可审计产物**（`gate_report.json` + logs）。

## 目录


> **字段约定**：`results[*].note` 为可选字段；当没有补充说明时 **不输出该字段**（不会写 `null`）。若输出，则必须为字符串。
- [描述](#描述)
- [适用范围](#适用范围)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [参数与用法](#参数与用法)
- [执行流程](#执行流程)
- [退出码与判定](#退出码与判定)
- [产物与副作用](#产物与副作用)
- [人类可读报告](#人类可读报告)
- [常见失败与处理](#常见失败与处理)
- [关联文档](#关联文档)


## 描述

本仓库提供“单入口 Gate runner”，用于把 PR/CI Lite 的多条门禁命令收敛为：

- **SSOT 驱动**：门禁顺序、输出路径、schema/policy 输入集由 `docs/reference/reference.yaml` 统一管理。
- **可审计产物**：固定输出 `data_processed/build_reports/gate_report.json`，并为每个 step 写入独立日志。
- **Schema + Policy**：
  - 生成后对 `gate_report.json` 做 JSON Schema 自校验（需要 `jsonschema`）。
  - 支持用 Conftest(Rego) 执行“流程/配置不变量”检查（CI 上强制；本地缺 conftest 时会 SKIP）。

入口有三种（行为一致）：
1) **兼容入口（wrapper）**：`python tools/gate.py ...`
2) **模块方式**：`python -m mhy_ai_rag_data.tools.gate ...`
3) **console script**：`rag-gate ...`（推荐：安装后更稳定）


## 适用范围

- 重构后快速自检：入口点、文档契约、最小测试是否回归。
- PR/CI 的确定性门禁（不触发 embedding/chroma）。
- 对外发布前：确保“工作流/门禁口径”不被悄悄改坏（可用 `profile=release` 增加 repo health 检查）  


## 前置条件

- Python 3.11+。
- 若要启用 schema 校验：安装 `.[ci]`（包含 `jsonschema`）。
- 若要启用 policy：安装 `conftest`。
  - **完全离线**可选：将 conftest 二进制 vendoring 到 `third_party/conftest/`（见 `docs/howto/offline_conftest.md`）。
  - 或通过 `CONFTEST_BIN` 指定二进制路径（适合内网制品库分发）。


## 快速开始

### 1) 推荐（已安装依赖后）

```bash
pip install -e ".[ci]"
rag-gate --profile ci --root .
```

### 2) 不依赖 console script（兼容入口）

```bash
pip install -e ".[ci]"
python tools/gate.py --profile ci --root .
```

### 3) 更快的 fast profile（本地）

```bash
python tools/gate.py --profile fast --root .
```


## 参数与用法

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root <path>` | `.` | 仓库根目录（会 `resolve()`）。 |
| `--profile <fast\|ci\|release>` | `ci` | 门禁组合；定义在 `docs/reference/reference.yaml`。 |
| `--ssot <path>` | `docs/reference/reference.yaml` | SSOT 配置路径（相对 `--root`）。 |
| `--json-out <path>` | 空 | 覆盖 `gate_report.json` 输出路径（相对/绝对均可）。 |


## 执行流程

1) 读取 SSOT：`docs/reference/reference.yaml`。
2) 解析 profile → steps：按 SSOT 指定顺序逐条执行。
   - `profile=ci/release` 默认包含 `check_ruff` / `check_mypy`；`RAG_RUFF_FORMAT=1`、`RAG_MYPY_STRICT=1` 可选收紧。
3) 每个 step：捕获 stdout+stderr → 写入 `gate_logs/<step_id>.log`。
4) 生成 `gate_report.json`：包含每步 argv/rc/status/耗时与 summary。
5) 自校验（Schema）：用 `schemas/gate_report_v1.schema.json` 校验 `gate_report.json`。
   - 若 schema 校验失败：判定为 **ERROR**（rc=3）。
6) Policy（Conftest）：
   - SSOT `policy.enabled=true` 时，尝试运行 `conftest test <inputs...> -p policy/`。
   - conftest 搜索顺序：`CONFTEST_BIN` → `third_party/conftest/v<version>/<system>_<arch>/...` → `PATH`。
   - 若找不到 conftest：默认记录为 **SKIP**（不阻断本地）；可在 SSOT 中设置 `policy.conftest.required=true` 强制缺失时 ERROR。


## 退出码与判定

Gate runner 统一遵循项目退出码契约：

| 退出码 | 含义 | 说明 |
|---:|---|---|
| 0 | PASS | 所有门禁通过（允许存在 SKIP）。 |
| 2 | FAIL | 门禁失败（例如 pytest fail、契约检查 fail、policy deny）。 |
| 3 | ERROR | 环境/运行异常（SSOT 读取失败、schema 校验失败、conftest 异常等）。 |

注意：
- `conftest` 的原始返回码会被归一化：`1 → 2(FAIL)`，其它非 0 → `3(ERROR)`。
- “自身产物不满足 schema”被视为 **契约破坏**，会直接 `ERROR(3)`。


## 产物与副作用

- 报告：`data_processed/build_reports/gate_report.json`
- 日志目录：`data_processed/build_reports/gate_logs/`
  - 例如：`pytest.log`、`check_tools_layout.log`、`policy_conftest.log`
- repo health 报告（release profile）：`data_processed/build_reports/repo_health_report.json`
- 人类可读摘要（可选）：`data_processed/build_reports/gate_report.md`
  - 由 `python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md` 生成
- 默认不修改仓库源文件；但会创建/更新上述产物目录。


## 人类可读报告

- `gate_report.json` 为机器可读主产物，人类可读摘要从 JSON 派生。
- 生成人类可读摘要（Markdown）：
  ```bash
  python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md
  ```
- 完成后，可直接打开 `data_processed/build_reports/gate_report.md` 快速扫描 FAIL/ERROR step 与 log 指向。

## 常见失败与处理

1) **SSOT 读取失败（rc=3）**
- 现象：`failed to load SSOT`。
- 原因：路径不对/文件损坏/YAML 非 mapping。
- 处理：确认 `docs/reference/reference.yaml` 存在，或用 `--ssot` 指定。

2) **jsonschema 缺失导致 schema 校验跳过/失败**
- 现象：`schema_validator_missing` warning，或校验异常。
- 原因：未安装 `.[ci]`。
- 处理：`pip install -e ".[ci]"`。

3) **policy 被 SKIP（本地）**
- 现象：`policy_conftest status=SKIP note=conftest_missing`。
- 原因：PATH 没有 conftest。
- 处理：仅依赖 CI/Linux 强制执行；或本地安装 conftest 后复跑。

4) **某 step FAIL（rc=2）**
- 现象：gate summary 为 FAIL；对应 step 的 log 里有具体错误。
- 处理：打开 `data_processed/build_reports/gate_logs/<step>.log` 定位。

5) **Ruff lint/format FAIL**
- 现象：`check_ruff status=FAIL` 或 `ruff` 输出违规。
- 处理：运行 `python tools/check_ruff.py --root .`；需要格式校验时加 `--format` 或 `RAG_RUFF_FORMAT=1`。

6) **mypy FAIL**
- 现象：`check_mypy status=FAIL` 或类型报错。
- 处理：运行 `python tools/check_mypy.py --root .`；需要严格模式时加 `--strict` 或 `RAG_MYPY_STRICT=1`。


## 关联文档

- [PR/CI Lite 门禁主线](../docs/howto/ci_pr_gates.md)
- [view_gate_report 使用说明](view_gate_report_README.md)
- [参考与契约（退出码/报告契约/SSOT）](../docs/reference/REFERENCE.md)
- [SSOT（机器可读）](../docs/reference/reference.yaml)
- [Gate report schema](../schemas/gate_report_v1.schema.json)
- [Policy（Conftest/Rego）](../policy/README.md)
