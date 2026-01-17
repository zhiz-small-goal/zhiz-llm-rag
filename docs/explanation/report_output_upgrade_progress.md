# 全局一致报告输出改造 - 进度清单（截至 2026-01-16 口径）

> 目标：仓库内所有“控制台 + 落盘报告”遵循同一套 v2 item 契约与排序/可点击/高耗时可恢复/进度反馈规则。
> 
> 本文件用于记录：已完成的改动点、涉及文件、待做事项、以及下一步从哪里继续，避免重复翻源。

## 0. 口径与默认假设
- 目标版本口径：截至 **2026-01-16** 的“稳定实现”。
- 本仓库当前基线：已存在 `schema_version=2` 的 item 契约模块（`report_contract.py`）、文件输出排序与 `loc_uri` 补齐模块（`report_order.py`）、以及 gate 专用渲染器（`view_gate_report.py`）。
- “全局一致”需要：把这些能力沉淀为通用组件，并逐个脚本迁移到统一输出管线。

## 1. 已完成（本轮交付：基础设施增量 #1）

### 1.1 loc/loc_uri 解析与可点击增强 ✅
- 目标：让 `loc` 支持 `path` / `path:line` / `path:line:col`（文本仍可 grep），并为缺省行列提供默认值，使 `loc_uri` 始终可点。
- 变更文件：
  - `src/mhy_ai_rag_data/tools/report_order.py`
    - `_parse_diag_loc` 支持 3 种 loc 形式，并对缺省行列默认 `1:1`。
    - `_build_vscode_file_uri` 改用 strict 形式，保证 `:line:col` 始终存在。
  - `src/mhy_ai_rag_data/tools/vscode_links.py`
    - 新增 `to_vscode_file_uri_strict(...)`：当 line/col 缺失时默认 `1:1`。

### 1.2 通用渲染与“报告包”写入 ✅
- 目标：把 gate 的“控制台滚屏友好 + Markdown 人类入口”渲染能力抽象为通用组件，作为后续所有脚本迁移的单一落点。
- 新增文件：
  - `src/mhy_ai_rag_data/tools/report_render.py`
    - `render_console(report)`：detail 轻->重、summary 在末尾、整体以 `\n\n` 结尾。
    - `render_markdown(report)`：summary 顶部、detail 重->轻、`[loc](loc_uri)` 可点击。
  - `src/mhy_ai_rag_data/tools/report_bundle.py`
    - `write_report_bundle(...)`：一次性产出 `report.json + report.md + console`，并保证 `report.md` 原子写入（tmp -> rename）。
  - `src/mhy_ai_rag_data/tools/view_report.py`
    - 通用查看器：支持从 `report.json` 或 `report.events.jsonl` 重建并渲染（恢复模式）。

### 1.3 样板脚本迁移：run_eval_rag ✅
- 目标：把 `run_eval_rag.py` 升级为“全局一致”的样板实现：
  - 控制台：最终只输出渲染后的 detail/summary（轻->重、summary 在末尾、整体以 `\n\n` 结尾）。
  - 落盘：同时产出 `report.json + report.md`，并在 `.md` 内将 `loc` 渲染为 `[loc](loc_uri)` 可点击跳转。
  - 高耗时恢复：运行中实时写入 `<out>.events.jsonl`（items-only jsonl；默认 durability=flush）。
  - 运行时反馈：`--progress auto|on|off`，输出到 `stderr`，结束时清理进度行。
- 变更文件：
  - `src/mhy_ai_rag_data/tools/run_eval_rag.py`
  - `src/mhy_ai_rag_data/tools/view_report.py`（将“写 md 的提示”改到 stderr，避免污染 stdout 的最终报告）

### 1.4 迁移：run_eval_retrieval ✅
- 目标：把检索评估脚本纳入统一输出管线（json/md/console 一致），并补齐高耗时恢复与进度反馈。
- 达成：
  - `--events-out auto|off|<path>`：默认 auto 写 `<out>.events.jsonl`（items-only jsonl；durability 默认 flush）。
  - `--progress auto|on|off`：运行中 stderr 单行刷新，结束清理后再输出最终报告。
  - 输出通过 `write_report_bundle(...)` 统一产出 `report.json + report.md`，stdout 仅输出渲染后的最终报告。
- 变更文件：
  - `src/mhy_ai_rag_data/tools/run_eval_retrieval.py`

