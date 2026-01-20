---
title: verify_sentence_transformer_cuda.py 使用说明
version: v1.0
last_updated: 2026-01-16
tool_id: verify_sentence_transformer_cuda

impl:
  module: mhy_ai_rag_data.tools.verify_sentence_transformer_cuda
  wrapper: tools/verify_sentence_transformer_cuda.py

entrypoints:
  - python tools/verify_sentence_transformer_cuda.py
  - python -m mhy_ai_rag_data.tools.verify_sentence_transformer_cuda

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# verify_sentence_transformer_cuda.py 使用说明


> 目标：验证 sentence-transformers 库能否使用 CUDA 加速，用于 Stage-2 embedding 环境检查。

## 快速开始

```cmd
python tools\verify_sentence_transformer_cuda.py
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--model` | `BAAI/bge-m3` | Sentence Transformer 模型名称 |
| `--device` | `cuda:0` | 目标设备 |
| `--text` | `hello world` | 测试文本 |

## 功能

- 检查 `torch.cuda.is_available()`
- 尝试加载 sentence-transformers 并检测设备
- 输出 CUDA 版本和设备信息

## 退出码

- `0`：PASS（CUDA 可用）
- `2`：FAIL（CUDA 不可用或未安装 sentence-transformers）

## 输出示例

**成功**：
```
torch.cuda.is_available()=True
device=cuda
STATUS: PASS
```

**失败**：
```
torch.cuda.is_available()=False
STATUS: FAIL (CUDA not available)
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/verify_sentence_transformer_cuda.py`。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--device` | — | 'cuda:0' | — |
| `--model` | — | 'BAAI/bge-m3' | — |
| `--text` | — | 'hello world' | — |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
