[关键词] LM Studio, proxy hijack, 127.0.0.1:7890, ReadTimeout, requests trust_env, NO_PROXY, OpenAI-compatible, /v1/chat/completions
[阶段] answer / llm / stage2 eval
[工具] tools/llm_http_client.py, tools/run_eval_rag.py, tools/probe_llm_server.py, tools/verify_stage1_pipeline.py, llm_client_http.py
[复现] 访问 http://127.0.0.1:8000/v1 时，环境变量 ALL_PROXY/HTTP_PROXY 指向 127.0.0.1:7890，requests 默认 trust_env=True 导致请求走代理；出现 ReadTimeout(host='127.0.0.1', port=7890)
[验收]
1) curl http://127.0.0.1:8000/v1/models 返回 200 且含 model 列表
2) python -m tools.probe_llm_server --base http://127.0.0.1:8000/v1 --timeout 10 --trust-env auto 端点可达
3) python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --timeout 120 --trust-env auto 不再出现 port=7890；eval_rag_report.json 里 llm.error 不再是 7890 代理超时

# Postmortem: LLM 请求被环境代理劫持到 127.0.0.1:7890 导致 ReadTimeout（LM Studio）— 2025-12-28

## 现象（Symptoms）
- 报错典型形态：`ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=7890): Read timed out (read timeout=XX)`。
- LM Studio UI/日志里能看到“模型收到了请求并回复”，但 Python 端收不到或超时（因为请求实际未到 8000，而是被送往代理端口 7890）。

## 证据链（Facts）
- `curl http://127.0.0.1:8000/v1/models` 能返回，证明 **8000 端口服务是可达的**。（LM Studio OpenAI-compatible 端点） citeturn0search4
- `requests.Session` 默认会从环境变量读取代理（trust_env=True），若环境变量配置了 HTTP(S)_PROXY/ALL_PROXY，则会对请求生效。（requests 文档） citeturn0search0
- HTTPX 官方也明确：默认使用环境变量；需 `trust_env=False` 才能忽略环境变量代理。（HTTPX 文档） citeturn0search6

## 根因（Root Cause）
- **客户端默认信任环境代理** + **Windows 环境变量代理指向 127.0.0.1:7890**，导致访问本地回环地址时仍然走代理，从而出现“端口 7890 的 ReadTimeout”。

## 修复策略（Fix）
### 方案 B（长期推荐）：从管道层统一 LLM HTTP Client
- 新增 `tools/llm_http_client.py`：
  - trust_env_mode=auto：对回环地址（localhost/127.0.0.1/::1）默认 `trust_env=False`（不读环境代理）
  - 统一 `timeout=(connect_timeout, read_timeout)`，并把关键上下文写入异常字符串
- 全项目的 OpenAI-compatible 调用统一迁移到该模块，以消除“某个脚本忘记禁用代理”的漂移风险。

## 代码改动清单（Change List）
- 新增：
  - `tools/llm_http_client.py`
  - `tools/llm_http_client_README.md`
- 修改（由 requests 直连改为统一 client）：
  - `tools/run_eval_rag.py`
  - `tools/probe_llm_server.py`
  - `tools/verify_stage1_pipeline.py`
  - `llm_client_http.py`（影响 answer_cli）
  - `check_llm_http.py`（openai 探测路径改为可控 trust_env）

## 回归验证（Verification）
- 环境变量存在代理时（例如 ALL_PROXY=127.0.0.1:7890），用 `--trust-env auto/false` 运行上述脚本，确保不再出现 port=7890。
- 若确需访问“非回环地址且必须走代理”，用 `--trust-env true` 显式启用。

## 预防（Prevention）
- 将 “LLM HTTP 调用必须走 tools/llm_http_client” 作为工程约束写入开发指南/代码审查清单。
- Stage-1/Stage-2 的回归脚本默认输出 connect/read/trust_env 字段，便于定位网络侧问题。
