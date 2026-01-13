# `compare_stage1_baseline_snapshots.py` 使用说明（对比两份 Stage-1 基线快照）


> **脚本位置建议**：`tools/compare_stage1_baseline_snapshots.py`  
> **输入**：两份 `stage1_baseline_snapshot.json`（或同 schema 的快照 JSON）  
> **输出**：一份差异报告 JSON（默认写到 `--a` 的同目录）

---

## 1. 目的与适用场景

当你执行过：

- `tools/snapshot_stage1_baseline.py`（生成 `stage1_baseline_snapshot.json`）

你后续会反复遇到一个问题：

- “这次重建/改动后，是否与上次基线一致？差异发生在哪里？”

本脚本用于对比两份快照，输出**结构化差异**，使你可以把“漂移归因”从主观讨论变成可审计证据。

典型用途：

- **重建 Chroma 后**：确认 `chroma_db_manifest` 是否变化（新增/删除/内容变化）。
- **修改抽取/分块后**：确认 `artifacts` 的 `sha256` 是否变化（输入侧漂移）。
- **多人协作/跨机器**：确认 `git commit` 或 `pip_freeze` 指纹是否变化（代码/依赖侧漂移）。

---

## 2. 工具做什么 / 不做什么

### 2.1 做什么（Facts）

对比两份快照 `A` 与 `B`，输出差异报告：

1) **artifacts 对比（强指纹）**
- `artifacts.text_units.size`、`artifacts.text_units.sha256`
- `artifacts.chunk_plan.size`、`artifacts.chunk_plan.sha256`

2) **Chroma 落盘对比（manifest）**
- 文件新增：`chroma_files_added`
- 文件删除：`chroma_files_removed`
- 文件内容变化：`chroma_files_changed`
  - 若双方至少一方有 `sha256`，优先比对 `sha256/size`
  - 若双方都无 `sha256`（通常是 >50MB），退化比对 `size/mtime`

3) **Git 对比（若快照包含）**
- `git.commit`、`git.dirty`

4) **pip_freeze 对比（可选）**
- 默认不比（避免大文本噪声）
- 使用 `--compare-pip-freeze` 时，以 **sha256 hash** 的方式对比

并给出 `overall=PASS/FAIL`：

- `PASS`：关键字段无差异
- `FAIL`：存在任意差异（artifact/git/manifest/pip_freeze）

### 2.2 不做什么（Non-goals）

- 不读取/解析 Chroma collection（不做 count 对齐、也不做召回评测）
- 不输出逐行 pip freeze 的全文 diff（只比较 hash；全文 diff 交给外部工具）
- 不修改任何输入文件

---

## 3. 前置条件

- 两份输入 JSON 都必须存在且可被解析
- 输入 JSON 的 schema 应与 `snapshot_stage1_baseline.py` 输出兼容，至少包含：
  - `artifacts.text_units.sha256`、`artifacts.chunk_plan.sha256`
  - `chroma_db_manifest.files[].rel/size/mtime`（可选 `sha256`）

---

## 4. 快速开始（推荐）

### 4.1 最常见：对比“当前基线”与“上一次基线”

```bash
python tools/compare_stage1_baseline_snapshots.py ^
  --a data_processed/build_reports/stage1_baseline_snapshot.json ^
  --b data_processed/build_reports/stage1_baseline_snapshot_prev.json ^
  --out data_processed/build_reports/baseline_diff.json
```

运行结果：

- 控制台打印：`[baseline_diff] overall=PASS|FAIL out=...`
- 输出 JSON：`baseline_diff.json`

### 4.2 也对比 pip_freeze（只比 hash）

```bash
python tools/compare_stage1_baseline_snapshots.py ^
  --a a.json --b b.json ^
  --compare-pip-freeze
```

---

## 5. 参数详解

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|
| `--a` | 是 | 无 | 快照 A（json 路径） |
| `--b` | 是 | 无 | 快照 B（json 路径） |
| `--out` | 否 | 空 | 输出差异报告 JSON；不填则写到 `--a` 的同目录 `baseline_diff_<ts>.json` |
| `--compare-pip-freeze` | 否 | false | 比对 pip_freeze 的 **sha256 hash**（默认不比） |

---

## 6. 输出报告（JSON）字段说明

输出文件示例结构：

- `overall`：`PASS` / `FAIL`
- `diffs.artifacts[]`：artifact 差异列表  
  - `artifact`: `text_units`/`chunk_plan`
  - `diff[]`: 逐字段差异（如 `sha256/size`）
- `diffs.chroma_files_added[]`：新增文件相对路径
- `diffs.chroma_files_removed[]`：删除文件相对路径
- `diffs.chroma_files_changed[]`：变化文件及其差异
- `diffs.git[]`：git commit/dirty 差异（若存在）
- `diffs.pip_freeze[]`：pip_freeze hash 差异（仅在启用时）
- `notes[]`：备注（例如默认未比较 pip_freeze）

---

## 7. 退出码与门禁用法

- 退出码 `0`：`overall=PASS`
- 退出码 `2`：`overall=FAIL` 或输入文件缺失/解析错误

因此你可以把它直接作为“门禁脚本”使用，例如：

```bash
python tools/compare_stage1_baseline_snapshots.py --a a.json --b b.json
if %ERRORLEVEL% NEQ 0 exit /b 1
```

---

## 8. 如何解读差异（建议的归因顺序）

1) `diffs.artifacts` 有差异  
说明输入侧已变（抽取/清洗/分块计划变化），后续检索/答案变化应优先归因到数据与分块。

2) artifacts 无差异，但 `chroma_files_*` 有差异  
说明索引落盘状态变化（写库策略、upsert、重建、Chroma 内部结构变化等），优先检查构建命令/参数与写入批次。

3) artifacts 与 chroma 都无差异，但 `git` 变化  
说明代码版本不一致；若 `dirty` 为 true，需补齐 diff 或先 clean 再建立长期基线。

4) 启用 pip_freeze 比较后出现差异  
说明依赖环境变化；优先关注 embedding/向量库相关包（FlagEmbedding/sentence-transformers/torch/chromadb/transformers）。

---

## 9. 常见问题与处理

### 9.1 为什么不默认比较 pip_freeze？
pip_freeze 文本长，且很多包变化与结果无关，容易制造噪声。默认策略是只对“更直接影响一致性”的 artifacts/manifest/git 做判定；需要时再开启 hash 对比。

### 9.2 大文件没有 sha256，会不会漏判？
当快照生成时对 >50MB 文件可能不算 sha256，此时对比退化为 `size/mtime`。这属于“成本与强度”的折中。若你确实需要对大文件做强指纹，可在 `snapshot_stage1_baseline.py` 提高阈值或对特定文件强制 hash。

---

## 10. 与 Stage-2 的关系（推荐流程）

建议顺序：

1) Stage-1 PASS（`verify_stage1_pipeline.py`）
2) 固化基线（`snapshot_stage1_baseline.py`）
3) 任何重建/改动后再固化一份快照
4) 用本脚本对比“新旧快照”，确定漂移发生在哪一层
5) 再进入 Stage-2 的检索回归与端到端回归（`run_eval_retrieval.py` / `run_eval_rag.py`）

