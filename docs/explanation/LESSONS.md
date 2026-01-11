---
title: Lessons / 经验库（可迁移）
version: 0.4
last_updated: 2026-01-11
scope: "跨 postmortem 的失败模式、控制点、门禁与清单"
owner: zhiz
---

# Lessons / 经验库（可迁移）

> 目的：把多次复盘里“可迁移的项目建设思维”从单篇 postmortem 中抽离出来，沉淀为**可检索、可复用、可演进**的长期资产。  
> 规则：这里只写“跨事件可复用”的内容；每条经验必须回链到至少 1 篇 postmortem 作为证据锚点（文件链接即可）。

## 目录
- [0. 使用与写入规则](#0-使用与写入规则)
- [1. 失败模式词表](#1-失败模式词表)
- [2. 控制点与门禁设计原则](#2-控制点与门禁设计原则)
- [3. 复用资产入口](#3-复用资产入口)
- [4. 经验条目模板](#4-经验条目模板)
- [5. 经验条目](#5-经验条目)
- [6. 待办与清理规则](#6-待办与清理规则)

---

## 0. 使用与写入规则

- **单一真源（SSOT）**：本文件用于“原则/反模式/控制点/触发器”的汇总；事件细节仍留在各自 postmortem 中。
- **最小条目**：每条经验写成“模式 → 控制点 → 可执行动作 → 验收方式”，避免抽象口号。
- **必须回链**：每条经验至少链接 1 篇相关 postmortem（位于 `docs/postmortems/`）。
- **可演进**：当某条经验被证伪或出现更好的控制点，更新同一条目并记录变更原因（不要堆叠新条目造成重复）。

---

## 1. 失败模式词表

> 用于给经验条目打标签，便于统计与检索（与 postmortem 模板的模式枚举保持一致）。

- **契约漂移**：schema/接口/参数口径不一致
- **环境漂移**：多设备/多 venv/依赖版本不一致
- **入口不一致**：CLI/脚本/CI 走不同路径
- **不可观测**：缺关键日志/缺指标/缺探针
- **无回滚/不可逆改动**：修复难以撤销或验证
- **状态不一致**：缓存/产物/索引与源数据错位
- **文档漂移**：文档与代码/契约不一致

---

## 2. 控制点与门禁设计原则

1) **先定义不变量，再做优化**  
   - 控制点：先明确 PASS 条件与产物契约（例如 report schema / stamp / chunk 数量），再做速度或体验优化。  
   - 动作：把 PASS 条件固化为脚本或 CI 门禁（避免靠人工目测）。

2) **入口统一优先于局部修补**  
   - 控制点：同一条主流程尽量让 CLI / 脚本 / CI 复用同一入口与参数解析，避免“看似跑通但走了不同代码路径”。  
   - 动作：为入口点写一致性检查（例如 entrypoints / import drift 检查）。

3) **先可观测，再可控**  
   - 控制点：缺日志/缺探针时，根因分析会退化为猜测。  
   - 动作：先补齐最小观测（probe、版本打印、产物摘要），再谈门禁收紧。

4) **默认可回滚**  
   - 控制点：任何会影响统计口径/契约的改动，都必须明确回滚点与验收命令。  
   - 动作：把“回滚步骤 + 验收命令”写进行动项表，并在 PR/commit 中保留可撤销性。

---

## 3. 复用资产入口

- **Preflight（重构/换机/换环境后必跑）**：见 [PREFLIGHT_CHECKLIST](../howto/PREFLIGHT_CHECKLIST.md)
- **PR/CI Lite 门禁（快速回归）**：见 [ci_pr_gates](../howto/ci_pr_gates.md)
- **Postmortems 索引**：见 [docs/postmortems/INDEX.md](../postmortems/INDEX.md)

---

## 4. 经验条目模板

> 复制以下模板新增条目；尽量控制在 15–25 行内。

### 条目：<一句话标题>
- 标签（失败模式）：`<从词表选择 1–3 个>`
- 适用场景：<何时会遇到>
- 触发/现象：<可观测现象>
- 根因机制（简述）：<因果链，避免口号>
- 缺失控制点：<本该更早拦住它的门禁/检查>
- 可执行动作：
  - A1：<做什么（命令/改动点）>
  - A2：<做什么（命令/改动点）>
- 验收方式（PASS 条件）：<命令 + PASS 字段>
- 回链证据（至少 1 篇 postmortem）：
  - <链接：`docs/postmortems/<file>.md`>

---

## 5. 经验条目

### 条目：公开发布前置检查必须“数据面 + 控制面 + workflow 面”分层
- 标签（失败模式）：`入口不一致`、`契约漂移`、`不可观测`
- 适用场景：将私有项目改为 public、首次开源、对外发布“可复制运行”的仓库快照
- 触发/现象：
  - 公开后才发现误包含数据/产物/截图或绝对路径指纹；
  - CI/workflow 因语法错误 `Invalid workflow file` 直接失效；
  - 发布快照携带 worktree `.git` 指针导致新仓库与原仓库耦合（分支/历史异常）。
- 根因机制（简述）：
  - 发布物输入集未定义为“独立可移植快照”，导致 `.git`/产物/数据混入；
  - 门禁缺少语法预检与 secrets 扫描，控制面不可用时无法保证发布质量。
- 缺失控制点：
  - 发布快照独立性门禁（`.git` 目录 vs 指针文件）；
  - workflow 语法预检（至少规约含 `:` 的字符串必须加引号，最好加 lint）；
  - secrets 扫描门禁（CI + 平台防回归）；
  - repo health/community files 门禁（CHANGELOG/CITATION/.editorconfig/CoC 联系方式占位符）。
- 可执行动作：
  - A1（数据面）：`python tools/check_public_release_hygiene.py --repo . --history 0`
  - A2（快照独立性）：`dir /a .git`（必须是 `<DIR>`）
  - A3（控制面）：在仓库启用 `secrets-scan` 工作流并确保至少跑过 1 次 PASS
  - A4（workflow 面）：push 后 Actions 不得出现 `Invalid workflow file`
  - A5（repo health）：`python tools/check_repo_health_files.py --repo . --mode public-release --out data_processed\build_reports\repo_health_report.json`
- 验收方式（PASS 条件）：
  - hygiene 报告 HIGH/MED=0；`.git` 为目录；CI 与 secrets-scan 均能进入 job/step 且最终 PASS。
- 回链证据（至少 1 篇 postmortem）：
  - `docs/postmortems/2026-01-08_postmortem_public_release_preflight.md`
  - `docs/postmortems/2026-01-09_postmortem_open_source_repo_health_files.md`



### 条目：门禁结果以退出码/结构化状态为准，避免被“report_written”误导
- 标签（失败模式）：`不可观测`、`契约漂移`
- 适用场景：本地跑 gate/单步脚本时，控制台同时出现“写盘成功/OK”与“门禁 FAIL”，导致判断摇摆
- 触发/现象：
  - gate 报 `rc=2 / FAIL`，但日志出现 `[OK] report_written=...`；
  - 报告可能落到 Desktop（含用户名绝对路径），影响分享与可复现。
- 根因机制（简述）：
  - hygiene 脚本把“写盘成功”（I/O）与“检查是否通过”（HIGH/MED 统计 + 退出码）输出拆开，且缺少单一权威汇总行。
- 缺失控制点：
  - Preflight 未显式要求检查退出码（例如 `echo %ERRORLEVEL%`）；
  - 未将“fallback 到 Desktop”视作可观测的 warning（容易被当成正常路径）。
- 可执行动作：
  - A1：跑完 hygiene 立刻检查退出码：`echo %ERRORLEVEL%`（非 0 直接当 FAIL）
  - A2：在报告中搜索 `[HIGH]` 并清零；直到 `HIGH=0 && MED=0`
  - A3：若 report 落 Desktop，优先修复写入 repo 目录的权限/路径或显式 `--out data_processed/build_reports/...`
- 验收方式（PASS 条件）：
  - `check_public_release_hygiene` 退出码为 0；报告 `HIGH/MED=0`；report 路径为 repo 内相对路径
- 回链证据（至少 1 篇 postmortem）：
  - `docs/postmortems/2026-01-11_postmortem_public_release_hygiene_rc2_and_report_written_signal.md`

---

## 6. 待办与清理规则

- 待办：为现有 postmortems 逐步补齐“标签（失败模式）”与“对应经验条目”。建议每次复盘写完只补 1–2 条，不做大扫除式重构。
- 清理规则：若同一问题在 3 篇以上 postmortem 中重复出现，必须：
  - 合并为 1 条经验条目（SSOT）
  - 并在 `../howto/PREFLIGHT_CHECKLIST.md` 中增加或收紧对应检查项

## 2026-01-08｜tools 分层与全量 wrapper 门禁自举（回链）

- 证据锚点：
  - [Postmortem：tools/分层与全量wrapper生成门禁自举失败 + 退出码契约对齐](../postmortems/2026-01-08_tools_layout_wrapper_gen_exitcode_contract.md)

### 原则库（Principles）
1) **先排除 repo-only/自举脚本，再做 wrapper->SSOT 映射**：受管对象集合必须可闭合，否则 `missing SSOT` 会让门禁永远 FAIL。
2) **FAIL/ERROR 退出码必须区分**：规则不满足返回 2，脚本异常返回 3，避免 CI 信号混淆。
3) **先 `--check` 出清单，再 `--write` 收敛**：全量对齐以可审计 diff 为先，避免一次性无差别改写。

