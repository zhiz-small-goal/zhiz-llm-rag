---
title: "2026-01-07｜docs↔code 对齐 + 缺失脚本补齐 + 文档门禁增强 + 输出可读性优化｜Postmortem"
version: 1.0
last_updated: 2026-01-07
scope: "docs↔code 对齐 / 缺失脚本补齐 / 文档门禁（verify_*）增强 / 控制台可读性"
owner: zhiz
status: done
---

# 2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md目录：


- [0. 元信息](#0-元信息)
- [1. 摘要](#1-摘要)
- [2. 背景与最初构思](#2-背景与最初构思)
- [3. 影响与症状](#3-影响与症状)
- [4. 复现路径与证据](#4-复现路径与证据)
- [5. 根因分析](#5-根因分析)
- [6. 修复与变更清单](#6-修复与变更清单)
- [7. 预防与门禁闭环](#7-预防与门禁闭环)
- [8. 可迁移经验](#8-可迁移经验)
- [9. 附录](#9-附录)


## 0. 元信息

- 事件主题：docs↔code 对齐 + 缺失脚本补齐 + 文档门禁增强 + 输出可读性优化
- 发生/收敛日期：2026-01-07
- 影响范围：仓库 `docs/` 文档体系、文档检查门禁、inventory 构建验证工具、控制台输出可读性
- 受影响角色：主要是“按文档操作的使用者/未来的自己”、以及依赖 `--strict` 门禁的 CI/PR 回归
- 结论一句话：这是一次“文档与代码/入口点发生漂移并被门禁误报与可读性问题放大”的事件，修复通过“补齐工具 + 分类规则 + 门禁工作流 + 输出格式化”收敛为可复用资产。

**Facts（可直接指向仓库工件）**
- 新增了 inventory 构建对比工具：`src/mhy_ai_rag_data/tools/check_inventory_build.py`，并提供 wrapper：`tools/check_inventory_build.py`。
- 文档门禁工具 `verify_postmortems_and_troubleshooting.py` 已具备严格模式与更友好的控制台排版，且配套了 README 说明。

**Inference（推断，需以一次严格门禁运行做最终确认）**
- 若所有文档引用已按“repo 文件 / 运行时工件 / 计划项占位 / 外部材料”分类并收敛，则 `python tools/verify_postmortems_and_troubleshooting.py --no-fix --strict` 应稳定 PASS。


## 1. 摘要

### 1.1 预期 vs 实际

- 预期：
  - 文档中的命令与脚本在仓库内可定位、可运行；
  - 文档引用校验（strict）只对“真实缺失/真实断链”报警，而不被运行时产物或计划项污染信号；
  - 关键工具脚本存在且有使用说明；
  - 控制台报告可读，便于人类快速扫出 FAIL/WARN 的根因。

- 实际：
  - 出现“文档引用脚本缺失”“文档命令路径错误”“计划脚本以真实路径出现导致误导”“运行时工件裸文件名导致 strict 误报”等问题；
  - 工具输出过密，降低人类阅读效率；
  - 缺少一份端到端的“复盘动作说明书（写回协议）”，导致经验沉淀可能停留在单篇复盘中。

### 1.2 本次修复做了什么

- 修正文档中会导致照抄即失败的命令与路径（典型：`python list_chroma_collections.py` → `python tools/list_chroma_collections.py`）。
- 补齐缺失工具：`check_inventory_build.py`（snapshot + diff，支持 `--strict`）。
- 增强文档门禁：对“运行时工件/计划项”引入规则（忽略或占位表达），并增加详细 README。
- 优化 verifier 控制台排版：文件间与分类间空行、`STATUS` 与信息块分隔，提升可读性。
- 形成可复用资产入口：用 `POSTMORTEM_WORKFLOW.md` 固化“模板 + LESSONS + PREFLIGHT”写回流程（本次复盘已按该流程写回）。


## 2. 背景与最初构思

### 2.1 最初构思（系统建设目标）

- 目标：建立一个本地 RAG/检索项目的“可演进文档体系 + 可门禁化的工具链”，要求：
  - 文档以 Diátaxis 组织：How-to、Reference、Explanation、Postmortems；
  - `HANDOFF.md` 作为 SSOT，给出基线口径与门禁触发器；
  - 关键脚本具备可运行入口与说明，避免“只有聊天记录，没有仓库事实”。

### 2.2 当时的验收/门禁覆盖了哪些层

- 覆盖（已有）：
  - 入口点/console_scripts 的检查（例如 `check_cli_entrypoints.py`）；
  - 部分文档引用检查（存在 verifier，但对输入类型分类不足）；
  - build/check pipeline 的阶段性产物校验（以生成的 report 为证据锚点）。

- 未覆盖或覆盖不足（导致本次暴露）：
  - 文档引用的“输入类型分类”（repo 文件 vs 运行时产物 vs 计划项 vs 外部材料）未形成统一规则；
  - 文档中“示例命令”的 cwd 约束未显式化（导致“命令前后相同”的伪修复路径）；
  - 缺失工具在文档中被引用但仓库未补齐（工具缺口未被 gate 及时升级为 FAIL）；
  - 控制台输出可读性不足，降低人类 review 效率（尤其在密集输出时）。


## 3. 影响与症状

### 3.1 直接影响

- 使用者按文档操作时可能：
  - 运行到“找不到脚本/模块”后中断，排障成本上升；
  - 误以为仓库已有某些工具（计划项）而浪费时间搜索；
  - 因 strict 误报而降低对门禁的信任（风险：开始忽略 FAIL/WARN）。

### 3.2 间接影响（系统演进层面）

- 文档与代码漂移会破坏“证据链”；当证据链断裂，根因分析将退化为猜测。
- 若门禁信号被噪声污染（误报过多），门禁将不再能作为演进触发器（fitness function）使用。


## 4. 复现路径与证据

> 本节按“最小可复现（MRE）”组织：能在仓库根目录直接执行或直接定位到文件。

### 4.1 文档引用严格门禁（主证据）

```cmd
python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict
```

- PASS 条件：退出码 0，控制台 `STATUS: PASS`
- FAIL/WARN 时应输出：按分类分组（BROKEN/AUTO-FIXED/SUGGESTED...），并能定位到 `file:line:col`

**证据锚点**
- 脚本：`src/mhy_ai_rag_data/tools/verify_postmortems_and_troubleshooting.py`
- 说明：`tools/verify_postmortems_and_troubleshooting_README.md`
- 配置：`tools/link_check_config.json`

### 4.2 inventory 构建快照/对比（补齐缺失工具后的验收）

```cmd
python tools\check_inventory_build.py --snapshot-out data_processed\build_reports\inventory_snapshot.json
python tools\check_inventory_build.py --compare-snapshot data_processed\build_reports\inventory_snapshot.json --diff-out data_processed\build_reports\inventory_diff.json
```

- PASS 条件（非 strict）：命令成功返回 0，输出包含统计与差异摘要
- PASS 条件（strict）：若发现差异则返回非 0（用于 gate）

**证据锚点**
- `src/mhy_ai_rag_data/tools/check_inventory_build.py`
- `tools/check_inventory_build.py`
- `tools/check_inventory_build_README.md`

### 4.3 文档命令路径正确性（样例）

- 典型修复：`docs/howto/TROUBLESHOOTING.md` 中将脚本路径改为 `python tools/...` 或明确 `python -m ...` + cwd=repo root。
- 验收方式：按文档逐条复制命令执行（建议先跑 `-h`）并在 postmortem 的 Evidence Ledger 记录输出摘要。

**信息缺口（本次未固化的证据）**
- 若你希望完全“可审计”，建议未来在每次复盘中保留一份 strict 输出的原始日志（例如落盘到 `data_processed/build_reports/docs_gate_run_*.log`）。


## 5. 根因分析

### 5.1 直接根因（机制层）

1) **文档引用未分类**  
   - 把“运行时工件（不入库）”“计划项脚本（未来可能实现）”写成了与“仓库内真实文件”相同的引用形式，导致 strict 校验将其视为断链/缺失，并产生噪声与误导。

2) **入口点与工作目录假设未显式化**  
   - 例如 `python -m tools.xxx` 只有在 cwd 为 repo root 时才成立，但文档没有把这个前提写出来，从而出现“修复前后命令相同”的无效建议。

3) **工具缺口未被及时转化为仓库事实**  
   - 文档引用了 `check_inventory_build.py` 等工具，但仓库当时缺失；缺少“文档引用必须可运行”的门禁原则，导致漂移长期存在。

4) **输出可读性不足**  
   - 报告输出过密，降低人类 review 的吞吐，间接延迟问题收敛。

### 5.2 缺失控制点（Missing Controls）

- 缺失控制点 A：严格文档门禁的“输入类型分类规则”（repo 文件/运行时工件/计划项/外部材料）。
- 缺失控制点 B：文档命令必须声明 cwd/入口点约束。
- 缺失控制点 C：工具引用必须“先实现再写入文档”，或明确占位语义。
- 缺失控制点 D：控制台输出缺少分段与留白，影响人类消费。

### 5.3 为什么当时的门禁没覆盖到

- 当时门禁更偏向“代码入口/依赖漂移”，而不是“文档引用语义正确性”；
- 文档引用检查缺少“语义层规则”，只能做到“字符串层存在性”，因此无法区分“应存在”与“不应存在”；
- 缺少 preflight 中对 doc-gate 的明确条目，导致“重构后必跑”序列未覆盖该风险。


## 6. 修复与变更清单

> 本节只列“能落到仓库路径”的变更；每条尽量给出为何存在的因果。

### 6.1 新增（补齐缺失能力）

- `src/mhy_ai_rag_data/tools/check_inventory_build.py`  
  - 作用：对 `inventory.csv` 生成 snapshot，并与历史 snapshot 做差异对比；支持 `--strict` 门禁化。

- `tools/check_inventory_build.py`（wrapper）  
  - 作用：保持 `python tools\...` 的使用习惯；降低未安装 editable 时的摩擦。

- `tools/check_inventory_build_README.md`  
  - 作用：把工具变为“团队可用资产”，避免只存在于代码。

### 6.2 修改（增强门禁与可读性）

- `src/mhy_ai_rag_data/tools/verify_postmortems_and_troubleshooting.py`  
  - 增强点：可选占位修复策略、运行时工件忽略策略、控制台分段留白排版。

- `tools/link_check_config.json`  
  - 增强点：可配置忽略规则（裸文件名与 regex），减少 strict 误报。

- `tools/verify_postmortems_and_troubleshooting_README.md`  
  - 增强点：补齐 strict/no-fix 的用法、退出码语义、工作流建议。

### 6.3 文档同步（确保 docs↔code 对齐）

- `docs/howto/TROUBLESHOOTING.md`  
  - 修复点：脚本路径、cwd 前提、修复路径有效性。

- `docs/howto/OPERATION_GUIDE.md`  
  - 修复点：Step 8 “闭环”职责分离，避免混入计时 wrapper；减少重复“做什么”。

- `docs/explanation/HANDOFF.md`  
  - 修复点：对计划项脚本使用占位表达（如 `tools/<name>.py`），并在基线口径中避免默认值混淆。

- `docs/howto/POSTMORTEM_WORKFLOW.md`（作为方法论资产）  
  - 作用：固化“模板 + LESSONS + PREFLIGHT”的写回协议与验收序列。


## 7. 预防与门禁闭环

### 7.1 以后遇到类似情况的执行清单（Preflight）

**重构/换机/换环境后必跑（推荐最小序列）**
1) 入口点与 wrapper 一致性  
   ```cmd
   python tools\check_cli_entrypoints.py
   ```
2) 文档引用严格门禁（只验证不改）  
   ```cmd
   python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict
   ```
3)（可选）inventory snapshot/diff（当你改动了收集范围/过滤规则）  
   ```cmd
   python tools\check_inventory_build.py --snapshot-out data_processed\build_reports\inventory_snapshot.json
   ```

### 7.2 多设备/多 venv 一致性操作规程（建议写进团队习惯）

- 任何 “`python -m tools.xxx`” 命令都要求 cwd 在 repo root；否则模块解析会失败并出现误导性报错。
- 每次运行关键脚本前打印并记录：
  - `sys.executable`、`sys.path[0]`、关键依赖版本（如 Python、chromadb、embedding 模型）
- 对外部服务（本地 LLM 代理）把 `base_url/timeout` 固化为“推荐值 + 默认值 + profile 覆盖来源”，避免不同入口点默认分叉。

### 7.3 门禁收紧触发器（从 warning 过渡到 fail）

- 当以下条件满足其一，可将“计划项脚本引用为真实路径”从 WARN 升级为 FAIL：
  - 连续 N 次 strict 运行无误报；
  - `warnings_ratio <= 1%` 且主要问题已被占位/忽略规则覆盖；
  - 新增团队成员使用文档的反馈中“误导”次数下降到可接受水平。


## 8. 可迁移经验

### 8.1 原则库（可迁移）

1) **SSOT 优先，redirect 次之，禁止双写**  
   - 同一事实只能有一个权威正文；其他地方只允许链接/索引。

2) **文档引用必须做“语义分类”**  
   - repo 文件：必须存在；  
   - 运行时工件：允许不存在，但必须有前缀/忽略规则；  
   - 计划项：必须用占位表达；  
   - 外部材料：必须显式标注“仓库外”。

3) **门禁可信度比门禁数量更重要**  
   - 误报会腐蚀门禁；宁可少而准，也不要多而噪。

