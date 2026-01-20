# README 与源码对齐：实施计划（面向本项目）

> 目标：持续保证 **指令/说明/描述** 与 **源码行为** 一致，并把漂移前置到提交/合并阶段被发现与阻断。  
> 范围：优先覆盖仓库根目录 `tools/` 下所有 `README*.md` / `*_README*.md`（后续可扩展到其它目录）。

## 文档位置与归档（补充）

- 计划文档当前放置：`docs/explanation/`（你已迁移）
- 项目按计划更新完成后归档：`docs/archive/` 或仓库约定的 `archive/`（以你实际目录为准）

## 现有文档检测工具（补充）

仓库当前已有 2 个“文档相关检测/门禁”工具（需与本计划的 README↔源码对齐门禁做职责切分与组合调用）：

- `tools/check_docs_conventions.py`：Markdown 工程约定检查（标题/空行等）。
- `tools/check_md_refs_contract.py`：`md_refs` 引用抽取 API 契约与调用点约束。

本计划默认策略：**不直接扩展上述工具职责**，而是 **新增专用的 README↔源码对齐门禁工具**，再在 `gate.py` / `check_all.py` 中组合。

---

## 结论

采用 **SSOT（单一事实来源）+ README 可再生产区块 + `--check/--write` 校验/生成脚本 + 本地与 CI 门禁 + 语义/快照抽样测试** 的组合，可系统性降低 README 落后于源码的风险（可行）。

---

## 假设（默认假设）

1. 工具入口与实现之间能够建立稳定映射（通过 README 顶部元数据或集中索引声明）。  
2. CLI 主要为 Python（argparse/Click/Typer/混用均可），但允许逐步覆盖不同框架。  
3. 输出格式升级存在可判定的“契约信号”（如 schema_version、contract_version、registry、统一写报告函数等）。  
4. 团队接受 README 的部分区块由脚本自动维护，并在 PR 中通过 diff review。

---

## 进度记录

> 记录格式：日期 / Step / 状态 / 产出（补丁或仓库路径）/ 备注  
> 状态枚举：`DONE` / `IN_PROGRESS` / `TODO` / `BLOCKED`

| 日期 | Step | 状态 | 产出 | 备注 |
|---|---:|---|---|---|
| 2026-01-20 | 1 | DONE | `ssot_contract_step1_patch.zip`（补丁包）<br>仓库路径：`docs/reference/readme_code_sync.yaml`、`docs/reference/TOOLS_README_CODE_ALIGNMENT_CONTRACT.md`、`docs/INDEX.md`、`docs/reference/REFERENCE.md` | 已按项目文档结构先落地 SSOT 契约（机器可读 + Reference 页面）并补齐导航；后续门禁工具优先读取 YAML。 |
| 2026-01-20 | 2 | DONE | `readme_code_alignment_step2_patch.zip`（补丁包）<br>仓库路径：`docs/reference/readme_code_sync_index.yaml`、`docs/reference/readme_code_sync_needs_manual.yaml`、`docs/reference/TOOLS_README_CODE_SYNC_INDEX.md` + `tools/*README*.md`（54 个 README 补齐 frontmatter/映射） | 已建立 README↔入口映射索引与“需人工确认”清单，为 Step3 的 `--check` 最小闭环提供输入。 |
| 2026-01-20 | 3 | TODO | — | 计划实现 `tools/check_readme_code_sync.py --check` 最小闭环（flags 差分 + 输出契约信号一致性）。 |
| 2026-01-20 | 4 | TODO | — | 计划实现 `--write` 写回 README 自动区块，并保证幂等输出。 |
| 2026-01-20 | 5 | TODO | — | 计划接入 pre-commit 与 CI 门禁（并与现有 doc gates 组合）。 |
| 2026-01-20 | 6 | TODO | — | 计划引入抽样语义测试与 help/输出快照回归（含归一化规则）。 |
| 2026-01-20 | 7 | TODO | — | 计划补齐例外登记、变更流程与 owner 规则。 |

---

