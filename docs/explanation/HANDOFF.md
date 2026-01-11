---
title: HANDOFF (SSOT) - Mhy_AI_RAG_data
version: 3
last_updated: 2026-01-11
timezone: America/Los_Angeles
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
- [5. 全局门禁策略（warning 过渡 → 收紧触发器）](#5-全局门禁策略warning-过渡--收紧触发器)
- [6. 新对话接手提示词（可复制）](#6-新对话接手提示词可复制)
- [7. 变更日志](#7-变更日志)

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
- repo gate（PR/CI Lite）：`profile=ci`，SSOT=`docs/reference/reference.yaml`（产物：`gate_report.json`）

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
  - 策略：`dense-only`（尚未常驻启用 BM25/hybrid/re-rank）
- E2E（Stage-3/端到端）：
  - `base_url = http://localhost:8000/v1`（OpenAI-compatible）
  - `timeout`：基线 300s（以报告落盘的 error_detail 为准做调整）
  - `llm_model`：建议 `auto`（运行时以 `/v1/models` 的真实 id 选择，并落盘审计）

### 1.3 当前核心工件（source of truth）
- 检索回归用例：`data_processed/eval/eval_cases.jsonl`
- 检索回归报告（SoT）：`data_processed/build_reports/eval_retrieval_report.json`（`schema_version=2`）
- 端到端回归报告（SoT）：`data_processed/build_reports/eval_rag_report.json`
- 方法论/演进背景：`docs/explanation/2026-01-04_retrieval_evolution_summary.md`

---
## 2. Active workstreams（并行线路一览）

> 并行线路以“同一 SSOT 内分栏”管理，禁止通过“多个 HANDOFF 文件”并行。

| id | status | scope | SoT artifacts | gates（验收/门禁） |
|---|---|---|---|---|
| WS-RETRIEVAL-REGRESSION | active | Stage-2 检索回归（分桶/对照/门禁收紧） | `eval_cases.jsonl` / `eval_retrieval_report.json` | warnings→fail 收紧触发器；非法桶直接 fail |
| WS-REPORT-OBSERVABILITY | active | report 实时观测（流式事件 + 控制台摘要），不破坏最终 JSON | `data_processed/build_reports/*.events.jsonl` + `*_report.json` | TTFS / case 增量 / stream vs final 对账 / 兼容性 |

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
- eval_retrieval_report 输出（schema v2）：
  - `metrics`（overall）与 `buckets`（按桶聚合）
  - `warnings`（迁移期缺字段/非法值等）
  - `run_meta`（argv、python、platform）用于复现
- E2E（端到端）回归增强：
  - LLM HTTP 失败落盘 `error_detail.status_code` / `error_detail.response_snippet`（截断正文），用于裁决“被拒绝 vs 超时”。

### 3.3 commands（基线命令）
```bash
python tools/validate_eval_cases.py --root . --cases data_processed/eval/eval_cases.jsonl
python tools/run_eval_retrieval.py --root . --cases data_processed/eval/eval_cases.jsonl --db chroma_db --collection rag_chunks --k 5 --out data_processed/build_reports/eval_retrieval_report.json
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --k 5 --out data_processed/build_reports/eval_rag_report.json
```

### 3.4 gates（迁移期门禁）
- 缺 bucket：允许运行，但写入 `warnings`（例如 `missing_bucket_default`），禁止 silent failure。
- 非法 bucket：建议直接 FAIL（避免统计失真）。
- `pair_id` 缺失：可先 warning，满足触发器后收紧为 FAIL。

### 3.5 next（最小改动优先）
1) k 扫描实验（k=5/10/20）：裁决失败是排序问题还是真漏召回。  
2) 对 `hit_at_k=false` 失败用例逐条判定：expected_sources 是否过窄导致假失败（先修契约）。  
3) 若 k=20 仍失败：优先 query 扩展（口语→术语映射），再考虑 hybrid（BM25 + 向量）与 RRF。  
4) E2E：400（ctx=4096）优先减小输入预算；ReadTimeout 优先减负，必要时再提高 timeout。  

### 3.6 rollback
- 本 workstream 的回滚以“保持 schema v2 输出 + 维持 warnings 过渡策略”为底线；任何收紧（warning→fail）必须满足触发器并能一键回退到 warning。

---
## 4. WS-REPORT-OBSERVABILITY（报告实时观测）

> 目标：缩短长任务反馈环路（不再“跑完才知道错”），但 **不破坏现有最终 JSON 报告** 的消费链路与门禁口径。

