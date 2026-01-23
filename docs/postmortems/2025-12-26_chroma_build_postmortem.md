> NOTE（现行口径 / SSOT 跳转）：本文为历史材料或旧入口，相关解释可能与当前实现存在差异。
> - CLI 与日志真相表（SSOT）：`docs/reference/build_chroma_cli_and_logs.md`
> - 文件语义（state/WAL/lock）：`docs/reference/index_state_and_stamps.md`
> - 术语表：`docs/reference/GLOSSARY_WAL_RESUME.md`
> - 文档裁决规则：`docs/reference/DOC_SYSTEM_SSOT.md`


[关键词] chroma build, expected_chunks, count mismatch, media skip, include-media-stub, chunk_plan


[阶段] chunk_plan / build / check

[工具] tools/plan_chunks_from_units.py, tools/build_chroma_index_flagembedding.py, check_chroma_build.py, tools/diff_units_sources_vs_chroma_sources.py

[复现] python tools/plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl --out data_processed/chunk_plan.json（chunk参数与build保持一致）

[验收] python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json（expected_chunks==count）


# 本次 Chroma 构建数量异常排查总结（705 vs 694）

> 注意（2026-01-23）：`build_chroma_index_flagembedding` 已引入断点续跑 WAL（`index_state.stage.jsonl`）与 `--resume-status`。因此当出现“state 缺失但库非空”的场景时，`on-missing-state=reset` 可能会被 WAL 的 resume 分支覆盖（以避免清除已写入进度）。若你确实要全量重建，可用 `--resume off` 显式关闭续跑。

> 日期：2025-12-26  
> 项目目录：`<REPO_ROOT>
> 虚拟环境：`.venv_rag`  
> 关注点：构建日志 `chunks_indexed=694`，但你期望（手填）`expected_chunks=705`，`check_chroma_build.py` 给出 WARN。

---

## 1. 现象与触发

### 1.1 构建输出（你提供）
- `=== BUILD DONE ===`
- `units_read=3228`
- `chunks_indexed=694`
- `db_path=<REPO_ROOT>
- `collection=rag_chunks`
- `embed_model=BAAI/bge-m3`

### 1.2 检查输出（你提供）
- `python check_chroma_build.py --db chroma_db --collection rag_chunks --expected-chunks 705`
- `embeddings_in_collection=694`
- `STATUS: WARN (expected_chunks=705, got=694)`

---

## 2. 排查目标（当时的“问题定义”）

把差异拆成两个问题：
1) **库里到底有多少条**（事实层：count/ids/metadata 分布）。  
2) **705 这个 expected 的来源/口径是否正确**（定义层：输入范围、过滤规则、切块参数、媒体是否入库等）。

---

## 3. 关键排查步骤与结果（按因果链组织）

### 3.1 排除“查错库/查错路径”
通过脚本输出确认：
- `cwd=<REPO_ROOT>
- `db_abs=<REPO_ROOT>
- 与 build 输出 `db_path=...\chroma_db` 一致  
结论：**不是相对路径导致的“检查了另一个库”。**

### 3.2 对 Chroma collection 做结构盘点（只读统计）
`dump_chroma_collection_stats.py` 输出（你提供）：
- `count=694`
- `unique_source_uri=210`
- `doc_id_count=210`
- `weird_id_count=0`
- `doc_id_gap_count=0`
结论：
- 库内条目数稳定为 **694**（与 build 日志一致）。
- 被索引的 source（文件）只有 **210** 个。
- id 形态规则统一、chunk 索引无缺口 → **不像“写入中丢块/随机缺失”。**

### 3.3 证实：units.jsonl 不是“最终 chunk 粒度”，无法直接推导 expected chunks
相关脚本输出（你提供）：
- `compute_expected_ids_from_units.py`：
  - `unknown_schema_lines=3228`
  - `expected_unique_ids=0`
- `inspect_units_schema_and_counts.py`：
  - `unique_candidate_ids_count=N/A`

含义：
- `data_processed/text_units.jsonl` 里只有 `source_uri + text`，**没有** `chunk_index/id` 这种可直接对应 “最终写入 Chroma 的 chunk id” 的字段。
- 因而外部脚本无法从 units 推出“应该有多少 chunks”，手填 `705` 这种 expected 不具备可追溯性。

### 3.4 找到核心因果：units 里绝大多数是媒体文件，被构建阶段跳过
你运行并贴出的统计是本次“定案证据”。

