# README 与源码对齐：实施计划（面向本项目）

> 目标：持续保证 **指令/说明/描述** 与 **源码行为** 一致，并把漂移前置到提交/合并阶段被发现与阻断。  
> 范围：优先覆盖仓库根目录 `tools/` 下所有 `README*.md` / `*_README*.md`（后续可扩展到其它目录）。

---

## 结论

采用 **SSOT（单一事实来源）+ README 可再生产区块 + `--check/--write` 校验/生成脚本 + 本地与 CI 门禁 + 语义/快照抽样测试** 的组合，可系统性降低 README 落后于源码的风险（可行）。

---

## 假设（默认假设）

1. 工具入口与实现之间能够建立稳定映射（通过 README 顶部元数据声明）。  
2. CLI 主要为 Python（argparse/Click/Typer/混用均可），但允许逐步覆盖不同框架。  
3. 输出格式升级存在可判定的“契约信号”（如 schema_version、contract_version、registry、统一写报告函数等）。  
4. 团队接受 README 的部分区块由脚本自动维护，并在 PR 中通过 diff review。

---

## 1) 详细指导（按 Step 组织）

### Step 1 — 明确 SSOT 与对齐目标分层（接口 / 语义 / 产物） [STD]

**做什么**

- 新增一份规则文档（建议：`docs/engineering/readme-sync.md`），声明对齐目标与 SSOT：
  - **接口层**：参数集合、默认值、必填性、互斥关系、子命令树  
    - SSOT：源码 parser 定义（argparse/Click/Typer）
  - **语义层**：关键参数行为、退出码、是否写文件/副作用边界  
    - SSOT：语义测试（黑盒/runner）
  - **产物层**：输出契约（schema_version 等）、产物路径/命名规则  
    - SSOT：契约文档 / registry / schema / contract gate 脚本

**为何（因果）**

- 不先定义 SSOT，会导致“比对不一致但无法判定谁对”；先定规则才能把漂移定义为“可阻断的工程问题”。

**关键参数/注意**

- 先覆盖 `tools/` 下 README；其它目录后续按批次纳入。
- 需要明确 legacy/v1 工具的标注方式与例外策略（见 Step 7）。

---

### Step 2 — README 顶部增加可机读“映射元数据”（消除脚本猜测与误报） [CON]

**做什么**

- 在每个工具 README 顶部增加极小的 YAML frontmatter（或注释块），至少包含：
  - `tool_script`: 源码入口（脚本路径或模块入口）
  - `cli_framework`: `argparse|click|typer|other`
  - `output_contract`: `report-output-v2|legacy|none`
  - 可选：`generation_mode`: `static-ast|help-snapshot|custom`
  - 可选：`entrypoints`: 多入口数组（一个 README 覆盖多个工具时）

**为何（因果）**

- 映射是对齐系统的索引；没有映射会产生错配、漏检、误报，导致“对齐动作”本身不可靠。

**关键参数/注意**

- 元数据只承担“定位”，不要把参数表写进元数据。
- wrapper 类入口需显式标注其“参数来源在下游工具”，避免 README 被误认为 SSOT。

---

### Step 3 — 校验脚本 v1：flags/默认值 + 契约信号一致性（仅检查，不写回） [OFF]

**做什么**

- 新增 `tools/check_readme_code_sync.py`（命名可调整），实现：
  1. 扫描 `tools/` 下 README 文档；
  2. 解析 frontmatter → 定位源码入口；
  3. 提取源码参数（建议优先 **静态 AST**；动态 CLI 走 `--help` 快照兜底）；
  4. 从 README 的指定区块抽取 `--flag`（限定范围，避免历史记录误触发）；
  5. 输出 diff：missing/extra/renamed-suspect；
  6. 输出契约校验：源码出现 v2 信号，但 README 未声明 v2 或未引用契约文档/registry → 报错。

**为何（因果）**

- 先把“可机械判定的漂移”门禁化，能快速提高一致性基线，并为生成脚本提供抽取能力。

**关键参数/注意**

- 抽取范围建议限定在 README 的 AUTO 区块或特定标题段落，降低噪声。
- 输出必须可定位：README 文件、入口脚本、差异列表、建议操作（运行 `--write` / 更新映射 / 登记例外）。

---

### Step 4 — 生成脚本 v1：README 自动区块（方案 B 核心，支持 `--write`） [CON]

**做什么**

- 在 README 中引入可覆盖区块（示例）：
  - `<!-- AUTO:BEGIN options -->`：参数表（flag、默认值、必填性、简要语义）
  - `<!-- AUTO:BEGIN output-contract -->`：输出契约摘要（版本、顶层字段、产物路径规则、stderr out-token 规则等）
- 脚本提供：
  - `--write`：从 SSOT 生成区块并写回 README
  - `--check`：对比区块与生成结果一致性（CI 门禁用）

**为何（因果）**

- 仅校验会把修复成本压给人；`--write` 才能把一致性维护变成低成本操作，并降低 README 漂移再发生率。

**关键参数/注意**

- 生成内容必须 **幂等**（稳定排序、固定列、固定空行与换行符）；否则 diff 噪声会增大。
- 对动态参数或 import 副作用强的工具，`options` 可退化为 `help-snapshot` 生成模式，并在元数据声明。

---

### Step 5 — 接入本地与 CI 门禁：让漂移不能静默合并 [OFF]

**做什么**

- 本地：使用 pre-commit（或同类框架），提交前运行：
  - `python tools/check_readme_code_sync.py --check`
