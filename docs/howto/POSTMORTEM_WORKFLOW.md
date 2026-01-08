---
title: Postmortem Workflow（复盘动作说明书：模板 → LESSONS → PREFLIGHT → HANDOFF）
version: 0.1
last_updated: 2026-01-07
owner: zhiz
status: draft
---

# POSTMORTEM_WORKFLOW目录：
- [目标与适用范围](#目标与适用范围)
- [触发器与门禁策略](#触发器与门禁策略)
- [最小输入集（证据与复现素材）](#最小输入集证据与复现素材)
- [工作流步骤（Write → Derive → Act → Write-back）](#工作流步骤write--derive--act--write-back)
- [写回协议（SSOT 与去漂移）](#写回协议ssot-与去漂移)
- [验收与退出码约定](#验收与退出码约定)
- [常见失败与处理](#常见失败与处理)
- [附录：命名约定与最小模板](#附录命名约定与最小模板)


## 目标与适用范围

本文件定义“复盘动作”的工程化流程：当出现**可复现的故障**、**门禁失败**、或**高价值的工程经验**时，如何用统一模板沉淀证据链，并将可迁移资产写回到：
- 复盘文档（Postmortem，时间线 + 证据链）
- 经验库（LESSONS，原则库/反模式库/控制点）
- 可执行清单（PREFLIGHT_CHECKLIST，门禁命令序列）
- 项目单一真源（HANDOFF，口径/默认值/触发器）

适用范围：本仓库 `docs/` 内所有工程问题复盘；尤其适合“文档与代码口径不一致、工具链缺失、门禁失真、默认值分叉”等系统性问题。


## 触发器与门禁策略

### 触发器（建议至少满足其一就复盘）
1) **门禁失败**：CI 或本地 `--strict` 门禁 FAIL（例如 docs 引用检查、CI preflight、评测回归）。
2) **重复问题**：同类问题在 7 天内重复出现，或修复后回潮。
3) **口径风险**：默认值、路径、schema、指标口径发生变化，可能影响历史对比与可复现性。
4) **高价值经验**：发现可迁移的工程策略（规则、触发器、脚本、检查流程）且具备复用价值。

### 门禁策略（推荐默认）
- 迁移期：允许 WARNING（不阻断），但必须落盘并进入复盘行动项。
- 永久 FAIL：任何会导致统计/契约失真的错误（schema 破坏、关键输出缺失、默认值分叉导致回归不可比）应直接 FAIL。


## 最小输入集（证据与复现素材）

为保证复盘可核验，至少收集以下材料（缺失时在 Postmortem 里显式标注“信息缺口”）：

1) **复现命令**：触发问题的完整命令行（含关键参数）。
2) **期望 vs 实际**：
   - 期望结果（例如 PASS、某个 count、某条文档应被命中）
   - 实际输出（控制台片段 + 结构化报告路径）
3) **产物路径**：指向 `data_processed/...` 或其它明确前缀的产物（避免裸文件名造成歧义）。
4) **环境与版本**：
   - Python 版本、关键依赖版本（若相关）
   - 运行平台（Windows/CMD/PowerShell 等）
   - 当前 commit hash（或 zip 快照日期）
5) **最小样本**：能复现问题的最小输入（例如 1 条 case、1 个 md 文件、1 个 inventory 行）。

建议：把关键命令输出保存到 `data_processed/build_reports/`，并在 Postmortem 的 Evidence Ledger 里引用（文件路径 + 生成命令）。


## 工作流步骤（Write → Derive → Act → Write-back）

> 目标：保证“写的复盘”与“做的修复”之间有可验证闭环。

### Step 1：Write（用模板产出 Postmortem 初稿）
- 做什么：用 `docs/reference/postmortem_prompt_template.md` 生成或手写 Postmortem 初稿。
- 为何：模板强制形成“复现→根因→缺失控制点→行动项→迁移经验”的证据链结构，避免只记录现象。
- 关键点：
  - Facts（有证据）与 Inference（推断）分开写。
  - 复现步骤必须可运行；如果需要外部条件，明确依赖与替代路径。

输出位置（建议）：
- `docs/postmortems/YYYY-MM-DD_postmortem_<topic>.md`
- 同步在 `docs/postmortems/INDEX.md` 增加条目（日期、关键词、文件链接）。

