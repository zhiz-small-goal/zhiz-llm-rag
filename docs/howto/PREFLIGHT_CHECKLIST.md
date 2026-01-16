---
title: Preflight Checklist（重构/换机/换环境后必跑）
version: 0.6
last_updated: 2026-01-15
scope: "本地门禁序列：在变更入口/依赖/环境后，快速确认系统仍可用；并覆盖公开发布前的最小检查"
owner: zhiz
---

# Preflight Checklist（重构/换机/换环境后必跑）


> 目的：把“容易因环境/入口/契约漂移导致返工”的检查固化为**最小可执行序列**。  
> 适用：重构后、换机器/换盘符后、重建 venv 后、升级关键依赖后、合并大 PR 前、**准备公开发布前**。  
> 原则：只收录高频且人工不可靠的检查；每条必须有**命令 + PASS 条件**。

## 目录
- [0. 使用方式](#0-使用方式)
- [1. Quick Path：最小必跑（推荐）](#1-quick-path最小必跑推荐)
- [2. Extended：需要时再跑（可选）](#2-extended需要时再跑可选)
- [3. Public Release Preflight：公开发布前最小检查（推荐）](#3-public-release-preflight公开发布前最小检查推荐)
- [4. 常见失败与处理](#4-常见失败与处理)
- [5. 更新规则](#5-更新规则)

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

### 1.1a 跨平台：单入口 Gate runner（可替代 CMD 脚本）
**命令（bash / PowerShell / CMD 通用）**
```bash
python tools/gate.py --profile ci --root .
```
**PASS 条件**
- 进程退出码为 0
- 产物落盘：`data_processed/build_reports/gate_report.json`（并可查看 `gate_logs/`）
- `gate_report.json` 中本步 `rc/status` 为 PASS（rc=0；FAIL=2；ERROR=3）

> 说明：policy 依赖 conftest；本地缺 conftest 时会 SKIP（CI/Linux 会安装并强制执行）。
>
> 注意：任何 `report_written=...` 仅表示“报告已写出”，不代表门禁通过；以退出码与 `gate_report.json` 为准。

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

### 1.3a 全量 wrapper 一致性门禁
**命令（CMD）**
```cmd
python tools\gen_tools_wrappers.py --check
```
**PASS 条件**
- 退出码为 0（FAIL=2 / ERROR=3）
- 输出无 `missing SSOT`
- 输出无 `wrappers not up-to-date`

### 1.3b 工具布局审计（tools↔src 分层 / 同名冲突）
**命令（CMD）**
```cmd
python tools\check_tools_layout.py --mode fail
```
**PASS 条件**
- 输出 `STATUS: PASS` 且退出码为 0
- 不出现 `unknown_tool_kind` / `name_conflict_tools_vs_src`（以工具输出为准）

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


### 1.4c 审查规范一致性门禁（Review Spec：priority 覆盖 + 生成一致性）

> 目标：保证审查规范的“优先级维度（priority_order）”与“清单域（checklists[].area）”不漂移，并保证 SSOT→生成文档链路是确定性的（避免门禁误报/漏报）。

**命令（CMD）**
```cmd
python tools\validate_review_spec.py --root .
```

**PASS 条件**
- `STATUS: PASS`（或输出含 `[PASS]`）且退出码为 0
- 若你新增了 `priority_order` 维度但未新增同名 `area` 清单，则必须 FAIL（退出码为 2）并提示 missing areas

**常见修复路径（本地）**
- 若提示生成文档 out-of-date：  
  `python tools\generate_review_spec_docs.py --root . --write`
- 若提示 priority 覆盖缺口：  
  修改 `docs/reference/review/review_spec.v1.json`，为新增维度补齐同名 `checklists[].area`；或临时归入“其它”并在 `extensions` 中记录迁移计划（含截止日期与拆分步骤）。


### 1.5 跑单元/轻量测试（若仓库包含 pytest）
**命令（CMD）**
```cmd
pytest -q
```
**PASS 条件**
- `0 failed`（允许 `skipped`，但若新增了门禁类测试不应被跳过）

---

### 1.6 入口治理一致性检查（pre-commit + CI 只认 gate）

> 目标：避免“本地跑 A、CI 跑 B、发布前又跑 C”导致口径漂移。入口应收敛为：**SSOT → gate →（schema/policy）→ 统一退出码**。

参考：[本地 pre-commit 使用指南](pre_commit.md)。

**命令（CMD）**
```cmd
rem pre-commit 是否通过 rag_python 中转并调用 gate（如未使用 pre-commit，可跳过）
if exist .pre-commit-config.yaml findstr /I "tools\\rag_python.py" .pre-commit-config.yaml
if exist .pre-commit-config.yaml findstr /I "tools\\gate.py" .pre-commit-config.yaml

rem GitHub Actions/CI 是否只调用 gate（如未使用 Actions，可跳过）
if exist .github\workflows findstr /S /I "tools/gate.py" .github\workflows\*.yml .github\workflows\*.yaml

rem 防止 CI 绕过 gate 直接调用底层检查脚本（示例：hygiene）
if exist .github\workflows findstr /S /I "check_public_release_hygiene.py" .github\workflows\*.yml .github\workflows\*.yaml
```

**PASS 条件**
- 若存在 `.pre-commit-config.yaml`：能匹配到 `tools\\rag_python.py` 且能匹配到 `tools\\gate.py`
- 若存在 `.github/workflows`：能匹配到 `tools/gate.py`
- CI 工作流中不应直接调用 `check_public_release_hygiene.py`（该条应无输出）；如确需例外，必须在 SSOT/文档中显式说明原因与边界。


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

### 2.4 报告输出可用性契约自检（路径分隔符 + vscode://file 链接）

> 目标：在不依赖 VS Code 启发式 linkify 的情况下，确保“落盘报告”对人类阅读可直接点击定位；同时统一路径展示分隔符以降低跨 OS diff 噪声。回链：  
> - `docs/postmortems/2026-01-15_postmortem_report_output_contract_paths.md`  
> - `docs/postmortems/2026-01-15_postmortem_vscode_clickable_loc_uri.md`

**前置条件**
- 已生成 `data_processed/build_reports/gate_report.json`（可通过 1.1a 的 gate runner 生成）。

**命令（CMD）**
```cmd
rem 1) 生成 gate_report.md（参数以脚本 --help 为准；此处给出常用示例）
python -m src.mhy_ai_rag_data.tools.view_gate_report --report data_processed/build_reports/gate_report.json --md-out data_processed/build_reports/gate_report.md

rem 2) 扫描 build_reports 下的 .json/.md：不应出现反斜杠（展示一致性）
python -c "import pathlib,sys; p=pathlib.Path('data_processed/build_reports'); bad=[x for x in p.rglob('*') if x.suffix in ('.json','.md') and '\\' in x.read_text(encoding='utf-8', errors='ignore')]; print('bad=', [str(x) for x in bad]); sys.exit(2 if bad else 0)"

rem 3) gate_report.md 必须包含显式 vscode://file 链接（点击能力的先决条件）
python -c "import pathlib,sys; t=pathlib.Path('data_processed/build_reports/gate_report.md').read_text(encoding='utf-8', errors='ignore'); ok=('](vscode://file/' in t) or ('vscode://file/' in t); print('has_vscode_link=', ok); sys.exit(2 if not ok else 0)"
```

**PASS 条件**
- 第 2 条扫描退出码为 0（`bad=[]`）。
- 第 3 条检测退出码为 0（`has_vscode_link=True`）。
- 在 VS Code 中打开 `gate_report.md`，点击链接可打开对应文件；若链接包含 `:line:col`，应定位到行/列。

## 3. Public Release Preflight：公开发布前最小检查（推荐）

> 目标：在“将仓库公开/开源”前，快速确认**发布输入集**干净且门禁可执行（数据面 + 控制面）。

### 3.1 仅针对“将要公开的目录”跑 hygiene 审计（数据面）
**命令（CMD）**
```cmd
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope tracked_and_untracked_unignored --respect-gitignore
```
**PASS 条件**
- 进程退出码为 0（若 HIGH>0 通常返回 2=FAIL）
- 报告中 HIGH/MED 为 0（以报告为准）
- `report_written=...` 出现仅用于定位输出路径（不作为 PASS 判断）
- 说明：该命令默认按 Git 语义扫描（tracked + 未跟踪但未被 gitignore 忽略），不会因本地已忽略的数据目录误报。

### 3.2 发布快照独立性检查（避免 worktree/.git 指针耦合）
**命令（CMD）**
```cmd
dir /a .git
```
**PASS 条件**
- 输出显示 `.git` 为 `<DIR>`（目录）。  
  若 `.git` 显示为文件（worktree 指针），则本目录不是独立发布物，需要先删除该 `.git` 文件再 `git init -b main`。

### 3.3 secrets 扫描门禁（控制面）
**推荐方式（无需本地安装 gitleaks）**
- Push 后在 GitHub Actions 确认 `secrets-scan` 工作流至少成功跑过 1 次（PASS）。

**可选：本地安装了 gitleaks 时**
```cmd
gitleaks detect --source . --no-git
```
**PASS 条件**
- 未报告 secrets 命中（或已按仓库策略完成替换/移出）

### 3.4 CI 工作流可解析性（workflow-plane）
**命令（最小做法）**
- 对 `.github/workflows/*.yml` 的任何改动，都必须通过一次远端解析验证：push 后 Actions 不出现 `Invalid workflow file`。

**PASS 条件**
- Actions 列表中 CI 工作流处于可运行状态（能进入 job/step 视图）。

### 3.5 Repo health / community files（开源补齐）
**命令（CMD）**
```cmd
python tools\check_repo_health_files.py --repo . --mode public-release --out data_processed\build_reports\repo_health_report.json
```
**PASS 条件**
- 输出 `result=PASS`
- `required_missing=0` 且 `placeholders=0`（脚本会在控制台列出缺口）
- 控制台出现 `report_written=...` 且对应 JSON 文件可解析

**WARN 处理**
- 若输出 `result=WARN`（通常是可选项如 `CITATION.cff` 或 `CODE_OF_CONDUCT.md` 缺失），表示"可公开但信息不完整"；建议在发布前补齐或在 README 里解释为何不提供。

> 说明：该检查用于拦截“CHANGELOG/CITATION/.editorconfig/CoC 联系方式占位符”等容易遗漏的公开发布治理文件。

**相关文件（仓库根目录）**
- [`../../CHANGELOG.md`](../../CHANGELOG.md)
- [`../../CITATION.cff`](../../CITATION.cff)
- [`../../.editorconfig`](../../.editorconfig)
- [`../../CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md)

---

## 4. 常见失败与处理

- 依赖缺失/可选依赖：优先参考 [PR/CI Lite 门禁说明](ci_pr_gates.md) 与 [排障手册](TROUBLESHOOTING.md)。
- 入口点不一致（console_scripts 缺失/路径漂移）：先修复 editable install 或 PATH/venv 激活，再复跑 1.3。
- wrapper 门禁失败（`missing SSOT` / `wrappers not up-to-date`）：先运行 `python tools\gen_tools_wrappers.py --write` 收敛；若仍提示 `missing SSOT`，检查 `src/mhy_ai_rag_data/tools/<name>.py` 是否存在或该 tools 脚本是否应标记为 REPO-ONLY TOOL（见 [postmortem](../postmortems/2026-01-08_tools_layout_wrapper_gen_exitcode_contract.md)）。
- 文档引用检查失败：先修复被引用文件路径/编码，再复跑 1.4。
- public snapshot 目录 `.git` 为文件：删除该文件并重新初始化独立仓库（见 3.2）。

---

## 5. 更新规则

- 新增条目条件（同时满足至少 2 条）：
  1) 属于关键不变量（破坏会导致统计/契约失真或公开风险）
  2) 高频复发或代价高（返工/重建/重跑成本高）
  3) 人工目测不可靠（必须脚本化才能稳定）
- 任何新增条目必须同时写清：
  - 命令
  - PASS 条件（可被观察到的字段）
  - 对应的失败模式（在 `../explanation/LESSONS.md` 里补一条经验或回链）
