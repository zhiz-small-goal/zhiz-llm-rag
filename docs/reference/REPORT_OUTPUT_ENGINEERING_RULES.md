---
title: 报告输出契约（v2）与工程规则（SSOT）
version: 1.1.3
last_updated: 2026-01-23
timezone: America/Los_Angeles
ssot: true
scope: "统一输出工程规则（schema_version=2）：报告/状态元数据/长跑任务（进度与 events）"
---

# 报告输出契约（v2）与工程规则（SSOT）


> 本文档是**输出契约的单一真源（SSOT）**：约束 `schema_version=2` 的报告落盘、控制台渲染、VS Code 可点击定位链接，以及长跑任务的进度与 `*.events.jsonl` 恢复链路。

## 目录
- [1. 背景与目标](#1-背景与目标)
- [2. 适用范围](#2-适用范围)
- [3. 术语与数据模型](#3-术语与数据模型)
- [4. 通道差异规则总览](#4-通道差异规则总览)
- [5. 文件输出规则（JSON/Markdown）](#5-文件输出规则jsonmarkdown)
- [6. 控制台输出规则（stdout）](#6-控制台输出规则stdout)
- [7. VS Code 可点击链接规则](#7-vs-code-可点击链接规则)
- [8. 长跑任务：进度（stderr）与 events（jsonl）](#8-长跑任务进度stderr-与-eventsjsonl)
- [9. 状态元数据纳入 v2](#9-状态元数据纳入-v2)
- [10. 验收与门禁](#10-验收与门禁)
- [11. MRE](#11-mre)
- [12. 参考资料](#12-参考资料)
- [13. 工具入口与发现（仓内约束）](#13-工具入口与发现仓内约束)

---

## 1. 背景与目标

本项目的“输出”覆盖：检查/评测报告、gate 结果、索引状态与构建戳，以及长跑任务的增量落盘与可恢复。若这些输出在结构、排序、链接形式、与落盘策略上分叉，会导致：

- 人类审阅路径分叉（同类报告在不同工具里格式不一致）。
- 排障时“定位链接不可点/不可复制”的体验不稳定。
- 机器侧门禁只能覆盖部分规则，出现“看起来对、但 gate 过不去 / gate 过了但人不好读”的情况。

本文档以 `schema_version=2` 的 **items model** 为中心，统一以下目标（需同时满足）：

- **文件可审阅**：JSON/Markdown 打开首屏即可看到结论与最高严重度问题。
- **控制台可滚屏**：明细从低到高滚动，最后停留在最高严重度问题与汇总结论。
- **定位可点击**：Markdown 预览与 VS Code 终端中均能点击跳转到源码位置。
- **长跑可恢复**：长任务支持进度反馈（stderr）与 items-only 的 `*.events.jsonl`（用于中断恢复/重放）。

> 非目标：本文不定义业务数据集的语义（例如 eval cases 字段含义），这些应在各自 schema 文档中约束。

---

## 2. 适用范围

本文适用于所有“输出类工件”，包括但不限于：

- v2 报告文件：`*.json`（`schema_version=2`）与可选 `*.md`
- items-only 事件流：`*.events.jsonl`（每行 1 个 item object，用于恢复/重放）
- 状态元数据：`data_processed/index_state/**/index_state.json`、`data_processed/index_state/db_build_stamp.json`（纳入 v2 envelope）
- 控制台渲染输出：stdout 的人类可读报告（由统一渲染器生成）

不在本规范内（需另立契约）：

- 业务数据集本身（例如 `eval_cases.jsonl` 字段语义与口径）
- 专用旁路 stream（若引入 `record_type=meta/case/summary` 之类的“观测流”，应遵循单独的 stream schema，例如 `docs/reference/EVAL_REPORTS_STREAM_SCHEMA.md`）

---

## 3. 术语与数据模型

### 3.1 Report v2（统一输出对象）

Report v2 是一个 JSON object，至少包含：

- `schema_version: 2`
- `generated_at: ISO8601 (UTC, Z)`（例如 `2026-01-18T21:03:00Z`）
- `tool: str`
- `root: str`（repo root 的 posix 形式，例如 `c:/repo/zhiz-llm-rag` 或 `/home/user/zhiz-llm-rag`）
- `summary: object`
- `items: list[Item]`

可选字段（用于溯源/机器消费）：

- `data: object`（结构化附加信息，如 events_path、统计明细等）
- `meta: object`（版本/环境/耗时/参数快照等）

### 3.2 Item（单条可诊断信息）

Item 是可呈现/可排序/可定位的诊断条目。建议字段：

- `tool: str`（产出该 item 的工具名）
- `key: str`（稳定的条目 id，用于对账/过滤）
- `title: str`
- `status_label: str`（例如 `PASS|INFO|WARN|FAIL|ERROR`）
- `severity_level: int`（数值越大越严重；排序只用此字段）
- `message: str`（面向人类的一段文本）
- `detail: object`（可选；结构化详情）
- `loc: str | list[str]`（可选；纯文本定位，如 `src/x.py:12:34`）
- `loc_uri: str | list[str]`（可选；VS Code 定位链接）

关键约束：

- **反斜杠禁用范围**：`root` 与每个 `item` 内的**所有字符串字段**不得包含反斜杠 `\`；路径展示统一使用 `/`。
- **severity 必须显式或可推导**：
  - 若 `severity_level` 缺失，仅允许对以下 `status_label` 进行隐式映射：`PASS/INFO/WARN/FAIL/ERROR`。
  - 若使用其它状态（例如 `SKIP/STALE/MISS/...`），必须显式提供 `severity_level`（否则会被视为契约违例并在验证中表现为 ERROR）。
- **多定位数量上限（与渲染器一致）**：当 `loc`/`loc_uri` 为 list 时，建议控制在 **<= 10**；过长会造成渲染截断与验证/审阅体验不稳定。

### 3.3 Summary（汇总块）

Summary 用于首屏结论，建议至少包含：

- `overall_status: str`（例如 `PASS|WARN|FAIL|ERROR`）
- `overall_rc: int`（建议与退出码口径一致：PASS=0, FAIL=2, ERROR=3）
- `counts: object`（按 `status_label` 统计）

> 说明：summary 的具体字段可扩展；但“结论可读”与“rc 可消费”应保持稳定。

---

## 4. 通道差异规则总览

同一份 Report v2 在“文件”与“控制台”两个通道的呈现规则不同，但数据源一致（同一 `items/summary`）：

- **文件（JSON/Markdown）**：summary 在顶部；items 按 `severity_level` **从高到低**（最严重在上）。
- **控制台（stdout）**：先输出 details；items 按 `severity_level` **从低到高**（最严重在下）；summary 最后输出。

排序只使用 `severity_level`（主键）并保持同级稳定（生成顺序/稳定次序键）；禁止依赖 `status_label` 的字符串比较。

---

## 5. 文件输出规则（JSON/Markdown）

### 5.1 JSON 文件（Report v2）

- JSON 必须是 `schema_version=2` 的 Report v2。
- 推荐写入策略：**临时文件写完 + `os.replace` 原子替换**，避免半文件。
- 落盘前必须执行“文件输出归一化”：
  - items 按严重度排序（高→低）。
  - 路径字段与 item 内字符串字段做 `/` 归一化（禁止 `\`）。
  - 为可定位条目补齐 `loc_uri`（详见第 7 节）。

> 代码入口（参考）：`src/mhy_ai_rag_data/tools/report_order.py::prepare_report_for_file_output()`。

### 5.2 Markdown 文件（Report v2 的确定性渲染）

- Markdown 顶部必须为 `## Summary`（首屏结论）。
- Markdown 的条目区必须为 `## Details`，并按 `severity_level` **从高到低**排序。
- 若 item 具备定位信息：
  - 展示文本使用 `loc`（如 `src/x.py:12:34`）。
  - 点击目标使用 `loc_uri`（`vscode://file/<abs_path>:line:col`）。

示例（单定位）：

```md
- [FAIL] (sev=3) Missing expected file
  - loc: [src/mhy_ai_rag_data/tools/gate.py:120:1](vscode://file/c:/repo/zhiz-llm-rag/src/mhy_ai_rag_data/tools/gate.py:120:1)
```

说明：Markdown 渲染的“可点击链接”以 `loc_uri` 为准；`loc` 保持纯文本以便复制与 grep。

> 渲染入口（参考）：`src/mhy_ai_rag_data/tools/report_render.py::render_markdown()`。

---

## 6. 控制台输出规则（stdout）

### 6.1 输出结构与通道隔离

- stdout 必须只承载“渲染后的报告正文”（details + summary），以便 `| tee`、CI 日志与复制粘贴稳定。
- 附加信息（例如“写入了哪个文件/耗时/下一步命令”）必须写入 **stderr**。
- 控制台正文必须由统一渲染器生成；脚本不应在渲染前/后向 stdout 追加业务 `print()`。

> 渲染入口（参考）：`src/mhy_ai_rag_data/tools/report_render.py::render_console()`。

### 6.2 控制台排序

- details 区 items 按 `severity_level` **从低到高**输出（最严重在下）。
- summary 必须出现在 details 之后（最后一屏停留在结论）。

### 6.3 终端可点击链接的 token 规则（建议）

VS Code 终端会对“疑似路径/URI token”进行自动识别。为降低误识别：

- 纯路径/URI 建议单独成行输出。
- 若必须输出键值对，使用 `key = value`（等号两侧留空格），并在下一行输出纯路径。

示例（stderr 建议输出）：

```text
out = data_processed/build_reports/gate_report.json
/data_processed/build_reports/gate_report.json
```

### 6.4 空行规范（与渲染器一致）

为匹配滚屏阅读行为并避免“最后一屏信息密度失控”，控制台渲染输出必须满足：

- **每个 item 之间**：插入 **1 行空行**。
- **severity 分组之间**：插入 **2 行空行**。
- **禁止连续超过 2 行空行**：任何位置连续空行不得达到 3（包含分组边界与条目分隔叠加的情况）。
- **末尾必须以 `\n\n` 结束**：输出结束时额外保留一个空行（并且该末尾空行计入“连续空行不超过 2”的约束）。

---

## 7. VS Code 可点击链接规则

### 7.1 双表示：`loc` + `loc_uri`

同一诊断位置应同时提供：

- `loc`：纯文本 `file:line:col`（便于复制/grep）。
- `loc_uri`：`vscode://file/<abs_path>:line:col`（便于点击跳转）。

其中：

- `abs_path` 使用 `/` 分隔符；Windows 盘符建议小写（例如 `c:/...`）。
- `loc_uri` 必须包含 `:line:col` 后缀；当上游缺失行列时，允许在 `loc_uri` 里使用默认 `1:1` 以保证可点击。

> 参考实现：`src/mhy_ai_rag_data/tools/vscode_links.py`。

### 7.2 Markdown 与终端的差异

- Markdown 预览：依赖标准 Markdown 链接语法，`[text](uri)`。
- 终端：依赖 VS Code 的 token 识别；建议把 `vscode://file/...` 单独成行输出，避免与 `key=value` 粘连。

---

## 8. 长跑任务：进度（stderr）与 events（jsonl）

### 8.1 进度反馈（stderr）

长跑任务应支持 runtime feedback（进度条/计数/耗时），但必须走 **stderr**，避免污染 stdout 的报告正文。

实现建议：统一使用 `src/mhy_ai_rag_data/tools/runtime_feedback.py`，并提供参数：

- `--progress auto|on|off`
- `--progress-min-interval-ms <int>`（节流刷新频率）

默认行为（建议）：

- `auto`：仅在 stderr 为 TTY 且不处于 CI 环境时启用。
- `on/off`：显式开关覆盖 auto。

### 8.2 items-only 事件流（`*.events.jsonl`）

对于高成本/可恢复的过程，必须支持 items-only 的事件流：

- 文件格式：NDJSON（每行 1 个 JSON object），**语义为 1 条 v2 的 `item`**。
- 写入方式：追加写入；每条至少 `flush`。
- 目的：中断后可用事件流重建 report（或用于复盘）。

推荐参数形态：

- `--events-out auto|off|<path>`（eval 类工具已采用该形式；`auto` 表示与 report.json 同目录同名后缀）
- `--durability-mode none|flush|fsync`
- `--fsync-interval-ms <int>`（对 fsync 节流）

> 参考实现：`src/mhy_ai_rag_data/tools/report_events.py::ItemEventsWriter`。

**补充（2026-01-23）：索引构建的 WAL 特例**
- `build_chroma_index_flagembedding` 为“写入 + 中断恢复”引入 `index_state.stage.jsonl`（WAL）。该文件是工具级恢复载体：每行是一个事件对象（含 `wal_version/ts/seq/event/run_id/...`），用于恢复 doc 提交边界。
- 该 WAL **不等同于** `*.events.jsonl`（v2 item 流）：它的 schema 以恢复为中心，而非 report 渲染；因此消费者不应把它当作 report events 读取。
- 若未来要统一到 v2 item events，可在 build 工具中同时写 `ItemEventsWriter`（以 `--events-out` 控制）而保留 WAL 作为内部 checkpoint。


### 8.3 恢复与重放

统一恢复入口：

- 从 report.json 渲染控制台/生成 markdown：
  - `python tools/view_report.py --root . --report <path/to/report.json> --md-out <path/to/report.md>`
- 从 `*.events.jsonl` 重建后渲染：
  - `python tools/view_report.py --root . --events <path/to/report.events.jsonl> --tool-default <tool>`

### 8.4 异常退出的最低要求

当长跑任务发生异常（或提前退出）时，应尽量满足：

- events 流中最后写入一个 `ERROR`/`FAIL` 类 item（包含可诊断 message/detail）。
- best-effort 写出最终 report.json（summary 标记为 FAIL/ERROR，items 至少包含该错误条目）。
- 关闭/flush events writer（避免尾部半写行）。

> 说明：本仓库当前以 `*.events.jsonl` 作为恢复载体，不要求额外引入 `checkpoint.json`。若未来需要 checkpoint，应另立 schema 并在工具中实现原子替换写入。

---

## 9. 状态元数据纳入 v2

### 9.1 统一原则

- `index_state.json` 与 `db_build_stamp.json` 属于“状态元数据报告”，必须满足 Report v2 的最小字段要求（`schema_version=2`、`generated_at`、`tool`、`root`、`summary`、`items`）。
- 业务状态字段可保留在顶层或归入 `data.*`，但 **写入到 `items` 的字符串字段**必须满足“无反斜杠”约束。

### 9.2 兼容策略

当前推荐策略：

- **兼容优先**：既有消费者读取的业务字段保留在顶层；同时新增 v2 envelope 与 items/summary。
- 迁移到“结构化优先”（将业务字段收敛到 `data.state`）时，应提供向后兼容读取（例如双写或 adapter）。

---

## 10. 验收与门禁

统一校验器：`tools/verify_report_output_contract.py`。

覆盖点（至少）：

- item/路径字段不包含 `\`（items 内字符串递归扫描）。
- 文件输出：Markdown/JSON 的 summary/details 顺序与严重度排序符合规则。
- 控制台输出：details/summary 顺序、严重度顺序、空行规则、末尾 `\n\n`。

常用命令：

- 验证单个报告：
  - `python tools/verify_report_output_contract.py --root . --report data_processed/build_reports/xxx.json`
- 从 events 重建并验证（用于恢复链路自检）：
  - `python tools/verify_report_output_contract.py --root . --events data_processed/build_reports/xxx.events.jsonl --tool-default <tool>`
- 验证状态元数据：
  - `python tools/verify_report_output_contract.py --root . --report data_processed/index_state/db_build_stamp.json`

---

## 11. MRE

### 11.1 VS Code 终端链接 token 回归（stderr/stdout 均可）

在 VS Code 终端执行（验证 `out = path` 与 `file:line:col` 的识别行为）：

- Windows CMD：

```bat
python -c "from pathlib import Path; p=Path('data_processed/build_reports').resolve(); print('out=%%s'%%p); print('out = %%s'%%p); print(str(p)+':12:34')"
```

### 11.2 最小 v2 报告渲染与校验

1) 准备一个最小 report.json（至少 3 条 items，覆盖不同 severity，至少 1 条含 loc/loc_uri）。
2) 渲染并生成 md：

```bash
python tools/view_report.py --root . --report data_processed/build_reports/mre.json --md-out data_processed/build_reports/mre.md
```

3) 运行契约校验：

```bash
python tools/verify_report_output_contract.py --root . --report data_processed/build_reports/mre.json
```

---

## 12. 参考资料

- JSON（语法与 JSON text 定义）：
  - URL: https://www.rfc-editor.org/rfc/rfc8259.txt
  - 日期/版本: 2017-12 (RFC 8259)
  - 来源类型: Primary（标准）
  - 定位: §2 JSON Grammar

- Python `os.replace`（原子替换写入基础）：
  - URL: https://docs.python.org/3/library/os.html#os.replace
  - 日期/版本: CPython 文档（访问以最新稳定版为准）
  - 来源类型: Primary（官方文档）
  - 定位: os.replace

- Python `os.fsync`（耐久化/落盘强度）：
  - URL: https://docs.python.org/3/library/os.html#os.fsync
  - 日期/版本: CPython 文档（访问以最新稳定版为准）
  - 来源类型: Primary（官方文档）
  - 定位: os.fsync

- VS Code Terminal（链接识别与终端行为）：
  - URL: https://code.visualstudio.com/docs/terminal/basics
  - 日期/版本: 官方文档（访问以最新稳定版为准）
  - 来源类型: Primary（官方文档）
  - 定位: Terminal Basics / Links

- NDJSON 规范（JSON Lines 业界约定）：
  - URL: https://github.com/ndjson/ndjson-spec
  - 日期/版本: GitHub 文档（访问以最新稳定版为准）
  - 来源类型: Secondary（社区规范）
  - 定位: Specification

---

## 13. 工具入口与发现（仓内约束）

### 13.1 工具入口（Windows 友好）

本仓库推荐以 `python tools/*.py` 作为稳定入口（wrapper 形式），原因：

- 不依赖安装态（`pip -e .`）也可运行。
- 入口可被 gate/CI 固定引用。

与本文相关的关键入口：

- `tools/view_report.py`：从 report.json 或 `*.events.jsonl` 渲染控制台/生成 Markdown。
- `tools/verify_report_output_contract.py`：契约校验（文件/控制台/路径归一化）。

### 13.2 wrapper 管理（SSOT）

- wrapper 生成配置：`tools/wrapper_gen_config.json`。
- 其中 `managed_wrappers` 用于声明需要稳定保留的工具入口（例如 `view_report.py`、`verify_report_output_contract.py`）。

> 说明：若未来需要对“所有会产出 v2 报告的工具”进行统一清单化检测，可在不破坏现有入口的前提下，引入额外 registry；但该 registry 不应替代本文作为“输出规则”的 SSOT。