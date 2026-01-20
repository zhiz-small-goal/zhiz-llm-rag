---
title: `run_eval_rag.py` 使用说明（Stage-2：端到端 RAG 回归 must_include 断言）
version: v1.0
last_updated: 2026-01-20
tool_id: run_eval_rag

impl:
  module: mhy_ai_rag_data.tools.run_eval_rag
  wrapper: tools/run_eval_rag.py

entrypoints:
  - python tools/run_eval_rag.py
  - python -m mhy_ai_rag_data.tools.run_eval_rag

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# `run_eval_rag.py` 使用说明（Stage-2：端到端 RAG 回归 must_include 断言）


> **适用日期**：2026-01-05  
> **脚本位置建议**：`tools/run_eval_rag.py`  
> **输出位置**：默认写入 `data_processed/build_reports/eval_rag_report.json`

---

## 1. 目的与适用场景

该脚本在“检索 + 上下文拼接 + LLM 调用”的完整链路上做轻量回归，并用 `must_include` 作为最小断言，避免完全主观评判。

你用它来回答：

- 端到端链路是否稳定可用（LLM 调用是否成功、是否输出内容）
- 在检索命中不变的情况下，答案是否满足基本关键要点（must_include）

---

## 2. 依赖与前置条件

必需：
- `chromadb`：检索 topK
- `requests`：调用 OpenAI-compatible 端点
- 可选 embedding：`FlagEmbedding` 或 `sentence_transformers`（与检索侧一致）

你需要：
- 用例集：`data_processed/eval/eval_cases.jsonl`
- 启动 LLM 服务（例如 LM Studio）：base URL 形如 `http://localhost:8000/v1`

---

## 3. 快速开始

```bash
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --k 5 --embed-model BAAI/bge-m3
```

---

## 4. 参数详解

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--db` | `chroma_db` | Chroma 落盘目录 |
| `--collection` | `rag_chunks` | collection 名 |
| `--cases` | `data_processed/eval/eval_cases.jsonl` | 用例集 |
| `--k` | `5` | topK |
| `--meta-field` | `source_uri|source|path|file` | 来源字段候选 |
| `--embed-backend` | `auto` | embedding 后端 |
| `--embed-model` | `BAAI/bge-m3` | embedding 模型 |
| `--device` | `cpu` | embedding 设备 |
| `--base-url` | `http://localhost:8000/v1` | LLM base url |
| `--timeout` | `30` | HTTP timeout 秒 |
| `--llm-model` | `auto` | model id（默认 auto：GET `/v1/models` 并优先选择 instruct/chat） |
| `--context-max-chars` | `12000` | 发送给 LLM 的上下文最大字符数 |
| `--max-tokens` | `256` | 生成 token 上限 |
| `--temperature` | `0.0` | 生成温度 |
| `--stream-out` | *(empty)* | 可选：实时事件流输出路径（JSONL/json-seq），用于长任务观测 |
| `--stream-format` | `jsonl` | `jsonl`（推荐）或 `json-seq`（RFC 7464） |
| `--progress-every-seconds` | `10` | 控制台进度摘要节流输出；0 表示关闭 |
| `--stream-answer-chars` | `0` | 若 >0，则在 stream 的 case 记录中写入截断答案片段（便于实时定位） |
| `--out` | `data_processed/build_reports/eval_rag_report.json` | 输出报告 |

---

## 5. 判定规则（最小断言）

每条 case 的通过条件：

1) LLM 调用成功（HTTP 2xx，并能解析出 `choices[0].message.content`）
2) `must_include` 中的每个关键词/短语都出现在 answer 中

> 这是“最小可操作门禁”，并不等价于事实正确性校验；若你需要更严格的事实一致性，可在后续阶段引入引用标注/结构化回答/更细评分。

---

## 6. 上下文拼接策略（可追溯）

脚本会把 topK 文档按 rank 拼接成 context，并在每段前加入来源标识：

```
[1] source=...
<doc text>

[2] source=...
<doc text>
```

超过 `context-max-chars` 会截断，避免发送过长导致延迟/超时。

---

## 7. 输出报告说明

**报告格式**: `schema_version=2`（v2 契约）

