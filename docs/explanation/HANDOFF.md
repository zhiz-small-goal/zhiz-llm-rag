---
title: HANDOFF (SSOT) - zhiz-llm-rag
version: 12
last_updated: 2026-01-27
timezone: America/Los_Angeles
owner: zhiz
status: active
ssot: true
---

# HANDOFF（单一真源 / SSOT）


> 目的：这是本仓库“当前阶段状态 + 运行契约 + 演进触发器”的可携带快照。  
> 规则：本仓库只允许 **1 个生效的 HANDOFF**，路径固定为 `docs/explanation/HANDOFF.md`。

## 目录
- [0. 使用方法（Read → Derive → Act → Write-back）](#0-使用方法read--derive--act--write-back)
- [1. 当前基线口径（先读这一节）](#1-当前基线口径先读这一节)
- [2. Active workstreams（并行线路一览）](#2-active-workstreams并行线路一览)
- [3. WS-RETRIEVAL-REGRESSION（检索回归）](#3-ws-retrieval-regression检索回归)
- [4. WS-REPORT-OBSERVABILITY（报告实时观测）](#4-ws-report-observability报告实时观测)
- [5. WS-DOC-SYSTEM-LEVEL3（文档体系重构：WAL/断点续跑语义）](#5-ws-doc-system-level3文档体系重构wal断点续跑语义)
- [6. 全局门禁策略（warning 过渡 → 收紧触发器）](#6-全局门禁策略warning-过渡--收紧触发器)
- [7. 新对话接手提示词（可复制）](#7-新对话接手提示词可复制)
- [8. 变更日志](#8-变更日志)

---

## 0. 使用方法（Read → Derive → Act → Write-back）

### Read
1) 先读本文件第 1 节（基线口径）与第 2 节（当前活跃 workstreams）。  
2) 再读与本次任务直接相关的脚本/配置/报告工件（本文件各 workstream 下都有 `artifacts` 与 `commands`）。
3) 对照稳定契约与术语口径：[`../reference/REFERENCE.md`](../reference/REFERENCE.md)。

### Derive（每次输出前必须声明）
每次开始一个新任务，必须在输出中明确本次采用的基线口径，至少包含：
- `k`（检索 topK）
- `db` / `collection`
- `embed_model` / `device`
- 门禁模式（`warning` 迁移期 / 已收紧为 `fail` 的条目）
- repo gate（PR/CI Lite）：`profile=ci`，SSOT=`docs/reference/reference.yaml`（产物：`gate_report.json` + `gate_report.md` + `gate_report.events.jsonl`）

### Act（最小改动、可回滚、可观测）
- 优先以“旁路工件 + 明确契约 + 对账门禁”的方式演进，避免一次性破坏现有消费链路。  
- 任何可能影响统计口径的改动，必须同时提供：可对账证据、回滚路径、以及门禁策略更新。

### Write-back（口径变化必须写回）
出现以下任何一项变化，必须更新本文件并记录变更日志：
- 基线口径与指标（k、模型、collection、阈值、样本规模）
- 门禁规则（warning/fail）或其收紧触发器
- 关键命令/工件路径/契约字段（schema）

---
## 1. 当前基线口径（先读这一节）

> 本节用于“跑得起来 + 可复现 + 不混淆”。未特别说明时，默认以本节为准。

### 1.1 目标与阶段
- 核心问题：用户口语 query 与知识库“官方术语/文档标题”存在 vocabulary mismatch，导致 dense topK 候选窗漏召回，进而端到端 RAG 失败。
- 当前阶段聚焦：
  - Stage-2：检索回归（retrieval-only），可分桶、可对照、可落盘证据。
  - E2E：端到端回归（retrieve + prompt + LLM），可区分 HTTP 错误 vs 超时。

### 1.2 默认运行参数（基线）
- Retrieval（Stage-2）：
  - `db = chroma_db`
  - `collection = rag_chunks`
  - `k = 5`（基线；实验时允许扫描 k=5/10/20，但必须写清采用值）
  - `embed_model = BAAI/bge-m3`
  - `device = cpu`（除非显式传参或 profile 指定，如 `cuda:0`）
  - 策略：`hybrid`（dense + keyword；fusion=rrf；dense_topk=50；keyword_topk=50；rrf_k=60）
- E2E（Stage-3/端到端）：
  - `base_url = http://localhost:8000/v1`（OpenAI-compatible）
  - `timeout`：基线 300s（以报告落盘的 error_detail 为准做调整）
  - `llm_model`：建议 `auto`（运行时以 `/v1/models` 的真实 id 选择，并落盘审计）

### 1.3 当前核心工件（source of truth）
- 检索回归用例：`data_processed/eval/eval_cases.jsonl`
- 检索回归报告（SoT）：`data_processed/build_reports/eval_retrieval_report.json`（`schema_version=2`）
- 端到端回归报告（SoT）：`data_processed/build_reports/eval_rag_report.json`
- Stage-2 评测契约：`docs/reference/EVAL_CASES_SCHEMA.md`
- 口语 vs 官方术语回归 How-to：`docs/howto/ORAL_OFFICIAL_RETRIEVAL_REGRESSION.md`
- 方法论/演进背景：`docs/explanation/2026-01-04_retrieval_evolution_summary.md`

### 1.4 运维/验收入口（Stage-1 补充）
- `rag-status`：只读扫描管线状态，产物 `data_processed/build_reports/status.json`；STALE 基于 `data_processed/index_state/db_build_stamp.json`（契约见 `docs/reference/index_state_and_stamps.md`；用法见 `docs/howto/rag_status.md`）
- `rag-accept`：一键验收入口（stamp → check → snapshot → status）；详见 `docs/howto/rag_accept.md`

---
## 2. Active workstreams（并行线路一览）

> 并行线路以“同一 SSOT 内分栏”管理，禁止通过“多个 HANDOFF 文件”并行。

| id | status | scope | SoT artifacts | gates（验收/门禁） |
|---|---|---|---|---|
| WS-RETRIEVAL-REGRESSION | active | Stage-2 检索回归（分桶/对照/门禁收紧） | `eval_cases.jsonl` / `eval_retrieval_report.json` | warnings→fail 收紧触发器；非法桶直接 fail |
| WS-REPORT-OBSERVABILITY | active | report 实时观测（流式事件 + 控制台摘要），不破坏最终 JSON | `data_processed/build_reports/*.events.jsonl` + `*_report.json` | TTFS / case 增量 / stream vs final 对账 / 兼容性 |
| WS-DOC-SYSTEM-LEVEL3 | active | 文档体系重构（WAL/断点续跑语义）：术语/契约/去重/链接修复/门禁 | `docs/explanation/planning_doc_system_level3_sync_20260123.md` + `docs/explanation/doc_inventory.md` + `docs/explanation/doc_map.json` | Step1 覆盖清点；Step6（后续）最小文档门禁（链接/术语/front-matter） |

---
## 3. WS-RETRIEVAL-REGRESSION（检索回归）

### 3.1 scope / non-goals
- scope：
  - 维护 Stage-2 回归用例（分桶：oral/official/ambiguous）
  - 输出可对照、可聚合的检索回归报告（schema v2）
  - 迁移期门禁：warnings 过渡 + 明确收紧触发器
- non-goals（本 workstream 不做）：
  - 不在此处引入重型检索架构重写（如更换向量库/大规模在线服务化）

### 3.2 已落地能力（截至 2026-01-05 快照）
- eval_cases 支持字段：
  - `bucket`：`oral|official|ambiguous`
  - `pair_id` / `concept_id`：同概念对照组（口语 vs 术语）
- 新增用例生成工具：`tools/suggest_eval_case.py`（半自动生成 expected_sources/must_include，并支持 bucket/pair_id/concept_id）
- eval_retrieval_report 输出（schema v2）：
  - `metrics`（overall，含 dense/hybrid 对照）与 `buckets`（按桶聚合）
  - `warnings`（迁移期缺字段/非法值等）
  - `run_meta`（argv、python、platform）用于复现
- E2E（端到端）回归增强：
  - LLM HTTP 失败落盘 `error_detail.status_code` / `error_detail.response_snippet`（截断正文），用于裁决“被拒绝 vs 超时”。

### 3.3 commands（基线命令）
```bash
python tools/validate_eval_cases.py --root . --cases data_processed/eval/eval_cases.jsonl
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 5 --retrieval-mode hybrid --dense-topk 50 --keyword-topk 50 --fusion-method rrf --rrf-k 60 --out data_processed/build_reports/eval_retrieval_report.json --events-out data_processed/build_reports/eval_retrieval_report.events.jsonl --progress auto --durability-mode flush
python tools/snapshot_eval_retrieval_baseline.py --root . --report data_processed/build_reports/eval_retrieval_report.json --baseline-out data_processed/baselines/eval_retrieval_baseline.json
python tools/compare_eval_retrieval_baseline.py --root . --baseline data_processed/baselines/eval_retrieval_baseline.json --report data_processed/build_reports/eval_retrieval_report.json --allowed-drop 0.0
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --k 5 --out data_processed/build_reports/eval_rag_report.json
```

### 3.4 gates（迁移期门禁）
- 缺 bucket：允许运行，但写入 `warnings`（例如 `missing_bucket_default`），禁止 silent failure。
- 非法 bucket：建议直接 FAIL（避免统计失真）。
- `pair_id` 缺失：可先 warning，满足触发器后收紧为 FAIL。

### 3.5 next（最小改动优先）
1) k 扫描实验（k=5/10/20）：裁决失败是排序问题还是真漏召回。  
2) 对 `hit_at_k=false` 失败用例逐条判定：expected_sources 是否过窄导致假失败（先修契约）。  
3) 若 k=20 仍失败：优先检查用例 expected_sources 的口径与索引是否漂移；其次做 query 扩展（口语→术语映射）或调整 hybrid 关键字侧候选窗（keyword_topk）与融合参数（rrf_k）。  
4) E2E：400（ctx=4096）优先减小输入预算；ReadTimeout 优先减负，必要时再提高 timeout。  

### 3.6 rollback
- 本 workstream 的回滚以“保持 schema v2 输出 + 维持 warnings 过渡策略”为底线；任何收紧（warning→fail）必须满足触发器并能一键回退到 warning。

---
## 4. WS-REPORT-OBSERVABILITY（报告实时观测）

> 目标：缩短长任务反馈环路（不再“跑完才知道错”），但 **不破坏现有最终 JSON 报告** 的消费链路与门禁口径。

### 4.1 scope / non-goals
- scope：
  - 为长任务脚本提供实时信号（文件/控制台），包含：
    - item 事件流文件（JSONL：每行 1 个 report v2 item；用于中断恢复/回放与审计）
    - 控制台聚合进度（节流输出到 stderr；避免 stdout 刷屏，保持 report bundle 输出整洁）

  - 保留最终汇总 JSON 作为判定真源（SoT）
- non-goals：
  - 不在此 workstream 内调整检索/RAG 算法与统计口径
  - 不把流式文件作为门禁判定输入（避免口径漂移）

### 4.2 artifacts（工件并存规则）
- 判定真源（SoT，保持不变）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- 观测旁路（新增）：
  - `data_processed/build_reports/*.events.jsonl`（item 事件流；每行 1 个 report v2 item）

- 命名约定（建议）：
  - `eval_retrieval_report.json`（final）
  - `eval_retrieval_report.events.jsonl`（stream）

### 4.3 acceptance gates（“一次性改造完”的可验收闭环）
- Gate-1：TTFS（Time To First Signal）
  - 运行开始后 X 秒内必须出现第一条 `meta/progress` 信号（控制台或流式文件均可）。
- Gate-2：case 增量
  - 每处理完 1 条 case，流式文件至少追加 1 条 `case` 事件（或 progress 的 `completed_count` 单调增长）。
- Gate-3：Consistency（对账）
  - 运行结束后，流式聚合统计与最终 JSON 的关键计数一致（至少 cases_total / pass/fail / hit 等）。
- Gate-4：兼容性
  - 现有消费端仍只读最终 JSON；不开启 stream/progress 开关时输出与行为保持不变。

### 4.4 implementation plan（按最小改动、可回滚顺序）

已落地（截至 2026-01-21）：
- `gate.py` 以及长任务工具（例如 `run_eval_retrieval.py` / `run_eval_rag.py`）提供：
  - `--events-out`：item 事件流输出（JSONL；每行 1 个 report v2 item；默认与 report.json 同名）
  - `--progress` + `--progress-min-interval-ms`：stderr 进度摘要（节流）
- 统一写入器：`src/mhy_ai_rag_data/tools/report_events.py`（jsonl；支持 durability_mode=none|flush|fsync）
- 相关文档：`docs/howto/OBSERVE_LONG_RUNS.md` 与 `docs/reference/EVAL_REPORTS_STREAM_SCHEMA.md`（与当前 events 语义对齐）

已落地（v2 升级，2026-01-17）：
- **schema_version=2 升级完成**（Tier 1+2，共4个脚本）：
  - `run_eval_retrieval.py`：schema_version=2 (int)，cases→items，完整 v2 契约 ✅
  - `run_eval_rag.py`：schema_version=2，cases→items with severity_level ✅
  - `probe_llm_server.py`：从 v1 迁移到 v2，GET/POST→items ✅  
  -` rag_status.py`：保持 v1 输出，扩展兼容检查 v1/v2 报告 ✅
- **核心特性**：
  - 所有 items 包含 `severity_level` (int) 用于数值排序，非字符串标签
  - 统一使用 `compute_summary()` 计算 summary（overall_status_label, overall_rc, counts 等）
  - 通过 `write_json_report()` 自动归一化路径 `/` + 添加 VS Code 跳转 `loc_uri`
  - 向后兼容：原始数据保留在 `data` 块
- **新增文档**：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`（输出契约 SSOT；`REPORT_OUTPUT_CONTRACT.md` 为兼容 alias）

next（最小改动优先）：
1) 可选：为长跑脚本补充 `--progress-out`（原子替换 `progress.json`），用于更易消费的“当前摘要快照”。
2) 新增 `tools/<verify_stream_vs_final>.py`：运行结束后对账 stream 与 final 的关键计数（默认 warning，满足触发器后可收紧为 fail）。
3) 可选：新增 `tools/<watch_stream>.py`，实时聚合 `.events.jsonl` 并以节流方式输出摘要（给人类看）。

### 4.5 rollback
- 回滚必须做到“删除 stream/progress 输出仍能生成 final JSON 且工具链可读”；换句话说：stream/progress 是旁路，不可成为主链路依赖。

---
## 5. WS-DOC-SYSTEM-LEVEL3（文档体系重构：WAL/断点续跑语义）

> 目标：将全仓与“Chroma build 的 WAL/断点续跑语义”相关的文档口径统一到 SSOT，避免不同入口互相矛盾。

### 5.1 scope / non-goals
- scope：
  - 全仓 `*.md` 的 Level 3 重构：统一术语、统一“reset/resume/WAL/state/锁/strict-sync”解释、去重、修复链接与 TOC/front-matter。
  - 解释并固化“用户真实输出”相关的可操作 runbook：
    - `--resume-status` 的字段含义与决策入口
    - `policy=reset` 的日志含义（默认评估 vs 最终生效决策）
    - `writer lock exists` 的互斥目的与处置
- non-goals：
  - 不改动代码行为；若文档发现与代码冲突，以代码为准并登记缺口。
  - 不重写 archive/postmortem 的历史叙事（只加 NOTE/跳转）。

### 5.2 SoT artifacts
- 计划（Step1–Step6）：`docs/explanation/planning_doc_system_level3_sync_20260123.md`

- Step1（Inventory + Map）
  - 人类可读：`docs/explanation/doc_inventory.md`
  - 机器可读：`docs/explanation/doc_map.json`
  - 生成工具：`tools/gen_doc_inventory.py`（用法：`tools/gen_doc_inventory_README.md`）

- Step2（SSOT + 术语）
  - 文档体系裁决/引用边界：`docs/reference/DOC_SYSTEM_SSOT.md`
  - 术语表（WAL/State/Resume）：`docs/reference/GLOSSARY_WAL_RESUME.md`
  - 索引状态与锁语义（既有契约，已补齐与 CLI 对齐 NOTE）：`docs/reference/index_state_and_stamps.md`

- Step3（CLI/日志真相表）
  - `build_chroma_index_flagembedding` 参数/默认值/组合语义 + `--resume-status` 字段与关键日志：`docs/reference/build_chroma_cli_and_logs.md`


### 5.3 commands（Step1–Step3）

Windows CMD：

- Step1：生成/更新清点与图谱
```cmd
python tools\gen_doc_inventory.py --root . --include-untracked --write
```

- Step3：只读预检（runbook 第一入口）
```cmd
rem 注意：--resume-status 也会计算 current schema_hash；必须携带与目标索引一致的口径参数（尤其 include_media_stub）
rem Scheme B（include_media_stub=true）
python tools\build_chroma_index_flagembedding.py build --collection rag_chunks --resume-status --include-media-stub
```

- Step6：文档门禁（links/terms/front-matter）
```cmd
python tools\check_doc_system_gate.py --root . --doc-map docs\explanation\doc_map.json --out data_processed\build_reports\doc_system_gate_report.json --md-out data_processed\build_reports\doc_system_gate_report.md
```

> 2026-01-25 起：该 Step6 已纳入 gate profiles（fast/ci/release），以 `docs/reference/reference.yaml` 为准。


### 5.4 acceptance（Step1）
- 覆盖面：`doc_map.json.meta.tracked_md_files_total` 必须覆盖 `git ls-files "*.md"` 的全部文件。
- 图谱完整性：每份文档必须有唯一 `role`（reference/guide/runbook/README/archive/postmortem）与 `action`（need_align/only_note/no_action）。
- 关键字命中：所有命中文档必须被标注（need_align/only_note）。

### 5.5 status / next
- 已完成：Step1（Inventory+Map）、Step2（SSOT+术语）、Step3（CLI/日志真相表）。
- 已推进：Step4/5（对 need_align 文档收敛到 SSOT，并补齐 TOC/front-matter/链接）。
- 已完成：Step6 最小门禁脚本 `tools/check_doc_system_gate.py`（当前 scope：仅 keyword_hits 文档 + ALWAYS_INCLUDE 入口文档）。
- 已收口：Step6 已挂入 gate（`python tools\gate.py --profile fast|ci|release --root .` 会自动执行）。

下一步建议（继续按批次推进）：
1) 依据 `doc_inventory.md` 的 `need_align` 集合，分目录扩展迁移去重范围（优先 README/howto/tools README）。
2) 将 Step6 gate 的 `INFO` 项逐步收紧为 `WARN/FAIL`（先入口文档，再扩展到全仓）。

### 5.6 rollback
- Step1 产物可随时用生成器重建；任何迁移改动必须分批提交并可回滚到“仅 NOTE/跳转”的状态。

---
## 6. 全局门禁策略（warning 过渡 → 收紧触发器）

### 6.1 迁移期（默认）
- 旧格式/缺字段允许继续运行，但必须产生 `warnings` 并落盘，禁止 silent failure。
- 会导致统计/契约失真的错误（例如：非法枚举值、schema 破坏、关键输出缺失）应直接 FAIL。

### 6.2 收紧触发器（逐条收紧，不一步到位）
- `warnings_ratio <= 1%`（或 warnings 连续 N 次回归接近 0）
- `oral_cases >= 10`（口语桶样本量达到可解释规模）
- `pair_id_coverage >= 5`（至少覆盖 5 个高价值概念对照组）
满足后，将对应 warning 升级为 FAIL。

### 6.3 Repo Gate（PR/CI Lite：Schema + Policy + 可审计报告）

- Review Spec（审查规范）门禁：
  - SSOT：`docs/reference/review/review_spec.v1.json`
  - 人类阅读产物：`docs/reference/review/REVIEW_SPEC.md`（由生成器写入；禁止手改）
  - 校验：`python tools/validate_review_spec.py --root .`（PASS=0 / FAIL=2 / ERROR=3）
  - 生成（本地修复）：`python tools/generate_review_spec_docs.py --root . --write`（然后重跑校验）
- SSOT：`docs/reference/reference.yaml`（门禁顺序/产物路径/schema/policy 输入集）
- 单入口：`python tools/gate.py --profile ci --root .`（或安装后 `rag-gate ...`）
- 产物（落盘 + 可恢复）：`data_processed/build_reports/gate_report.json`（SoT） + `gate_report.md`（人类入口） + `gate_report.events.jsonl`（运行中增量，可重建） + `gate_logs/`
- 进度反馈（stderr）：`--progress {auto|on|off}`；auto 仅在 TTY 且非 CI 启用，更新节流默认 200ms，结束时清理进度行后再输出最终报告。
- durability_mode（events 落盘强度）：`--durability-mode {none|flush|fsync}`（默认 flush）；fsync 允许按 `--fsync-interval-ms` 节流。
- 文件落盘报告顺序（人类可读）：对“写入文件”的报告在落盘入口做归一化：汇总块置顶；明细按严重度稳定排序（ERROR/FAIL 在前，PASS 在后）。回链：`docs/postmortems/2026-01-15_postmortem_file_report_ordering.md`。
- 路径展示一致性（跨 OS diff 降噪）：落盘报告内的路径展示串统一使用 `/`（`Path.as_posix()`）；但“可点击跳转”不依赖该启发式，仍以 `loc_uri`/Markdown 链接为准。回链：`docs/postmortems/2026-01-15_postmortem_report_output_contract_paths.md`。
- 诊断定位可点击：落盘报告中若包含 `DIAG_LOC_FILE_LINE_COL`，应补充 `loc_uri`（`vscode://file/<abs_path>:line:col`）或用 Markdown 链接渲染，避免依赖 VS Code 的启发式 linkify。
- `profile=ci/release` 默认包含 `check_ruff` / `check_mypy`（format/strict 默认关闭，可用 `RAG_RUFF_FORMAT=1`、`RAG_MYPY_STRICT=1` 收紧）
- Policy：通过 conftest 执行 `policy/` 下 Rego 规则；CI/Linux 会安装并强制执行，本地缺 conftest 时默认 SKIP。

---

## 7. 新对话接手提示词（可复制）

> 你是“技术顾问+系统分析师”。我在维护一个本地 RAG/检索项目。  
> SSOT：请先读取 `docs/explanation/HANDOFF.md` 并遵循其中的 Read→Derive→Act→Write-back。  
> 当前有三条并行 workstream：  
> 1) WS-RETRIEVAL-REGRESSION：口语 query 与官方术语不一致导致 topK 漏召回。我已完成 eval_cases 分桶（oral/official/ambiguous）并生成检索回归与端到端回归报告。请基于最新 `eval_cases.jsonl` 与 `eval_retrieval_report.json / eval_rag_report.json` 做诊断并给最小改动方案，保持可回滚与可观测，并给门禁收紧触发器。  
> 2) WS-REPORT-OBSERVABILITY：我希望长任务可实时观测。请在不破坏最终报告 JSON 兼容性的前提下，引入流式事件/进度快照/控制台摘要，并提供对账门禁（stream vs final）。  
> 3) WS-DOC-SYSTEM-LEVEL3：我希望把全仓 Markdown 做 Level 3 文档体系重构（WAL/断点续跑语义）。请先执行 Step1（Inventory + Map）：运行 `python tools/gen_doc_inventory.py --root . --include-untracked --write`，并基于 `docs/explanation/doc_inventory.md` + `doc_map.json` 规划后续 Step2/3（SSOT/术语/CLI&日志真相表）与分批迁移。  
> 若涉及模型字段：以 `GET /v1/models` 返回 id 为准，不要使用占位符。

