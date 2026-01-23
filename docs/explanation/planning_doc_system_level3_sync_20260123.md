---
title: "Level 3：文档体系重构与一致性收敛计划（WAL/续跑语义）"
version: "v0.1"
last_updated: "2026-01-23"
timezone: "America/Los_Angeles"
owner: "zhiz"
status: "draft"
---

# Level 3：文档体系重构与一致性收敛计划（WAL/续跑语义）



## 目录

- [SSOT 与口径入口](#ssot-与口径入口)
- [结论](#结论)
- [假设（默认）](#假设默认)
- [范围与非目标](#范围与非目标)
- [输出物（交付形态）](#输出物交付形态)
- [1) 详细指导（分步骤，按依赖顺序）](#1-详细指导分步骤按依赖顺序)
  - [Step1 — 全量清点与建立“文档图谱”（Inventory + Map）[CON]](#step1-全量清点与建立文档图谱inventory-mapcon)
  - [Step2 — 确立 SSOT 与术语表（Glossary + Contract）[STD][OFF]](#step2-确立-ssot-与术语表glossary-contractstdoff)
  - [Step3 — 统一 CLI/参数/日志字段表（Single Source of CLI Truth）[CON]](#step3-统一-cli参数日志字段表single-source-of-cli-truthcon)
  - [Step4 — 迁移与去重：README/howto/runbook 全面收敛到 SSOT [CON]](#step4-迁移与去重readmehowtorunbook-全面收敛到-ssot-con)
  - [Step5 — 链接、TOC、front-matter 统一与格式化（Mechanical Consistency）[CON]](#step5-链接tocfront-matter-统一与格式化mechanical-consistencycon)
  - [Step6 — 文档门禁与回归（CI Checks + Review Checklist）[CON]](#step6-文档门禁与回归ci-checks-review-checklistcon)
- [自检（快速验证点）](#自检快速验证点)
- [失败模式与缓解](#失败模式与缓解)
- [MRE（最小可复现：用于验证文档与现实现一致）](#mre最小可复现用于验证文档与现实现一致)

## SSOT 与口径入口

- **文档体系 SSOT**：`docs/reference/DOC_SYSTEM_SSOT.md`
- **WAL/续跑术语表**：`docs/reference/GLOSSARY_WAL_RESUME.md`
- **build CLI/日志真相表**：`docs/reference/build_chroma_cli_and_logs.md`

> 约束：本文仅保留“怎么做/怎么排障”的最短路径；参数默认值与字段解释以真相表为准。

## 结论
本计划采用“先确立单一事实源（SSOT）与术语/契约，再批量迁移与去重，最后用自动化检查锁定一致性”的路径，整体可行；每个阶段均以可核验的验收清单作为退出条件，避免一次性大改导致语义漂移。

## 假设（默认）
1) 文档范围：仓库内所有 `*.md`（含 `docs/`、`tools/`、根目录等），并包含 legacy/archive/postmortem，但对历史叙事采取“标注与跳转”为主，不重写时间线。  
2) 权威契约优先级：源码行为（CLI `-h`/日志字段）与 `docs/reference/*` 的契约文档 > 工具 README > howto/runbook > archive。  
3) 术语固定：`index_state.json` 为完成态快照（success-only）、`index_state.stage.jsonll` 为 WAL/进度（append-only），两者边界在文档中明确且一致。  
4) Windows CMD 为默认命令体例，文档示例以此为准；如需 PowerShell/Unix 体例，后续作为扩展项单列。  

## 范围与非目标
- 范围：围绕 Chroma build/续跑/WAL/锁/一致性校验/覆盖率检查相关的所有文档段落，统一术语、统一参数名、统一行为解释、统一示例与输出字段。  
- 非目标：不改动代码行为；若文档与代码冲突，以代码为准并在计划中登记“需代码修复/补全”的缺口清单。  

## 输出物（交付形态）
- 新增：术语表与 SSOT 导航页；统一的 runbook（含决策树）；统一的 CLI/日志字段表；迁移说明与废弃标记策略。  
- 修改：所有相关 README/howto/reference/archive 中与 WAL/续跑/锁/strict-sync 相关的段落、参数表、示例命令与故障处理。  
- 自动化：最小文档门禁（链接检查 + 关键字一致性检查 + front-matter 校验）。  

---

## 1) 详细指导（分步骤，按依赖顺序）

### Step1 — 全量清点与建立“文档图谱”（Inventory + Map）[CON]
【做什么】对仓库内所有 `*.md` 建立清单（路径、标题、front-matter、最后更新时间、包含关键字的段落位置），并输出一张“文档图谱”：每份文档标注其角色（reference/guide/runbook/README/archive/postmortem）、引用关系（links）、以及是否包含与 WAL/续跑/锁/strict-sync 相关内容。对关键字集合固定为：`index_state.json`、`index_state.stage.jsonll`、`resume-status`、`on-missing-state`、`writer.lock`、`strict-sync`、`sync-mode`、`collection.count`、`schema_hash`。  
【为何】Level 3 的风险不在改动本身，而在覆盖面与一致性。先建立可审计的清点结果，可以让后续每个变更都有“来源文档→目标契约→更新位置”的可追踪链路；并能防止遗漏某些 legacy/archive 文档造成“读者从不同入口得到相反结论”。  
【关键参数/注意】清点输出建议落到 `docs/explanation/doc_inventory.md` 与 `docs/explanation/doc_map.json`（或等价），并在后续步骤中作为“门禁的输入”；清点阶段不做语义重写，只做标注与分类。  
【验收】清单覆盖 `git ls-files "*.md"` 的 100%；图谱中每份文档有唯一角色标签；关键字命中文档全部被标注“需对齐/仅标注/无需处理”。

### Step2 — 确立 SSOT 与术语表（Glossary + Contract）[STD][OFF]
【做什么】在 `docs/reference/` 建立或强化一份“SSOT 导航页”，明确：哪些文档是规范（contract），哪些是说明（guide），哪些是历史（postmortem/archive）。同时新增术语表（glossary）：对 `state`、`WAL`、`run_id`、`schema_hash`、`committed`、`attempted`、`resume_active`、`strict-sync` 等词给出精确定义与示例，并明确“提交边界”以 `flush()->upsert` 成功返回为准（文档口径）。  
【为何】没有 SSOT 与术语表，迁移与去重会导致“同一概念在不同文档用不同叫法/不同口径”，最终只能靠经验解释。先把词与契约固定下来，后续 README/howto 只需引用 SSOT，即可降低重复维护。  
【关键参数/注意】冲突裁决规则写入导航页：源码/CLI `-h`/日志字段 > reference 契约文档 > 其它；并把“常见误读点”（例如 `policy=reset` 是默认分支评估而非已执行动作）写成规范化措辞，供后续批量替换引用。  
【验收】SSOT 页能回答：输出字段含义、WAL 与 state 的职责边界、何时会覆盖 `on-missing-state=reset`、writer lock 的目的与处置；术语表每条均有“定义+示例+反例/误读”。

### Step3 — 统一 CLI/参数/日志字段表（Single Source of CLI Truth）[CON]
【做什么】新增一份“CLI 与日志字段表”（建议 `docs/reference/build_chroma_cli_and_logs.md`）：以 `python tools/build_chroma_index_flagembedding.py -h` 与 `--resume-status` 输出为基准，列出所有参数、默认值、互斥关系、组合语义，以及关键日志字段（包含你已观察到的 `state_present/wal_docs_committed/wal_last_event/resume_active` 与两条 WARN 的解释）。工具 README/OPERATION_GUIDE 中不再复制整张表，而是引用该表并只保留最短的“常用命令片段”。  
【为何】参数表在多处复制会导致版本漂移，尤其是 Level 3 需要跨多文档迁移。把参数与日志字段集中到一处，既能提升检索效率，也能为门禁提供“关键字一致性检查”的固定基准。  
【关键参数/注意】对组合语义做显式规则：例如 `sync-mode=none + strict-sync=true` 的行为应在表中写明，并给出建议（关闭 strict 或换 sync-mode）；对 `--resume off` 的效果写成“强制不走 WAL 恢复”。  
【验收】仓库中不再出现多份“参数表互相矛盾”；任何 README/howto 中的参数名均能在该 SSOT 表中找到对应条目。

### Step4 — 迁移与去重：README/howto/runbook 全面收敛到 SSOT [CON]
【做什么】按 Step1 图谱的角色标签分批处理：  
- 工具 README：删除重复的契约解释，保留“用途/输入输出/常用命令/指向 SSOT 链接/故障入口”。  
- OPERATION_GUIDE：升级为 runbook 风格，加入“决策树”（例如遇到 `writer lock exists`、遇到 `policy=reset`+WAL 覆盖、遇到 strict mismatch）与“低成本预检”（优先 `--resume-status`）。  
- Coverage/检查类文档：统一引用 `index_state` 与 WAL 的口径，解释在 state 缺失但 WAL 存在时的预期行为与建议动作。  
【为何】Level 3 的目标之一是减少“读者从不同入口获得不同口径”。通过去重与统一引用，文档之间形成清晰层级：reference 定义“是什么”，runbook 定义“怎么做”，README 定义“怎么用”。  
【关键参数/注意】历史文档（postmortem/archive）不改写结论，只在顶部加“现行行为链接/术语差异提示/迁移说明”；避免破坏历史语境。  
【验收】关键主题（WAL 覆盖 reset、writer lock、resume-status 字段）在所有入口文档中表述一致；README 中不再出现对同一字段的重复但不同解释。

### Step5 — 链接、TOC、front-matter 统一与格式化（Mechanical Consistency）[CON]
【做什么】统一 front-matter 模板（title/version/last_updated/timezone/owner/status），并将 TOC 结构收敛为固定层级（不强制所有文档都有 TOC，但有则遵循统一格式）。全仓修复相对链接、过期路径、重复锚点；为 archive 文档加“DEPRECATED/ARCHIVED” 标识与跳转。必要时引入一个最小格式化工具（只做 markdownlint 的可接受规则子集），避免引入与现有写作习惯冲突的强约束。  
【为何】文档重构后最常见的回归是链接断裂与锚点变化，且这种问题会在读者使用时才暴露。机械一致性步骤把这些问题前移，通过自动化快速发现。  
【关键参数/注意】链接修复需结合 Step1 图谱；对外部链接不做强制更新，但对仓内链接必须可达；front-matter 的 `last_updated` 统一为本次变更日期，版本号按“内容语义变化”递增。  
【验收】全仓链接检查通过；front-matter 校验通过；主要入口文档（OPERATION_GUIDE、SSOT）无死链。

### Step6 — 文档门禁与回归（CI Checks + Review Checklist）[CON]
【做什么】新增最小门禁：

- 新增 gate 工具：`tools/check_doc_system_gate.py`（输出 Report v2，可落盘 JSON/MD）
- 推荐运行（Windows CMD）：
```cmd
python tools\check_doc_system_gate.py --root . --doc-map docs\explanation\doc_map.json --out data_processed\build_reports\doc_system_gate_report.json --md-out data_processed\build_reports\doc_system_gate_report.md
```

  
1) 仓内链接检查（相对路径与锚点）；  
2) 关键术语一致性检查（例如不再出现 `index_state.stage.jsonll` 误写；`policy=reset` 段落必须同时出现“默认评估/最终生效”措辞）；  
3) front-matter 校验（字段齐全、日期格式正确）。  
同时建立 Review Checklist：每次改动必须回答“是否触碰 SSOT？是否新增重复解释？是否更新示例命令与输出？”  
【为何】Level 3 的质量来源不是一次性人工阅读，而是“变更后能持续保持一致”。门禁让后续迭代不把口径带歪；checklist 让评审成本可控。  
【关键参数/注意】门禁规则需可逐步收紧，初期建议仅对 SSOT 与 OPERATION_GUIDE 强制；其它文档先 warning，避免一次性引入大量修复工作阻塞开发。  
【验收】CI 能在 PR 中稳定发现死链/术语漂移；新增文档遵循模板；关键入口文档变更有 checklist 记录。

---

## 自检（快速验证点）
1) 覆盖面自检：`git ls-files "*.md"` 的清单与 Step1 inventory 输出数量一致；并能列出“未命中关键字但仍被改动”的文件理由。  
2) 语义自检：对同一主题（WAL 覆盖 reset、writer lock）随机抽取 5 份不同类型文档，检查表述是否一致且均引用 SSOT。  
3) 可操作性自检：在高成本机器上仅运行 `--resume-status` 就能回答“是否会 resume、是否需要删锁、是否会 reset”；runbook 的决策树能把你贴出的两类日志映射到具体动作。  

## 失败模式与缓解
1) 现象：文档改动范围扩大导致 review 负担上升。原因：去重与链接修复触达面广。缓解：按 Step4 分批提交（每批按目录/主题），并要求每批都有“变更摘要 + 影响面”；备选：先仅对入口文档做 Level 3，其余文档 Level 2。  
2) 现象：历史文档被重写导致时间线混乱。原因：对 postmortem/archive 直接改正文。缓解：只加顶部 NOTE 与跳转，不改历史正文；备选：把历史正文复制到 `docs/archive/` 并在原位置留 stub。  
3) 现象：门禁规则过严导致迭代阻塞。原因：一次性对全仓强制执行。缓解：分级门禁（SSOT/OPERATION 强制，其它 warning）；备选：仅在 release 分支启用强规则。  

## MRE（最小可复现：用于验证文档与现实现一致）
- 环境：Windows CMD，仓库根目录。  
- 命令：  
```cmd
python tools\build_chroma_index_flagembedding.py build --collection chrome_db --resume-status
```
- 期望：输出字段在 `docs/reference/build_chroma_cli_and_logs.md` 可逐条解释；遇到 `writer lock exists` 与 `policy=reset`+WAL 覆盖时，`docs/howto/OPERATION_GUIDE.md` 的决策树给出可执行处置。  