v2 契约特性：
- `schema_version`: `2` (int, 非字符串)
- `summary`: 自动计算的聚合统计（overall_status_label, overall_rc, counts 等）
- `items`: 标准 item 模型数组（每个 case 转为一个 item，含 severity_level）
- `data`: 向后兼容，保留原始 cases/metrics 数据

核心字段（v2 顶层）：
- `summary.overall_status_label`: 整体状态（PASS/FAIL/ERROR）
- `summary.overall_rc`: 推荐退出码（0=PASS, 2=FAIL, 3=ERROR）
- `summary.counts`: 各状态计数（PASS/FAIL/ERROR/INFO）
- `items[]`: 每条用例转换为标准 item（含 severity_level 用于排序）

原始数据（v2 中的 data 块）：
- `data.metrics.pass_rate`：通过率
- `data.cases[]`：每条用例包含：
  - `passed`、`llm_call_ok`
  - `missing`：缺失的 must_include
  - `context_chars`：实际发送给 LLM 的上下文字符数（用于定位是否因上下文过长导致 400）
  - `topk`：rank/source/distance
  - `answer`：模型输出（用于审计与定位）
  - `error_detail`：当 LLM 调用失败且为 HTTP 4xx/5xx 时，会尽量落盘服务端响应摘要：
    `status_code/content_type/response_snippet`（正文截断），用于快速裁决“是超时还是请求被拒绝”。

**相关文档**: [报告输出契约与工程规则（SSOT）](../docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md) - schema_version=2 完整规范

---

## 8. 常见故障排查

1) `timeout` 或 502  
处理：增大 `--timeout`，降低 `--max-tokens`，确认 LM Studio 已加载完成模型。

1.5) `HTTP 400 Bad Request`（但不是 ReadTimeout）
处理：优先查看报告中该 case 的 `error_detail.response_snippet`，通常会直接写明原因（例如 model 不存在、上下文超限等）；
若提示上下文超限，先降低 `--context-max-chars` / `--k` / `--max-tokens`。

2) `must_include` 大量缺失，但检索 hit 稳定  
处理：增大 `--context-max-chars` 或 `--k`，或调整系统 prompt 约束，让模型更贴合“严格基于上下文”。

3) 本地服务对 `model` 字段敏感  
处理：默认 `--llm-model auto` 会自动 GET `/models` 并优先选择包含 `instruct/chat` 的 id；如需固定则显式传入该 id（可先 `curl http://127.0.0.1:8000/v1/models` 查询）。

## 代理与超时（重要）
- 新增参数：
  - `--connect-timeout`：连接超时（默认 10）
  - `--timeout`：读取超时（默认 30；建议评测 120~180）
  - `--trust-env`：是否信任环境代理（auto/true/false）。默认 auto：回环地址自动不走代理，避免 127.0.0.1:7890 劫持。

示例：
```bash
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --connect-timeout 10 --timeout 120 --trust-env auto
```


## 模型字段（重要）
- 报告 `llm.model_arg`：你传入的参数值（可能是 `auto`）
- 报告 `llm.model_field`：本次实际发送到服务端请求体里的 model id（已解析）
- 报告 `llm.model_resolve`：自动解析过程（server_models 列表、选择原因、失败时的 fallback/error 取证）


---

## 9. 实时观测（stream/progress）

长任务（尤其是 LLM 调用）如果只在结束后一次性写出 JSON 报告，反馈环路会被拉长。
脚本新增了可选的旁路输出：

- `--stream-out`：实时事件流文件（推荐 `.events.jsonl`）
- `--progress-every-seconds`：控制台聚合摘要（节流输出）

示例：

```bash
python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --k 5 --base-url http://127.0.0.1:8000/v1 --out data_processed/build_reports/eval_rag_report.json --stream-out data_processed/build_reports/eval_rag_report.events.jsonl --stream-format jsonl --progress-every-seconds 5 --stream-answer-chars 200
```

Windows PowerShell 观测（实时刷新）：

```powershell
Get-Content -Wait data_processed\build_reports\eval_rag_report.events.jsonl
```

注意：最终门禁/统计仍以 `eval_rag_report.json` 为准；stream 仅用于实时观测与调试。
