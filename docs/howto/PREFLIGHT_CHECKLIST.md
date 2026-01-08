---
title: Preflight Checklist（重构/换机/换环境后必跑）
version: 0.1
last_updated: 2026-01-06
scope: "本地门禁序列：在变更入口/依赖/环境后，快速确认系统仍可用"
owner: zhiz
---

# Preflight Checklist（重构/换机/换环境后必跑）

> 目的：把“容易因环境/入口/契约漂移导致返工”的检查固化为**最小可执行序列**。  
> 适用：重构后、换机器/换盘符后、重建 venv 后、升级关键依赖后、合并大 PR 前。  
> 原则：只收录高频且人工不可靠的检查；每条必须有**命令 + PASS 条件**。

## 目录
- [0. 使用方式](#0-使用方式)
- [1. Quick Path：最小必跑（推荐）](#1-quick-path最小必跑推荐)
- [2. Extended：需要时再跑（可选）](#2-extended需要时再跑可选)
- [3. 常见失败与处理](#3-常见失败与处理)
- [4. 更新规则](#4-更新规则)

---

## 0. 使用方式

- 默认在 Windows CMD/PowerShell 下执行（命令示例以 CMD 为主）。
- 约定：任何一步 FAIL 时，先不要继续跑后续大步骤；先修复并复跑本步。
- 入口对齐：若你只想“一条命令跑完”，优先使用本项目的 CI Lite 脚本（见 Quick Path 第 1 条）。

---

## 1. Quick Path：最小必跑（推荐）

> 目标：在不触发大规模 embedding/chroma 构建的情况下，确认“工具链/契约/文档引用/测试”未漂移。

### 1.1 跑 CI Lite 门禁（推荐单入口）
**命令（CMD）**
```cmd
tools\run_ci_gates.cmd
```
**PASS 条件**
- 进程退出码为 0（无 `[FATAL]` / `Traceback` / `pytest FAIL`）
- 关键检查均显示 PASS（以脚本输出为准）

> 说明：该命令是最小集合入口；若你只愿意跑一条命令，跑它。

### 1.2 预检 pyproject / TOML 与环境基础一致性
**命令（CMD）**
```cmd
python tools\check_pyproject_preflight.py --ascii-only
```
**PASS 条件**
- 输出无 `[FATAL]`，退出码为 0

### 1.3 校验 CLI entrypoints（入口一致性）
**命令（CMD）**
```cmd
python tools\check_cli_entrypoints.py
```
**PASS 条件**
- 输出列出的 `console_scripts` 与 scripts 目录 wrapper 一致（工具输出无 FAIL）

### 1.4 校验 Markdown 引用与文档契约（防文档漂移）
**命令（CMD）**
```cmd
python tools\check_md_refs_contract.py
```
**PASS 条件**
- 输出无 FAIL，退出码为 0

### 1.4b 文档引用一致性门禁（docs↔code 对齐 / 断链 / 计划项占位）
**命令（CMD）**
```cmd
python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict
```

**PASS 条件**
- `STATUS: PASS` 且退出码为 0

**常见修复路径（本地）**
- 先允许自动修复（会改写 md）：  
  `python tools\verify_postmortems_and_troubleshooting.py`
- 再回到严格验证：  
  `python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict`

### 1.5 跑单元/轻量测试（若仓库包含 pytest）
**命令（CMD）**
```cmd
pytest -q
```
**PASS 条件**
- `0 failed`（允许 `skipped`，但若新增了门禁类测试不应被跳过）

---

## 2. Extended：需要时再跑（可选）

### 2.1 含 embed 的 CI 门禁（更重）
**命令（CMD）**
```cmd
tools\run_ci_gates.cmd --with-embed
```
**PASS 条件**
- 退出码为 0；且 embed 相关检查 PASS

### 2.2 验证 Stage-1 管线（更接近端到端）
> 若你刚动了抽取/分块/索引等主链路，建议跑一次 Stage-1 验证脚本。

**命令（CMD）**
```cmd
python tools\verify_stage1_pipeline.py
```
**PASS 条件**
- 退出码为 0；输出提示验证通过（以脚本输出为准）

### 2.3 验证报告 schema/单报告输出（防契约漂移）
**命令（CMD）**
```cmd
python tools\verify_reports_schema.py
```
**PASS 条件**
- 退出码为 0；schema 校验无错误

---

## 3. 常见失败与处理

- 依赖缺失/可选依赖：优先参考 [PR/CI Lite 门禁说明](ci_pr_gates.md) 与 [排障手册](TROUBLESHOOTING.md)。
- 入口点不一致（console_scripts 缺失/路径漂移）：先修复 editable install 或 PATH/venv 激活，再复跑 1.3。
- 文档引用检查失败：先修复被引用文件路径/编码，再复跑 1.4。

---

## 4. 更新规则

- 新增条目条件（同时满足至少 2 条）：
  1) 属于关键不变量（破坏会导致统计/契约失真）
  2) 高频复发或代价高（返工/重建/重跑成本高）
  3) 人工目测不可靠（必须脚本化才能稳定）
- 任何新增条目必须同时写清：
  - 命令
  - PASS 条件（可被观察到的字段）
  - 对应的失败模式（在 `../explanation/LESSONS.md` 里补一条经验或回链）
