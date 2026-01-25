---
title: Report Output v2 后续落地规划（Planning）
version: 1.0.0
last_updated: 2026-01-18
timezone: "America/Los_Angeles"
owner: "zhiz"
status: draft
scope: report-output-v2
---

## 目录
- [1. 目标与范围](#1-目标与范围)
- [2. 基线口径](#2-基线口径)
- [3. 交付物清单](#3-交付物清单)
- [4. 里程碑与步骤](#4-里程碑与步骤)
  - [4.1 里程碑 A：契约 SSOT 收口](#41-里程碑-a契约-ssot-收口)
  - [4.2 里程碑 B：报告工具元数据声明](#42-里程碑-b报告工具元数据声明)
  - [4.3 里程碑 C：报告工具 Registry](#43-里程碑-c报告工具-registry)
  - [4.4 里程碑 D：Selftest 动态验收](#44-里程碑-dselftest-动态验收)
  - [4.5 里程碑 E：统一检测脚本与门禁接入](#45-里程碑-e统一检测脚本与门禁接入)
  - [4.6 里程碑 F：收紧策略与回滚](#46-里程碑-f收紧策略与回滚)
- [5. 验收标准](#5-验收标准)
- [6. 失败模式与缓解](#6-失败模式与缓解)
- [7. MRE](#7-mre)

## 1. 目标与范围
本规划面向仓库内所有“会产出输出工件”的工具与脚本（报告 JSON/Markdown、事件流、checkpoint、状态元数据 index_state/db_build_stamp），以 **Report v2 契约**为统一输出层。目标是把“格式、排序、链接可点、空行规范、即时写入、异常可追溯、终端回放”从约定升级为 **可自动验收的门禁**。

范围包含：
- 报告类工具（check/eval/gate 等）
- 状态元数据（index_state.json、db_build_stamp.json）
- 高成本生成（events.jsonl、checkpoint.json、durability 模式）
- 控制台渲染（严重度分组、空行规范、末尾 `\n\n`、token 规则 `out = path`）

不包含（除非另行纳入）：
- 业务正确性集成测试（只验证输出契约与可追溯/可恢复能力）
- 外部插件生态（PyPA entry points 可作为后续增强）

## 2. 基线口径
- 时间口径：截至 2026-01-18
- 契约版本：Report Output v2（schema_version=2）
- SSOT：`docs/reference/REPORT_OUTPUT_CONTRACT.md`（建议固定该路径，避免引用漂移）
- 输出通道规则：
  - 文件：summary 置顶，按严重度从重到轻排序（最重要在上）
  - 控制台：summary 置底，按严重度从轻到重输出（最重要在下），末尾额外空行 `\n\n`
  - 空行：item 间 1 行空行；severity 分组间 2 行空行；禁止连续超过 2 行空行
- 链接：文件内需 VS Code 可点击（loc_uri / Markdown 链接）；控制台需避免 `key=value` 粘连导致误识别（推荐 `out = path`）

## 3. 交付物清单
文档与契约（SSOT 相关）：
- `docs/reference/REPORT_OUTPUT_CONTRACT.md`（合并后的单一真源）
- （可选）旧文件 deprecated stub（若历史存在旧路径）

工具声明与 registry：
- `docs/reference/report_tools_registry.toml`（报告工具 registry，SSOT）
- 各报告工具模块内新增 `REPORT_TOOL_META` 常量（字面量 dict）

统一检测与门禁：
- `tools/check_report_tools_contract.py`（静态+动态两层）
- pre-commit 配置新增 hook（静态必跑；动态按变更集/分层）
- pytest 用例（全量动态验收，可上传产物）

## 4. 里程碑与步骤

### 4.1 里程碑 A：契约 SSOT 收口
**做什么**
- 固定 SSOT 路径为 `docs/reference/REPORT_OUTPUT_CONTRACT.md`
- 合并现有工程规则（空行、token、即时写入、回放、registry/meta/selftest/门禁）进入 SSOT
- 将旧契约文件（若存在）改为 deprecated stub，仅保留新 SSOT 链接与迁移说明（≤10 行）

**为何（因果）**
- 解决“多份契约并存导致引用漂移与口径冲突”
- 为后续统一检测脚本提供单一版本号/规则来源

**关键参数/注意**
- YAML 中 `ssot: true` 全仓只能出现一次
- 锚点（目录链接）尽量保持稳定，减少外链失效

**验收**
- 全仓搜索旧路径/旧标题，除 stub 外不再出现
- SSOT 文档目录可跳转，且包含你要求的控制台空行规范与回放条款

---

### 4.2 里程碑 B：报告工具元数据声明
**做什么**
- 对所有会产出 v2 输出工件的工具模块，增加模块级字面量：
  - `REPORT_TOOL_META = {...}`
- 字段至少包含：
  - `kind`（CHECK_REPORT/INDEX_REPORT/STATE_REPORT/EVAL_REPORT/GATE_REPORT）
  - `contract_version=2`
  - `channels`（console/file/events/checkpoint）
  - `high_cost`（bool）
  - `supports_selftest`（bool）

**为何（因果）**
- 用“脚本自描述”替代注释口头约定，便于静态提取与审计
- 为 registry 与统一检测提供一致性对照

**关键参数/注意**
- 必须是字面量（便于 AST 静态提取），禁止运行时计算
- `kind` 枚举由 SSOT 定义，新增枚举必须同步更新 SSOT 与检测器

**验收**
- 静态扫描能列出所有 META，并输出非法/缺失项列表（无缺失/无非法）

---

### 4.3 里程碑 C：报告工具 Registry
**做什么**
- 新增 `docs/reference/report_tools_registry.toml` 作为报告工具集合的 SSOT：
  - 模块路径
  - kind
  - selftest 调用参数（含 out 目录/文件模板）
  - 期望产物（report_json、md、events、checkpoint）

**为何（因果）**
- “覆盖面”不依赖安装态（entry points）也不依赖启发式扫描
- 统一检测脚本能严格按 registry 执行，避免漏跑

**关键参数/注意**
- registry 与 `REPORT_TOOL_META` 必须一致（检测脚本要校验）
- 新增/重命名工具必须更新 registry（作为 code review checklist）

**验收**
- registry 中每个条目都能定位到存在的模块
- registry 数量与扫描到的 META 数量一致（差异需解释或禁止）

---

### 4.4 里程碑 D：Selftest 动态验收
**做什么**
- `supports_selftest=true` 的工具实现 `--selftest`（或等价）：
  - 生成最小 report.json（覆盖 ≥3 种状态）
  - 控制台渲染输出满足空行与末尾 `\n\n` 规范
  - 输出包含 `out = path` 形式的路径 token（回归 VS Code 终端识别）
- `high_cost=true` 的工具 selftest 还必须：
  - 生成 events.jsonl（≥2 条事件）
  - 生成 checkpoint.json（至少一次原子替换写）
  - 覆盖 durability 参数解析（flush/fsync 至少走到分支）

**为何（因果）**
- 运行时渲染与落盘策略无法仅靠静态扫描证明
- selftest 让契约校验可重复、可在 CI 里自动执行

**关键参数/注意**
- selftest 不依赖真实 DB/网络/大文件
- stdout 只输出“最终报告渲染”；进度条建议走 stderr（避免污染 stdout 契约）
- 失败路径要落 ERROR 事件与 best-effort 最终报告

**验收**
- 对每个工具执行 selftest 后，`verify_report_output_contract` 可通过
- events.jsonl 行级 JSON 可解析（NDJSON）

---

### 4.5 里程碑 E：统一检测脚本与门禁接入
**做什么**
- 新增 `tools/check_report_tools_contract.py`：
  - 静态层：读 registry + AST 提取 META + 一致性校验
  - 动态层：逐工具执行 selftest + 调用 `verify_report_output_contract` + 检查 events/checkpoint
  - 输出：自身也产出一个 v2 gate report（便于统一查看）
- 接入 pre-commit：
  - 静态层必跑
  - 动态层按变更集/按 high_cost 分层
- CI：
  - 全量跑动态层
  - 失败时上传 selftest 产物目录为 artifact

**为何（因果）**
- 防止规则只停留在文档层
- 将“契约不回退”变成可执行门禁

**关键参数/注意**
- 对“未登记/缺 META/枚举非法”默认应为 FAIL（你可按目标直接收紧）
- 对高成本工具可设置最大步数/最大样本，避免 CI 时间不可控

**验收**
- 本地 pre-commit 与 CI 对同一变更给出一致 FAIL/WARN/定位信息
- gate report 具备 loc/loc_uri（便于 VS Code 点击跳转）

---

### 4.6 里程碑 F：收紧策略与回滚
**收紧策略**
- 第 1 周：缺 META/缺 registry 先 WARN；动态 selftest 仅覆盖改动工具
- 稳定后：缺 META/缺 registry 升级 FAIL；CI 全量跑所有工具 selftest
- 最终：启发式发现“疑似报告工具但未登记”也升级为 FAIL

**回滚策略**
- 所有门禁变更必须可通过配置开关降级（例如 `--mode warn`）
- 出现大面积阻断时，先回退门禁等级，再逐工具补 selftest

## 5. 验收标准
- SSOT 唯一：全仓只存在一个 `ssot: true` 的契约入口
- 覆盖面明确：registry 覆盖所有报告工具；新增工具无登记会被门禁拦截
- 行为一致：console/file 的排序、空行、末尾 `\n\n`、token 规则可由检测脚本稳定验收
- 可追溯可恢复：high_cost 工具具备 events/checkpoint；异常退出可落 ERROR 事件；支持回放终端报告

## 6. 失败模式与缓解
- 断链：用 deprecated stub 过渡，门禁禁止新引用旧路径
- 漏检：registry 为 SSOT，AST 作为补漏提示；缺登记升级为 FAIL
- 不稳定 selftest：只验证输出层，固定输入，禁用外部资源依赖
- CI 耗时：按 high_cost 分层、限制步数/样本、分支/夜间全量跑

## 7. MRE
在仓库根目录执行（示例）：
1) 静态扫描（不运行工具）：
   - `python tools/check_report_tools_contract.py --mode static`
2) 动态验收（只跑改动工具）：
   - `python tools/check_report_tools_contract.py --mode changed --selftest`
3) CI 全量验收（本地模拟）：
   - `python tools/check_report_tools_contract.py --mode all --selftest --artifacts data_processed/build_reports/_selftest_artifacts`

期望：
- static 阶段无缺 META/无非法枚举
- selftest 阶段所有 report.json 通过 `verify_report_output_contract`
- artifacts 目录包含每个工具的最小产物（json/md/events/checkpoint）
