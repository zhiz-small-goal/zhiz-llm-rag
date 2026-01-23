---
title: "check_doc_system_gate 使用说明"
version: "v0.1"
last_updated: "2026-01-23"
timezone: "America/Los_Angeles"
owner: "zhiz"
status: "active"
---

# check_doc_system_gate 使用说明

## 目录

- [目的](#目的)
- [输入](#输入)
- [输出](#输出)
- [运行命令（Windows CMD）](#运行命令windows-cmd)
- [规则与严重度](#规则与严重度)
- [期望结果](#期望结果)
- [常见失败与处理](#常见失败与处理)

## 目的

对 Level 3 文档体系做最小门禁检查，聚焦三类“高频回归点”：
1) 仓内链接（路径/锚点）是否可达；  
2) 关键术语是否统一（避免 `index_stage.json` 等误写）；  
3) front-matter 必填字段是否齐全（便于后续机械化处理与索引）。  

脚本输出 **Report v2（schema_version=2）**，可与项目现有的报告渲染/聚合路径对齐。

## 输入

- `--root`：仓库根目录（默认 `.`）
- `--doc-map`：Step1 产物 `docs/explanation/doc_map.json`（默认该路径）

## 输出

- `--out`：JSON 报告（默认 `data_processed/build_reports/doc_system_gate_report.json`）
- `--md-out`：可选 Markdown 报告（建议同目录落盘）

## 运行命令（Windows CMD）

```cmd
python tools\check_doc_system_gate.py --root . --doc-map docs\explanation\doc_map.json --out data_processed\build_reports\doc_system_gate_report.json --md-out data_processed\build_reports\doc_system_gate_report.md
```

## 规则与严重度

- `reference/runbook/README`：作为入口与契约文档，问题更倾向以 `FAIL/ERROR` 呈现。  
- `archive/postmortem`：以历史叙事为主，默认把同类问题降级为 `WARN`（避免阻塞主线）；但仍会在报告中显式列出。  

关键规则：
- **禁止术语**：`index_stage.json`、`index_state.stage.json`（应为 `index_state.stage.jsonl`）  
- **policy=reset 两阶段解释**：若出现 `policy=reset` 或 `on-missing-state`，文本中需同时覆盖“默认评估/最终生效”。  
- **仓内链接**：相对路径必须存在；`#anchor` 必须能在目标文档标题中解析到对应锚点。  

## 期望结果

- 在你完成 Step2/3 的 SSOT 收敛后，入口文档（SSOT/OPERATION_GUIDE/tools README）应逐步达到 `PASS/WARN` 为主；  
- 若出现 `FAIL/ERROR`，报告中的 `loc_uri` 可直接跳转定位到问题位置。  

## 常见失败与处理

1) 现象：`doc_map not found`  
   - 原因：未生成或路径写错。  
   - 处理：先运行 `python tools\gen_doc_inventory.py --root . --include-untracked --write` 生成 `docs/explanation/doc_map.json`。  

2) 现象：大量 `锚点不存在`  
   - 原因：标题改动导致旧链接锚点失效。  
   - 处理：以目标文档标题为准更新链接；必要时在目标文档保留旧标题的兼容节（仅用于锚点兼容）。  

3) 现象：`front-matter 缺字段`  
   - 原因：旧文档未采用统一模板。  
   - 处理：对入口文档优先补齐；对 archive/postmortem 可先以 `WARN` 方式观察，再在 Step5 机械化补齐。  
