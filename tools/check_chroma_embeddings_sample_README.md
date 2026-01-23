---
title: check_chroma_embeddings_sample.py 使用说明（检查 Chroma 嵌入向量质量）
version: v1.0
last_updated: 2026-01-23
tool_id: check_chroma_embeddings_sample

impl:
  module: mhy_ai_rag_data.tools.check_chroma_embeddings_sample
  wrapper: tools/check_chroma_embeddings_sample.py

entrypoints:
  - python tools/check_chroma_embeddings_sample.py
  - python -m mhy_ai_rag_data.tools.check_chroma_embeddings_sample

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
# check_chroma_embeddings_sample.py 使用说明

> 注意（2026-01-23）：`build_chroma_index_flagembedding` 已引入断点续跑 WAL（`index_state.stage.jsonl`）与 `--resume-status`。因此当出现“state 缺失但库非空”的场景时，`on-missing-state=reset` 可能会被 WAL 的 resume 分支覆盖（以避免清除已写入进度）。若你确实要全量重建，可用 `--resume off` 显式关闭续跑。


> 目标：抽样读取 Chroma collection 的 embeddings，检查维度一致性、L2 范数分布、是否存在 NaN/Inf，用于快速诊断向量质量问题。


## SSOT 与口径入口

- **文档体系 SSOT**：`docs/reference/DOC_SYSTEM_SSOT.md`
- **WAL/续跑术语表**：`docs/reference/GLOSSARY_WAL_RESUME.md`
- **build CLI/日志真相表**：`docs/reference/build_chroma_cli_and_logs.md`

> 约束：本文仅保留“怎么做/怎么排障”的最短路径；参数默认值与字段解释以真相表为准。

### 关于 `policy=reset` 的两阶段含义（默认评估 vs 最终生效）

当你看到类似 `index_state missing ... policy=reset` 的 WARN 时，它表达的是对 `--on-missing-state=reset` 的**默认评估**分支，并不等价于“已经执行 reset”。  
若同一轮启动还出现 `WAL indicates resumable progress; ignore on-missing-state=reset and continue with resume.`，则代表 WAL 判定可续跑，进入 resume 路径为**最终生效**决策，此时不会执行 reset（避免重复写入与无谓重置）。  
详见：`docs/reference/build_chroma_cli_and_logs.md` 的“关键日志与含义”。


## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [输出说明](#输出说明)
- [退出码](#退出码)
- [示例](#示例)
- [常见问题](#常见问题)

## 目的

本工具抽样检查 Chroma embeddings，用于：

- **维度一致性检查**：确认所有向量维度相同
- **归一化检查**：通过 L2 范数判断是否做了归一化（cosine 距离需要）
- **异常值检测**：检查是否存在 NaN/Inf

## 适用场景

- 构建索引后快速检查向量质量
- 排查检索结果异常（distance 值不合理）
- 验证 embedding 模型切换后向量维度是否正确
- 确认归一化是否生效

## 快速开始

```cmd
python tools\check_chroma_embeddings_sample.py --db chroma_db --collection rag_chunks --limit 50
```

期望输出：
```
db_path=f:\zhiz-c++\zhiz-llm-rag\chroma_db
collection=rag_chunks
sampled=50
dims_set=[1024]
norm2_min=0.999950
norm2_max=1.000050
norm2_mean=1.000000
STATUS: OK (dimension consistent)
near_unit_norm=50/50
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--collection` | `rag_chunks` | Collection 名称 |
| `--limit` | `50` | 抽样数量（数据集大时请设小） |

## 输出说明

### 核心指标

| 字段 | 含义 | 正常值 |
|---|---|---|
| `sampled` | 抽样数量 | 应等于 `--limit` |
| `dims_set` | 唯一维度集合 | 应只有1个值（如 `[1024]`） |
| `norm2_min/max/mean` | L2 范数最小/最大/平均值 | 归一化后应接近 1.0 |
| `near_unit_norm` | 范数接近 1 的向量数量 | 若使用 cosine，应等于 sampled |

### 状态判定

- `STATUS: OK (dimension consistent)`：维度一致，正常
- `STATUS: WARN (embedding dimension not consistent)`：维度不一致，**需要检查**
- `STATUS: WARN (no embeddings returned)`：collection 为空或后端禁用了 embeddings

## 退出码

- `0`：成功（无论结果如何，本工具只报告不阻断）

## 示例

### 1) 检查向量质量
```cmd
python tools\check_chroma_embeddings_sample.py --db chroma_db --collection rag_chunks
```

### 2) 增大抽样数量
```cmd
python tools\check_chroma_embeddings_sample.py --db chroma_db --collection rag_chunks --limit 200
```

### 3) 检查是否归一化
观察 `norm2_mean`：
- **接近 1.0**（如 0.999~1.001）：已归一化（适用于 cosine）
- **远离 1.0**（如 5.0~30.0）：未归一化（可能用 L2/IP 距离）

## 常见问题

### 1) `STATUS: WARN (no embeddings returned)`
**可能原因**：
- collection 为空
- Chroma 后端未配置返回 embeddings

**处理**：
```cmd
rem 检查 collection 是否为空
python tools\list_chroma_collections.py --db chroma_db --expect rag_chunks
```

### 2) dims_set 有多个值（如 `[768, 1024]`）
**原因**：collection 中混合了不同模型的 embeddings

**处理**：
- 确认是否在构建过程中切换了 embedding 模型
- 建议重置 collection 后重建：
  ```cmd
  python tools\reset_chroma_db.py --db chroma_db --collection rag_chunks
  ```

### 3) norm2_mean 远离 1.0，但我使用的是 cosine 距离
**原因**：build 脚本未做 L2 归一化

**处理**：
- 检查 `build_chroma_index_flagembedding.py` 是否调用了 `normalize_dense()`
- 或在构建时确保归一化逻辑生效

### 4) near_unit_norm 远小于 sampled
说明大部分向量未归一化，若使用 cosine 距离会导致结果不准确。

**建议**：重建索引并确保归一化。

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/check_chroma_embeddings_sample.py`。推荐使用 `python -m mhy_ai_rag_data.tools.check_chroma_embeddings_sample`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_chroma_embeddings_sample`
> entrypoints: `python tools/check_chroma_embeddings_sample.py`, `python -m mhy_ai_rag_data.tools.check_chroma_embeddings_sample`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--collection` | — | 'rag_chunks' | — |
| `--db` | — | 'chroma_db' | — |
| `--limit` | — | 50 | type=int |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
