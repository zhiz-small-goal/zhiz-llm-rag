# 2025-12-29_chroma_build_postmortem_count_mismatch_3728_vs_4433.md目录：

> 注意（2026-01-23）：`build_chroma_index_flagembedding` 已引入断点续跑 WAL（`index_state.stage.jsonl`）与 `--resume-status`。因此当出现“state 缺失但库非空”的场景时，`on-missing-state=reset` 可能会被 WAL 的 resume 分支覆盖（以避免清除已写入进度）。若你确实要全量重建，可用 `--resume off` 显式关闭续跑。


- [1. 现象与触发](#1-现象与触发)
  - [1.1 检查输出（你提供）](#1-1-检查输出-你提供)
  - [1.2 直接结论（现象级）](#1-2-直接结论-现象级)
- [2. 问题定义](#2-问题定义)
- [3. 关键证据与排查过程](#3-关键证据与排查过程)
  - [3.1 期望值来自 plan（expected=3728）](#3-1-期望值来自-plan-expected-3728)
  - [3.2 实际库内条目数（got=4433）](#3-2-实际库内条目数-got-4433)
  - [3.3 计数大于期望的含义：存在“计划外残留”](#3-3-计数大于期望的含义-存在计划外残留)
  - [3.4 为什么“重跑流程”仍会保留残留](#3-4-为什么重跑流程仍会保留残留)
- [4. 根因分析（RCA）](#4-根因分析-rca)
  - [4.1 直接根因（Direct Cause）](#4-1-直接根因-direct-cause)
  - [4.2 促成因素（Contributing Factors）](#4-2-促成因素-contributing-factors)
  - [4.3 反事实验证（如何证伪/证实）](#4-3-反事实验证-如何证伪-证实)
- [5. 修复与处置](#5-修复与处置)
  - [5.1 一次性修复（推荐）：隔离旧库/重置 collection 后重建](#5-1-一次性修复-推荐-隔离旧库-重置-collection-后重建)
  - [5.2 低成本验证（不重建也能定位）：证明存在多余 ids](#5-2-低成本验证-不重建也能定位-证明存在多余-ids)
  - [5.3 长期方案：构建语义从 merge(upsert) 升级为 sync（index_state/manifest）](#5-3-长期方案-构建语义从-merge-upsert-升级为-sync-indexstate-manifest)
- [6. 预防与回归测试](#6-预防与回归测试)
- [7. 最小可复现（MRE）](#7-最小可复现-mre)
- [8. 一句话复盘](#8-一句话复盘)

[关键词] chroma build, expected_chunks, count mismatch, residual data, plan-driven, include_media_stub, schemeB

[阶段] chunk_plan / build / check

[工具] tools/plan_chunks_from_units.py, tools/build_chroma_index_flagembedding.py, check_chroma_build.py

[复现] python tools/plan_chunks_from_units.py ... --include-media-stub true --out data_processed/chunk_plan.json（plan/build/check 参数一致）

[验收] python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json（expected_chunks==collection.count）


# 本次 Chroma 构建数量异常排查总结（expected=3728 vs got=4433）

> 日期：2025-12-29  
> 项目目录：`<REPO_ROOT>
> 虚拟环境：`.venv_rag`  
> 关注点：你已“重新跑了一遍流程”，但 `check_chroma_build.py` 仍 FAIL：**库内条目数大于 plan 期望值**。


## 1. 现象与触发

### 1.1 检查输出（你提供）
```
python.exe check_chroma_build.py --db chroma_db --collection rag_chunks --plan <REPO_ROOT>
expected_chunks=3728 (from plan)
plan.include_media_stub=True
plan.chunk_conf={'chunk_chars': 1200, 'overlap_chars': 120, 'min_chunk_chars': 200}
plan.units_read=3231 units_indexed=3231 units_skipped=0
embeddings_in_collection=4433
STATUS: FAIL (count mismatch; expected=3728 got=4433)
plan.type_breakdown.top_chunks=[('image', 3003), ('md', 700), ('video', 20), ('other', 5)]
```

### 1.2 直接结论（现象级）
- 本次验收脚本以 **plan 的 planned chunks 数（3728）** 为期望。
- 实际 collection 内记录数为 **4433**，比期望多 **705**。
- 因此判定为：**存在“计划外条目残留”或“检查指向了非本次构建的库/collection”。**


## 2. 问题定义

本次问题与 2025-12-26（“705 vs 694”）的差异点：
- 12-26 的核心是：units 中大量媒体被默认跳过，导致“手填 expected 不可靠”，需要改为 **plan-driven expected**。
- 12-29 的核心是：已经是 **plan-driven expected**，但 collection.count 仍然大于 expected，说明问题不再是“expected 来源不可靠”，而是“库里混入了计划外数据”。

因此，本次问题定义为：
1) 期望值（expected=3728）是否确实来自“本次 plan + 本次参数口径”。  
2) 若是，则必须解释：为什么 collection 里会多出 705 条“计划外条目”。  


## 3. 关键证据与排查过程

### 3.1 期望值来自 plan（expected=3728）
你提供的 `check_chroma_build.py` 输出已明确：
- `expected_chunks=3728 (from plan: ...chunk_plan.json)`  
- `plan.include_media_stub=True`  
- `plan.chunk_conf={1200/120/200}`  
- `plan.units_read=3231 ... units_skipped=0`  

这说明：**expected 的口径与 plan 文件绑定**，不再是“手填常量”。

### 3.2 实际库内条目数（got=4433）
同一输出中：`embeddings_in_collection=4433`。  
该值来自对 `chroma_db/rag_chunks` 的实际读取（collection.count 或等价统计），属于“事实层”。

### 3.3 计数大于期望的含义：存在“计划外残留”
当 `collection.count > expected_chunks` 时，意味着至少存在以下一种情况：
- (A) **同一 collection 曾用不同 plan/不同口径写入过**，旧 chunk_id 仍然保留；本次重跑只做 upsert/追加，不会清理旧条目。
- (B) **你检查的库/collection 并不是本次 build 写入的目标**（例如 build 指向了另一个 db_path 或 collection 名称，但 check 指向 chroma_db/rag_chunks）。
- (C) **本次 build 的写入逻辑做了“额外插入”**（例如把某些条目写入了，但 plan 没把它们计入 expected），导致写入与计划不一致。

在你当前日志信息下，(A) 与 (B) 是更优先的排查方向；(C) 通常需要回看 build 端是否与 plan 完全同参数、同 include_media_stub 口径。

### 3.4 为什么“重跑流程”仍会保留残留
关键机制点（与你的现象严格匹配）：
- Chroma 是持久化库：只要你复用同一个 `chroma_db` 路径与 `rag_chunks` collection，历史数据会保留。
- 典型 build 写入使用 upsert（merge）：**更新/新增**，但**不会删除**“本次计划里不再存在的旧条目”。

因此，即便你“完整重跑 plan→build→check”，只要你没有做“删除旧条目/重置 collection”，历史残留就可能一直存在，表现为 `count` 只能增不能减。


## 4. 根因分析（RCA）

### 4.1 直接根因（Direct Cause）
- `chroma_db/rag_chunks` 内存在本次 `chunk_plan.json` 未覆盖或未包含的旧记录（计划外残留），导致 `embeddings_in_collection(4433) > expected_chunks(3728)`。

### 4.2 促成因素（Contributing Factors）
- 复用了同一个持久化 db 路径与 collection 名称（历史数据天然保留）。
- build 采用 merge(upsert) 语义，没有执行“按计划同步删除（GC）”或“重置 collection”。
- 本次 `include_media_stub=True`，生成的 chunk 类型中 `image` 占比极高；只要之前某次构建口径/输入略有差异，残留体量会更明显。

### 4.3 反事实验证（如何证伪/证实）
- 若将旧库隔离后重建（见 5.1），check PASS，则可证实根因是“旧残留”而非“计划/写入算法错误”。
- 若隔离后仍 FAIL，则需要进一步定位 build 与 plan 参数/口径是否一致（可能存在写入额外条目的路径）。


## 5. 修复与处置

### 5.1 一次性修复（推荐）：隔离旧库/重置 collection 后重建
目标：让 “本次库 == 本次计划”，避免混入历史残留。

**方案 1：目录隔离（最直观，风险最低）**
1) 在项目根目录：
   - `ren chroma_db chroma_db_backup_20251229`
2) 重新跑：plan → build → check（与本次相同参数/口径）。
3) 预期：`embeddings_in_collection == expected_chunks`，check PASS。

**方案 2：collection 级重置（更快，但要确保 API 支持）**
1) 在 build 前执行：`client.delete_collection("rag_chunks")`（或等价清空）。
2) 再 build 写入同名 collection。
3) 再 check。

> 选择建议：如果你经常遇到 Windows 文件占用/锁导致删除失败，目录隔离更稳；如果你想减少磁盘复制与目录操作，collection 重置更轻。

### 5.2 低成本验证（不重建也能定位）：证明存在多余 ids
如果你希望在不立即重建的情况下“证明多余条目确实存在”，可以做两件事（只读）：
1) 让 build 端输出（或临时写一个只读统计）本次 plan 的 chunk_id 集合大小。
2) 从 collection 拉取 ids（分页）并与 plan_ids 做差集，得到“多余 ids”样例（前 10 个即可）。

这个动作的价值：把“怀疑残留”变成“可展示的差集证据”，便于后续决定采用“重置”还是“差量 GC”。

### 5.3 长期方案：构建语义从 merge(upsert) 升级为 sync（index_state/manifest）
你已明确后续数据规模会增大且“每次全量重建成本高”。长期更稳的做法是引入本地 `index_state/manifest`：
- 新增：只对新增 doc 入库。
- 变更：固定为 `delete(old_doc_chunks) → rebuild_doc_chunks → upsert(new_doc_chunks)`。
- 删除：按 doc 删除其旧 chunk_ids。
- schema/口径变化（chunk_conf/embed_model/include_media_stub 变化）：触发一次性 reset collection 或新 collection 版本化。

该方案的关键收益：
- 计算成本从 O(N) 降到 O(Δ)；
- 同时仍能维持 `expected_chunks==count` 的强一致验收（因为删除也被纳入同步语义）。


## 6. 预防与回归测试

建议把以下门禁固化到 build 输出/CI（至少本地 smoke）：
1) **preflight**：若 `collection.count>0 且 count!=expected`，明确提示“可能存在残留”，并给出两条动作：重置/隔离后重建。
2) **strict check（build 内部）**：build 完成后立即断言 `collection.count == expected_chunks`，失败即返回非 0。
3) **版本化策略**：对每次 schema 变更（chunk_conf/embed_model/include_media_stub），使用新 collection 名称或先 reset，避免跨口径污染。


## 7. 最小可复现（MRE）

在项目根目录（示意，参数以你当前 profile 为准）：

```powershell
# 1) 生成 plan（确保 include-media-stub 与 chunk_conf 一致）
python tools/plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 `
  --include-media-stub true --out data_processed/chunk_plan.json

# 2) 写入（复用同一 chroma_db/rag_chunks）
python tools/build_chroma_index_flagembedding.py build --root . --units data_processed/text_units.jsonl `
  --db chroma_db --collection rag_chunks `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub

# 3) 验收
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json
```

若你在同一 `chroma_db/rag_chunks` 曾经写入过不同口径数据且未重置，很容易复现：`count > expected`。


## 8. 一句话复盘
- 本次不是 plan 口径问题，而是 **持久化库复用导致计划外条目残留**：`expected=3728`（本次 plan）正确，但 `got=4433` 表明 `rag_chunks` 中混入历史数据；处理方式应优先是“隔离旧库/重置 collection 后重建”，长期用 manifest 把写入语义升级为 sync。