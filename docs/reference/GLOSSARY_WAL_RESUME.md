---
title: 术语表（WAL/断点续跑/State）
version: v1.0
last_updated: 2026-01-23
timezone: America/Los_Angeles
status: active
---

# 术语表（WAL/断点续跑/State）

> 目的：为 build/续跑相关文档提供统一词汇表，避免“同一概念多叫法”导致误读。  
> 裁决：若与源码/CLI 输出不一致，以源码/CLI 为准，并在 `docs/reference/build_chroma_cli_and_logs.md` 修订。

## 目录

- [1. State / WAL / Stamps](#1-state--wal--stamps)
- [2. committed / attempted（提交边界）](#2-committed--attempted提交边界)
- [3. schema_hash / run_id](#3-schema_hash--run_id)
- [4. resume_mode / resume_active](#4-resume_mode--resume_active)
- [5. strict-sync / expected_chunks / collection.count](#5-strict-sync--expected_chunks--collectioncount)
- [6. writer.lock（单写入者互斥）](#6-writerlock单写入者互斥)

---

## 1. State / WAL / Stamps

- **State（index_state.json）**：成功完成后写入的完成态快照（success-only）。用于下次增量判断（added/changed/deleted）以及校验上次写入的语义输入（schema_hash、docs manifest）。  
- **WAL（index_state.stage.jsonl）**：append-only 的进度事件流，用于 build 中断后的恢复与审计；WAL 的存在不等价于“本次 build 已成功”。  
- **Stamps（db_build_stamp.json 等）**：用于记录“写库完成戳/来源参数指纹”，避免用目录 mtime 推断状态。

参考：`docs/reference/index_state_and_stamps.md`（文件语义与路径）与 `docs/reference/build_chroma_cli_and_logs.md`（CLI 行为）。

---

## 2. committed / attempted（提交边界）

- **attempted（尝试）**：进入处理路径但不保证写入成功的动作（例如开始 embed、开始 upsert）。  
- **committed（已提交）**：以“upsert 成功返回”为边界的可恢复完成态；WAL 中通常以 `DOC_COMMITTED` 或等价事件表达。  
- 目的：断点续跑时只跳过 committed 的 doc，避免“尝试过但未写入成功”被误判为已完成。

---

## 3. schema_hash / run_id

- **schema_hash**：当前构建口径的稳定指纹（chunk_conf + embedding_model + hnsw_space 等关键参数组合）。用于区分不同口径生成的 state/WAL 目录，防止交叉污染。  
- **run_id**：一次 build 运行的唯一标识；用于 WAL 审计与写入者锁的归属记录。

---

## 4. resume_mode / resume_active

- **resume_mode**：用户意图（`auto/off/force`）。  
- **resume_active**：实际生效决策（由 WAL 是否存在且未 finished_ok 等条件导出）。  
- 关键点：当 `resume_mode=auto` 且 WAL 表示可续跑时，build 会进入 resume；当 `resume_mode=off`，即便 WAL 存在也不使用。

---

## 5. strict-sync / expected_chunks / collection.count

- **expected_chunks**：本次输入（units）与 chunk_conf 计算出的应写入 chunk 数（验收期望）。  
- **collection.count**：Chroma collection 当前条目数。  
- **strict-sync=true**：build 完成后强一致验收：要求 `collection.count == expected_chunks`，否则以 FAIL 退出（用于阻止 silent drift）。

---

## 6. writer.lock（单写入者互斥）

- **writer.lock**：写入互斥保护文件，用于阻止同一 state_dir 上并发 build 导致 WAL/manifest 交叉污染。  
- 常见触发：上次 build 中断遗留锁文件；此时会出现 `writer lock exists` 相关 FATAL。  
- 推荐处置：先运行 `--resume-status` 读取状态，再依据 runbook 选择“继续续跑/人工清理锁/禁用 resume”等动作（详见 `docs/howto/OPERATION_GUIDE.md`）。
