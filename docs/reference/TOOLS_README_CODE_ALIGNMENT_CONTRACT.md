---
title: tools/ README ↔ 源码对齐契约（Reference）
version: v1.0
last_updated: 2026-01-20
timezone: America/Los_Angeles
---

# tools/ README ↔ 源码对齐契约（Reference）


> 本文定义“工具 README 与源码一致性”的口径：哪些信息以源码/契约为准，README 应如何承载，以及后续自动校验/生成的边界。  
> **机器可读 SSOT**：`docs/reference/readme_code_sync.yaml`（后续 gate 与生成脚本以此为准）。

## 目录

- [1. 目的与范围](#1-目的与范围)
- [2. 角色划分（SSOT vs 生成产物）](#2-角色划分ssot-vs-生成产物)
- [3. 冲突裁决与优先级（对齐口径）](#3-冲突裁决与优先级对齐口径)
- [4. tools/ README 结构契约](#4-tools-readme-结构契约)
- [5. 对齐点定义（哪些必须与源码一致）](#5-对齐点定义哪些必须与源码一致)
- [6. 自动区块契约（面向生成与门禁）](#6-自动区块契约面向生成与门禁)
- [7. README 映射元数据契约（对齐索引）](#7-readme-映射元数据契约对齐索引)
- [8. 校验与生成接口契约（未来工具约束）](#8-校验与生成接口契约未来工具约束)
- [9. 例外策略（明确登记，不隐式放行）](#9-例外策略明确登记不隐式放行)
- [10. 演进与版本策略](#10-演进与版本策略)
- [11. MRE](#11-mre)

---

## 1. 目的与范围

### 1.1 目的

本契约解决以下问题：

- README 中的命令、参数、输出描述与源码实现不一致，导致误用、误判与复盘证据链断裂。
- 输出格式/字段/路径规则在升级后发生变化，但工具 README 仍停留在旧口径。

本契约的目标是把“对齐”做成仓库资产：

- **可核验**：差异可被脚本稳定发现（`--check`）。
- **可再生产**：关键区块可被脚本刷新（`--write`）。
- **可治理**：允许例外，但必须登记并可追踪。

### 1.2 范围

本契约仅约束：

- `tools/README.md`
- `tools/*_README.md`（以及符合 `tools/` 下 README 约定的同类文件）

不在范围内：

- `docs/` 下的 Diátaxis 文档（除非它们显式声明自己受本契约约束）。
- `src/` 下库 API 文档（其对齐策略属于库文档治理，不归入本契约）。

### 1.3 与现有文档检测工具的关系

当前仓库已存在至少两类“文档相关门禁/检测”工具：

- `tools/check_docs_conventions.py`：对 `docs/` 与 `tools/` 下的 Markdown 做工程约定检查（例如 H1 + 标题后空行），并产出 `docs_conventions_report.json`（report-output-v2）。
- `tools/check_md_refs_contract.py`：对 `md_refs` 的引用抽取 API 做契约门禁（signature + keyword-only callsites），用于防止“文档引用解析接口”在重构时静默漂移。

本契约对应的“README↔源码对齐门禁”属于 **独立职责**：它关注的是 *工具 README 的参数/输出/产物描述是否与实现一致*，而不是 Markdown 版式或引用抽取 API。

因此默认策略是：

1) **不扩大既有工具职责边界**（避免把 style check / API contract gate 与 README 对齐混在同一工具里）。
2) **新建一个专用门禁工具**（本计划的 `--check/--write`），并在 `tools/gate.py` / `tools/check_all.py` 的 gate 链中组合调用。
3) 现有工具保持原语义与输出路径不变；README 对齐门禁只新增其自身报告（若需要），并遵循同一 report-output-v2 规范。

---

## 2. 角色划分（SSOT vs 生成产物）

本仓库在“入口层 / 实现层 / 契约层”三者之间做角色分离：

1) **实现（SSOT：代码）**

- 默认实现位置：`src/mhy_ai_rag_data/tools/<tool>.py`。
- 对于少量 **repo-only 工具**（实现直接位于 `tools/<tool>.py`），`tools/<tool>.py` 本身即为 SSOT（此时 `impl.module` 可为空，仅保留 `impl.wrapper`）。
- 若 `tools/<tool>.py` 为 wrapper，则其行为应转发到 `src`（参见 `tools/README.md` 的 wrapper 约定）。

2) **输出契约（SSOT：Reference）**

- 报告输出与工程规则（schema_version=2）：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`。
- Gate/门禁配置 SSOT：`docs/reference/reference.yaml`。
- 若某工具受 `report_tools_registry.toml` 约束，则 registry 也是输出相关口径的一部分：`docs/reference/report_tools_registry.toml`。

3) **工具 README（Reference：面向使用与操作）**

- README 的角色是“使用说明与操作入口”；其中一部分内容是**派生**（应与 SSOT 一致），另一部分内容是**叙述**（可手写）。
- README 不应成为“参数/字段/路径”的事实源；其事实性内容应可由 SSOT 复核。

---

## 3. 冲突裁决与优先级（对齐口径）

当 README 与其它来源不一致时，裁决顺序如下（从高到低）：

1) **标准/Schema/显式 SSOT 文档**（例如 `REPORT_OUTPUT_ENGINEERING_RULES.md`、JSON Schema、`reference.yaml`）
2) **源码实现（含 CLI 定义与 runtime 行为）**
3) **README 中的自动区块（若存在）**
4) **README 自由文本**

说明：

- README 的职责是“对外呈现”，不是“定义事实”。当版本不一致时，优先检查“README 未升级/README 指向旧版本契约”。

---

## 4. tools/ README 结构契约

### 4.1 Frontmatter（必需字段）

每个 `tools/*README*.md` 必须包含 YAML frontmatter，至少包含：

- `title`
- `version`
- `last_updated`

建议包含：

- `timezone: America/Los_Angeles`

### 4.2 最小章节结构（建议标题集合）

工具 README 建议包含以下章节（允许增删，但“参数/产物/退出码”建议长期保留，以便对齐与检索）：

- 描述
- 适用范围
- 前置条件
- 快速开始
- 参数与用法
- 执行流程（可选）
- 退出码与判定
- 产物与副作用
- 常见失败与处理（可选）
- 关联文档

### 4.3 命令示例的可复制性

- 每段命令块必须标注执行环境（例如 `bash` / `cmd` / `powershell`）。
- 若同一命令在不同 shell 的转义/路径分隔符不同，应分块给出。
- 路径展示遵循项目统一口径：在文档与报告中**统一使用 `/`**（Windows 盘符写作 `c:/...`）。

---

## 5. 对齐点定义（哪些必须与源码一致）

下列信息属于“事实性内容”，README 与 SSOT/源码必须一致（否则视为漂移）：

### 5.1 CLI 参数（接口层）

- 参数名（长短选项）、是否必填、默认值、枚举取值、互斥关系、子命令树。
- `--help` 中可观测的行为必须与 README 的“参数与用法”一致。

约束：

- README 的参数表应由自动区块维护（见第 6 节），或至少可被脚本校验。
- 当参数含运行期动态注册（非静态可枚举）时，应在 README 明确：哪些参数由 `--help` 快照作为对齐对象。

### 5.2 输出契约与产物（产物层）

- `schema_version`（若输出 v2 报告，则必须为 `2`）。
- 默认输出路径（例如 `data_processed/build_reports/...`）与命名规则。
- stdout/stderr 通道边界（哪些输出在 stdout，哪些属于 stderr 提示）。

约束：

- 若工具声明遵循 `schema_version=2`，README 必须引用 `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`，且不得自创与其冲突的字段/排序/路径规则。

### 5.3 退出码

面向门禁/回归的工具，退出码应与仓库统一口径一致：

- PASS = 0
- FAIL = 2
- ERROR = 3

口径来源：`docs/reference/reference.yaml` 的 `exit_codes`。

### 5.4 副作用与可重复性

- 是否写文件、写哪些目录、是否覆盖、是否产生时间戳文件。
- 若支持 dry-run，应在 README 与实现中一致描述其副作用边界。

---

## 6. 自动区块契约（面向生成与门禁）

为让“事实性内容”可被再生产与门禁校验，README 支持在指定区块内放置脚本生成内容。

### 6.1 Marker 约定

自动区块必须使用以下 marker（区块内容由生成器维护）：

- `<!-- AUTO:BEGIN options -->` ... `<!-- AUTO:END options -->`
- `<!-- AUTO:BEGIN output-contract -->` ... `<!-- AUTO:END output-contract -->`
- `<!-- AUTO:BEGIN artifacts -->` ... `<!-- AUTO:END artifacts -->`

### 6.2 区块编辑规则

- `AUTO:BEGIN/END` 之间的内容视为“生成区”。
- 人工改动若与生成结果不一致，`--check` 应报告差异。
- 若确需临时手写（迁移期），必须通过“例外策略”登记（见第 9 节），不得隐式放行。

---

## 7. README 映射元数据契约（对齐索引）

为让校验/生成工具在不猜测的前提下定位实现与入口，工具 README 建议在 frontmatter 中追加“映射元数据”。

### 7.1 推荐字段（迁移期可选；新工具建议必填）

- `tool_id`：稳定工具 id（建议与模块名一致）
- `impl.module`：实现模块（例如 `mhy_ai_rag_data.tools.gate`）
- `impl.wrapper`：兼容入口（例如 `tools/gate.py`，若存在）
- `entrypoints`：推荐入口列表（console_scripts / 模块方式 / wrapper）
- `contracts.output`：输出契约引用（通常为 `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`）

### 7.2 示例

```yaml
---
title: gate.py / rag-gate 使用说明（单入口 Gate）
version: v1.3
last_updated: 2026-01-16
timezone: America/Los_Angeles

# 对齐索引（建议新增）
tool_id: gate
impl:
  module: mhy_ai_rag_data.tools.gate
  wrapper: tools/gate.py
entrypoints:
  - rag-gate
  - python -m mhy_ai_rag_data.tools.gate
  - python tools/gate.py
contracts:
  output: docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md
  gate_ssot: docs/reference/reference.yaml
generation:
  options: help-snapshot
  output_contract: derive-from-reporting
---
```

说明：

- `generation.options` 用于告知生成器如何抽取参数（静态 AST / help 快照 / 手工）。
- `generation.output_contract` 用于告知生成器输出契约段落的来源（从 reporting/registry 推导或人工维护）。

---

## 8. 校验与生成接口契约（未来工具约束）

本契约预期存在一个 repo-only 工具（命名可调整），提供一致的接口：

- `--check`：仅校验一致性（用于 CI/gate）。
- `--write`：在保持幂等的前提下刷新 README 自动区块（用于开发者本地）。

### 8.1 幂等与归一化要求

- 参数排序：建议按 flag 名稳定排序（同一行/同一列格式固定）。
- 默认值展示：建议使用稳定表示（字符串加引号、列表/字典使用 JSON 风格或 Python literal 风格，但必须统一）。
- 路径分隔符：输出内容（含 Markdown）统一 `/`。
- 行尾：生成内容统一 `\n`，避免平台差异引入 diff 噪声。

---

## 9. 例外策略（明确登记，不隐式放行）

允许例外，但必须满足：

1) 可定位：例外明确指向 README 路径与工具 id。
2) 有原因：说明为何无法自动生成/无法稳定校验（例如动态参数、运行期依赖外部服务等）。
3) 有替代：说明替代校验方式（例如 help 快照回归、语义测试、手工 checklist）。
4) 可复审：定义复审触发条件（例如契约版本升级、工具重构、输出格式升级等）。

例外登记位置由 SSOT 指定（见 `docs/reference/readme_code_sync.yaml`）。

---

## 10. 演进与版本策略

- 本文件 `version` 的升级用于记录契约结构的变化（字段新增/语义变更/marker 变更）。
- `docs/reference/readme_code_sync.yaml` 的 `version` 升级用于记录“机器可读约束”的变更。
- 当引入不兼容变更时，应提供迁移期策略：
  - 允许在一段窗口内同时接受旧 marker/旧字段；
  - gate 先 warn 后 fail（若仓库已存在对应门禁分级机制）。

---

## 11. MRE

本契约的最小执行闭环（在未来工具就绪后）：

```bash
# 仅校验（用于 CI）
python tools/check_tools_readme_sync.py --check

# 刷新生成区块（用于本地）
python tools/check_tools_readme_sync.py --write
```

预期输出：

- PASS：无差异或差异均在例外清单范围内。
- FAIL：README 与 SSOT/源码不一致，或 README 自动区块被改动且未同步。
