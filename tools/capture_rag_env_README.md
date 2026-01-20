---
title: capture_rag_env.py 使用说明（捕获 RAG 环境信息报告）
version: v1.0
last_updated: 2026-01-16
tool_id: capture_rag_env

impl:
  module: mhy_ai_rag_data.tools.capture_rag_env
  wrapper: tools/capture_rag_env.py

entrypoints:
  - python tools/capture_rag_env.py
  - python -m mhy_ai_rag_data.tools.capture_rag_env

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# capture_rag_env.py 使用说明


> 目标：抓取开发机/模型机的关键运行环境信息（Python版本、依赖、CUDA可用性等），生成可回溯报告，辅助排查环境不一致、版本冲突、GPU 不可用等问题。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [输出报告说明](#输出报告说明)
- [退出码](#退出码)
- [示例](#示例)
- [常见问题](#常见问题)

## 目的

本工具生成环境诊断报告，用于：

- **环境对齐**：对比两台机器（开发机 vs 模型机）的 Python/依赖版本
- **问题复现**：在 issue/日志中附上完整环境快照
- **排查 CUDA/torch 问题**：确认 GPU 是否可用、CUDA 版本是否匹配
- **依赖审计**：记录关键包（chromadb/FlagEmbedding/torch 等）的精确版本

## 适用场景

- 提交 bug汇报前，附上环境报告
- 双机同步后验证依赖版本一致性
- 排查 "在开发机正常，在模型机报错" 的问题
- 定期审计生产环境依赖版本

## 快速开始

```cmd
python tools\capture_rag_env.py --out data_processed\env_report.json
```

报告将写入 `data_processed/env_report.json`，可直接查看或附在 issue 中。

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--out` | `data_processed/env_report.json` | 输出报告路径 |

## 输出报告说明

报告为 JSON 格式，包含以下字段：

### 核心字段
```json
{
  "generated_at": "2026-01-16T00:00:00Z",
  "python": {
    "version": "3.11.5 (main, ...",
    "executable": "/path/to/python"
  },
  "platform": {
    "system": "Windows",
    "release": "10",
    "machine": "AMD64"
  },
  "env": {
    "VIRTUAL_ENV": "/path/to/venv",
    "CUDA_VISIBLE_DEVICES": null
  },
  "packages": {
    "chromadb": {
      "Name": "chromadb",
      "Version": "0.4.22"
    },
    "FlagEmbedding": {
      "Name": "FlagEmbedding",
      "Version": "1.2.10"
    }
  },
  "pip_freeze": [
    "chromadb==0.4.22",
    "FlagEmbedding==1.2.10",
    "..."
  ],
  "torch": {
    "__version__": "2.1.2+cu118",
    "cuda_is_available": true,
    "cuda_version": "11.8",
    "gpu_count": 1,
    "gpu_names": ["NVIDIA GeForce RTX 3090"]
  }
}
```

### 关键包（KEY_PACKAGES）
自动抓取以下包的版本信息：
- `chromadb`
- `FlagEmbedding`
- `sentence-transformers`
- `torch`
- `transformers`
- `huggingface-hub`
- `numpy`
- `pandas`

### torch 详细信息
如果安装了 torch，报告包含：
- CUDA 是否可用
- CUDA 版本
- cuDNN 版本
- GPU 数量与名称

## 退出码

- `0`：PASS（报告成功生成）

本工具仅生成报告，不做校验，因此始终返回 0。

## 示例

### 1) 生成环境报告
```cmd
python tools\capture_rag_env.py
```

输出：
```
Wrote: f:\zhiz-c++\zhiz-llm-rag\data_processed\env_report.json
```

### 2) 自定义输出路径
```cmd
python tools\capture_rag_env.py --out build_reports\机器A_env_report.json
```

### 3) 对比两台机器的环境
```bash
# 开发机
python tools/capture_rag_env.py --out env_dev.json

# 模型机（同步后）
python tools\capture_rag_env.py --out env_model.json

# 手动对比或用 jq/diff 工具
diff <(jq -S . env_dev.json) <(jq -S . env_model.json)
```

## 常见问题

### 1) torch 字段为 `{"error": "..."}`
**原因**：torch 未安装或 import 失败

**处理**：
```bash
pip install torch rem 或参考 PyTorch 官方安装指引
```

### 2) 想排查版本冲突，但 pip_freeze 太长
可用 `jq` 提取关键包：
```bash
jq '.packages' data_processed/env_report.json
```

### 3) GPU 明明存在，但 `cuda_is_available` 为 false
可能原因：
- CUDA 驱动版本不匹配
- torch 安装的是 CPU 版本（无 `+cu118` 后缀）

检查：
```python
import torch
print(torch.__version__)  # 确认是否包含 +cu118/cu121 等
print(torch.cuda.is_available())
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/capture_rag_env.py`。推荐使用 console script 或 `python -m mhy_ai_rag_data.tools.capture_rag_env`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `capture_rag_env`
> entrypoints: `python tools/capture_rag_env.py`, `python -m mhy_ai_rag_data.tools.capture_rag_env`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--out` | — | 'data_processed/env_report.json' | — |
| `--root` | — | '.' | repo root |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
