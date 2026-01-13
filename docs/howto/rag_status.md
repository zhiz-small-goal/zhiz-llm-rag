---
title: rag-status 使用说明
version: v1.0
last_updated: 2026-01-13
---

# rag-status 使用说明


- [目标](#目标)
- [相关文档（权威定义与可执行主线）](#相关文档权威定义与可执行主线)
- [输出字段快速理解](#输出字段快速理解)
- [STALE 的判定规则](#stale-的判定规则)
- [db_build_stampjson](#db_build_stampjson)
- [常见问题](#常见问题)

## 目标
`rag-status` 用于**只读扫描**本地 RAG 管线的关键产物（inventory / units / plan / Chroma DB / reports / index_state），并给出：
1) 当前每个产物的 OK/MISS/STALE/FAIL 状态；
2) 下一步建议（NEXT/WHY/CMDS）。

该命令默认不作为门禁（INFO 级别），但可以作为“我现在该跑哪一步”的稳定导航。

## 相关文档（权威定义与可执行主线）
- 日常操作主线（什么时候该跑哪一步、验收口径）：[`OPERATION_GUIDE.md`](OPERATION_GUIDE.md)
- 一键验收入口（核心序列 + 可选评测）：[`rag-accept 使用说明`](rag_accept.md)
- 产物契约（stamp/index_state 的位置、字段、更新规则）：[`../reference/index_state_and_stamps.md`](../reference/index_state_and_stamps.md)
- 排障分流（看到 STALE/FAIL 时怎么做最小动作）：[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

## 输出字段快速理解
- **OK**：文件存在且不需要更新（或虽为旧文件但不影响当前依赖关系）。
- **MISS**：缺失，需要生成。
- **FAIL**：存在但无法解析，或报告显示 FAIL/ERROR。
- **STALE**：存在且可解析，但**上游输入更新**了，需要重跑以确保一致性。

## STALE 的判定规则
`rag-status` 的 STALE 是“工程依赖”意义上的：
- 对于大多数产物：如果其任一 `inputs` 的 mtime **晚于**该产物（或其“freshness basis”），则判定为 STALE。
- 对于 `dir`（例如 Chroma DB 目录）：默认使用目录内“最新 mtime”的文件作为该目录的 mtime。

问题：在 Windows 上，SQLite/Chroma 在**仅查询（read）**时也可能触发 WAL/元数据写入，导致 DB 目录 mtime 变化，进而让 `check.json` 被误判为 STALE。

因此本仓库引入 `db_build_stamp.json` 作为 DB 的稳定 freshness basis（见下文）。

## db_build_stamp.json
### 为什么需要它
- **事实**：Windows + SQLite/Chroma 可能在查询时更新 DB 目录/文件 mtime；
- **后果**：`check.json` 可能在你跑了 `eval_rag.py`/检索回归之后，被 `rag-status` 提示为 STALE（尽管 check 本身仍然 PASS）。

### 它解决什么
`db_build_stamp.json` 是一个“构建戳”文件：
- 仅在 build/upsert/sync 等“写库”步骤成功后更新；
- query/eval/retriever 等“读库”步骤不会触碰它。

`rag-status` 的两处判定会优先使用该戳：
- **DB 是否 STALE**：用 `plan.mtime` 对比 `db_build_stamp.json.mtime`；
- **check.json 是否 STALE**：用 `db_build_stamp.json.mtime`（而不是 DB 目录 mtime）作为“DB 变化”的信号。

### 如何生成
- 新版本 build 脚本成功后会**自动写入**：`data_processed/index_state/db_build_stamp.json`。
- 如果你的库是在旧版本脚本下构建的（没有该文件），只需手动补一次：

```cmd
rag-stamp --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json

:: 没有重新安装 entrypoint 时，用 python 直跑
python tools\write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json
```

补戳之后，建议再跑一次 check 生成新的 `check.json`：

```cmd
rag-check --json-out data_processed\build_reports\check.json
```

## 常见问题
### 1) 我刚跑完 `rag-check`，但一跑检索回归就提示 check.json STALE
优先检查是否存在 `data_processed/index_state/db_build_stamp.json`。
- 若缺失：按上文先 `rag-stamp` 补戳，再重跑一次 `rag-check --json-out data_processed\\build_reports\\check.json`。
- 若存在：确认 `check.json.mtime` 晚于 `db_build_stamp.json.mtime`（否则就是正常 STALE，需要重跑 check）。
