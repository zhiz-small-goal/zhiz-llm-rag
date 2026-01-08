---
title: "Postmortem｜公开项目的前置检查（Public Release Preflight）"
version: 1.0
last_updated: 2026-01-08
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "公开发布前置检查（数据面隔离 + 文档脱敏 + 门禁）"
  severity: P2
---

# Postmortem｜公开项目的前置检查（Public Release Preflight）

## 目录（TOC）
- [0) 元信息（YAML）](#0-元信息yaml)
- [1) 总结（Summary）](#1-总结summary)
- [2) 预期 vs 实际（Expected vs Actual）](#2-预期-vs-实际expected-vs-actual)
- [3) 证据账本（Evidence Ledger）](#3-证据账本evidence-ledgere)
- [4) 复现（MRE：最小可复现）](#4-复现mre最小可复现)
- [5) 排查过程（Investigation）](#5-排查过程investigation)
- [6) 根因分析（RCA）](#6-根因分析rca)
- [7) 修复与处置（Mitigation & Fix）](#7-修复与处置mitigation--fix)
- [8) 回归测试与门禁（Regression & Gates）](#8-回归测试与门禁regression--gates)
- [9) 行动项（Action Items）](#9-行动项action-items)
- [10) 方法论迁移（可迁移资产）](#10-方法论迁移可迁移资产)
- [11) 信息缺口与补采计划（Gaps & Next Evidence）](#11-信息缺口与补采计划gaps--next-evidence)
- [12) 输出自检（Quality Gates）](#12-输出自检quality-gates)

---

## 0) 元信息（YAML）

```yaml
date: "2026-01-08"
mode: "solo_debug"
repo_path: "zhiz-llm-rag（GitHub public repo）"
env:
  os: "Windows（本地） + GitHub Actions（CI）"
  python: "本地多版本；CI 使用 actions/setup-python"
  venv: "本地多 venv（.venv_*）"
  key_deps:
    - "git"
    - "GitHub Actions"
    - "public release hygiene scripts（tools/check_public_release_hygiene.py 等）"
scope:
  component: "公开发布前置检查：数据/产物隔离、文档脱敏、secrets 门禁、CI 工作流有效性"
  severity: "P2"
```

---

## 1) 总结（Summary）

- 现象（Facts）：
  - 在准备公开仓库前，需要确认工作区不含真实数据/构建产物/环境指纹，并把检查固化为可回归的门禁；检查与迁移过程中出现了“门禁脚本/快照复制/CI 配置”等典型控制面问题（如 worktree 关联、workflow YAML 语法错误）。
- 影响（Facts）：
  - 若不做前置检查，风险集中在两类：**数据面泄露（真实数据/产物/截图）**与**控制面失效（CI 门禁不可信或无法运行）**；其后果是“公开后纠错成本显著上升”。
- 结论一句话（Inference，可证伪）：
  - 采用“**公开镜像仓库 + Public Release Preflight 清单 + secrets 扫描门禁 + CI 语法预检**”的组合可以将公开风险收敛到可控范围（可行）；可证伪方式：在新仓库 main 上复跑清单并确保 CI/扫描工作流均 PASS。

---

## 2) 预期 vs 实际（Expected vs Actual）

- 预期：
  - 在发布前，能够一次性回答三个问题：
    1) 工作区是否含不该公开的内容（数据/产物/截图/绝对路径等）？
    2) 历史记录是否需要重写（若曾提交敏感内容）？
    3) 发布后是否有门禁防回归（secrets 扫描、hygiene 检查、文档契约检查）？
- 实际：
  - 检查脚本与门禁逐步跑通并产出报告；在建立公开镜像与 CI 门禁的过程中暴露了两类“发布特有”的工程坑：
    - **快照导出不彻底**：复制/导出目录携带 `.git`（worktree 指针），导致新仓库不是“干净历史”。
    - **控制面配置易碎**：CI workflow YAML 因字符串包含 `:` 未加引号而直接 invalid，导致门禁无法运行。

---

## 3) 证据账本（Evidence Ledger）{: #3-证据账本evidence-ledgere }

> 说明：Ledger 只记录本次对话中已出现的可定位证据；涉及“用户终端输出/Actions 提示”的部分以 `log:` 记为外部证据锚点。