---

## 8. 变更日志

### v9 (2026-01-23)
- WS-DOC-SYSTEM-LEVEL3：补齐 Step2/Step3 SSOT 工件（DOC_SYSTEM_SSOT / GLOSSARY_WAL_RESUME / build_chroma_cli_and_logs），并在 index_state_and_stamps 增补与 CLI 对齐 NOTE。


### v8 (2026-01-23)
- 新增 workstream：WS-DOC-SYSTEM-LEVEL3（文档体系重构：WAL/断点续跑语义）
- 落盘 Step1 产物：`docs/explanation/doc_inventory.md` + `docs/explanation/doc_map.json`
- 新增生成工具：`tools/gen_doc_inventory.py`（用法：`tools/gen_doc_inventory_README.md`）
- 新增计划文档：`docs/explanation/planning_doc_system_level3_sync_20260123.md`

### v7 (2026-01-17)
- **报告输出 v2 升级完成**（WS-REPORT-OBSERVABILITY）：
  - 升级 4 个脚本到 schema_version=2：run_eval_retrieval, run_eval_rag, probe_llm_server（完整v2），rag_status（兼容v1/v2检查）
  - 新增契约文档（SSOT）：`docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`（兼容 alias：`REPORT_OUTPUT_CONTRACT.md`）
  - 核心特性：severity_level 数值排序、compute_summary()、VS Code 跳转 loc_uri、向后兼容
