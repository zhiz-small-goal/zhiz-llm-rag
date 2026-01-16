---
title: run_build_profile.py 使用说明（运行构建性能分析）
version: v1.0
last_updated: 2026-01-16
---

# run_build_profile.py 使用说明

> 目标：用 JSON profile 驱动 plan → build → check 的一致性执行，把"口径"从手工命令行升级为可复现的配置文件。

## 快速开始

```cmd
python tools\run_build_profile.py --profile build_profile_schemeB.json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--profile` | `build_profile_schemeB.json` | Profile JSON 路径 |
| `--build-script` | `tools/build_chroma_index_flagembedding.py` | 构建脚本 |
| `--force-extract-units` | `false` | 强制重新生成 text_units.jsonl |
| `--skip-build` | `false` | 跳过构建（调试用）|

## 退出码

- `0`：PASS
- `2`：FAIL

## 示例

```cmd
python tools\run_build_profile.py --profile build_profile_schemeB.json
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/run_build_profile.py`。
