---
title: run_build_profile.py 使用说明（运行构建性能分析）
version: v1.0
last_updated: 2026-01-23
tool_id: run_build_profile

impl:
  module: mhy_ai_rag_data.tools.run_build_profile
  wrapper: tools/run_build_profile.py

entrypoints:
  - python tools/run_build_profile.py
  - python -m mhy_ai_rag_data.tools.run_build_profile

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
owner: "zhiz"
status: "active"
---
# run_build_profile.py 使用说明


## 目录

- [SSOT 与口径入口](#ssot-与口径入口)
  - [关于 `policy=reset` 的两阶段含义（默认评估 vs 最终生效）](#关于-policyreset-的两阶段含义默认评估-vs-最终生效)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [示例](#示例)
- [自动生成区块（AUTO）](#自动生成区块auto)

> 注意（2026-01-23）：`build_chroma_index_flagembedding` 已引入断点续跑 WAL（`index_state.stage.jsonl`）与 `--resume-status`。因此当出现“state 缺失但库非空”的场景时，`on-missing-state=reset` 可能会被 WAL 的 resume 分支覆盖（以避免清除已写入进度）。若你确实要全量重建，可用 `--resume off` 显式关闭续跑。


> 目标：用 JSON profile 驱动 plan → build → check 的一致性执行，把"口径"从手工命令行升级为可复现的配置文件。


## SSOT 与口径入口

- **文档体系 SSOT**：`docs/reference/DOC_SYSTEM_SSOT.md`
- **WAL/续跑术语表**：`docs/reference/GLOSSARY_WAL_RESUME.md`
- **build CLI/日志真相表**：`docs/reference/build_chroma_cli_and_logs.md`

> 约束：本文仅保留“怎么做/怎么排障”的最短路径；参数默认值与字段解释以真相表为准。

### 关于 `policy=reset` 的两阶段含义（默认评估 vs 最终生效）

当你看到类似 `index_state missing ... policy=reset` 的 WARN 时，它表达的是对 `--on-missing-state=reset` 的**默认评估**分支，并不等价于“已经执行 reset”。  
若同一轮启动还出现 `WAL indicates resumable progress; ignore on-missing-state=reset and continue with resume.`，则代表 WAL 判定可续跑，进入 resume 路径为**最终生效**决策，此时不会执行 reset（避免重复写入与无谓重置）。  
详见：`docs/reference/build_chroma_cli_and_logs.md` 的“关键日志与含义”。


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

## 自动生成区块（AUTO）
<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--build-script` | — | 'tools/build_chroma_index_flagembedding.py' | Which build script to call (recommended: tools/build_chroma_index_flagembedding.py). |
| `--force-extract-units` | — | 'false' | true/false; force re-generate text_units.jsonl even if it already exists |
| `--profile` | — | 'build_profile_schemeB.json' | Path to profile json |
| `--skip-build` | — | 'false' | true/false; for debugging |
<!-- AUTO:END options -->
<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->
<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->