- **E1**
  - 来源：`file: postmortem_prompt_template.md`
  - 定位：模板第 9 节“最终输出模板（0–12 小节）”
  - 能证明什么：本复盘输出的结构与硬约束来源于模板，并要求 Evidence Ledger / RCA / Action Items / 可迁移资产等。
  - 反证方式：若输出缺少任意必填小节或无 E# 引用，则不满足模板约束。

- **E2**
  - 来源：`file: PREFLIGHT_CHECKLIST.md`
  - 定位：Quick Path 的“只跑一条命令优先 tools\run_ci_gates.cmd”与“每条检查必须有命令+PASS 条件”
  - 能证明什么：当前项目已经有“preflight 门禁序列”的 SSOT 入口，但其范围更偏“重构/换机/换环境”，缺少“公开发布特有控制点”。
  - 反证方式：若清单中已完整覆盖公开发布（数据面/控制面/历史/回归），则无需新增条目。

- **E3**
  - 来源：`file: LESSONS.md`
  - 定位：经验条目模板（模式→控制点→动作→验收→回链）
  - 能证明什么：项目已有“跨 postmortem 复用资产”的承载位置，适合沉淀“公开发布前置检查”这类可迁移经验。
  - 反证方式：若该经验仅一次性且不可复用，则不应写入 LESSONS，而仅留在本篇 postmortem。

- **E4**
  - 来源：`log: GitHub Actions 提示`
  - 定位：`.github/workflows/ci.yml` “Invalid workflow file / yaml syntax on line 38”
  - 能证明什么：控制面（CI）可因为纯语法问题直接失效，属于“发布门禁链路”的高优先控制点。
  - 反证方式：修复 YAML 后，Actions 能正常解析进入 job 执行（即使后续 step fail，也不应再报 invalid workflow）。

- **E5**
  - 来源：`log: git worktree 导出/复制目录的 git 行为`
  - 定位：`git init` 输出指向 `.../.git/worktrees/_public_snapshot/`；`git branch -M main` 报 worktree 分支占用
  - 能证明什么：公开镜像若意外携带 worktree 指针，会导致“新仓库历史/分支/引用”与原仓库耦合，违背“独立发布物”的预期。
  - 反证方式：删除导出目录 `.git` 指针并重新 `git init` 后，`git branch -M main` 不再报 worktree 占用，且 push 只含新历史。

---

## 4) 复现（MRE：最小可复现）

- 环境：
  - Windows 本地仓库 + GitHub Actions 开启。
- 步骤（命令）：
  1) 从私有仓库用 worktree/复制方式生成 `_public_snapshot` 或导出目录。
  2) 在导出目录执行 `git init` / `git branch -M main` / `git push`。
  3) 在 `.github/workflows/ci.yml` 中写入未加引号且包含 `:` 的 step name（例如 `Gate: ...`），再 push。
- 期望输出：
  - 导出目录是独立仓库（不关联原仓库 worktree），push 成功；
  - Actions 能解析 workflow 并运行门禁。
- 实际输出（引用 E#）：
  - worktree 耦合导致分支重命名失败（E5）；
  - workflow YAML 语法错误导致 Actions 报 invalid（E4）。

---

## 5) 排查过程（Investigation）

### 5.1 Timeline（solo_debug 可 N/A）
N/A（仅保留关键控制点）

### 5.2 Response/Comms（solo_debug 可 N/A）
N/A

### 5.3 Investigation Steps（必填）
- Step 1：先用“hygiene 审计脚本”生成报告，识别数据/产物/路径指纹风险；目标是把“公开前检查”从人工记忆变成可执行产物。
- Step 2：采用“公开镜像/快照目录”策略，而不是直接把私有仓库改 public；这样可把发布面缩小到一个可控输入集（导出目录）。
- Step 3：在导出目录初始化新仓库时，发现 `.git` 指向 worktree，导致分支/历史与原仓库耦合（E5）；通过删除导出目录 `.git` 并重新 init 切断耦合。
- Step 4：配置 CI 门禁后，发现 workflow YAML 语法错误导致 invalid（E4）；修复后重新触发 Actions 进入可执行状态。

---

## 6) 根因分析（RCA）