## 1) 详细指导（按 Step 组织）

### Step 1 — 明确 SSOT 与对齐目标分层（接口 / 语义 / 产物） [STD]

**进度（2026-01-20）**

- 状态：DONE  
- 落地文件：
  - 机器可读 SSOT：`docs/reference/readme_code_sync.yaml`
  - Reference 契约页：`docs/reference/TOOLS_README_CODE_ALIGNMENT_CONTRACT.md`
  - 并在 `docs/INDEX.md`、`docs/reference/REFERENCE.md` 增加导航入口

用于声明对齐目标与 SSOT：
  - **接口层**：参数集合、默认值、必填性、互斥关系、子命令树  
    - SSOT：源码 parser 定义（argparse/Click/Typer）
  - **语义层**：关键参数行为、退出码、是否写文件/副作用边界  
    - SSOT：语义测试（黑盒/runner）
  - **产物层**：输出契约（schema_version 等）、产物路径/命名规则  
    - SSOT：契约文档 / registry / schema / contract gate 脚本

**为何（因果）**

- 没有 SSOT，校验会退化为“纯文本比对”，无法裁决“谁是事实源”；SSOT 把漂移定义为可阻断事件，并给出裁决顺序。

**关键参数/注意**

- SSOT 作为配置入口应保持稳定（路径与字段名稳定优先于格式偏好），避免脚本与文档再度分叉。

---

### Step 2 — README↔入口映射：frontmatter + 集中索引（对齐索引） [CON]

**进度（2026-01-20）**

- 状态：DONE  
- 落地文件：
  - 集中索引：`docs/reference/readme_code_sync_index.yaml`
  - 需人工确认清单：`docs/reference/readme_code_sync_needs_manual.yaml`
  - 速查索引（人读）：`docs/reference/TOOLS_README_CODE_SYNC_INDEX.md`
  - `tools/*README*.md`：批量补齐 YAML frontmatter（覆盖 54 个 README，不含 `tools/README.md`）

**做什么**

- 为每个 `tools/*README*.md` 引入可机读的映射元数据（frontmatter），并生成集中索引（便于脚本无歧义定位实现入口）。

**为何（因果）**

- 映射是后续 `--check/--write` 的依赖；没有映射，校验只能猜测文件名与入口，错配会造成误报/漏检。

**关键参数/注意**

- 对 wrapper 类工具，应把实现入口指向 `src/mhy_ai_rag_data/tools/...`，而不是 wrapper 本体。
- 动态参数/运行期注册的工具，需要在索引中标注生成策略（例如 `help-snapshot`），避免静态抽取误判。

---

### Step 3 — 校验脚本 v1：接口差分 + 契约信号一致性（`--check`） [OFF]

**做什么**

- 新增 `tools/check_readme_code_sync.py`（建议与 `docs/reference/readme_code_sync.yaml` 同名一致），提供：
  - `--check`：失败即退出码 2（契约违例）
  - `--root` / `--config`：定位 repo root 与 SSOT YAML
- 核心检查：
  1) frontmatter 存在与 required keys
  2) AUTO 区块 marker 合法（BEGIN/END 成对）
  3) options 区块存在时：README flags ≈ 源码 flags（按 generation 模式抽取）
  4) 输出契约：若工具为 report-output-v2/contract_version=2，则 README 必须包含契约引用（或自动区块中出现 schema_version=2 要点）

**为何（因果）**

- 先上线 `--check` 能把漂移前置为可阻断事件，为 Step4 的 `--write` 与后续门禁组合铺路。

**关键参数/注意**

- 输出差异必须可定位：README 文件、对应 tool_id/入口、差异列表、建议修复动作（`--write` / 更新映射 / 登记例外）。
- 抽取策略优先“静态 AST”；对动态 CLI 退化到 `--help` 快照（并做归一化）。

---

### Step 4 — 生成脚本 v1：README 自动区块（`--write`） [CON]

**做什么**

