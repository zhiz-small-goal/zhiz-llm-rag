---
title: schema_validate.py / rag-schema-validate 使用说明（JSON Schema 校验工具）
version: v1.0
last_updated: 2026-01-11
---

# schema_validate.py / rag-schema-validate 使用说明（JSON Schema 校验工具）

> 目标：把“报告/产物 JSON 的结构契约”变成可执行的校验步骤（本地/CI 可复用）。

## 目录
- [描述](#描述)
- [适用范围](#适用范围)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [参数与用法](#参数与用法)
- [退出码与判定](#退出码与判定)
- [常见失败与处理](#常见失败与处理)
- [关联文档](#关联文档)


## 描述

`schema_validate` 用于校验：某个 JSON instance 是否满足给定的 JSON Schema（Draft 2020-12）。

入口有三种（行为一致）：
1) **兼容入口（wrapper）**：`python tools/schema_validate.py ...`
2) **模块方式**：`python -m mhy_ai_rag_data.tools.schema_validate ...`
3) **console script**：`rag-schema-validate ...`（推荐：安装后更稳定）

注意：该工具依赖 Python 包 `jsonschema`；本仓库将其放在 `.[ci]` 可选依赖中。


## 适用范围

- 本地/CI 对产物做“结构契约”回归校验。
- 验证 gate runner 生成的 `gate_report.json` 是否满足 `schemas/gate_report_v1.schema.json`。
- 为新的报告/工件引入 schema 时，作为最小验证器（比写自定义校验脚本更稳定）。


## 前置条件

- Python 3.11+。
- 已安装 `jsonschema`：推荐 `pip install -e ".[ci]"`。


## 快速开始

### 1) 校验 gate report（常用）

```bash
pip install -e ".[ci]"
python tools/gate.py --profile ci --root .
python tools/schema_validate.py --schema schemas/gate_report_v1.schema.json --instance data_processed/build_reports/gate_report.json
```

### 2) 用 console script（安装后）

```bash
pip install -e ".[ci]"
rag-schema-validate --schema schemas/gate_report_v1.schema.json --instance data_processed/build_reports/gate_report.json
```


## 参数与用法

| 参数 | 必填 | 说明 |
|---|:---:|---|
| `--schema <path>` | ✅ | JSON Schema 路径（`.json`）。 |
| `--instance <path>` | ✅ | 要校验的 JSON instance 路径（`.json`）。 |


## 退出码与判定

| 退出码 | 含义 | 说明 |
|---:|---|---|
| 0 | PASS | instance 满足 schema。 |
| 2 | FAIL | instance 不满足 schema（ValidationError）。 |
| 3 | ERROR | 运行异常（读取失败、jsonschema 未安装等）。 |


## 常见失败与处理

1) **jsonschema 未安装（rc=3）**
- 现象：`[ERROR] jsonschema is not installed`。
- 处理：`pip install -e ".[ci]"`。

2) **校验失败（rc=2）**
- 现象：输出 `[FAIL] schema validation failed`，并包含 `message` 与路径定位（若可定位）。
- 处理：
  - 先确认 instance 是否写错文件（路径/环境）；
  - 再对照 `schemas/*.schema.json` 看 required 字段是否缺失。

3) **JSON 读取失败（rc=3）**
- 现象：`failed to load json`。
- 原因：文件不是合法 JSON、编码损坏、路径不存在。
- 处理：先 `cat`/`jq` 验证文件内容与路径。


## 关联文档

- Gate runner：`tools/gate_README.md`
- SSOT（paths/schemas）：`docs/reference/reference.yaml`
- Schemas：`schemas/`