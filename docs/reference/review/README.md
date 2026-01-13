---
title: 审查规范（Review Spec）入口
version: v1.0
last_updated: 2026-01-12
---

# 审查规范（Review Spec）


本目录提供“审查规范”的 **单一真源（SSOT）** 与其 **生成产物**，用于把审查口径固化为仓库资产，降低口头说明与个人经验依赖。

## 目录
- [1. 你应该读哪一个文件](#1-你应该读哪一个文件)
- [2. 文件清单](#2-文件清单)
- [3. 与 Gate/CI 的集成](#3-与-gateci-的集成)
- [4. 演进接口（extensions）](#4-演进接口extensions)

## 1. 你应该读哪一个文件

- 人类阅读（Reference）：[`REVIEW_SPEC.md`](REVIEW_SPEC.md)
- 如何在 PR 中执行审查（How-to）：[`../../howto/review_workflow.md`](../../howto/review_workflow.md)
- 机器可读 SSOT：[`review_spec.v1.json`](review_spec.v1.json)

## 2. 文件清单

- `review_spec.v1.json`：SSOT（机器可读，唯一真源）
- `REVIEW_SPEC.md`：生成产物（人类可读，用于审查引用）
- `review_spec.schema.json`：SSOT 的最小 JSON Schema（用于本地/工具校验）
- `review_report_template.md`：审查报告模板（人类可读）
- `review_report_template.json`：审查报告模板（机器可读）

## 3. 与 Gate/CI 的集成

本仓库通过 `tools/validate_review_spec.py` 将以下不变量纳入 gate：

1) SSOT 结构校验（必需字段、枚举、优先级覆盖等）  
2) 生成产物一致性校验（`REVIEW_SPEC.md` 必须与 SSOT 对应的生成结果一致）

常用命令：

```bash
# Gate（单入口）
python tools/gate.py --profile fast --root .

# 仅校验审查规范 SSOT + 生成产物一致性
python tools/validate_review_spec.py --root .

# 刷新生成产物（在修改 SSOT 后运行）
python tools/generate_review_spec_docs.py --root . --write
```

## 4. 演进接口（extensions）

- SSOT 顶层 `extensions`：用于新增维度/字段（优先扩展，后续再决定是否升级主结构版本）
- `reporting.extensions`：用于报告字段扩展（统计指标、回归对照组等）

版本策略见 `REVIEW_SPEC.md` 的“演进接口与版本策略”一节。