- 为 README 引入派生区块（示例）：
  - `<!-- AUTO:BEGIN options --> ... <!-- AUTO:END options -->`
  - `<!-- AUTO:BEGIN output-contract --> ... <!-- AUTO:END output-contract -->`
  - `<!-- AUTO:BEGIN artifacts --> ... <!-- AUTO:END artifacts -->`
- `--write`：从 SSOT/源码/契约文档生成并写回，保证幂等。

**为何（因果）**

- `--check` 负责发现问题；`--write` 负责把修复变为低成本操作，降低人力维护与再次漂移概率。

**关键参数/注意**

- 幂等要求：稳定排序、固定列、固定空行与换行符；否则 diff 噪声会增大、review 负担上升。

---

### Step 5 — 门禁接入：pre-commit + CI + 与现有 doc gates 组合 [OFF]

**做什么**

- 在 CI gate 链中新增 README↔源码对齐门禁（本计划的工具），并与现有工具并列执行：
  - `check_docs_conventions`（Markdown 工程约定）
  - `check_md_refs_contract`（md_refs API 契约）
  - `check_readme_code_sync`（本计划新增：README↔源码一致性）
- 本地可选：pre-commit hook 运行 `--check`。

**为何（因果）**

- 只要门禁在 PR 合并前强制执行，README 漂移就不能静默进入主分支；同时职责切分能避免把不同 gate 的失败原因混杂。

**关键参数/注意**

- 本计划默认是“新增 gate 工具 + 组合调用”，而不是升级/扩展现有 doc gate 工具职责边界。

---

### Step 6 — 语义抽样测试 + 快照回归（覆盖行为漂移） [CON]

**做什么**

- 选取 5–10 个关键入口建立语义测试：exit code、stderr/stdout 关键提示、是否生成产物、`--dry-run` 副作用等。
- 对 `--help` 或关键输出做快照回归，并对不稳定字段归一化。

**为何（因果）**

- 文档落后于源码的高风险点往往在“行为与产物”；抽样测试能以可控成本覆盖关键路径。

**关键参数/注意**

- 快照归一化必须明确规则（时间戳/路径/随机字段/终端宽度）。

---

### Step 7 — 例外、变更流程与 owner（长期治理） [STD]

**做什么**

- 增加例外登记：`docs/reference/readme_code_sync_exceptions.yaml`
- 贡献指南写入规则：参数/契约变更必须跑 `--write`；例外必须登记并可追踪。
- 指定 owner：README-sync 工具 owner、输出契约 owner、工具目录 owner。

**为何（因果）**

- 最大风险来自“例外无限扩散、无人维护”；登记与 owner 让偏离成为可治理对象。

---

## 2) 替代方案（1–2 个：适用场景 + 代价/限制）

### 替代方案 1：先只上 `--check` 门禁，暂不启用 `--write`

- 适用场景：团队先建立“漂移必须被发现/阻断”的纪律，再逐步引入自动修复。
- 代价/限制：修复动作偏人工；参数迭代频繁时，维护成本会上升。

### 替代方案 2：文档站生成作为主载体，README 仅保留索引

- 适用场景：需要统一呈现多工具文档与版本化发布。
- 代价/限制：需要维护构建与发布管线；若 README 仍承载细节，仍需生成区块/门禁约束。

---

## 交付物清单（建议）

- `docs/reference/readme_code_sync.yaml`（机器可读 SSOT：范围/优先级/markers/checks）
- `docs/reference/TOOLS_README_CODE_ALIGNMENT_CONTRACT.md`（Reference：契约说明与演进规则）
- `docs/reference/readme_code_sync_index.yaml`（README↔入口映射索引）
- `docs/reference/readme_code_sync_needs_manual.yaml`（需人工确认清单）
- `docs/reference/TOOLS_README_CODE_SYNC_INDEX.md`（人读速查索引）
- `tools/check_readme_code_sync.py`（Step3/4：`--check/--write`）
- pre-commit hook（可选）+ CI gate 链新增步骤（Step5）
- 语义测试与快照回归（Step6）
- `docs/reference/readme_code_sync_exceptions.yaml`（Step7）
