---
title: 文档体系 SSOT（Level 3：WAL/断点续跑语义）
version: v1.0
last_updated: 2026-01-23
timezone: America/Los_Angeles
status: active
---

# 文档体系 SSOT（Level 3：WAL/断点续跑语义）

> 目的：把“WAL/断点续跑语义”相关文档的**裁决优先级、术语口径、引用边界**写成可执行约定，避免 README/howto/archive 之间互相矛盾。  
> 范围：仅覆盖 Chroma build（`build_chroma_index_flagembedding.py`）与其 state/WAL/锁/strict-sync 相关解释。

## 目录

- [1. 裁决优先级（出现冲突时以谁为准）](#1-裁决优先级出现冲突时以谁为准)
- [2. SSOT 清单（哪些文档是“定义”，哪些是“用法”）](#2-ssot-清单哪些文档是定义哪些是用法)
- [3. 术语口径（必须统一的关键词）](#3-术语口径必须统一的关键词)
- [4. 允许复制的内容与禁止复制的内容](#4-允许复制的内容与禁止复制的内容)
- [5. 历史文档（archive/postmortem）处理规则](#5-历史文档archivepostmortem处理规则)
- [6. 变更触发器（何时必须同步更新文档）](#6-变更触发器何时必须同步更新文档)

---

## 1. 裁决优先级（出现冲突时以谁为准）

当同一主题在不同文档出现不一致时，按以下顺序裁决：

1) **源码行为与 CLI 输出**（`python tools/build_chroma_index_flagembedding.py -h`、`--resume-status` 的字段与日志）  
2) **Reference 契约文档**（本目录 `docs/reference/` 中标注为 contract/SSOT 的文件）  
3) **howto/runbook/工具 README**（面向操作；必须引用 SSOT，不得自建口径）  
4) **archive/postmortem**（历史记录；只允许加 NOTE/跳转，不改写正文结论）

> 取舍理由：源码与 CLI 是运行事实；reference 用于固定解释与名词；其它文档只承载“入口与操作”。

---

## 2. SSOT 清单（哪些文档是“定义”，哪些是“用法”）

**定义（contract / SSOT）**：任何解释、字段含义、默认值以这些文档为准  
- `docs/reference/build_chroma_cli_and_logs.md`：CLI 参数/默认值/组合语义 + `--resume-status` 字段与关键日志解释（单一真相表）  
- `docs/reference/index_state_and_stamps.md`：`index_state.json`（success-only）与 `index_state.stage.jsonl`（WAL）以及 `writer.lock` 的文件语义与并发约束  
- `docs/reference/GLOSSARY_WAL_RESUME.md`：术语表（state/WAL/committed/attempted/run_id/schema_hash/resume_active 等）

**用法（guide / runbook）**：只描述“怎么做”，不得复制整张参数表  
- `docs/howto/OPERATION_GUIDE.md`：以 runbook 形式给出决策树，第一步必须是 `--resume-status`

**历史（archive/postmortem）**：只做跳转与语义差异提示  
- `docs/archive/*`、`docs/postmortems/*`

---

## 3. 术语口径（必须统一的关键词）

下列词汇在仓内所有入口必须同义使用（允许换行/中英混排，但语义不可变）：

- `index_state.json`：**完成态快照**，仅在成功完成后写入（success-only），缺失不代表“未写入任何数据”  
- `index_state.stage.jsonl`：**WAL/进度事件流**，append-only，用于中断恢复与审计  
- `policy=reset` / `--on-missing-state=reset`：当 `state` 缺失且 `collection.count>0` 时的**默认评估分支**；若 WAL 可续跑，最终决策可被 resume 覆盖（详见 CLI&日志真相表）  
- `writer lock exists`：单写入者互斥保护；常见原因是上次中断遗留锁文件  
- `strict-sync`：验收开关；`true` 时要求 build 后 `collection.count == expected_chunks`

---

## 4. 允许复制的内容与禁止复制的内容

**允许复制（可在 README/howto 展示）**
- 2–5 条“常用命令片段”（Windows CMD）
- 1 个最小故障定位流程：`--resume-status` → 依据字段选择动作
- 指向 SSOT 的链接（推荐以“单一真相表/术语表/契约”命名）

**禁止复制（必须引用 SSOT，不允许在多处维护）**
- 完整参数表（包含默认值、choices、互斥关系）
- `--resume-status` 全字段解释表
- `policy=reset` 与 resume 覆盖的规则细节（只能在 SSOT 表述一次）

---

## 5. 历史文档（archive/postmortem）处理规则

- 不改写历史正文（避免破坏时间线与复盘语境）
- 仅在顶部添加 NOTE：  
  1) 指向现行 SSOT（build_chroma_cli_and_logs / index_state_and_stamps / glossary）  
  2) 标注“本文可能使用旧名词/旧默认值”，并提示以 SSOT 为准

---

## 6. 变更触发器（何时必须同步更新文档）

出现以下任一变更时，必须同步更新 **SSOT 文档** 与 **OPERATION_GUIDE**：

- CLI 参数新增/删除/默认值改变（以源码为准）
- `--resume-status` 输出字段新增/改名
- WAL 事件类型、提交边界（committed）的定义改变
- 锁文件路径/行为改变（writer lock 语义变化）
- strict-sync 相关默认值或验收规则改变


## 7. 文档门禁（持续一致性）

为避免后续迭代把口径带歪，仓内提供最小门禁脚本（Report v2 输出）：

- 工具：`tools/check_doc_system_gate.py`
- 推荐（Windows CMD）：
```cmd
python tools\check_doc_system_gate.py --root . --doc-map docs\explanation\doc_map.json --out data_processed\build_reports\doc_system_gate_report.json --md-out data_processed\build_reports\doc_system_gate_report.md
```

门禁检查范围基于 Step1 的 `doc_map.json`，对 `reference/runbook/README` 更倾向给出 FAIL；对 `archive/postmortem` 更倾向给出 WARN（不阻塞主线但可见）。
