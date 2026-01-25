---
title: "README（Legacy 完整版）"
version: "v0.1"
last_updated: 2026-01-25
timezone: "America/Los_Angeles"
owner: "zhiz"
status: "archived"
---

> NOTE（现行口径 / SSOT 跳转）：本文为历史材料或旧入口，相关解释可能与当前实现存在差异。
> - CLI 与日志真相表（SSOT）：`docs/reference/build_chroma_cli_and_logs.md`
> - 文件语义（state/WAL/lock）：`docs/reference/index_state_and_stamps.md`
> - 术语表：`docs/reference/GLOSSARY_WAL_RESUME.md`
> - 文档裁决规则：`docs/reference/DOC_SYSTEM_SSOT.md`



> 关于 policy=reset 的两阶段含义：日志里的 index_state missing ... policy=reset 属于对 --on-missing-state=reset 的默认评估，并不代表已经执行 reset；若同一轮发现 WAL 可续跑会走 resume 作为最终生效决策，不会清库。确需强制重置时，请显式加上 --resume off 或手动清理 WAL。

# README目录：


- [一、快速开始（最短可用路径，Scheme B：媒体 Stub 入库）](#一快速开始最短可用路径scheme-b媒体-stub-入库)
  - [1) 创建虚拟环境并安装依赖](#1-创建虚拟环境并安装依赖)
  - [2) 抽取与校验文本单元（units）](#2-抽取与校验文本单元units)
  - [3) plan → build → check（plan-driven expected）](#3-plan-build-checkplan-driven-expected)
    - [3.1) 增量构建（index_state/manifest，同步语义，推荐）](#31-增量构建index_statemanifest同步语义推荐)
- [二、RAG 闭环（检索→拼接→LLM）](#二rag-闭环检索拼接llm)
  - [1) 只看检索（不调用 LLM）](#1-只看检索不调用-llm)
  - [2) 管线自检（检索 + prompt 构造，不调用 LLM）](#2-管线自检检索-prompt-构造不调用-llm)
  - [3) 完整闭环（需要 LLM 服务已就绪）](#3-完整闭环需要-llm-服务已就绪)
  - [4) LLM 服务探测（推荐固定落盘）](#4-llm-服务探测推荐固定落盘)
- [三、阶段门禁与回归（新增工具入口）](#三阶段门禁与回归新增工具入口)
  - [Stage-1：一键验收（是否可以进入下一阶段）](#stage-1一键验收是否可以进入下一阶段)
  - [Stage-1：基线快照与漂移对比（定位“变了什么”）](#stage-1基线快照与漂移对比定位变了什么)
  - [Stage-2：评测（检索回归 hit@k + 端到端 must_include）](#stage-2评测检索回归-hitk-端到端-must_include)
- [四、文档与规范门禁（新增）](#四文档与规范门禁新增)
- [五、脚本概览（根目录骨架）](#五脚本概览根目录骨架)
  - [说明：src-layout 后脚本在哪里？](#说明src-layout-后脚本在哪里)


---

## 一、快速开始（最短可用路径，Scheme B：媒体 Stub 入库）

### 1) 创建虚拟环境并安装依赖

```cmd
cd <REPO_ROOT>
python -m venv .venv_rag
.venv_rag\Scripts\activate

:: 推荐（分阶段安装，避免默认安装重依赖）：
:: Stage-1（inventory → units → validate → plan）：默认轻量依赖
pip install -e .

:: Stage-2（embedding/chroma/检索闭环）：显式安装重依赖（extras）
pip install -e ".[embed]"

:: 旧用法（不推荐；等价于直接安装 Stage-2 全量依赖）：
:: pip install -r requirements_rag_min.txt
```

### 2) 抽取与校验文本单元（units）

> 前置：`extract_units.py` 的输入不是直接扫描目录，而是读取根目录的 `inventory.csv`。  
> 当你遇到“同样资料多次运行行数不同”，优先在建表阶段做归因：看扫描到的文件数/被排除文件/扫描错误，而不是先怀疑 plan/build/check。

**生成/刷新 `inventory.csv`（建表，解释行数漂移的第一现场）**

```cmd
python make_inventory.py
```

脚本新增的“确定性契约”（你需要知道它在做什么）：
- **默认排除易变噪声文件**：为了减少 run-to-run 漂移，默认会排除：`**/~$*`、`**/*.tmp`、`**/*.temp`、`**/*.part`、`**/Thumbs.db`、`**/.DS_Store`。这些通常来自 Office 临时文件/缩略图缓存/下载中间态。
- **可回退到旧口径（全收录）**：如果你要与历史行为做对照或确认是否“误伤”，用 `--no-default-excludes` 关闭默认排除（以脚本帮助信息为准）。
- **可附加排除规则（posix glob）**：用 `--exclude-glob` 追加排除（可重复多次）。注意匹配用的是 **posix 相对路径**（`/` 分隔），例如：`--exclude-glob "data_raw/**/~$*"` 或 `--exclude-glob "**/~$*"`.
- **build report 证据落盘（推荐保留）**：默认会写 `data_processed/build_reports/inventory_build_report.json`（可 `--report-out` 改路径，或 `--no-report` 关闭）。report 至少包含：`root/raw_dir/out_csv`、`scanned_files/included_rows/excluded_files/errors` 计数，以及 `excluded_samples/error_samples`，用来解释“为什么这次行数与上次不同”。
- **严格模式（用于锁文件/同步中间态排查）**：`--strict` 表示只要出现扫描/哈希错误就返回非 0，避免“行数变了但被悄悄跳过”。


```cmd
python extract_units.py
python validate_rag_units.py --max-samples 50

:: 可选：回归/CI 固定落盘（只写一份报告）
python validate_rag_units.py --max-samples 50 --json-out data_processed\build_reports\units.json
```

验收信号：末尾 `Result: PASS`，并且 summary 计数项（bad_json / missing_fields / md_broken_* 等）为 0。

### 3) plan → build → check（plan-driven expected）

> 从 2025-12-26 起，默认使用 **plan 驱动的 expected_chunks**，禁止长期维护手填常量（例如 `expected_chunks=705`）。  
> 关键要求：plan/build/check 的 `include_media_stub` 与 chunk 参数必须一致。

**一键执行（推荐）**

```cmd
python tools\run_build_profile.py --profile build_profile_schemeB.json
```

该命令会依次运行（按 profile 固化参数）：
- env：`tools/capture_rag_env.py`
- units：`extract_units.py`（缺失时生成） + `validate_rag_units.py`
- plan：`tools/plan_chunks_from_units.py` → `data_processed/chunk_plan.json`
- build：`build_chroma_index.py build`（开启 `--include-media-stub`）
- check：`check_chroma_build.py --plan ...`（count 必须 == planned_chunks）

**拆分执行（需要你人工观察每步输出时）**

```cmd
python tools\capture_rag_env.py --out data_processed\env_report.json
python extract_units.py
python validate_rag_units.py --max-samples 50

python tools\plan_chunks_from_units.py --root . --units data_processed\text_units.jsonl --include-media-stub true --out data_processed\chunk_plan.json
python build_chroma_index.py build --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks --device cuda:0 --embed-model BAAI/bge-m3 --embed-batch 32 --upsert-batch 256 --include-media-stub
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json

:: 可选：回归/CI 固定落盘（只写一份报告）
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-out data_processed\build_reports\check.json
```

#### 3.1) 增量构建（index_state/manifest，同步语义，推荐）

**做什么**：`tools/build_chroma_index_flagembedding.py` 现默认启用 `--sync-mode incremental`（增量同步），会在本地生成并维护索引状态文件（manifest）：  
- 仅对 **新增/内容变更** 的文件重新 chunk + embedding + upsert；  
- 对 **删除/内容变更** 的文件，先按 doc 粒度执行 `collection.delete(ids=doc_id:0..n-1)` 清理旧 chunk，避免残留导致 `count mismatch`；  
- 对 **未变化** 的文件直接复用上一轮索引状态，从而把每次入库的主要成本从 O(N) 降为 O(Δ)。

**为何（因果）**：你当前的验收门槛是 `check_chroma_build.py` 的“强一致”（`collection.count == expected_chunks`）。单纯 `upsert` 不会删除旧条目，资料集合发生删除/缩短时就会出现 `count > expected`。引入 `index_state` 后，build 具备“同步语义”，既能保持强一致，又能在大规模资料下避免反复全量重建。

**关键参数（常用默认已够用）**：  
- `--sync-mode incremental|delete-stale|none`  
  - `incremental`：只对变更集做 embedding（推荐长期使用）；  
  - `delete-stale`：删除旧 chunk 后对全部文档做 embedding（更稳但仍 O(N)）；  
  - `none`：仅 upsert（可能产生残留，不建议）。  
- `--on-missing-state reset`：若状态缺失但库非空，自动重置 collection 后全量重建（避免“无法定位残留 ids”）。  
- `--schema-change reset`：当 embed_model/chunk_conf/include_media_stub 变化时视为“新索引口径”，自动重置 collection 并写入新 schema_hash 的状态目录。

**状态文件位置**：  
- `data_processed/index_state/<collection>/<schema_hash>/index_state.json`  
- `data_processed/index_state/<collection>/LATEST`（指向当前 schema_hash）


---

## 二、RAG 闭环（检索→拼接→LLM）

> 先把“检索 + prompt 构造”跑通，再接 LLM；避免把上游问题误判为模型问题。

### 1) 只看检索（不调用 LLM）
```cmd
python retriever_chroma.py --q "存档导入与导出怎么做" --k 5
```

### 2) 管线自检（检索 + prompt 构造，不调用 LLM）
```cmd
python check_rag_pipeline.py --q "存档导入与导出怎么做"
```

### 3) 完整闭环（需要 LLM 服务已就绪）
```cmd
python answer_cli.py --q "存档导入与导出怎么做"
```

### 4) LLM 服务探测（推荐固定落盘）
```cmd
python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed\build_reports\llm_probe.json
```

---

## 三、阶段门禁与回归（新增工具入口）

> 这一组工具的目标是把“是否退化”变成**可机器消费的证据**（报告 + 退出码），降低你每次改动后的验证成本。

### Stage-1：一键验收（是否可以进入下一阶段）
- 工具：`tools/verify_stage1_pipeline.py`（说明：[`tools/verify_stage1_pipeline_README.md`](../../tools/verify_stage1_pipeline_README.md)）
- 典型命令：
```cmd
python tools\verify_stage1_pipeline.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --timeout 10
```
- 输出：`data_processed/build_reports/stage1_verify.json`（可作为门禁报告）

### Stage-1：基线快照与漂移对比（定位“变了什么”）
- 生成基线：`tools/snapshot_stage1_baseline.py`（说明：[`tools/snapshot_stage1_baseline_README.md`](../../tools/snapshot_stage1_baseline_README.md)）
- 对比两份快照：`tools/compare_stage1_baseline_snapshots.py`（说明：[`tools/compare_stage1_baseline_snapshots_README.md`](../../tools/compare_stage1_baseline_snapshots_README.md)）

```cmd
python tools\snapshot_stage1_baseline.py --root . --db chroma_db
python tools\compare_stage1_baseline_snapshots.py --a data_processed\build_reports\stage1_baseline_snapshot.json --b data_processed\build_reports\stage1_baseline_snapshot_prev.json --out data_processed\build_reports\baseline_diff.json
```

### Stage-2：评测（检索回归 hit@k + 端到端 must_include）
- 初始化用例集：`tools/init_eval_cases.py`（说明：[`tools/init_eval_cases_README.md`](../../tools/init_eval_cases_README.md)）
- 取证 expected_sources：`tools/suggest_expected_sources.py`（说明：[`tools/suggest_expected_sources_README_v2.md`](../../tools/suggest_expected_sources_README_v2.md)）
- 用例集门禁：`tools/validate_eval_cases.py`（说明：[`tools/validate_eval_cases_README.md`](../../tools/validate_eval_cases_README.md)）
- 检索回归：`tools/run_eval_retrieval.py`（说明：[`tools/run_eval_retrieval_README.md`](../../tools/run_eval_retrieval_README.md)）
- 端到端回归：`tools/run_eval_rag.py`（说明：[`tools/run_eval_rag_README.md`](../../tools/run_eval_rag_README.md)）
- 汇总解读：`tools/view_stage2_reports.py`（说明：[`tools/view_stage2_reports_README.md`](../../tools/view_stage2_reports_README.md)）

推荐顺序（强约束→弱约束）：
```cmd
python tools\init_eval_cases.py --root .
python tools\validate_eval_cases.py --root . --check-sources-exist

python tools\run_eval_retrieval.py --root . --db chroma_db --collection rag_chunks --k 5 --embed-model BAAI/bge-m3
python tools\run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --k 5 --embed-model BAAI/bge-m3 --timeout 120 --trust-env auto

python tools\view_stage2_reports.py --root . --md-out data_processed\build_reports\stage2_summary.md
```

---

## 四、文档与规范门禁（新增）

- docs 目录工程约定检查：`tools/check_docs_conventions.py`（说明：[`tools/check_docs_conventions_README.md`](../../tools/check_docs_conventions_README.md)）
- 全仓库 Markdown 链接扫描/自动修复：`tools/verify_postmortems_and_troubleshooting.py`（支持 `--no-fix/--strict/--any-local`）

---

## 五、脚本概览（根目录骨架）

### 说明：src-layout 后脚本在哪里？

本仓库已切换为 **src-layout**：权威实现放在 `src/mhy_ai_rag_data/` 下。
为了兼容你过去的命令，本仓库根目录与 `tools/` 目录仍保留同名脚本，但它们已变为 **wrapper**（只负责把执行转发到 `mhy_ai_rag_data.*`）。

推荐用法：
- `pip install -e .` 安装后，直接用 console scripts：`rag-inventory / rag-extract-units / rag-plan / rag-build / rag-check / rag-check-all`。
- 或者用 `python -m mhy_ai_rag_data.<module> ...` / `python -m mhy_ai_rag_data.tools.<module> ...`。

如果你坚持继续用旧命令（如 `python tools/build_chroma_index_flagembedding.py ...`），也可以工作，但本质上仍会跑到 `src/` 下的实现。


根目录核心脚本（RAG 闭环骨架）：
- `rag_config.py`：集中配置（Chroma 路径、向量模型、LLM 接口、top_k、上下文长度）
- `embeddings_bge_m3.py`：封装 BGE-M3 embedding（query 向量）
- `retriever_chroma.py`：Chroma 检索
- `prompt_rag.py`：上下文拼接与 messages 构造
- `llm_client_http.py`：OpenAI-compatible `/v1/chat/completions` 调用
- `check_rag_pipeline.py`：检索 + prompt 自检（不调用 LLM）
- `answer_cli.py`：CLI：问题 → 检索 →（可选）LLM 回答

> 工具脚本的详细参数与示例，优先以 `tools/*_README*.md` 为准（它们与脚本同步维护）。
