---
template: incident_postmortem
version: v2.0
last_updated: 2026-01-05
style: pagerduty_atlassian_plus_project_contracts
incident_id: INC-20260105-LLM-OBS-MODEL
---

# 事故复盘：E2E 回归中 LLM HTTP POST 错误取证缺失与模型身份不准确 — 2026-01-05

## 目录
- [1. 摘要](#1-摘要)
- [2. 影响与严重级别](#2-影响与严重级别)
- [3. 发现与时间线](#3-发现与时间线)
- [4. 根因分析](#4-根因分析)
- [5. 修复与验证](#5-修复与验证)
- [6. 预防与改进（行动项）](#6-预防与改进行动项)
- [7. 最小可复现（MRE）](#7-最小可复现mre)
- [附录 A：证据定位](#附录-a证据定位)
- [附录 B：决策与取舍](#附录-b决策与取舍)
- [附录 C：本项目专用契约与门禁](#附录-c本项目专用契约与门禁)

---

## 1. 摘要

- **问题陈述**：端到端（E2E）回归在调用 OpenAI-compatible `POST /v1/chat/completions` 失败时，历史错误信息只包含 `HTTPError: 400` 等摘要，缺少响应正文与关键上下文，导致“超时 vs 请求被拒绝”难以快速裁决；同时回归报告中 `model_field` 记录为占位字符串（例如 `gpt-3.5-turbo`），与服务端真实模型 `GET /v1/models` 返回的 id 不一致，导致对“实际调用模型”的审计失真。
- **范围**：本次复盘覆盖两类症状，但抽象为同一类根因：**可观测性/契约语义不完整导致的误判与返工**。
- **当前状态**：已通过代码改造补齐“错误取证字段（status_code / response_snippet / content_type）”与“模型身份解析（/v1/models 解析 + auto 选择 + 落盘选择过程）”，并将其纳入后续门禁建议。

**[Fact] 触发样本（来自本次报告）**  
- 报告时间：`2026-01-05T09:53:47+0800`  
- base_url：`http://127.0.0.1:8000/v1`  
- timeout：connect=10.0s, read=120.0s  
- report.model_field：`gpt-3.5-turbo`  
- 本次 E2E 指标：cases=5, passed=2, pass_rate=0.400  
- 400 失败用例 id：customize_game_character_actions, designing_game_weapons  

---

## 2. 影响与严重级别

- **严重级别（Dev-SEV）**：SEV-2（阻塞有效定位，降低回归系统可信度；但不破坏数据与环境，可通过人工绕过继续推进）
- **影响面**：
  - **诊断效率**：出现 4xx/5xx 时无法快速判断“拒绝原因（如上下文超限/参数非法/模型不存在）”，排障依赖反复试错。
  - **审计可信度**：报告中的 `model_field` 不代表服务端真实模型 id，导致误以为使用外部模型或误判配置漂移。
  - **工程返工**：在算力与时间受限环境下，误判会显著放大迭代成本（尤其是 E2E 回归较慢的情况下）。
- **持续时间**：[Inference] 该问题在“首次引入 E2E 回归报告字段”之后持续存在，直到本次补齐可观测性与模型解析逻辑为止；可通过 `git log` 定位首次引入 `model_field` 的提交时间做验证。

---

## 3. 发现与时间线

> 说明：此处强调“观测→判断→动作→结果”，避免散文式描述。

| 时间戳 | 观测 | 判断与原因 | 动作 | 结果 | 证据 |
|---|---|---|---|---|---|
| 2026-01-05T09:53:47+0800 | E2E 回归中出现 `HTTPError: 400`，错误信息缺少响应正文 | 无法区分“请求被拒绝原因”（ctx 超限/参数不兼容/模型不存在） vs 其它 | 规划补齐错误取证字段落盘 | 将错误从“黑箱”改为“可裁决” | 附录 A.1 |
| 2026-01-05T09:53:47+0800 | 报告 `llm.model_field=gpt-3.5-turbo` | `model_field` 语义不清：更像客户端占位值，不等价于服务端真实模型 id | 调用 `GET /v1/models` 获取真实 id 列表；引入 `--llm-model auto` 解析策略 | 报告模型字段可审计；减少误读 | 附录 A.2 |

---

## 4. 根因分析

### 4.1 直接根因

1) **HTTP 错误取证缺失**  
- **[Fact]** 失败错误字符串仅包含 `HTTPError: 400 Client Error: Bad Request` 等摘要信息，不含 response body。  
- **[Inference]** 由于 `requests.Response.raise_for_status()` 抛出异常后未捕获并提取 `response.text`/`response.json`，导致响应正文丢失；而 OpenAI-compatible 服务在 400 时通常会给出结构化错误信息（例如上下文长度/参数错误），不落盘会造成误判。

2) **模型身份字段契约不清**  
- **[Fact]** 报告字段 `model_field` 为占位字符串（`gpt-3.5-turbo`），与服务端 `/v1/models` 返回的 id 可能不一致。  
- **[Inference]** 由于 OpenAI-compatible 服务器可能忽略/宽松接受请求体中的 `model` 字段，导致“请求体 model 字符串”与“服务端真实模型 id”脱钩；若报告只记录请求体字段，会产生审计歧义。

### 4.2 促成因素（Contributing Factors）

- **环境异构**：不同 OpenAI-compatible 实现对 `model` 字段校验强度不同（严格校验会直接 4xx；宽松实现会忽略），导致“占位符也能跑”，掩盖了契约问题。
- **资源约束**：本地推理较慢时，排障更依赖“一次运行拿到充分证据”，否则每轮试错成本很高。
- **缺少门禁**：缺少“报告失败必须落盘 error_detail”的强制门禁，导致该缺口长期存在而不自知。

---

## 5. 修复与验证

### 5.1 修复措施（已落地）

1) **增强 HTTP 错误可观测性（4xx/5xx）**  
- 在统一 HTTP Client 中引入结构化错误对象（例如 `LLMHTTPError`），落盘字段至少包括：
  - `status_code`
  - `response_content_type`
  - `response_snippet`（截断，避免污染日志）
  - `cause`（原始异常类型与信息）
- 目标：使一次失败即可裁决“是超时（ReadTimeout）还是请求被拒绝（4xx/5xx + 具体原因）”。

2) **模型身份解析与落盘（/v1/models）**  
- 增加 `GET /v1/models` 探测与解析：
  - 默认 `--llm-model auto`
  - 优先选择 `*-instruct`（若存在），否则 fallback
  - 将 `server_models`、`resolved_model`、`selection_reason`、`models_fetch_error` 落盘到报告
- 目标：使报告中的模型字段具有审计意义，避免 `gpt-3.5-turbo` 等占位符造成误解。

### 5.2 验证方法（验收口径）

- **错误取证验收**：构造一次 400（或其它 4xx/5xx）后，报告/日志中必须包含 `status_code` 与 `response_snippet_head`（或等价字段）；ReadTimeout 必须能在 `cause` 中被明确识别（且没有误报为 4xx）。
- **模型身份验收**：运行时必须记录 `/v1/models` 返回的候选 id 列表，并且最终使用的 `resolved_model` 必须是其中之一；若探测失败则必须落盘失败原因并显式 fallback。

---

## 6. 预防与改进（行动项）

| 行动项 | 类型 | DRI/Owner | 截止日期 | 验收口径 | 状态 |
|---|---|---|---|---|---|
| 将“E2E 失败必须落盘 error_detail（status_code/cause/response_snippet）”加入回归门禁（缺失即 FAIL） | 固化/门禁 | zhiz | 2026-01-05 | 任一失败 case 的报告均含可裁决字段；缺失时报错退出 | DONE |
| 将“model 必须来自 /v1/models 解析，且记录 model_resolve”加入门禁建议（或至少 warning→fail 触发器） | 固化/门禁 | zhiz | 2026-01-05 | 报告包含 server_models + resolved_model + selection_reason | DONE |
| 在 HANDOFF/项目指令中固定“SSOT 交接包 + Read→Derive→Act→Write-back”协议，避免新会话误读门禁语义 | 固化/治理 | zhiz | 2026-01-05 | 新对话仅凭 HANDOFF 可复现实验口径与门禁策略 | DONE/可持续 |
| 为 400（ctx 超限）提供明确 Runbook：优先减输入预算，再评估增大 ctx；为 ReadTimeout 提供减负优先策略 | Runbook | zhiz | 2026-01-12 | 文档中给出参数调整优先级与验收命令 | TODO |

---

## 7. 最小可复现（MRE）

- **运行环境**：
  - LLM base_url：`http://127.0.0.1:8000/v1`
  - timeout：connect=10.0s, read=120.0s
- **步骤**：
  1) 获取服务端模型列表（用于验证 model resolve）：
     ```powershell
     curl http://127.0.0.1:8000/v1/models
     ```
  2) 运行一次 E2E 回归（选择包含会触发 400 的用例集/或构造超长输入）：
     ```bash
     python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --k 5 --out data_processed/build_reports/eval_rag_report.json
     ```
- **期望输出（PASS/FAIL 判定点）**：
  - 若出现 4xx/5xx：报告中能看到 `status_code` 与 `response_snippet`（用于裁决拒绝原因）。
  - 若出现 ReadTimeout：报告中 `cause` 明确包含 `ReadTimeout` 与 read_timeout 秒数。
  - `resolved_model` 必须来自 `/v1/models` 列表；若失败必须落盘 `models_fetch_error`。

---

## 附录 A：证据定位

### A.1 本次 E2E 回归报告（失败信息缺少正文、模型占位）
- 文件：`eval_rag_report.json`
- 字段：
  - `llm.base_url` = `http://127.0.0.1:8000/v1`
  - `llm.model_field` = `gpt-3.5-turbo`
  - `llm.read_timeout` = `120.0`
  - 失败样本：`cases[].error` 包含 `HTTPError: 400 ...`（但无 response body）

### A.2 服务端模型列表（用于验证真实 model id）
- 命令：`curl http://127.0.0.1:8000/v1/models`
- 观测（用户输出）：`data[].id` 包含 `qwen2.5-7b`、`qwen2.5-7b-instruct` 等

### A.3 修复实现（关键文件）
- `src/mhy_ai_rag_data/tools/llm_http_client.py`
  - 新增：结构化 `LLMHTTPError`（status_code/content_type/response_snippet）
  - 新增：`/models` 解析与 `resolve_model_id(...)`（auto 选择 + 落盘 selection_reason）

---

## 附录 B：决策与取舍

- **为何优先补齐“证据链”，而不是先调超时/换模型**：  
  [Inference] 在资源受限（本地推理慢）的条件下，每次运行成本高；优先补齐“失败时输出可裁决信息”能显著降低后续所有排障的边际成本，并避免把 400 误判为超时或误把 ctx 超限当作性能问题。

- **为何选择 `auto` 默认并偏好 `*-instruct`**：  
  [Inference] E2E 评测属于对话式 completion，`instruct/chat` 变体通常对指令遵循更稳定；同时 `auto` 能避免新环境下手工指定模型 id 的摩擦。若需要严格可比性，可在 HANDOFF 中固定 `--llm-model <id>` 作为基线口径。

---

## 附录 C：本项目专用契约与门禁

### C.1 Facts / Inference 写作契约
- **[Fact]** 必须可定位：文件路径 + 字段/行 + 可复现实验。
- **[Inference]** 必须给证伪方式：如何验证/反证。

### C.2 报告可观测性不变量（建议门禁化）
- E2E 失败时必须落盘：`error_detail.cause` 或 `error_detail.status_code`；若为 4xx/5xx，建议同时落盘 `response_snippet`（截断）。
- 任一失败若只剩“HTTPError 摘要”而无可裁决信息，视为回归系统缺陷（应修复而非继续猜测）。

### C.3 模型身份不变量（建议门禁化）
- `model_field/resolved_model` 必须来自 `GET /v1/models` 返回的 `data[].id`，或在 fallback 时明确记录失败原因与回退值。
- 报告必须记录模型解析过程（server_models/selection_reason/models_fetch_error），避免占位符造成误读。

### C.4 warning 过渡门禁（演进式收紧）
- 迁移期允许 warning（例如旧报告缺字段），但必须落盘并可统计。
- 当 warnings_ratio <= 1% 且 oral_cases >= 10 且 pair_id_coverage >= 5 时，将关键 warning 升级为 FAIL（逐条收紧）。
