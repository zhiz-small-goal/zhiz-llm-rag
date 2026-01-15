---
title: "Postmortem｜落盘报告顺序契约：汇总置顶 + 严重度排序（FAIL/ERROR 优先）"
version: 1.0
last_updated: 2026-01-15
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "tools.reporting / report_order（file report ordering）"
  severity: P3
---

# Postmortem｜落盘报告顺序契约：汇总置顶 + 严重度排序（FAIL/ERROR 优先）

## 目录（TOC）
- [0) 元信息（YAML）](#0-元信息yaml)
- [1) 总结（Summary）](#1-总结summary)
- [2) 预期 vs 实际（Expected vs Actual）](#2-预期-vs-实际expected-vs-actual)
- [3) 证据账本（Evidence Ledger）](#3-证据账本evidence-ledger)
- [4) 复现（MRE：最小可复现）](#4-复现mre最小可复现)
- [5) 排查过程（Investigation）](#5-排查过程investigation)
- [6) 根因分析（RCA）](#6-根因分析rca)
- [7) 修复与处置（Mitigation & Fix）](#7-修复与处置mitigation--fix)
- [8) 回归测试与门禁（Regression & Gates）](#8-回归测试与门禁regression--gates)
- [9) 写回（Write-back：LESSONS / PREFLIGHT / HANDOFF / REFERENCE）](#9-写回write-backlessons--preflight--handoff--reference)
- [10) 行动项（Action Items）](#10-行动项action-items)

---

## 0) 元信息（YAML）
见本文顶部 YAML。

## 1) 总结（Summary）
### 发生了什么
多个“步骤验收脚本”会落盘 JSON 报告到 `data_processed/build_reports/`。在 VS Code 直接打开 JSON 时：
- 关键汇总字段（`summary/metrics/...`）并不总在顶部；
- 明细（`results/cases/items/...`）中 FAIL/ERROR 项可能被 PASS 项夹在中间，导致阅读与定位成本上升；
- 由于不同脚本各自构建 dict/list，序列化顺序缺乏统一契约，跨脚本体验不一致。

### 影响面
- 人类阅读：需要滚动/搜索才能找到失败项与核心汇总；
- 差异对比：同一语义变更在 JSON diff 里噪声偏大（失败项不聚合）。

### 处置结果
引入统一归一化函数 `prepare_report_for_file_output()`，在“写文件”路径上集中做两件事：
1) 汇总块置顶；
2) 明细按严重度稳定排序（ERROR/FAIL 在前，PASS/OK 在后）。

## 2) 预期 vs 实际（Expected vs Actual）
- 预期（文件输出）：
  - JSON 顶部优先出现 `summary/metrics/buckets/counts/totals`；
  - 明细列表中 `ERROR/FAIL` 项集中在列表前部，`PASS/OK` 放后；
  - 字段语义不变，仅影响序列化顺序。
- 实际（修复前）：
  - 汇总与失败项的可视优先级依赖“脚本构造顺序”，无稳定保证。

## 3) 证据账本（Evidence Ledger）
- 触发/场景：
  - 在本地或 CI 产出 `data_processed/build_reports/*.json`，用 VS Code 打开阅读。
- 修复点（代码）：
  - `src/mhy_ai_rag_data/tools/report_order.py`：实现 `prepare_report_for_file_output()`（汇总置顶 + 严重度排序）。
  - `src/mhy_ai_rag_data/tools/reporting.py`：落盘前调用 `prepare_report_for_file_output(report)`。
  - `src/mhy_ai_rag_data/tools/gate.py`：写 `gate_report.json` 时调用 `prepare_report_for_file_output(obj)`。
- 关联文档：
  - `docs/reference/REFERENCE.md`：补充“落盘顺序（人类可读约定）”。

## 4) 复现（MRE：最小可复现）
> 目标：生成一份落盘 JSON，并验证“汇总在上、失败在前”。

- 环境：仓库根目录；Python 版本按项目约束。
- 命令（示例一，生成 gate_report）：
  - `python tools/gate.py --profile ci --root .`
  - 期望：`data_processed/build_reports/gate_report.json` 顶部出现 `summary`，且 `results` 内 FAIL/ERROR 项排在 PASS 前。
- 命令（示例二，生成任意 write_report 产物）：
  - 运行任一会调用 `tools.reporting.write_report()` 的脚本并指定 `--json-out data_processed/build_reports/<name>.json`。

## 5) 排查过程（Investigation）
1) 观察 JSON 文件的阅读顺序与 diff 噪声；
2) 发现不同脚本构建 dict/list 的顺序差异导致体验不一致；
3) 决定把“人类可读顺序”集中到“写文件出口”统一处理，避免每个脚本各自实现。

## 6) 根因分析（RCA）
- 直接原因：落盘 JSON 的序列化顺序由上游数据结构的插入顺序决定；缺乏统一的“人类可读顺序契约”。
- 系统性原因：
  - 写文件出口不统一（部分脚本自行 `json.dump`，部分通过公共写入器）；
  - 缺少门禁/清单验证“报告可读性契约”（属于迁移期缺失控制点）。

## 7) 修复与处置（Mitigation & Fix）
- 修复策略：
  - 新增 `report_order.py`，仅在“写文件”路径生效；
  - 不改字段语义，只做稳定排序与 key 重排；
  - 在 `tools.reporting.write_report()` 与 `tools.gate` 的落盘入口接入。
- 关键取舍：
  - 选择“集中出口归一化”而非“逐脚本手工排序”，避免规则漂移与漏改。

## 8) 回归测试与门禁（Regression & Gates）
- 建议的产物级回归：
  - 打开 JSON：确认 `summary` 在顶部、FAIL/ERROR 集中在前；
  - 对比修复前后：字段集合与关键值一致（只允许顺序变化）。
- 门禁策略建议：
  - 迁移期：允许 WARNING（不阻断），但必须在复盘与行动项中跟踪；
  - 对“会导致统计/契约失真”的变更升级为 FAIL（退出码 2）。

## 9) 写回（Write-back：LESSONS / PREFLIGHT / HANDOFF / REFERENCE）
- REFERENCE：已补充“落盘顺序（人类可读约定）”。
- LESSONS：新增一条“报告可读性契约应集中在写入出口”的经验条目（回链本文）。
- PREFLIGHT / HANDOFF：
  - 本次未新增必跑命令与默认值口径变更；因此不更新 HANDOFF（避免噪声写回）。

## 10) 行动项（Action Items）
- [DONE] 建立 `prepare_report_for_file_output()` 作为“文件输出”统一顺序归一化入口。
- [TODO] 对仍绕过公共写入器的落盘点做收敛（若后续发现新增脚本自行 `json.dump`）。
- [TODO] 在 Preflight 或 gate 中增加“产物层可读性契约检查”（按触发器阈值逐步收紧）。