### 1.5 迁移：run_rag_eval_batch ✅
- 目标：把批量评测脚本的 stdout/落盘统一到 v2 items 报告，避免混杂 print 输出。
- 达成：
  - `--out/--md-out`：稳定输出路径（默认带时间戳），同时落盘 `.md`。
  - 可选 `--events-out auto|off|<path>`：用于长批次的恢复渲染（items-only jsonl）。
  - `--progress auto|on|off`：stderr 运行时反馈。
- 变更文件：
  - `src/mhy_ai_rag_data/tools/run_rag_eval_batch.py`

### 1.6 迁移：validate_eval_cases ✅
- 目标：将用例校验输出从 legacy json 转为 v2 items，并保证控制台/落盘一致。
- 达成：
  - 所有 errors/warnings 均转为 items（severity_level 数值）。
  - stdout 仅输出渲染后的最终报告；`.md` 提供可点击定位。
- 变更文件：
  - `src/mhy_ai_rag_data/tools/validate_eval_cases.py`

### 1.7 兼容入口：tools/view_report.py ✅
- 目标：允许在未安装为包或偏好 wrapper 的场景下使用 `python tools/view_report.py ...`（例如 Windows 虚拟环境/便捷脚本调用）。
- 新增文件：
  - `tools/view_report.py`（wrapper；SSOT 指向 `src/mhy_ai_rag_data/tools/view_report.py`）



## 2. 待完成（后续迁移主线）

### 2.1 “全局一致”迁移（脚本级）⬜
> 原则：每个脚本最终都只调用 `write_report_bundle(...)`（或等价的统一输出入口），并将运行时进度输出到 `stderr`。

- [x] `tools/run_eval_rag.py`
- [x] `tools/run_eval_retrieval.py`
- [x] `tools/run_rag_eval_batch.py`
- [x] `tools/validate_eval_cases.py`
- [x] `tools/check_all.py`（已迁移：write_report_bundle + md 输出 + stdout 末尾空行）
- [ ] `tools/gate.py`（目前已有独立实现；若要完全统一组件，可后续替换为 report_bundle/report_render）
- [ ] 其他输出报告脚本：逐个排查是否直接 `print()` 或直接写 md/json。

### 2.2 高耗时两段式：events.jsonl + 最终渲染 ⬜
- [ ] 统一事件流文件命名：`<report_base>.events.jsonl`（例如 `eval_rag_report.events.jsonl`）。
- [ ] durability_mode：`none/flush/fsync`（默认 flush；fsync 支持节流）。
- [ ] 中断/异常：追加最高严重度终止 item，并立刻落盘。

### 2.3 runtime_feedback（进度条/阶段反馈） ⬜
- [ ] `--progress auto|on|off`：TTY 且非 CI 才开启。
- [ ] 输出到 `stderr`，不得进入 items，也不得写入 events。
- [ ] 刷新节流（>=200ms），单行重绘，结束清理。

### 2.4 验收用例与验证命令 ⬜
- [ ] 新增或更新 `verify_*`：覆盖排序、末尾空行、md 可点击、路径分隔符、强制中断可恢复。

## 3. 下一步从哪里继续（建议推进顺序）
1) 选一个“高耗时 + 当前输出最不符合”的脚本做样板（优先 `run_eval_rag.py`）。
2) 把它的最终落盘统一改为 `write_report_bundle(...)`，保证 json/md/console 三通道一致。
3) 在样板脚本内引入 events.jsonl（运行时 append + flush），并在 finally/except 路径追加终止 item。
4) 把进度输出迁移到 `runtime_feedback`（stderr），并确保最终报告输出不被污染。
5) 抽出通用的“事件 -> report v2”重建逻辑（目前 `view_report.py` 已具备基础）。

## 4. 本轮交付文件清单（用于打包核对）
- 修改：
  - `src/mhy_ai_rag_data/tools/report_order.py`
  - `src/mhy_ai_rag_data/tools/vscode_links.py`
  - `src/mhy_ai_rag_data/tools/run_eval_rag.py`
  - `src/mhy_ai_rag_data/tools/run_eval_retrieval.py`
  - `src/mhy_ai_rag_data/tools/run_rag_eval_batch.py`
  - `src/mhy_ai_rag_data/tools/validate_eval_cases.py`
  - `src/mhy_ai_rag_data/tools/check_all.py`
  - `src/mhy_ai_rag_data/tools/view_report.py`
- 新增：
  - `src/mhy_ai_rag_data/tools/report_render.py`
  - `src/mhy_ai_rag_data/tools/report_bundle.py`
  - `docs/explanation/report_output_upgrade_progress.md`
  - `tools/view_report.py`