4) **输出先可读，再可控**  
   - 控制台输出不可读，会降低人类 review 效率，间接延迟修复闭环。

### 8.2 反模式库（可迁移）

- 反模式：文档里出现 `tools/xxx.py`，但仓库不存在且未标注“计划项”。  
- 反模式：用裸文件名（`inventory.csv`）指代运行产物，且未声明其生成步骤/路径前缀。  
- 反模式：同一命令“修复前后相同”，但修复点其实是 cwd；却不写前提。  
- 反模式：把工作流写进模板正文，导致模板膨胀且难维护（应拆分为 How-to）。

### 8.3 类比迁移到其他工程（至少 3–4 个场景）

- **微服务/SDK**：README 的示例代码与 SDK API 漂移 → 需要“示例编译门禁 + 文档引用语义分类”。  
- **配置系统**：运行时生成的 `config.lock` 被当作仓库文件引用 → 需要“产物目录约定 + ignore 规则 + strict gate”。  
- **数据管线**：schema/字段名在代码与数据字典双写 → 需要“schema SSOT + redirect + diff gate”。  
- **CI 与本地分叉**：本地通过、CI 失败，根因是入口点/工作目录不同 → 需要“preflight 固化 cwd/环境探针 + 统一命令入口”。


## 9. 附录

### 9.1 行动项（建议以 commit/issue 跟踪）

| 动作 | 目的 | Owner | 状态 |
|---|---|---|---|
| 将 doc-gate 命令写入 `PREFLIGHT_CHECKLIST.md` | 防止重构后漏跑 | zhiz | 已写回（见本次变更包） |
| 将原则/反模式写入 `LESSONS.md` | 形成跨事件可复用资产 | zhiz | 已写回（见本次变更包） |
| 每次 strict 运行落盘日志（可选） | 提升证据链可审计性 | zhiz | 建议（可后续加入） |

### 9.2 Evidence Ledger（建议你在合并后补齐真实输出）

- E1：`python tools\verify_postmortems_and_troubleshooting.py --no-fix --strict` 的控制台输出与退出码
- E2：`python tools\check_inventory_build.py --help` 的输出截图/文本
- E3：关键文档修订处的 `git diff`（特别是 TROUBLESHOOTING/OPERATION_GUIDE/HANDOFF）