### 反模式库（Anti-patterns）
- 将 `gen_tools_wrappers.py` 等 repo-only 工具纳入受管集合，触发自举与 `missing SSOT`。
- wrapper 中混入业务逻辑，造成“入口漂移 + 双实现”。
- 异常退出码不对齐，CI 无法区分规则失败与脚本异常。

### 控制点与门禁（Controls）
- wrapper 一致性门禁：`python tools\gen_tools_wrappers.py --check`
- tools<->src 分层/同名冲突门禁：`python tools\check_tools_layout.py --mode fail`
## 2026-01-07｜docs↔code 对齐与文档门禁治理（回链）

- 证据锚点：
  - [Postmortem：docs↔code 对齐 + 缺失脚本补齐 + 文档门禁增强 + 输出可读性优化](../postmortems/2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md)

### 原则库（Principles）
1) **引用语义分类优先于字符串检查**：区分 repo 文件 / 运行时工件 / 计划项 / 外部材料，再决定“必须存在/允许不存在/必须占位”。
2) **门禁可信度优先**：strict 输出应以“少而准”为目标；误报会长期腐蚀执行力。
3) **SSOT + redirect**：同一事实只允许 1 份权威正文，其余位置用链接索引，禁止双写漂移。
4) **先可读，再可控**：控制台报告需分段留白，否则人类 review 吞吐下降，导致收敛变慢。

### 反模式库（Anti-patterns）
- 文档写 `tools/xxx.py` 像“已内置”，但仓库缺失且不标注计划项。
- 用裸文件名（如 `inventory.csv`、`check.json`）指代运行产物且不声明生成与路径约定，导致门禁误报或误导。
- “修复前后命令相同”，但隐含修复点其实是 cwd/入口点约束。
- 模板/Reference 文档内塞入工作流细节，导致职责混杂与维护困难（应拆成 How-to）。

### 控制点与门禁（Controls）
- Doc-gate（严格验证不改文件）：  
  `python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict`
- Inventory 输入集合漂移 gate（需要时启用）：  
  `python tools\check_inventory_build.py --compare-snapshot <snapshot> --strict`