1) **Trigger（直接触发）**
   - 将“发布门禁”接入 CI 并 push 到 public repo 后，GitHub Actions 在解析期发现 `.github/workflows/ci.yml` 语法错误而失败（E4）。
   - 在导出目录执行 `git init/branch -M` 时，该目录仍带 worktree 指针导致分支操作失败（E5）。

2) **Root Cause（根因）**
   - **发布面输入集未被严格定义为“独立、可移植的快照”**：导出目录携带 `.git(worktree)` 使其不是独立发布物（E5）。
   - **控制面缺少“语法层预检”控制点**：CI workflow 的 YAML 语法错误在平台解析期才暴露，导致门禁整体短路（E4）。

3) **Contributing Factors（促成因素）**
   - “快速接线式”变更（加门禁/加步骤）容易引入格式性错误，但缺少本地/CI 的 lint 反馈回路（E4）。
   - 公开发布涉及的数据面（文件/产物/截图）与控制面（CI/扫描/分支保护）跨域，若缺少单一清单 SSOT，容易漏项（E2/E3）。

4) **Missing Controls（缺失控制点/门禁）**
   - MC1（发布快照独立性门禁）：导出目录必须满足 `.git` 为目录（独立 repo），不得为 worktree 指针文件；触发时机：发布前；失败策略：FAIL；验收：`dir /a .git` 显示 `<DIR>` 且 `git rev-parse --is-inside-work-tree` 为 true。
   - MC2（workflow 语法预检）：对 `.github/workflows/*.yml` 加入 lint（例如 actionlint）或至少规约“含 `:` 的字符串统一加引号”；触发时机：PR/CI；失败策略：FAIL；验收：Actions 不再报 invalid（E4）。

---

## 7) 修复与处置（Mitigation & Fix）

- 止血（可选）：
  - 若已公开且发现数据/凭据误提交：第一优先是撤下敏感内容并旋转凭据；然后再讨论历史重写（此处作为原则，不展开）。
- 最终修复（本次沉淀的“标准动作”）：
  1) **发布输入集隔离**：以导出目录为发布源，确保不含 data/产物/截图与绝对路径，并保持目录可复跑检查脚本。
  2) **切断 worktree 耦合**：导出目录若含 `.git` 指针文件，则删除并重新 `git init -b main`（E5）。
  3) **门禁分层**：
     - data-plane：hygiene 审计（禁止路径/二进制/绝对路径）；
     - control-plane：secrets 扫描（gitleaks/secret scanning）；
     - workflow-plane：CI workflow 语法预检（E4）。
- 回滚点：
  - 发布采用“新仓库镜像”天然可回滚：保留私有仓库不变；公开仓库只需重推新快照或重新创建仓库。

---

## 8) 回归测试与门禁（Regression & Gates）

- 回归测试命令（发布前本地）：
  - `python tools/check_public_release_hygiene.py --repo . --history 0`
  - `dir /a .git`（确认独立仓库，不是 worktree 指针文件）
- PASS 条件：
  - hygiene 报告 HIGH/MED 为 0（以报告为准）；`.git` 为目录；能成功 push。
- 新增/建议门禁（至少 1 条）：
  - G1：将 hygiene check 纳入 CI（已存在路径时保持）；触发：push/PR；策略：FAIL。
  - G2：新增 secrets 扫描工作流（secrets.yml，已在实践）；触发：push/PR；策略：FAIL（发现 secrets 即失败）。
  - G3：workflow 语法预检（推荐引入 actionlint）；触发：PR；策略：FAIL。

---

## 9) 行动项（Action Items）

| action_id | 类型 | 改动点（文件/脚本/配置） | owner | due | 验证方式（命令 + PASS 条件） | 回滚策略 |
|---|---|---|---|---|---|---|
| A1 | prevent | docs/howto/PREFLIGHT_CHECKLIST.md 增加 “Public Release Preflight” 小节 | zhiz | 2026-01-08 | 复跑清单：hygiene/独立性/CI/scan 均 PASS | 回滚该段落 |
| A2 | prevent | docs/explanation/LESSONS.md 新增“公开发布前置检查”经验条目（含控制点与验收） | zhiz | 2026-01-08 | 按条目给出的命令均可执行且能拦截对应失败模式 | 回滚该条目 |
| A3 | detect | CI 增加 workflow 语法预检（actionlint 或等价） | zhiz | 2026-01-10 | PR 中引入 YAML 语法错误时，lint 先于 Actions 解析期失败 | 移除 lint job |
| A4 | doc | docs/postmortems 新增本篇 postmortem，并在 INDEX 中回链（若存在索引） | zhiz | 2026-01-08 | LESSONS 条目回链可点击；postmortem 存在且可读 | 回滚新增文件 |

