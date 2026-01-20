---
title: verify_torch_cuda.py 使用说明
version: v1.0
last_updated: 2026-01-16
tool_id: verify_torch_cuda

impl:
  module: mhy_ai_rag_data.tools.verify_torch_cuda
  wrapper: tools/verify_torch_cuda.py

entrypoints:
  - python tools/verify_torch_cuda.py
  - python -m mhy_ai_rag_data.tools.verify_torch_cuda

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: other
---
# verify_torch_cuda.py 使用说明


> 目标：验证 PyTorch 的 CUDA 可用性，用于 GPU 加速环境检查。

## 快速开始

```cmd
python tools\verify_torch_cuda.py
```

## 功能

- 检查 `torch.cuda.is_available()`
- 显示 PyTorch 版本（包含 CUDA 版本后缀，如 `+cu118`）
- 列出可用 GPU 数量和设备名称

## 退出码

- `0`：PASS（CUDA 可用）
- `2`：FAIL（CUDA 不可用或未安装 PyTorch）

## 输出示例

**成功**：
```
torch.__version__=2.1.2+cu118
torch.cuda.is_available()=True
torch.cuda.device_count()=1
torch.cuda.get_device_name(0)='NVIDIA GeForce RTX 3090'
STATUS: PASS
```

**失败**：
```
torch.__version__=2.1.2+cpu
torch.cuda.is_available()=False
STATUS: FAIL (CUDA not available)
```

## 使用场景

- 环境配置验证（在运行 embedding/训练前）
- 排查 GPU 识别问题
- CI 中的硬件能力检测

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/verify_torch_cuda.py`。

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
_(no long flags detected by static AST)_
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
