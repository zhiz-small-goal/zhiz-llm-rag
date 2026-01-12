---
title: How-to：在本项目执行审查（Review Workflow）
version: v1.0
last_updated: 2026-01-12
---

# How-to：在本项目执行审查（Review Workflow）

> 目标：把审查从“主观判断”收敛为“按优先级执行的清单 + 证据包”，并与本仓库 gate runner（`tools/gate.py`）对齐，降低迭代过程中的口径漂移与回归风险。

## 目录
- [1) 适用场景](#1-适用场景)
- [2) 输入（审查者需要什么）](#2-输入审查者需要什么)
- [3) 步骤（按优先级）](#3-步骤按优先级)
- [4) 验收信号](#4-验收信号)
- [5) 常见失败与处理](#5-常见失败与处理)

## 1) 适用场景
- 你在开发期提交 PR 或本地分支合并前自检
- 你要评估一项变更是否需要同步更新文档/契约/门禁
- 你要把审查输出沉淀为可复用的报告（用于复盘/回归对比）

## 2) 输入（审查者需要什么）
审查者在开始前应能获得以下信息（建议写在 PR 描述顶部）：

- 目标：本次改动要解决什么问题
- 范围：涉及哪些目录/模块/契约
- 影响面：对产物、CLI、schema、gate 的影响
- 验证方式：至少 1 条可复核命令 + 期望信号（PASS/产物路径/关键计数）

## 3) 步骤（按优先级）

### Step 1：文档清晰度（优先）
**做什么**：先从入口文件确认“新信息可发现”。检查 `README.md` 与 `docs/INDEX.md` 是否新增了指向新文档/新工具的链接；再打开目标文档确认它按 Diátaxis 分型落点正确：操作流程应在 `docs/howto/`，契约/格式应在 `docs/reference/`。对 How-to 文档逐步核对每个 Step 是否包含“做什么 + 为何（因果）+ 关键参数/注意”，并提供验收信号（命令输出或产物路径）。  
**为何（因果）**：入口不可发现会导致后续维护依赖个人记忆；How-to 缺少验收信号会让审查无法区分“描述正确”与“可执行且可复核”。  
**注意**：若文档引用外部工具/规范，必须标注版本或访问日期；若未指定版本，默认“截至当前日期最新稳定版”。

### Step 2：代码质量（退出码/诊断/覆盖）
**做什么**：对新增/修改脚本检查三类不变量：退出码是否收敛到 {0,2,3}；失败诊断是否可定位（建议 `file:line:col`）；关键不变量是否已有 tests 或 gate step 覆盖。建议优先运行 `python tools/gate.py --profile fast --root .` 作为统一信号入口，并在必要时查看 `data_processed/build_reports/gate_logs/*.log` 进行定位。  
**为何（因果）**：CI 与 gate runner 的自动判定依赖退出码语义稳定；诊断不可定位会把排障成本转移到人工搜索；关键不变量缺覆盖会在重构后复现回归。  
**注意**：若你添加的是 `tools/*.py`，需要遵循 tools contract（wrapper vs repo-only）并包含 marker；否则 `tools/check_tools_layout.py` 会在 gate 中 FAIL。

### Step 3：可复用性（SSOT 与单一真源）
**做什么**：检查同一规则是否存在“多处双写”。例如：若新增了契约（schema/参数/门禁顺序），应优先落到 SSOT（`docs/reference/reference.yaml` 或本目录的 `review_spec.v1.json`），并通过生成器/校验脚本保持人类可读文档与 SSOT 一致。对于对外入口，优先 `console_scripts` 或 `python -m`；如需 `tools/` 兼容入口，应以 wrapper 转发到 `src/` 的权威实现。  
**为何（因果）**：双写会在迭代中产生语义漂移；入口不统一会造成“同名多实现/导入影子覆盖”，增加回归风险。  
**注意**：若你引入新字段但不想立刻破坏旧口径，优先放到 `extensions` 预留区，并用 SemVer 控制升级节奏。

### Step 4：安全性（secrets/依赖/策略）
**做什么**：检查是否引入明文密钥/令牌或把敏感路径写入文档示例；若新增依赖，确认其用途、替代方案与影响面被写入变更说明（必要时更新 `docs/reference/deps_policy.md`）。对 policy 改动，确认 conftest/reg o 输入路径与 CI 行为一致。  
**为何（因果）**：明文 secrets 属于不可逆风险；依赖会带来长期维护与供应链风险；policy/CI 行为不一致会造成“本地 PASS、CI FAIL”的差异信号。  
**注意**：对外服务示例必须使用占位符（如 `YOUR_TOKEN_HERE`），避免误复制粘贴造成泄露。

### Step 5：报告可读性（人类与机器双通道）
**做什么**：如果本次变更产出报告（JSON/日志/汇总），检查其是否有“摘要先行”：顶部包含 status、关键计数与产物路径；并确认人类可读输出与 JSON 字段一致。建议使用 `docs/reference/review/review_report_template.md`/`.json` 的结构作为基线，确保未来可聚合对比。  
**为何（因果）**：缺摘要会导致审查者需要在长日志中定位关键信息；字段不一致会使回归聚合与工具消费不可靠。  
**注意**：诊断信息建议同时写入 gate logs（便于在 CI artifact 中获取）并保持稳定字段名。

## 4) 验收信号
- Gate 统一信号：`python tools/gate.py --profile ci --root .` 输出 PASS，且 `data_processed/build_reports/gate_report.json` 生成成功
- 文档入口：README 与 docs/INDEX 均可跳转到新增文档
- 产物一致性：若存在 SSOT→生成文档链路，则 `tools/validate_review_spec.py` PASS

## 5) 常见失败与处理
- Gate FAIL：优先查看 `data_processed/build_reports/gate_logs/<step>.log`，按其中的 `path:line:col` 定位修复
- 文档断链：更新 `README.md`/`docs/INDEX.md` 的相对路径或锚点标题
- SSOT 与生成产物不一致：修改 SSOT 后运行 `python tools/generate_review_spec_docs.py --root . --write` 刷新生成文档
