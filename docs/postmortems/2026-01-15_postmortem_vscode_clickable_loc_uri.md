# 2026-01-15_postmortem_vscode_clickable_loc_uri.md目录：


- [2026-01-15_postmortem_vscode_clickable_loc_uri.md目录：](#2026-01-15_postmortem_vscode_clickable_loc_urimd目录)
  - [0) 元信息](#0-元信息)
  - [1) 现象与触发](#1-现象与触发)
  - [2) 问题定义](#2-问题定义)
  - [3) 关键证据与排查过程](#3-关键证据与排查过程)
    - [3.1 事实："/" 分隔符并不会让 VS Code 对报告中的路径可点击](#31-事实-分隔符并不会让-vs-code-对报告中的路径可点击)
    - [3.2 推断：VS Code 的 linkify 属于启发式，且对 JSON/Markdown 内容不稳定](#32-推断-vs-code-的-linkify-属于启发式且对-jsonmarkdown-内容不稳定)
    - [3.3 方案选择：在落盘报告中提供 vscode://file 的 loc_uri（或 Markdown 链接）](#33-方案选择在落盘报告中提供-vscodefile-的-loc_uri或-markdown-链接)
  - [4) 根因分析（RCA）](#4-根因分析rca)
  - [5) 修复与处置（止血→稳定修复→工程固化）](#5-修复与处置止血稳定修复工程固化)
    - [5.1 止血](#51-止血)
    - [5.2 稳定修复](#52-稳定修复)
    - [5.3 工程固化](#53-工程固化)
  - [6) 预防与回归测试](#6-预防与回归测试)
  - [7) 最小可复现（MRE）](#7-最小可复现mre)
  - [8) 一句话复盘](#8-一句话复盘)
  - [9) 方法论迁移（可复用工程经验）](#9-方法论迁移可复用工程经验)


## 0) 元信息
- [Fact] 发生日期：2026-01-15（用户交互当日）。
- [Fact] 影响范围：所有“落盘报告（JSON/Markdown）”中包含诊断定位（DIAG_LOC_FILE_LINE_COL）的输出。
- [Fact] 关联模块/脚本：
  - `src/mhy_ai_rag_data/tools/report_order.py`（落盘报告的统一排序/序列化入口）
  - `src/mhy_ai_rag_data/tools/view_gate_report.py`（把 gate_report.json 渲染为 Markdown 摘要）
  - `src/mhy_ai_rag_data/tools/view_stage2_reports.py`（把 stage2 报告渲染为 Markdown 摘要）
  - `tools/check_public_release_hygiene.py`（生成 Markdown 报告）
  - 相关文档：`AGENTS.md`、`docs/reference/review/REVIEW_SPEC.md`、`tools/check_public_release_hygiene_README.md`、`docs/reference/review/review_report_template.md`
- [Inference] 受影响的 VS Code 版本、以及具体打开方式（直接打开文件/预览/终端输出）未提供；需要以本机现象为准验证。

---

## 1) 现象与触发
- [Fact] 用户反馈：即使把报告中的路径分隔符统一为 `/`，在 VS Code 中打开报告文件时，路径仍不能点击跳转到本地文件位置。
- [Fact] 触发点：对“报告可读性/可用性”的要求中包含“人类阅读时可点击定位”。

---

## 2) 问题定义
当前项目把诊断定位展示为 `file:line:col`（DIAG_LOC_FILE_LINE_COL），但 VS Code 对“文件内容中的本地路径”是否自动识别为可点击链接并不稳定；因此需要在“落盘报告”中提供一个**确定可点击**的链接形式，使读者在报告里能一键跳转到对应文件的行列。

---

## 3) 关键证据与排查过程
### 3.1 事实："/" 分隔符并不会让 VS Code 对报告中的路径可点击
- [Fact] 用户明确反馈：报告路径采用 `/` 后，在 VS Code 中仍不可点击。
- 结论：仅调整分隔符不足以满足“报告里可点击跳转”的需求。

### 3.2 推断：VS Code 的 linkify 属于启发式，且对 JSON/Markdown 内容不稳定
- [Inference] VS Code 对文本的 linkify 依赖启发式规则（例如终端输出 vs 编辑器内容、不同语言模式、不同扩展），
  `path:line:col` 并非稳定协议。
- 如何验证：同一段文本在“终端输出/问题面板/Markdown 预览/JSON 编辑器”中的可点击性可能不同；对比即可证伪/证实。

### 3.3 方案选择：在落盘报告中提供 vscode://file 的 loc_uri（或 Markdown 链接）
- [Fact] `vscode://file/<abs_path>:line:col` 是明确的 URI 形式，适合在文件内容中被识别为链接。
- [Inference] 把定位展示保持为 `file:line:col`（便于 grep/复制），同时补充 `loc_uri` 或用 Markdown 链接包裹，可兼顾“可读”与“可点”。
- 取舍：
  - 选择 `loc_uri`（字段）而不是强行替换 `loc`，避免破坏既有消费端对 `loc` 的解析。
  - 选择在 Markdown 输出中渲染为链接，是为了让“人类阅读入口（.md）”直接可点。

---

## 4) 根因分析（RCA）
- Trigger（直接触发）：用户在 VS Code 中打开落盘报告，发现 `file:line:col` 不可点击。
- Root Cause（根因）：把“VS Code 能点击 path:line:col”当作稳定契约，但该行为属于编辑器启发式，不是协议化链接。
- Contributing Factors（促成因素）：
  - 报告格式多样（JSON/Markdown），且打开方式不同（预览/编辑器/终端），导致同一定位串在不同上下文表现不同。
  - 先前修复仅聚焦“路径分隔符”，缺少“可点击性”的端到端验收样例。
- Missing Controls（缺失控制点/门禁）：
  - 缺少一条“落盘报告必须包含可点击 URI（vscode://file）”的契约与文档入口。
  - 缺少一条“渲染器（view_*）应优先使用 loc_uri 输出链接”的固定规则。

---

## 5) 修复与处置（止血→稳定修复→工程固化）
### 5.1 止血
- 在报告中临时手动查找 `file:line:col` 并用 VS Code 的 Go to File / Go to Line 能定位，但仍需要人工拷贝与拆分；不满足“报告可点”的目标。

### 5.2 稳定修复
- 在落盘 JSON 报告的序列化阶段补充 `loc_uri`：
  - 改动点：`src/mhy_ai_rag_data/tools/report_order.py`
  - 机制：递归遍历报告对象；对包含 `file/line/col` 或 `loc`（DIAG_LOC）字段的条目，生成 `vscode://file/<abs_path>:line:col` 并写入 `loc_uri`。
  - 兼容：不替换原 `loc` 字段，避免破坏旧消费端。

- 在 Markdown 渲染器中把定位渲染为可点击链接：
  - `src/mhy_ai_rag_data/tools/view_gate_report.py`：若发现 `loc_uri`，输出为 `[loc](loc_uri)`。
  - `src/mhy_ai_rag_data/tools/view_stage2_reports.py`：生成 `vscode://file` 链接（Markdown 形式）。
  - `tools/check_public_release_hygiene.py`：Locations 渲染为 Markdown 链接。

- 增加可移植配置：
  - 环境变量 `RAG_VSCODE_SCHEME`：默认 `vscode`；若使用 VS Code Insiders，可设为 `vscode-insiders`。

### 5.3 工程固化
- 文档与规范写回：
  - `AGENTS.md`：把“诊断展示”与“落盘报告可点击”拆开说明，要求落盘报告提供 `loc_uri`。
  - `docs/reference/review/REVIEW_SPEC.md` / `review_report_template.md`：把 `loc_uri`/Markdown 链接作为推荐实践。
  - `tools/check_public_release_hygiene_README.md`：明确 Locations 在 Markdown 报告内会以链接形式渲染。

---

## 6) 预防与回归测试
- [ ] 生成任意包含 `loc` 的 JSON 报告（如 gate_report 或校验器报告），检查相关条目是否出现 `loc_uri`。
- [ ] 执行 `python -m src.mhy_ai_rag_data.tools.view_gate_report --report data_processed/build_reports/gate_report.json --out <md>`，打开输出 md，点击定位是否能跳转。
- [ ] 执行 `python tools/check_public_release_hygiene.py --repo .`，打开报告 md，点击 Locations 是否能跳转。

---

## 7) 最小可复现（MRE）
1) 生成一个包含 DIAG_LOC 的报告（例如任意校验器发现 FAIL 时输出 locations）。
2) 打开该报告文件（JSON/Markdown）观察：
   - 期望：存在 `loc_uri`（或 Markdown 链接），点击后跳转到对应文件行列。
   - 实际（故障态）：只有 `file:line:col` 文本，且在 VS Code 中不可点击。

---

## 8) 一句话复盘
把 `file:line:col` 当作“编辑器可点击协议”会导致报告可用性不稳定，落盘报告应显式提供 `vscode://file` 的 `loc_uri` 或 Markdown 链接来保证跳转可用。

---

## 9) 方法论迁移（可复用工程经验）
- 在“人类阅读产物”里，凡是需要点击跳转的定位，优先使用**协议化 URI**（如 `vscode://file`），不要依赖编辑器启发式。
- 把“展示字段（loc）”与“跳转字段（loc_uri）”分离，能减少对旧消费端的破坏并便于渐进迁移。
- 对可用性类需求（可读/可点），需要有至少一个“打开报告并点击”的回归步骤，否则改动容易只覆盖格式而未覆盖体验。
