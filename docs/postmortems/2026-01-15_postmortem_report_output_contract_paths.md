---
title: "Postmortem｜报告输出契约：VS Code 可点击定位（vscode://file）与路径分隔符归一化"
version: 1.1
last_updated: 2026-01-15
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "reports（JSON/Markdown）人类消费契约：可点击定位（vscode://file）+ 路径分隔符归一化"
  severity: P3
---

# Postmortem｜报告输出契约：VS Code 可点击定位（vscode://file）与路径分隔符归一化

## 目录（TOC）
- [0) 元信息（YAML）](#0-元信息yaml)
- [1) 总结（Summary）](#1-总结summary)
- [2) 预期 vs 实际（Expected vs Actual）](#2-预期-vs-实际expected-vs-actual)
- [3) 证据账本（Evidence Ledger）](#3-证据账本evidence-ledger)
- [4) 复现（MRE：最小可复现）](#4-复现mre最小可复现)
- [5) 排查过程（Investigation）](#5-排查过程investigation)
- [6) 根因分析（RCA）](#6-根因分析rca)
- [7) 修复与处置（Mitigation & Fix）](#7-修复与处置mitigation--fix)
- [8) 回归测试与门禁（Regression & Gates）](#8-回归测试与门禁regression--gates)
- [9) 行动项（Action Items）](#9-行动项action-items)
- [10) 方法论迁移（可迁移资产）](#10-方法论迁移可迁移资产)
- [11) 信息缺口与补采计划（Gaps & Next Evidence）](#11-信息缺口与补采计划gaps--next-evidence)
- [12) 输出自检（Quality Gates）](#12-输出自检quality-gates)

## 0) 元信息（YAML）
见文首 YAML。

## 1) 总结（Summary）
本次处置最初聚焦“落盘报告内容中的路径分隔符归一化”：在 JSON 与 Markdown 报告落盘时，将 Windows 风格 `\` 归一化为 `/`（例如 `C:/repo/a.py:12:3`），以降低跨 OS 的 diff 噪声。

随后出现事实证据：**仅归一化分隔符并不能保证在 VS Code 中可点击跳转**。对于“报告文件（Markdown/JSON）阅读场景”，VS Code 对 `path:line(:col)` 的可点击识别属于启发式，稳定性受文件类型/渲染形态影响。本次将输出契约升级为：在报告中提供**显式可点击定位**，优先采用 `vscode://file/<abs_path>:line:col`；在 Markdown 中将定位与关键路径渲染为 `[text](vscode://file/...)` 链接。路径分隔符归一化仍保留，但其定位从“保证可点击”调整为“保证跨平台一致的展示/可复制性”。

## 2) 预期 vs 实际（Expected vs Actual）
- 预期（Expected）
  - 报告落盘后（JSON/MD），定位信息可被人类在 VS Code 中点击打开并定位到行/列；
  - 报告内路径展示统一使用 `/` 作为分隔符，跨 OS 因分隔符造成的差异应为 0。
- 实际（Actual）
  - 仅将 `\` 替换为 `/` 后，`gate_report.md` 仍以纯文本展示路径（例如 `F:/.../gate_logs/...log`），在 VS Code 中不产生稳定的点击跳转；
  - 需要将“点击跳转能力”从启发式识别升级为显式链接（Markdown link / `vscode://file` URL scheme）。

## 3) 证据账本（Evidence Ledger）
- E0（需求）：报告里的人类阅读定位希望在 VS Code 中可点击跳转（来自需求说明）。
- E1（外部依据｜VS Code 官方）：支持通过 URL 直接打开文件并定位到行/列：
  - `vscode://file/{full path to file}:line:column`
  - 参考：https://code.visualstudio.com/docs/configure/command-line （“Opening VS Code with URLs” 章节，2026-01-08）
- E2（修复点｜JSON 落盘归一化）：`src/mhy_ai_rag_data/tools/reporting.py` 在 `write_report()` 落盘前对 `Path` 与包含 `\` 的字符串递归归一化为 `/`（减少跨 OS 噪声）。
- E3（修复点｜Stage2 Markdown 汇总）：`src/mhy_ai_rag_data/tools/view_stage2_reports.py` 将关键“路径”字段渲染为显式 `vscode://file` 链接（而不是反引号纯文本），并继续保留既有的定位链接渲染。
- E4（修复点｜Gate Markdown 汇总）：`src/mhy_ai_rag_data/tools/view_gate_report.py` 将 `report_path` 与 `log_path` 渲染为 `[text](vscode://file/...)`，避免依赖 VS Code 的文本 linkify 启发式。
- E5（修复点｜public release hygiene 报告）：`tools/check_public_release_hygiene.py` 的 Locations 等定位项渲染为 Markdown 链接（`vscode://file`），满足可点击定位。

## 4) 复现（MRE：最小可复现）
### 环境
- OS：Windows（用于观察 `\` 与点击跳转链路）
- VS Code：Stable 或 Insiders（Insiders 需对应 scheme）
- Python：项目约束版本（以仓库门禁为准）

### 命令
```cmd
# 1) 生成 JSON 报告（示例：gate）
python tools\gate.py --profile fast --root . --json-out data_processed/build_reports/gate_report.json

# 2) 生成 Markdown 汇总（示例：gate 视图）
python -m src.mhy_ai_rag_data.tools.view_gate_report --report data_processed/build_reports/gate_report.json --md-out data_processed/build_reports/gate_report.md
```

### 验收（不依赖手工点击）
```cmd
# A) 验收：报告文本中不出现反斜杠（展示一致性）
python -c "import pathlib,sys; p=pathlib.Path('data_processed/build_reports'); bad=[x for x in p.rglob('*') if x.suffix in ('.json','.md') and '\\' in x.read_text(encoding='utf-8', errors='ignore')]; print('bad=', [str(x) for x in bad]); sys.exit(2 if bad else 0)"

# B) 验收：Markdown 里出现显式 vscode 链接（点击能力的先决条件）
python -c "import pathlib,sys; t=pathlib.Path('data_processed/build_reports/gate_report.md').read_text(encoding='utf-8', errors='ignore'); ok=('](vscode://file/' in t) or ('vscode://file/' in t); print('has_vscode_link=', ok); sys.exit(2 if not ok else 0)"
```

### 期望输出
- A 退出码为 0（`bad=[]`）；
- B 退出码为 0（`has_vscode_link=True`）；
- 在 VS Code 中打开 `gate_report.md`，点击 `[...](vscode://file/...)` 可打开对应文件；若提供 `:line:col`，应定位到行/列。

## 5) 排查过程（Investigation）
- 将“可点击跳转”拆解为两条链路：
  1) **展示一致性**：报告中路径字符串的分隔符形式（`\` vs `/`）——用于跨平台展示与 diff。
  2) **点击跳转能力**：报告中是否存在显式可点击链接（Markdown link 或 `vscode://file` URL）——用于 VS Code 可点击定位。
- 对照 `gate_report.md` 发现：路径已为 `/`，但仍是纯文本，因此点击链路未满足；随后引入显式 `vscode://file` 链接并在 Markdown 渲染层落地。

## 6) 根因分析（RCA）
- Facts：
  - `str(Path)` 在 Windows 下会产生 `\` 分隔符；
  - VS Code 对报告文件（Markdown/JSON）中“纯文本路径”的可点击识别属于启发式，不能作为稳定契约；
  - VS Code 官方提供了 URL scheme `vscode://file/<abs_path>:line:col` 用于直接打开文件定位。
- Inference（推断）：
  - 若只做分隔符归一化，不输出显式链接，不同报告/视图脚本会出现“部分可点、部分不可点”的体验分叉（可证伪：统计各报告文件中 `vscode://file/` 出现与否，并与点击成功率相关性对照）。

## 7) 修复与处置（Mitigation & Fix）
- 分隔符归一化（展示一致性，保留）：
  - JSON：在落盘入口递归转换 `Path -> as_posix()`，并对包含 `\` 的定位字符串做 `/` 归一化（E2）。
  - Markdown：汇总脚本对路径展示统一走 `as_posix()` 或归一化（避免 `\` 混入）。
- 显式链接（点击能力，新增为契约）：
  - 为关键路径（`report_path`、`log_path`、输入/报告路径等）输出 Markdown 链接：`[display](vscode://file/<abs_path>)`（E3/E4）。
  - 为诊断定位输出 `vscode://file/<abs_path>:line:col`（如可得），并在 Markdown 中渲染为链接（E4/E5）。
  - 增加 scheme 可配置（Stable/Insiders）为运行时开关（例如环境变量 `RAG_VSCODE_SCHEME`）。

## 8) 回归测试与门禁（Regression & Gates）
- 回归命令（建议本地/CI 均可跑）：
  - 生成至少 1 份 JSON 报告 + 1 份 Markdown 汇总后：
    - 跑 “反斜杠扫描”（展示一致性）；
    - 跑 “vscode 链接存在性扫描”（点击能力先决条件）。
- 门禁化建议（待后续迭代时处理）：
  - 将上述两类扫描封装为独立脚本，并接入 gate/profile 或 pre-commit 作为可选门禁。
  - 迁移期建议：先 WARN；当覆盖面满足阈值后再升级为 FAIL。

## 9) 行动项（Action Items）
- [DONE] A1：JSON 落盘分隔符归一化（`reporting.write_report()`）
- [DONE] A2：Gate Markdown：`report_path`/`log_path` 渲染为显式 `vscode://file` 链接（`view_gate_report`）
- [DONE] A3：Stage2 Markdown：关键“路径”字段渲染为显式链接（`view_stage2_reports`）
- [DONE] A4：hygiene 报告 Locations 使用显式链接（`check_public_release_hygiene`）
- [TODO] A5：后续同主题要求（Phase2）：
  - 控制台汇总排序（PASS→WARN→FAIL→ERROR 且汇总块在末尾）
  - 控制台输出适度空行
  - 高耗时检查的“即时写入即时存储”（streaming write）

## 10) 方法论迁移（可迁移资产）
- 输出契约建议显式区分：
  - 展示一致性（路径分隔符、编码、换行符）；
  - 交互能力（点击跳转）——必须使用显式链接，不依赖启发式识别；
  - 机器消费（schema、退出码、稳定字段）。
- 优先将策略放在输出侧（序列化/渲染），避免污染业务检查逻辑。

## 11) 信息缺口与补采计划（Gaps & Next Evidence）
- 缺口：当前未将“vscode 链接存在性扫描”固化为自动门禁。
- 补采计划：
  - 统计落盘 Markdown 报告中 `vscode://file/` 覆盖率；
  - 若发现仍有视图脚本输出关键路径为纯文本，则补齐其渲染函数，或沉淀为统一的 `md_link()` 工具函数。

## 12) 输出自检（Quality Gates）
- 已区分 Facts/Inference；
- 给出了可运行的 MRE 与两条验收命令（展示一致性 + 链接存在性）；
- 行动项标注 DONE/TODO，支持后续同主题迭代。
