---
title: probe_llm_server.py 使用说明（探测 LLM 服务器可用性）
version: v1.0
last_updated: 2026-01-16
---

# probe_llm_server.py 使用说明


> 目标：快速探测 LLM HTTP 服务是否为 OpenAI-compatible 接口，验证端点可用性（base_url/端口/路径/最小 chat/completions），回答服务是否可达。

## 快速开始

```cmd
python tools\probe_llm_server.py ^
  --base http://localhost:8000\v1 ^
  --timeout 10 ^
  --json-out data_processed\build_reports\llm_probe.json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--base` | *(required)* | 基础 URL（如 `http://localhost:8000/v1`） |
| `--connect-timeout` | `5.0` | 连接超时秒 |
| `--timeout` | `10.0` | 读取超时秒 |
| `--trust-env` | `auto` | 是否信任环境代理（auto/true/false） |
| `--json-out` | *(空)* | JSON 报告输出路径 |
| `--json-stdout` | *(flag)* | 将 JSON 报告打印到 stdout |

## 退出码

- `0`：PASS（至少一个 POST 探测返回 HTTP 200）
- `2`：FAIL（所有 POST 探测失败）
- `3`：ERROR（脚本异常）

## 探测内容

### GET 探测
- `/`
- `/v1/models`
- `/models`
- `/docs`
- `/openapi.json`

### POST 探测
- `/v1/chat/completions`（chat format）
- `/chat/completions`
- `/v1/completions`（prompt format）

## 示例

### 1) 探测本地 LM Studio
```cmd
python tools\probe_llm_server.py --base http://localhost:8000\v1
```

### 2) 调大超时（慢速服务）
```cmd
python tools\probe_llm_server.py ^
  --base http://localhost:8000\v1 ^
  --connect-timeout 30 ^
  --timeout 60
```

### 3) 强制不走代理
```cmd
python tools\probe_llm_server.py ^
  --base http://127.0.0.1:8000\v1 ^
  --trust-env false
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/probe_llm_server.py`。