### 4.1 scope / non-goals
- scope：
  - 为长任务脚本提供实时信号（文件/控制台），包含：
    - 流式事件文件（推荐 JSONL；可选 RFC 7464 json-seq）
    - 进度快照（`progress.json`，原子替换）
    - 控制台聚合摘要（节流输出）
  - 保留最终汇总 JSON 作为判定真源（SoT）
- non-goals：
  - 不在此 workstream 内调整检索/RAG 算法与统计口径
  - 不把流式文件作为门禁判定输入（避免口径漂移）

### 4.2 artifacts（工件并存规则）
- 判定真源（SoT，保持不变）：
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`
- 观测旁路（新增）：
  - `data_processed/build_reports/*.events.jsonl`（或 `*.json-seq`）
  - `data_processed/build_reports/*.progress.json`（原子替换）
- 命名约定（建议）：
  - `eval_retrieval_report.json`（final）
  - `eval_retrieval_report.events.jsonl`（stream）
  - `eval_retrieval_report.progress.json`（snapshot）

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

已落地（截至 2026-01-06）：
- `run_eval_retrieval.py` / `run_eval_rag.py` 新增开关：`--stream-out` / `--stream-format` / `--progress-every-seconds`（默认关闭，final JSON 写入逻辑不变）。
- 新增统一写入器：`src/mhy_ai_rag_data/tools/report_stream.py`（jsonl + json-seq）。
- 新增文档：`docs/howto/OBSERVE_LONG_RUNS.md` 与 `docs/reference/EVAL_REPORTS_STREAM_SCHEMA.md`。

next（最小改动优先）：
1) 可选：为长跑脚本补充 `--progress-out`（原子替换 `progress.json`），用于更易消费的“当前摘要快照”。
2) 新增 `tools/<verify_stream_vs_final>.py`：运行结束后对账 stream 与 final 的关键计数（默认 warning，满足触发器后可收紧为 fail）。
3) 可选：新增 `tools/<watch_stream>.py`，实时聚合 `.events.jsonl` 并以节流方式输出摘要（给人类看）。

### 4.5 rollback
- 回滚必须做到“删除 stream/progress 输出仍能生成 final JSON 且工具链可读”；换句话说：stream/progress 是旁路，不可成为主链路依赖。

---
## 5. 全局门禁策略（warning 过渡 → 收紧触发器）

### 5.1 迁移期（默认）
- 旧格式/缺字段允许继续运行，但必须产生 `warnings` 并落盘，禁止 silent failure。
- 会导致统计/契约失真的错误（例如：非法枚举值、schema 破坏、关键输出缺失）应直接 FAIL。

### 5.2 收紧触发器（逐条收紧，不一步到位）
- `warnings_ratio <= 1%`（或 warnings 连续 N 次回归接近 0）
- `oral_cases >= 10`（口语桶样本量达到可解释规模）
- `pair_id_coverage >= 5`（至少覆盖 5 个高价值概念对照组）
满足后，将对应 warning 升级为 FAIL。

### 5.3 Repo Gate（PR/CI Lite：Schema + Policy + 可审计报告）
- SSOT：`docs/reference/reference.yaml`（门禁顺序/产物路径/schema/policy 输入集）
- 单入口：`python tools/gate.py --profile ci --root .`（或安装后 `rag-gate ...`）
- 产物：`data_processed/build_reports/gate_report.json` + `gate_logs/`
- Policy：通过 conftest 执行 `policy/` 下 Rego 规则；CI/Linux 会安装并强制执行，本地缺 conftest 时默认 SKIP。

---

## 6. 新对话接手提示词（可复制）

> 你是“技术顾问+系统分析师”。我在维护一个本地 RAG/检索项目。  
> SSOT：请先读取 `docs/explanation/HANDOFF.md` 并遵循其中的 Read→Derive→Act→Write-back。  
> 当前有两条并行 workstream：  
> 1) WS-RETRIEVAL-REGRESSION：口语 query 与官方术语不一致导致 topK 漏召回。我已完成 eval_cases 分桶（oral/official/ambiguous）并生成检索回归与端到端回归报告。请基于最新 `eval_cases.jsonl` 与 `eval_retrieval_report.json / eval_rag_report.json` 做诊断并给最小改动方案，保持可回滚与可观测，并给门禁收紧触发器。  
> 2) WS-REPORT-OBSERVABILITY：我希望长任务可实时观测。请在不破坏最终报告 JSON 兼容性的前提下，引入流式事件/进度快照/控制台摘要，并提供对账门禁（stream vs final）。  
> 若涉及模型字段：以 `GET /v1/models` 返回 id 为准，不要使用占位符。

---

## 7. 变更日志

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