#### 3.4.1 units 的扩展名分布（`count_units_sources_and_exts.py`）
- `unique_source_uri=3228`
- Top extensions：
  - `.png: 2871`
  - `.md: 207`
  - `.gif: 127`
  - `.mp4: 20`
  - `.py: 1`
  - `.jsonl: 1`
  - `.svg: 1`

#### 3.4.2 units vs Chroma 的 source 差集（`diff_units_sources_vs_chroma_sources.py`）
- `units_unique_sources=3228`
- `chroma_unique_sources=210`
- `skipped_sources(units_only)=3018`
- `added_sources(chroma_only)=0`
- Skipped extensions：
  - `.png: 2871`
  - `.gif: 127`
  - `.mp4: 20`

推导（可核验）：
- `2871 + 127 + 20 = 3018`，恰好等于 `skipped_sources=3018`  
结论：**构建阶段默认不索引媒体（png/gif/mp4）。**

进一步对应：
- units 中非媒体的 source 数：
  - `.md 207 + .py 1 + .jsonl 1 + .svg 1 = 210`
- Chroma 中 `unique_source_uri=210`  
结论：**Chroma 正好只索引了这 210 个非媒体 source。**

---

## 4. “705 vs 694” 的最终解释（结论层）

1) `694` 是本次构建在“只索引非媒体 source”口径下，按当前 chunk 参数产生的实际 chunks 数；并且与库内 count 完全一致。  
2) `705` 不是从本次输入（`data_processed/text_units.jsonl`）可推导出的稳定指标，属于“旧口径/旧参数/或启用了媒体占位 stub”时才可能出现的数字。  
3) 因为 units 不包含 chunk 粒度字段，**手填 expected_chunks 的检查方式会天然产生误报**。

---

## 5. 你当前配置与可影响结果的参数（你贴的 help）

`python build_chroma_index.py build --help` 显示可影响 chunks 的参数：
- `--chunk-chars`：每 chunk 最大字符数
- `--overlap-chars`：邻近 chunk 重叠字符数
- `--min-chunk-chars`：小于该阈值的尾块合并到前块
- `--include-media-stub`：把图片/视频以 stub 文本也索引（默认关闭）

以及 embedding 参数：
- `--embed-model`
- `--device`（cpu/cuda）
- `--embed-batch`
- `--upsert-batch`

---

## 6. 当前最建议的“稳定口径”与下一步（不含改代码也能执行）

### 6.1 先定口径（二选一）
A) **文本-only（推荐默认）**：只索引 `.md/.py/.jsonl/.svg` 等文本类 source。  
- 预期：`unique_source_uri≈210`（与你现在一致）  
- chunks 数只随 `chunk-chars/overlap/min-chunk-chars` 变化

B) **媒体也入库（仅 stub，不做 OCR/ASR）**：构建时加 `--include-media-stub`  
- 预期：`unique_source_uri≈3228`  
- chunks 会显著增加（至少增加媒体数量级）

### 6.2 把“expected”从手填常数改为可追溯（建议）
最稳做法：新增/使用 dry-run 产物（计划数）来替代手填 `expected_chunks`。
- 你可以用 `plan_chunks_from_units.py` 先生成 `data_processed/chunk_plan.json`（planned_chunks）  
- 再用同一套参数写库  
- check 时对比 planned_chunks 与 `collection.count()`，口径可复现

---

## 7. 本次新增/使用的脚本清单（都放在同一目录下可直接运行）

- `resolve_db_and_collection.py`：打印 cwd 与 db 绝对路径，排除查错库  
- `dump_chroma_collection_stats.py`：统计 collection.count / source 分布 / doc_id gap  
- `validate_text_units_jsonl.py`：units 的一致性、字段猜测、重复键检测  
- `inspect_units_schema_and_counts.py`：units 的 source 分布与 schema 探测  
- `diff_units_vs_chroma.py`：尝试按 id 差集定位缺失（本次因 schema 不足不可用）  
- `count_units_sources_and_exts.py`：统计 units source 数与扩展名分布（本次定案关键）  
- `diff_units_sources_vs_chroma_sources.py`：对比 units sources 与 chroma sources（本次定案关键）  
- `plan_chunks_from_units.py`：dry-run 规划 chunk（用于替代手填 expected）

---

## 8. 一句话复盘（便于明天继续）
- 本次不是“构建漏写 11 条”，而是 **units 里 3018 个媒体 source 被默认跳过**，最终只索引了 210 个非媒体 source，并在当前 chunk 参数下产生 694 chunks；手填的 705 没有稳定来源，需要改为“口径明确 + planned report 驱动的 expected”。