---

## 10) 方法论迁移（可迁移资产）

### 10.1 事件级公式（This time）
在“需要把私有项目公开”的约束下，因为缺少“发布快照独立性 + workflow 语法预检”控制点，导致快照与 CI 门禁链路出现耦合/失效，最终暴露为 worktree 分支冲突与 Actions invalid workflow（E4/E5）。

### 10.2 模式级归类（Recurring pattern）
- 入口不一致：本地导出/CI/远端触发走不同路径，问题在远端解析期才暴露（E4）。
- 契约漂移：发布物的“独立性契约”未显式化（导出目录携带 `.git` 指针）（E5）。
- 文档漂移（潜在）：若不把“公开发布特有控制点”写入清单与经验库，后续复用时会漏项（E2/E3）。

### 10.3 原则级规则（Principles）
- P1：发布前先定义“发布输入集”，并用脚本把它变成可审计对象  
  - 适用：开源/公开/镜像发布。  
  - 操作化：导出目录=唯一发布输入；必须可跑 hygiene 报告且 HIGH/MED=0。  
  - 反例：直接把私有仓库切 public，或发布输入集不明确，导致补救成本上升。

- P2：控制面先可用，再谈门禁收紧  
  - 适用：CI/workflow/门禁系统。  
  - 操作化：先保证 workflow 可解析（语法预检/规约），再加更多 gates。  
  - 反例：workflow invalid 直接短路，导致“看起来有门禁，实际不可用”（E4）。

- P3：可回滚优先：发布采用“镜像仓库”天然隔离与回滚  
  - 适用：首次公开、风险不确定。  
  - 操作化：私有仓库不变；公开仓库重建/重推成本低；行动项必须写回滚点。  
  - 反例：在主仓直接改历史/强删文件，难以验证并引入协作成本。

### 10.4 跨域类比（Engineering → Life）
- L1：公开发布=对外交付，交付物必须“能独立存在”  
  - 动作：发布前加一条“导出目录 `.git` 必须为目录”清单项（落盘：PREFLIGHT_CHECKLIST）。
- L2：门禁=门锁，门锁自身必须可用  
  - 动作：为 workflow 增加语法预检（落盘：CI job）。
- L3：经验=规程，规程必须能被下一次执行  
  - 动作：把本次经验写入 LESSONS 并回链本篇 postmortem（落盘：LESSONS）。

---

## 11) 信息缺口与补采计划（Gaps & Next Evidence）

- 缺口清单：
  - 未收录本次 hygiene 报告/修复报告的最终摘要（HIGH/MED/INFO 具体项）作为可追溯证据。
  - 未收录 Actions run 的链接与日志片段（仅有“line 38 invalid”文本证据）。
- 补采命令/文件（CMD / file）：
  - `file: public_release_hygiene_report_*.md`（保存到 docs/postmortems/attachments 或 docs/archive）
  - `CMD: git log --oneline -n 10`（记录关键提交）
  - Actions run URL（粘到 postmortem 的 Evidence Ledger）
- 预期看到什么（将变成哪条 E#）：
  - 新增 E6：hygiene 报告摘要证明数据面风险已清零；
  - 新增 E7：Actions run 链接证明 workflow 已可解析并执行 gates。

---

## 12) 输出自检（Quality Gates）

- Q1：所有 Inference 是否都引用了至少一个 E#？Yes（主要引用 E4/E5，且给出可证伪方式）
- Q2：所有建议是否都包含 为何 + 如何做 + 如何验收？Yes
- Q3：是否至少产出 1 条自动化门禁并给出命令与 PASS 条件？Yes（hygiene、secrets、workflow 预检）
- Q4：行动项表是否每条都包含 owner/due/verify/rollback？Yes
- Q5：方法论迁移是否包含 事件公式 + 模式枚举 + 3 原则（带反例）+ 3 类比动作？Yes
- Q6：是否列出了信息缺口清单与补采计划？Yes