- CI：在单元测试之前运行同一命令，失败阻断合并。
- 迁移策略：分阶段从“仅覆盖高风险 README”扩展到全覆盖：
  - 阶段 1：覆盖当前 mismatch 名单（历史存量集中清）
  - 阶段 2：扩展到所有 `tools/README*.md`
  - 阶段 3：扩展到其它目录（如需要）

**为何（因果）**

- 只有流程门禁才能把一致性从“建议”变成“约束”，并把问题前置到提交/合并前解决。

**关键参数/注意**

- CI 需统一 Python 主版本与行尾规则，避免无意义差异。
- 允许本地跳过（紧急）不应影响 CI 的最终裁决。

---

### Step 6 — 语义层抽样测试 + 快照回归（覆盖“描述落后于行为”的风险） [CON]

**做什么**

- 从 `tools/` 中选取 5–10 个关键入口（高频/高影响），建立最小语义测试：
  - exit code、stderr/stdout 关键提示、是否生成输出文件、`--dry-run` 是否无副作用等
- 对以下内容做快照回归（并归一化去噪）：
  - `--help` 输出（覆盖动态参数）
  - 最小输入下的 JSON 输出/关键 report 片段（锁定产物结构与关键字段）

**为何（因果）**

- 参数对齐主要覆盖接口层；语义与产物层漂移会导致“说明正确但行为变了”，需通过测试与快照将其显性化。

**关键参数/注意**

- 快照必须归一化：时间戳、绝对路径、随机字段、终端宽度等。
- 控制执行成本：使用临时目录与最小夹具，避免引入外部服务依赖。

---

### Step 7 — 长期运行机制：例外策略、变更流程、责任归属（防止体系退化） [STD]

**做什么**

- 新增例外登记文件（建议：`docs/engineering/readme-sync-exceptions.yml`），每条例外必须包含：
  - 工具标识、原因、替代校验方式、复审条件/触发点
- 在贡献指南中写入规则：
  - CLI 参数/输出契约变更必须运行 `--write` 更新 README 自动区块
  - 需要修改契约/registry 时必须同步更新引用与门禁
- 指定 owner：
  - README-sync 脚本 owner
  - 输出契约 owner
  - 各工具目录 owner（至少到目录层级）

**为何（因果）**

- 主要风险来自“规则无人维护、例外无限扩散”；例外与 owner 使偏离成为可治理对象。

**关键参数/注意**

- 例外必须具备复审触发条件（版本升级、重大重构等）。
- 可与 CODEOWNERS 或审查规则联动，让变更自动触发相关人 review（如仓库已有机制）。

---

## 自检（≥3）

1. 方案不绑定 argparse：通过 `cli_framework` 与 `generation_mode` 支持 Click/Typer/自研框架的 backend 扩展。  
2. 不强依赖“执行工具”才能校验：静态 AST 为主，动态 help/语义测试为兜底与抽样。  
3. 对齐覆盖面分层：接口层门禁优先上线，语义/产物层通过抽样测试与快照逐步增强，控制初期引入成本。

---

## 失败（≥3：触发/原因/缓解/备选）

1. **现象**：上线门禁后大量失败；  
   - 原因：历史存量漂移集中；  
   - 缓解：分阶段覆盖 + `--write` 批量修复；  
   - 备选：CI 先 warn 并产出修复补丁工件，后续切换 hard gate。  

2. **现象**：动态子命令参数漏检；  
   - 原因：静态 AST 无法覆盖运行期注册；  
   - 缓解：对该工具启用 `help-snapshot` 模式 + 快照回归；  
   - 备选：要求工具提供 `--dump-spec json` 结构化声明供校验与生成使用。  

3. **现象**：快照不稳定导致频繁失败；  
   - 原因：时间戳/路径/随机/环境差异；  
   - 缓解：归一化过滤 +（必要时）工具层提供确定化开关；  
   - 备选：快照仅锁定结构与关键字段，其它字段用模式断言或忽略。  

---

## MRE（最小可复现）

**环境**

- Python 3.11+；仓库根目录可运行 `python tools/...`。  
- 如需：pre-commit、pytest、pytest-regressions（按仓库依赖体系纳入）。

**命令**

```bash
# 1) 仅校验（CI/门禁）
python tools/check_readme_code_sync.py --check

# 2) 自动修复（开发者本地）
python tools/check_readme_code_sync.py --write

# 3) 运行抽样语义/快照测试（CI）
pytest -q
```

**pre-commit 示例（可选）**

```yaml
repos:
  - repo: local
    hooks:
      - id: readme-code-sync
        name: readme-code-sync
        entry: python tools/check_readme_code_sync.py --check
        language: system
        pass_filenames: false
```

---

## 2) 替代方案（1–2 个：适用场景 + 代价/限制）

### 替代方案 1：先只上“门禁校验”，暂不启用 README 自动生成

- 适用场景：团队对自动覆盖 README 接受度尚未建立，先把漂移变成可见失败。  
- 代价/限制：修复动作仍偏人工；工具数量与参数迭代频率上升时，修复成本上升。

### 替代方案 2：文档站生成作为主载体（Sphinx/MkDocs），README 仅保留索引

- 适用场景：需要统一呈现多工具文档与版本化发布；README 只做导航。  
- 代价/限制：需要维护构建与发布管线；若 README 仍含细节，仍需生成区块/门禁约束。

---

## 交付物清单（建议）

- `docs/engineering/readme-sync.md`（规则与 SSOT）
- `docs/engineering/readme-sync-exceptions.yml`（例外登记）
- `tools/check_readme_code_sync.py`（`--check/--write`）
- README 自动区块模板（各工具 README 内）
- `.pre-commit-config.yaml` hook（可选）
- CI 工作流中新增门禁步骤（按现有 CI 入口接入）
- `tests/` 下语义抽样与快照回归（逐步扩展覆盖）
