[关键词] LM Studio, read timeout=120, requests timeout, OpenAI-compatible, /v1/chat/completions, long generation

[阶段] answer / llm

[工具] tools/probe_llm_server.py, check_llm_http.py, llm_client_http.py, answer_cli.py

[复现] python answer_cli.py --q "存档导入与导出怎么做" --k 5（历史上触发 read timeout=120 的典型用例）

[验收]
1) python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed/build_reports/llm_probe.json
2) python answer_cli.py --q "存档导入与导出怎么做" --k 5（无超时；或 read timeout 已按本文方案调整）



# Postmortem: RAG 闭环问答阶段 LLM Read Timeout（LM Studio）— 2025-12-27

## 摘要
在本地 RAG 闭环（Chroma 检索 + 拼接上下文 + LLM 生成）流程中，`answer_cli.py` 在调用本机 LM Studio 的 OpenAI-compatible HTTP 服务时，出现 `Read timed out (read timeout=120)` 导致问答失败。最终定位为客户端 `requests.post(..., timeout=120)` 的读超时阈值过小；通过将超时改为 `timeout=(10, 600)`（连接/读取分离）后问题解除，并在 `k=2`、`k=5` 场景下验证稳定性。

---

## 影响范围（Impact）
- 影响命令：`python answer_cli.py --q "<问题>" [--k N]`
- 影响程度：LLM 调用阶段直接失败（检索与向量库本身正常），导致闭环不可用。
- 触发条件：上下文较长（例如 `k=5`）、模型首 token 延迟较高或生成较慢时更易触发。

---

## 现象与错误特征（Symptoms）
- 典型报错（stdout/exception）：
  - `[LLM ERROR] LLM request failed: HTTPConnectionPool(host='localhost', port=8000): Read timed out. (read timeout=120)`
- 关键观察：
  - `retriever_chroma.py` 可正常返回 top-k 命中，说明向量库与检索链路 OK。
  - 将 `k` 从 5 降到 2 后，LLM 返回概率显著提高，提示问题与“上下文规模/生成耗时”相关。

---

## 排查过程（Timeline / Diagnosis）
### 1) 验证检索链路是否正确
- 命令：
  - `python retriever_chroma.py --q "存档导入与导出怎么做" --k 5`
- 结果：
  - top-k 命中目标教程文档 `data_raw/教程/05_1.4存档导入与导出.md`，说明向量召回正常。

### 2) 误用 /health 端点后，确认不是服务不可达
- 尝试：
  - `curl -s -m 10 http://localhost:8000/health`
- 返回：
  - `{"error":"Unexpected endpoint or method. (GET /health)"}`
- 结论：
  - 这不代表服务故障，仅代表服务未实现 `/health`（常见）。

### 3) 用端点探测工具确认 LM Studio OpenAI-compatible 服务端点可用
- 工具：`tools/probe_llm_server.py`
- 命令：
  - `python -m tools.probe_llm_server --base http://localhost:8000 --timeout 10`
  - `python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10`
- 结果：
  - `GET /v1/models`、`POST /v1/chat/completions` 等均返回 200，且耗时 ~2–3s。
- 结论：
  - 服务端与端点均正常；问题集中在“特定请求耗时超过客户端 read timeout”。

### 4) 缩小搜索范围定位客户端超时写死位置
- 关键线索：
  - `answer_cli.py` 并不直接发 HTTP 请求，而是调用 `llm_client_http.call_llm()`：
    - `from llm_client_http import call_llm, LLMError`
- 定位命令：
  - `findstr /s /n /i "requests.post timeout=120" *.py`
- 命中位置：
  - `llm_client_http.py:37: resp = requests.post(url, headers=headers, json=payload, timeout=120)`
- 根因结论（Root Cause）：
  - 客户端 `requests` 的读超时阈值固定为 120 秒；当上下文较长或生成较慢时，LM Studio 无法在 120 秒内返回完整响应，触发读超时异常。

---

## 解决方案（Resolution）
### 方案：连接/读取分离并提高 read timeout
- 修改文件：`llm_client_http.py`
- 变更：
  - 将：
    - `requests.post(..., timeout=120)`
  - 改为：
    - `requests.post(..., timeout=(10, 600))`
  - 说明：`timeout=(connect_seconds, read_seconds)`，将连接阶段保持快速失败，同时允许生成阶段更长等待。

---

## 验证（Verification）
1) 端点探测（确保服务端可用）：
- `python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10`

2) 闭环问答验证（覆盖 k=2 与 k=5）：
- `python answer_cli.py --q "存档导入与导出怎么做" --k 2`
- `python answer_cli.py --q "存档导入与导出怎么做" --k 5`

3) 生效判据：
- 若仍失败，应观察异常文本中 `read timeout=` 数值：
  - 仍为 120：说明未命中实际请求点（可能运行了另一份模块/目录）。
  - 变为 600：说明超时改动生效，但推理仍过慢（需要进入“上下文控制/性能优化”阶段）。

---

## 使用到的工具与用法（Tooling）
### A) LLM 端点探测：`tools/probe_llm_server.py`
用途：快速判断服务是否 OpenAI-compatible、支持哪些端点、最小请求是否可返回。
- `python -m tools.probe_llm_server --base http://localhost:8000 --timeout 10`
- `python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10`
输出：控制台每个端点的状态码与耗时，并写 `llm_probe_report_*.json`。

### B) Windows 定位命令：`findstr`
用途：在不引入大量噪声的情况下定位真实请求点。
- 先从调用链缩小范围（优先单文件）：
  - `findstr /n /i "llm_client_http call_llm" answer_cli.py`
- 再定位实际请求点：
  - `findstr /s /n /i "requests.post timeout=" *.py`

---

## 预防措施（Preventive Actions / Next）
1) 将超时参数配置化（建议环境变量）：
- 例如：
  - `RAG_HTTP_CONNECT_TIMEOUT=10`
  - `RAG_HTTP_READ_TIMEOUT=600`
- 避免把个人机器的阈值写死在仓库代码中。

2) 上下文规模控制（减少“长上下文导致慢/超时”的概率）：
- 同 doc 去重/配额：同一 `doc_id` 最多取前 N 个 chunk。
- 每 chunk 限长：截断图片链接等低信息密度内容。

3) 基础落盘与回归评估（用于后续调参对比）：
- 建议引入：
  - `tools/<run_answer_with_report>.py`（问答 stdout + 耗时落盘 JSON）
  - `tools/<run_rag_eval_batch.py>`（回归集批跑）
- 目标：让“k 调整/过滤/rerank/截断”有可比对证据，而不是靠终端滚屏印象。

---

## 变更清单（Change List）
- [x] `llm_client_http.py`：调整 `requests.post` 的超时策略（120 -> (10,600)）
- [ ]（建议）将 timeout 参数做成可配置（env 或 config）
- [ ]（建议）加入最小落盘与回归评估脚本（见下一步计划）
