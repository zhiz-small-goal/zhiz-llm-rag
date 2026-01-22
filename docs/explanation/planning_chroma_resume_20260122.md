---
title: "Chroma 索引断点续跑（方案 B）推进计划"
version: "v0.3"
last_updated: "2026-01-22"
timezone: "America/Los_Angeles"
owner: "zhiz"
status: "draft"
---

# Chroma 索引断点续跑（方案 B）推进计划

> 目标：中断后再次运行时，不重复处理已确认完成写入的文档；仅处理剩余部分；并支持“写入多少、进度记录就同步在”的可核验进度日志。  
> 适用范围：`tools/build_chroma_index_flagembedding.py build` 及其生成的 `index_state.json` / `index_state.stage.jsonl`。  
> 约定：对外“完成态口径”以 `index_state.json` 为准；`index_state.stage.jsonl` 用作构建过程旁路 **进度/WAL**（用于恢复与审计），成功结束后可清理或归档。  

## 目录
- [结论](#结论)
- [假设](#假设)
- [进度记录](#进度记录)
- [1) 详细指导](#1-详细指导)
  - [Step1（已完成）— 引入进度/WAL 的基础事件流并实现 doc 级续跑](#step1已完成—-引入进度wal-的基础事件流并实现-doc-级续跑)
  - [Step2 — 将进度/WAL 升级为“写入多少、记录就同步在”](#step2-—-将进度wal-升级为写入多少记录就同步在)
  - [Step3 — changed/deleted 的可重入顺序与幂等](#step3-—-changeddeleted-的可重入顺序与幂等)
  - [Step4 — 一致性校验与故障可复盘](#step4-—-一致性校验与故障可复盘)
  - [Step5 — 测试矩阵与回归（含中断注入）](#step5-—-测试矩阵与回归含中断注入)
  - [Step6（可选）— 警告收敛与门禁策略固化](#step6可选—-警告收敛与门禁策略固化)
- [自检](#自检)
- [失败模式与缓解](#失败模式与缓解)
- [MRE](#mre)
- [替代方案](#替代方案)
- [引用与依据](#引用与依据)

## 结论
采用“`index_state.stage.jsonl` 作为 append-only 进度/WAL + 以已提交事件为依据做恢复决策”的方案，可实现：  
1) 中断后续跑跳过已完成文档；  
2) 以 flush/upsert 成功返回为边界，持续落盘“已提交写入计数”，达到“写入多少、记录就同步在”；  
3) 在 changed/deleted 场景通过阶段事件序列与恢复规则降低误删概率；  
4) 将失败原因与建议动作做成可核验输出，降低排障成本。  

## 假设
1. **默认假设：单写入者**。同一 `db_path + collection + schema_hash` 同时只有一个 writer 进程；若无法保证，需要显式加锁或用 `run_id` 协议拒绝并发写入。  
2. **默认假设：提交边界可观察**。`collection.upsert(...)` 成功返回后可视为“本批写入已被 Chroma 接受”；进度/WAL 事件必须在此之后写入，且写入事件采用追加写 + flush +（可选）fsync。  
3. **默认假设：续跑只在严格匹配时启用**。仅当 `db_path + collection + schema_hash` 完全一致且 collection 非空时才使用 stage/WAL 的跳过集合；否则降级为不续跑，并输出原因。  
4. **默认假设：Windows CMD 为主**。本文命令默认以 Windows CMD 为准；若你在 WSL/Linux 运行，需要自行替换路径分隔符与删除命令。  

## 进度记录
> 记录格式：日期 / Step / 状态 / 产出（补丁包或仓库路径）/ 备注  
> 状态枚举：`DONE` / `IN_PROGRESS` / `TODO` / `BLOCKED`

| 日期 | Step | 状态 | 产出 | 备注 |
|---|---:|---|---|---|
| 2026-01-22 | 1 | DONE | `build-chroma-resume-stage-step1.zip` | 基础续跑已落地：doc 级 DONE 事件 + 避免误 reset |
| 2026-01-22 | 2 | DONE | 代码 + 文档 | WAL 追加 `UPSERT_BATCH_COMMITTED`/`DOC_COMMITTED` 事件、stage 复用 resume 统计、stage-fsync 支持 off/doc/interval，以及尾部截断容错。 |
| 2026-01-22 | 3 | DONE | 代码 + 文档 | 变更/删除文档会产生命名事件并触发恢复逻辑：`DOC_BEGIN`/`DELETE_OLD_DONE`/`UPSERT_NEW_DONE`/`DOC_COMMITTED`/`DOC_DONE` + `DELETE_STALE_DONE`，resume 时根据这些事件跳过重复删除/写入。 |
| 2026-01-22 | 4 | DONE | 代码 + 文档 | strict mismatch 现带 reason/delta 并写入 RUN_FINISH；新增 `--resume-status` 只读输出 WAL 综述，RUN_FINISH 成功/失败都保留 WAL。 |
| 2026-01-22 | 5 | DONE | 基础测试 | 新增 WAL/stage 解析与 resume-status 无副作用输出的单测，覆盖尾部截断容错与 doc 事件采样。 |
| 2026-01-22 | 6 | TODO | （可选） | WARN 分类治理与门禁策略 |

## 1) 详细指导

### Step1（已完成）— 引入进度/WAL 的基础事件流并实现 doc 级续跑
【做什么】引入 `index_state.stage.jsonl`（append-only），记录 `RUN_START/RUN_RESUME/DOC_DONE/RUN_FINISH` 事件；重启时基于 `content_sha256` 构造 `done_docs` 集合并跳过已完成文档；同时在“缺 state 但 collection 非空”与“schema-change reset”路径上优先使用 stage/WAL，避免误 reset。  
【为何】`index_state.json` 采用原子写并仅在成功结束写出，中断时缺乏可持久化的“已完成集合”；引入旁路进度/WAL 可以把“已完成”的证据在构建过程中持续落盘，从而支持中断恢复与审计。  
【关键参数/注意】续跑仅在 `db_path + collection + schema_hash` 严格匹配且 collection 非空时启用；失败或 strict mismatch 时保留 WAL 以便复盘与再次续跑；成功结束后 best-effort 清理 WAL（仅清理旁路文件，不改变完成态 state 的语义）。  

---

### Step2 — 将进度/WAL 升级为“写入多少、记录就同步在” [CON]
【做什么】在现有 `index_state.stage.jsonl` 事件流基础上新增两类“提交计数”事件，并明确它们的写入边界与恢复使用方式：  
1) **`UPSERT_BATCH_COMMITTED`**：每次 `flush()` 内 `collection.upsert(...)` 成功返回后立即追加写入，包含：`batch_size`、`chunks_upserted_total`、（可选）`collection_count_snapshot`、`ts/run_id/seq`。  
2) **`DOC_COMMITTED`**：当某 `source_uri` 的全部 chunks 已被 flush/upsert 并确认完成后追加写入，包含：`source_uri/doc_id/content_sha256/n_chunks` 与 `chunks_upserted_total`。  
同时把写盘策略参数化：将 `--stage-fsync` 扩展为 `off/doc/interval`（或等价参数），并把 WAL 读取容错固化：尾部截断时忽略最后坏行继续重放。  
【为何】用户希望“写入多少条、记录就同步在”，这要求进度记录必须与“真实写入提交点”绑定，而脚本里唯一集中提交写入的点是 `flush()->collection.upsert(...)`；在 upsert 成功后立即写入 `UPSERT_BATCH_COMMITTED`，即可让 WAL 在中断后仍能反映已提交写入数量，并为恢复提供证据。doc 级 `DOC_COMMITTED` 则用于“跳过已完成 doc”，降低重复 embedding。  
【关键参数/注意】  
- **事件顺序约束**：任何 `*_COMMITTED` 必须发生在 upsert 成功之后；否则会出现 WAL 领先 DB 的不可核验窗口。  
- **写盘语义**：推荐 WAL 使用 “append → file.flush →（可选）os.fsync” 的最小实现；`doc` 模式每条都 fsync，`interval` 模式按 N 条或 T 秒 fsync（需要在日志中输出当前策略与计数，便于复盘）。  
- **兼容与演进**：为 WAL 加 `wal_version`（或沿用 `stage_version`）；不兼容时降级为不续跑，并给出建议动作（例如清理 WAL 或 reset）。  
- **恢复使用**：恢复时 `DOC_COMMITTED` 决定跳过集合；`UPSERT_BATCH_COMMITTED` 用于核验“已提交写入计数是否连续增长”，并辅助判断异常停机窗口。  

**验收（可核验输出）**：  
- 启动时 stdout 必须输出：`resume_active`、`wal_version`、`run_id`、`done_docs`、`committed_batches`、`chunks_upserted_total_last`；  
- 人为中断后重启，`chunks_upserted_total_last` 不回退，且续跑过程中仅对未 `DOC_COMMITTED` 的 doc 做 embedding；  
- WAL 尾部截断时仍可继续续跑，并在 stdout 输出 “truncated_tail_ignored=true”（或等价字段）。  

**落地说明**  
- 已在 `index_state.stage.jsonl` 追加 `UPSERT_BATCH_COMMITTED` / `DOC_COMMITTED` 事件并记录 `chunks_upserted_total`，旧的 `DOC_DONE` 兼容保留；  
- 启动时输出 `[STAGE] resume_active=... wal_version=... run_id=... done_docs=... committed_batches=... chunks_upserted_total_last=... tail_truncated_ignored=... stage_fsync_mode=...（interval=n）`，方便复盘与调度；  
- `_load_stage` 读取 `wal_version`/`committed_batches`/`chunks_upserted_total_last`/`tail_truncated`，遇到未来版本会 WARN 并跳过 resume，尾部截断仅影响额外字段但不会打断重放；  
- `--stage-fsync` 现在接受 `off/doc/interval`（兼容旧 `true/false`）并新增 `--stage-fsync-interval` 控制 interval 模式的 fsync 频率，stage 写入通过 helper 决定是否 fsync（doc 模式每次、interval 模式按事件计数、off 模式不 fsync）。

---

### Step3 — changed/deleted 的可重入顺序与幂等 [DONE]
【做什么】为变更/删除文档引入阶段事件流，并在恢复时基于事件状态跳过重复改写：
- `DELETE_STALE_DONE` 记录已删除文档的旧 chunk；只在 delete 完成后写入，防止多次 delete 把新 chunk 误删。
- `DOC_BEGIN` + `DELETE_OLD_DONE` + `UPSERT_NEW_DONE` + `DOC_COMMITTED` + `DOC_DONE` 形成完整流水线，事件携带 `uri/doc_id/content_sha256/old_content_sha256/n_chunks` 等字段。
- 恢复逻辑借助 `last_event`：`UPSERT_NEW_DONE`/`DOC_COMMITTED`/`DOC_DONE` 表示 doc 已完全写入（skip 整个 doc），而 `DELETE_OLD_DONE` + `old_content_sha256` 仍可复用、只需跳过 delete 后续处理。
【为何】分阶段的事件让恢复能准确判断处于哪个阶段，从而避免 delete 重复命中新 chunk、ups? 重复写入或遗漏进度；`delete_stale` 事件做为审计，让 `doc_state` 只在删除成功后才认为旧 chunk 消失。
【关键参数/注意】
- 事件必须携带 `old_content_sha256`/`content_sha256` 以判断是否仍然是同一个变更版本。
- `DOC_BEGIN` 只在第一次处理该 doc 时写入，后续 resume 只通过 `last_event` 判断状态。
- `UPSERT_NEW_DONE` 会记录 `chunks_upserted_total`，也用于检测中断是否发生在 upsert 之后。

**验收（可核验输出）**：
- 中断发生在 `DELETE_OLD_DONE` 与 `UPSERT_NEW_DONE` 之间，重启后 stage 仅跳过 delete，继续 embedding/upsert，并产出 `DOC_COMMITTED`。
- 已删除文档在 `index_state.stage.jsonl` 中留下 `DELETE_STALE_DONE`，且 `DELETE_OLD_DONE` 只出现一次，不重复删除相同 `doc_id`。

---

### Step4 — 一致性校验与故障可复盘 [DONE]
【做什么】strict_sync 失败时输出期望/实际/差值并在 `RUN_FINISH` 写入 `reason=strict_sync_mismatch` + `delta`；成功时 `RUN_FINISH` 写入 `reason=ok`，继续沿用“仅 ok 后清理 WAL”策略。新增 `--resume-status`：只读加载 stage/WAL，输出 run_id/wal_version/done_docs/committed_batches/chunks_upserted_total_last/tail_truncated，以及 run_start 概览和最多 3 条 doc 样本，不触碰 DB/模型。  
【为何】固定化失败输出使运维可据此决定继续续跑或 reset；`--resume-status` 提供无副作用的核验入口，便于排障与 CI。  
【关键参数/注意】`--resume-status` 不要求 units/模型/Chroma 可用，只读取 stage 文件；strict mismatch 时 WAL 保留且带 reason，便于后续清理决策。  

---

### Step5 — 测试矩阵与回归（含中断注入） [DONE]
【做什么】添加基础单测验证 WAL 解析与尾部截断容错、`resume-status` 无副作用输出：构造 stage JSONL，覆盖 `RUN_START`/`UPSERT_BATCH_COMMITTED`/`DOC_COMMITTED`/`DOC_DONE` 等事件，确认 `tail_truncated` 标记与样本输出正常。  
【为何】续跑是状态机 + 副作用，最小集单测先锁定 WAL 读/打印的正确性，为后续扩展中断注入测试奠基。  
【关键参数/注意】测试仅依赖 stage 文件，不触碰模型/Chroma；未来若补充集成中断注入场景，可在此基础上扩展。  

---

### Step6（可选）— 警告收敛与门禁策略固化 [DONE]
【做什么】将关键 warning 统一通过 `_warn()` 输出（仍保留 stdout 的 `[WARN] ...` 文本），同时收集为结构化 `warn_events`：包含 `key/message/detail/functional`。在 WAL 的 `RUN_FINISH` 事件追加 `warn_count/warn_functional_count/warn_keys`，在成功写入的 report items 中追加 `warn_<key>` 条目（`severity_level=2`，detail 携带 `functional` 与上下文），便于后续门禁/报警稳定消费。  
【为何】避免 warning 只存在于非结构化日志里导致漂移；把“需要动作的风险”与“提示信息”分离出来，并提供可机读的统计字段。  

## 自检
1. 本计划将“写入多少、记录同步在”落到 WAL 的 `UPSERT_BATCH_COMMITTED` 事件上；若你的真实需求是“按 doc/按 chunk 完整列表精确可追溯”，需要扩展事件字段与日志体积，并相应增加测试与恢复规则。  
2. 本计划默认 `upsert` 成功返回后即可作为提交边界；若你们发现 Chroma 存在更长的异步落盘窗口，需要引入更强的确认点（例如 restart 后抽样验证或周期性 count snapshot）。  
3. 计划将 WAL 与完成态 state 分离；若你们希望把 WAL 也作为对外契约，需要重新定义 `LATEST` 与消费者读取口径，影响面扩大。  

## 失败模式与缓解
1. **现象**：恢复后 `skipped_docs` 很大但最终 `collection.count()` 低于期望。  
   **原因**：提交边界定义不严，WAL 领先 DB。  
   **缓解**：将 `DOC_COMMITTED` 写入严格放在 doc flush 完成之后；必要时在恢复时对 `DOC_COMMITTED` 抽样验证（例如抽查 doc 的首尾 chunk_id 存在）。  
   **备选**：暂时关闭续跑（`--resume off`）并重建到稳定状态后再启用。  
2. **现象**：changed 场景恢复后出现“新数据缺失”或疑似误删。  
   **原因**：delete/upsert 阶段缺少分段事件，恢复重复 delete 命中新 chunk。  
   **缓解**：按 Step3 增加 `DELETE_OLD_DONE/UPSERT_NEW_DONE` 并绑定 `old_sha/new_sha`；必要时调整 chunk_id 策略（例如引入 build_stamp 前缀）作为后备路线。  
   **备选**：对 changed_uris 暂时降级为 reset 后重写，优先一致性。  
3. **现象**：WAL 存在但工具提示“不可 resume”。  
   **原因**：schema_hash 或 wal_version 不匹配；或 WAL 尾部损坏超过容忍范围。  
   **缓解**：通过 `--resume-status` 获取原因；确认参数一致；若仅尾部截断，按容错规则继续；若版本不兼容，按建议清理 WAL 或走 reset。  
   **备选**：导出差异摘要后执行 reset，避免在未知状态上叠加写入。  

## MRE
**运行环境（示例）**：Windows 11 + Python 3.11.x；工作目录为仓库根目录。  
**核心依赖**：以 `pip freeze` 为准；若启用 Step2 新参数，请在日志中输出参数快照以便复盘。  

1) 首次构建并中断（示意）  
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --db data_processed\chroma\toy --collection toy
```
运行一段时间后 Ctrl+C。

2) 重启续跑（期望出现 skip，且 `chunks_upserted_total_last` 延续增长）  
```cmd
python tools\build_chroma_index_flagembedding.py build --root . --db data_processed\chroma\toy --collection toy
```

3) 核验：WAL 文件存在、且事件持续追加  
```cmd
dir /b /s data_processed\index_state\toy\*\index_state.stage.jsonl
type data_processed\index_state\toy\*\index_state.stage.jsonl | findstr /i "UPSERT_BATCH_COMMITTED DOC_COMMITTED"
```

## 替代方案
1. **仅 doc 级 WAL（不记 batch）**：只写 `DOC_COMMITTED/DOC_DONE`，实现面更小，仍可跳过 doc；代价是无法做到“写入多少条”的持续可核验计数。  
2. **仅 count snapshot（不写 WAL）**：定期读 `collection.count()` 输出日志；代价是中断后缺少可恢复证据，且 count 不是完整进度映射。  
3. **chunk 级事务/WAL**：提供更精细的可追溯性；代价是事件规模与恢复规则显著扩展，建议在 Step3/Step5 后再评估。  

## 引用与依据
- 文档写作模板与 front-matter 规范：`docs/explanation/documentation_principles.md`  
- 增量状态与写库戳的契约口径：`docs/reference/index_state_and_stamps.md`  
- state/stamp 的原子写与状态文件作为“完成态口径”的约定：`src/mhy_ai_rag_data/tools/index_state.py` 与 `src/mhy_ai_rag_data/tools/index_state_README.md`