### Step 2：Derive（从 Postmortem 抽取可迁移资产）
- 做什么：从 Postmortem 中抽取 3–10 条“可迁移”结论，分类为：
  - 原则库：如何避免系统性漂移、如何设计门禁/触发器
  - 反模式库：导致故障/回潮的常见写法与组织方式
  - 控制点：应当自动化检查的关键不变量（命令、脚本、阈值）
- 为何：Postmortem 以事件为中心；LESSONS 以长期复用为中心。两者职责不同，必须拆开沉淀。

输出位置：
- 追加到 `docs/explanation/LESSONS.md` 的对应分区（尽量只追加“规则”，不重复时间线）。

### Step 3：Act（实现修复与门禁）
- 做什么：落地实际修复（代码/文档/脚本），并把“缺失控制点”转成可执行门禁。
- 为何：没有门禁的修复容易回潮；没有可执行的验收，复盘就无法闭环。
- 关键点：
  - 对“计划项”脚本：用占位形式 `tools/<name>.py` 表达，不要让读者误以为已内置。
  - 对“运行时工件”：文档引用应尽量使用明确前缀（例如 `data_processed/...`），必要时在检查器里配置忽略。

### Step 4：Write-back（写回三处 SSOT）
- 做什么：把修复结果写回到三个长期入口：
  1) `LESSONS.md`：新增/更新原则、反模式、控制点
  2) `PREFLIGHT_CHECKLIST.md`：把新门禁命令加入 Quick Path 或 Extended（按成本分层）
  3) `HANDOFF.md`：如影响“基线口径/默认值/门禁策略/触发器阈值”，必须同步更新
- 为何：这三处是“新会话/新设备/新成员”最快恢复上下文的入口；缺写回会导致知识断裂。


## 写回协议（SSOT 与去漂移）

### 1) Postmortem（事件真源）
- 只记录与该事件相关的事实、复现、根因与行动项。
- 禁止复制粘贴大量通用规则；通用规则应写入 LESSONS/PREFLIGHT/HANDOFF。

### 2) LESSONS（原则库/反模式库）
- 只收敛“可复用规则”，每条建议包含：
  - 适用范围（何时用/何时不用）
  - 触发器/阈值（何时升级为 FAIL）
  - 最小验收命令（可复制执行）
- 建议使用“别名/同义词”减少检索失败（例如“反模式库/失败模式词表”）。

### 3) PREFLIGHT_CHECKLIST（可执行清单）
- 以“最少命令覆盖最大风险”为目标，分层组织：
  - Quick Path：几分钟内跑完，覆盖最关键的不变量
  - Extended：较耗时，但用于重构/换机/大改后的回归
- 清单项必须具备：
  - 命令
  - 通过判据（PASS/WARN/FAIL）
  - 失败时的下一步指向（链接到 TROUBLESHOOTING 或 Postmortem）

### 4) HANDOFF（单一真源）
- 只保留“当前口径 + 运行契约 + 演进触发器”。
- 任何可能影响对比口径的变更（默认值、collection、k、device、阈值）必须写入，并给出理由与生效日期。


## 验收与退出码约定

### 必跑验收（建议最低集合）
1) 文档引用一致性（CI 推荐只验证不修复）：
   - `python tools/verify_postmortems_and_troubleshooting.py --no-fix --strict`
2) 关键新增工具的可执行性：
   - `python -m py_compile <new_script.py>`
   - `python <tool> --help`

### 退出码（示例约定）
- PASS：0
- WARN：1（迁移期允许，但必须落盘并跟踪）
- FAIL：2（阻断）


## 常见失败与处理

1) 现象：复盘写完但没有行动项闭环  
原因：没有把“缺失控制点”转为门禁或清单项。  
处理：在 Postmortem 的 Missing Controls 中明确“门禁命令 + PASS 判据 + 触发器”，并写回 PREFLIGHT。

2) 现象：LESSONS 越写越像事件时间线  
原因：职责混淆。  
处理：LESSONS 只保留规则与例外；事件细节留在 Postmortem。

3) 现象：文档检查误报大量“缺文件”  
原因：把运行时工件/计划脚本当作仓库内文件引用。  
处理：运行时工件用明确前缀；计划脚本改占位形式；必要时更新检查器忽略配置。


## 附录：命名约定与最小模板

### 文件命名建议
- Postmortem：`docs/postmortems/YYYY-MM-DD_postmortem_<topic>.md`
- 主题建议包含可检索关键词（例如 doc-gate / handoff / timeout / default drift）。

### Postmortem YAML 最小头（示例）
```yaml
---
title: ...
date: YYYY-MM-DD
status: draft|final
scope: ...
---
```
