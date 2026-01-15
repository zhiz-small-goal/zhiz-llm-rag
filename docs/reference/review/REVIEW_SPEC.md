---
title: 项目审查规范（Review Spec）
version: v1.0.1
last_updated: 2026-01-15
timezone: America/Los_Angeles
source: docs/reference/review/review_spec.v1.json
generated_artifact: docs/reference/review/REVIEW_SPEC.md
---

# 项目审查规范（Review Spec）


> SSOT（机器可读）：`docs/reference/review/review_spec.v1.json`
> 生成产物（人类阅读）：`docs/reference/review/REVIEW_SPEC.md`（本文件）

本规范用于在仓库内以一致口径审查：文档、代码、复用、安全与报告输出。核心思想是“证据化审查”：每条关键判断都应能通过可定位证据复核（文件路径/行列、命令、报告产物、schema）。

## 目录
- [1. 概览](#1-概览)
- [2. 适用范围与优先级](#2-适用范围与优先级)
- [3. 审查工作流（PR 边界）](#3-审查工作流pr-边界)
- [4. 审查清单（按优先级）](#4-审查清单按优先级)
- [5. 证据包与报告模板](#5-证据包与报告模板)
- [6. 演进接口与版本策略](#6-演进接口与版本策略)
- [7. 引用](#7-引用)

## 1. 概览

- 项目类型：LLM RAG 检索/数据管线（Python）
- 当前阶段：开发中
- 审查优先级（高→低）：文档清晰度 > 代码质量 > 可复用性 > 安全性 > 报告可读性 > 其它

## 2. 适用范围与优先级

### 2.1 适用范围（paths）

- `docs/**`
- `src/**`
- `tools/**`
- `schemas/**`
- `policy/**`
- `.github/**`

### 2.2 不在范围内（out-of-scope）

- 训练数据/模型权重本体
- 第三方依赖源码（third_party/）的上游变更

## 3. 审查工作流（PR 边界）

以 PR 为边界的证据化审查：先保证文档入口与契约可发现，再检查代码不变量与回归信号，最后确认报告与诊断可定位。

### 3.1 角色

- Author：提交者（PR 作者）
- Reviewer：审查者（维护者/协作者）

### 3.2 流程（MUST）

**Step 1：PR 准备**
- MUST: 变更说明包含：目标、范围、影响面、验证方式（命令+期望信号）。
- MUST: 若改动引入/修改契约（schema/exit code/产物路径），必须同步更新 reference 文档与 SSOT。

**Step 2：审查执行**
- MUST: 按优先级顺序审查：文档→代码→复用→安全→报告。
- MUST: 对关键结论必须给可定位证据（文件/行号、命令输出、schema/commit）。

**Step 3：合并与写回**
- MUST: 合并前 gate 必须 PASS（或明确记录豁免理由与后续收紧触发器）。
- MUST: 必要时写回：docs/howto、docs/reference、HANDOFF 或 Postmortem。

## 4. 审查清单（按优先级）

说明：每个条目包含 Level（MUST/SHOULD/MAY）、要求、理由与证据。若条目有 automation 字段，表示可接入 gate/CI 进行自动化校验。

### 4.1 文档清晰度

- **DOC-ENTRY-001** `[MUST]`：新增/关键文档必须在可发现入口处有跳转（README 或 docs/INDEX 或 reference 入口）。
  - Why：入口不可发现会导致维护知识无法被复用，审查与排障依赖个人记忆。
  - Evidence：
    - README.md 与 docs/INDEX.md 中存在可点击相对链接
    - 链接目标文件存在且锚点可定位
- **DOC-CAN-002** `[MUST]`：How-to 文档按 Step 组织，每步包含：做什么 + 为何（因果）+ 关键参数/注意，并给验收信号。
  - Why：将文字转化为可执行过程，降低漂移。
  - Evidence：
    - 每个 Step 有命令/改动说明
    - 提供期望输出或产物路径
- **DOC-VERSION-003** `[MUST]`：涉及契约/工具/依赖的文档必须标注版本/日期；未指定时按“截至当前日期最新稳定版”。
  - Why：减少因版本差异产生的口径冲突。
  - Evidence：
    - 文档 YAML header 含 version/last_updated
    - 对外部规范/工具引用含版本或访问日期

### 4.2 代码质量

- **CODE-EXIT-001** `[MUST]`：脚本退出码遵循项目契约 {0,2,3}，并在 README/Reference 中可定位说明。
  - Why：CI 与 gate runner 依赖稳定退出码进行自动化判定。
  - Evidence：
    - tools/check_exit_code_contract.py PASS
    - 新脚本在 docstring 中声明退出码语义
  - Automation：`tools/check_exit_code_contract.py`（mode=fail）
- **CODE-LOC-002** `[SHOULD]`：诊断展示使用 `file:line:col`；若输出为“落盘报告”（JSON/Markdown），应额外提供 `loc_uri`（`vscode://file/<abs_path>:line:col`）或把定位渲染为 Markdown 链接，以保证在报告文件内可点击跳转。
  - Why：缩短问题定位路径，提升审查与排障效率。
  - Evidence：
    - 失败输出包含可点击定位，例如: [path/to/file.py:12:5](vscode://file/...:12:5): [FAIL] ...
- **CODE-TEST-003** `[MUST]`：关键不变量（高频回归点）必须在 tests/ 或 gate step 中有自动化覆盖。
  - Why：人工审查对隐藏回归不具备稳定性。
  - Evidence：
    - pytest -q 覆盖关键路径
    - 或 gate profile 中包含对应检查 step

### 4.3 可复用性

- **REUSE-SSOT-001** `[MUST]`：同一规则/契约仅保留一个 SSOT；若需要人类可读文档，应由生成器从 SSOT 生成。
  - Why：减少双写导致的语义漂移。
  - Evidence：
    - 存在 SSOT 文件（yaml/json）
    - 存在生成器或自动校验（--check）
- **REUSE-CLI-002** `[SHOULD]`：对外入口优先通过 console_scripts 或 python -m 方式提供，避免依赖相对路径运行。
  - Why：减少因工作目录/导入路径差异导致的运行问题。
  - Evidence：
    - tools/README.md 中入口说明与 gate 校验一致

### 4.4 安全性

- **SEC-SECRET-001** `[MUST]`：不得在仓库中提交明文密钥/令牌；涉及外部服务的示例必须使用占位符。
  - Why：避免泄露与不可逆风险。
  - Evidence：
    - .gitleaks.toml / pre-commit 配置存在
    - 新增文档未包含真实 token
- **SEC-SUPPLY-002** `[SHOULD]`：新增依赖需给出用途与替代方案，避免引入不必要的攻击面与维护成本。
  - Why：依赖是长期接口，影响可维护与可审计性。
  - Evidence：
    - pyproject.toml 变更说明含动机与影响
    - docs/reference/deps_policy.md 更新（如适用）

### 4.5 报告可读性

- **REP-SUMMARY-001** `[MUST]`：机器可读报告（JSON）必须在顶部提供 summary（status/关键计数/路径），并与人类可读输出一致。
  - Why：CI 聚合与人工阅读都需要稳定的入口字段。
  - Evidence：
    - schema_version 字段存在
    - status 与退出码映射可复核
- **REP-TEMPLATE-002** `[SHOULD]`：对人工审查输出提供统一模板（md/json），包括：结论、假设、步骤、证据、失败分支、MRE。
  - Why：降低不同人输出风格差异带来的理解成本。
  - Evidence：
    - docs/reference/review/review_report_template.md 存在并可引用

### 4.6 其它

- **OTHER-NOTE-001** `[MAY]`：若本次变更引入新的审查维度（未覆盖在现有清单中），在 SSOT 的 extensions 中记录，并在后续迭代补齐到清单。
  - Why：为演进式架构预留“先记录、后收敛”的接口，避免口径缺失导致的审查争议。
  - Evidence：
    - extensions 字段存在并记录迁移说明（如适用）

## 5. 证据包与报告模板

### 5.1 PR 证据包（建议最小集）

- 变更摘要：目标/范围/影响面/回滚方式（如适用）
- 验证命令：至少包含 1 条本地可复核命令（例如 `python tools/gate.py --profile fast --root .`）
- 产物路径：若产出 JSON 报告或中间文件，给出相对路径
- 定位信息：诊断尽量使用 `file:line:col`（编辑器可跳转）

### 5.2 报告模板

- 人类可读模板：`docs/reference/review/review_report_template.md`
- 机器可读模板：`docs/reference/review/review_report_template.json`

### 5.3 与 Gate/CI 的关系

本规范自身通过 `tools/validate_review_spec.py` 在 gate 中进行“SSOT 校验 + 生成产物一致性检查”。当 SSOT 变更但未同步刷新生成文档时，gate 将 FAIL，避免口径漂移。

## 6. 演进接口与版本策略

- 版本策略：SemVer（2.0.0）
- 兼容策略：新增字段优先放入 extensions；破坏性变更提升 MAJOR，并在 CHANGELOG.md 记录迁移说明。

### 6.1 扩展点（extensions）

- `extensions`：预留给新增维度/新字段；优先以扩展字段落地，再评估是否升级主结构版本。
- `reporting.extensions`：预留给报告额外字段（例如统计指标、回归对照组）。

## 7. 引用

下列引用用于解释本规范的组织方式与通用审查实践；项目内实现以仓库 SSOT/源码为准。

- Diátaxis documentation framework | https://diataxis.fr/ | accessed 2026-01-12 | official_doc | Homepage (4 documentation types)
- Google Engineering Practices: Code Review Developer Guide | https://google.github.io/eng-practices/review/developer/ | accessed 2026-01-12 | official_doc | Developer guide
- PEP 8 – Style Guide for Python Code | https://peps.python.org/pep-0008/ | accessed 2026-01-12 | standard | PEP 8
- Semantic Versioning 2.0.0 | https://semver.org/ | 2.0.0 / accessed 2026-01-12 | standard | Specification
- OWASP Code Review Guide v2 (PDF) | https://owasp.org/www-project-code-review-guide/assets/OWASP_Code_Review_Guide_v2.pdf | v2 / accessed 2026-01-12 | official_doc | Code Review Guide v2