- 更新本文档：补充 v2 升级状态到第 4.4 节

### v7 (2026-01-15)
  - 报告可用性契约：落盘报告中的诊断定位新增 `loc_uri`（`vscode://file/...`），并更新渲染脚本/文档
  - 新增复盘：`docs/postmortems/2026-01-15_postmortem_vscode_clickable_loc_uri.md`


- 2026-01-13
  - 新增复盘：`docs/postmortems/2026-01-13_postmortem_review_spec_priority_coverage_gate_and_handoff.md`
  - HANDOFF 写回：新增 Review Spec 门禁入口与修复命令（SSOT/生成/校验）
  - 修复：`tools/validate_review_spec.py` 渲染口径与生成器对齐，避免一致性误判
- 2026-01-06
  - 新增 SSOT：`docs/explanation/HANDOFF.md`（本文件）
  - 引入 workstreams 分栏：检索回归 + 报告实时观测
  - 约定归档位置：`docs/explanation/handoffs/`（历史快照仅归档，不作为当前口径）
  - report 实时观测：新增 stream 旁路输出（jsonl/json-seq）与进度摘要参数，保持 final JSON 兼容

- 2026-01-09
  - Public Release Preflight：新增 repo health/community files 检查项（CHANGELOG/CITATION/.editorconfig/CoC 联系方式占位符）
  - 新增脚本：`tools/check_repo_health_files.py`（stdlib-only；0/1/2 退出码契约）
  - 新增 postmortem：`docs/postmortems/2026-01-09_postmortem_open_source_repo_health_files.md`

- 2026-01-11
  - 收敛 PR/CI Lite 门禁：新增单入口 gate runner（`rag-gate` / `tools/gate.py`），输出确定性产物 `gate_report.json` + `gate_logs/`
  - 新增 machine-readable SSOT：`docs/reference/reference.yaml`（paths/schemas/policy/steps）
  - 新增 schema/policy：`schemas/gate_report_v1.schema.json` + `policy/`（conftest/Rego）
  - Public Release Hygiene 审计升级：新增 `--file-scope` / `--respect-gitignore`，默认输出落盘到 `data_processed/build_reports/`
  - 新增 JSON Schema 校验工具：`tools/schema_validate.py` / `rag-schema-validate`，用于校验 `gate_report.json` 与 `schemas/gate_report_v1.schema.json`

- 2026-01-12
  - PR/CI Lite 门禁新增 ruff/mypy（`check_ruff` / `check_mypy`）并保留 format/strict 可选开关
  - 新增 repo-only gate 工具与说明：`tools/check_ruff.py` / `tools/check_mypy.py`（含 README）
  - SSOT 与门禁文档同步：`docs/reference/reference.yaml` / `docs/howto/ci_pr_gates.md` / `tools/gate_README.md`

- 2026-01-13
  - 补充 Stage-2 评测契约与口语/术语回归 how-to 入口：`docs/reference/EVAL_CASES_SCHEMA.md` / `docs/howto/ORAL_OFFICIAL_RETRIEVAL_REGRESSION.md`
  - 补充 Stage-1 运维/验收入口与 db_build_stamp 契约：`docs/howto/rag_status.md` / `docs/howto/rag_accept.md` / `docs/reference/index_state_and_stamps.md`
  - Repo Gate 补充 Review Spec SSOT 校验与生成器入口：`tools/validate_review_spec.py` / `tools/generate_review_spec_docs.py`
