---
title: 排障手册（Runbook）
version: v1.0
last_updated: 2026-01-26
---

# 排障手册（Runbook）


> 目标：把故障定位从“感觉不对”变成“分层检查 + 可复核证据”。  
> 约定：按层级顺序排查，**不要跳层**（先数据/plan，再写库，再检索，再 LLM）。

---

## 1) 详细指导（按 Step 组织）

### Step 1：先确认你没有“查错库/查错路径”
**做什么**：确认当前工作目录是项目根目录（与 `inventory.csv` 同级），并检查 `chroma_db/` 是否为本次构建目标目录。建议把旧库目录版本化（例如 `chroma_db_YYYYMMDD`）。  
**为何（因果）**：最常见的“明明刚建完却看不到变化”是路径错或旧库混入。路径错会让后续所有排查都变成噪声；先把路径固定下来是最低成本的确定性增益。  
**快速验证**：`dir inventory.csv`、`dir chroma_db`、以及 `python tools/list_chroma_collections.py --db chroma_db`。

### Step 2：数据层（units）先过硬闸
**做什么**：运行 `python validate_rag_units.py --max-samples 50`，必须 PASS；如果 FAIL，先修数据处理/抽取逻辑，不要继续建库。  
**为何（因果）**：units 是 plan/build 的输入集合，units 不稳定会在下游以“数量不对/召回跑偏/引用断链”出现，且更难回溯。数据层失败必须在数据层解决。  
**快速验证**：看 summary 里的 `missing_fields/empty_text/md_broken_refs` 是否为 0。

### Step 3：计划层（plan）是否可解释
**做什么**：运行 plan 生成 `data_processed/chunk_plan.json`，重点看：
- `planned_chunks` 是否合理（chunk_plan.json 为 report-output-v2 时字段在 `data.planned_chunks`）
- `type_breakdown` 中各类（md/image/video）indexed/chunks 是否符合当前 Scheme  
**为何（因果）**：plan 是你“expected”的唯一合法来源；如果 plan 输出不可解释，后面的 build/check 都没有讨论基础。  
**快速验证**：`python tools/plan_chunks_from_units.py ... --include-media-stub true`。
可选：快速打印 planned_chunks（兼容 schema_version=1/2）：
`python -c "import json;obj=json.loads(open('data_processed/chunk_plan.json',encoding='utf-8').read());print(obj.get('planned_chunks') or obj.get('data',{}).get('planned_chunks'))"`

### Step 3a：plan 阶段报 `No module named 'chromadb'`（Stage-1 依赖泄漏）
**现象**：你在只安装了 Stage-1/CI 依赖（例如 `.venv_ci` 里仅 `pip install -e .[ci]`）的情况下运行 `rag-plan` 或 `tools/plan_chunks_from_units.py`，却出现：`[FATAL] cannot import ... No module named 'chromadb'`。  
**原因（因果）**：chunk 规划脚本为了复用“与 build 完全一致”的 chunking 逻辑，会 import `mhy_ai_rag_data.build_chroma_index`；如果该模块在 import-time 直接 `import chromadb`，就会把 Stage-2 的重依赖提前到 Stage-1，导致 plan 阶段也需要安装 chromadb。  
**缓解（两条路线）**：  
1) **推荐（工程化修复）**：把 `chromadb` 与 `sentence-transformers` 改为“按需导入”（lazy import），只在 build/query 路径触发。这样 Stage-1 可以稳定运行 plan，而 Stage-2 仍然通过 `pip install -e .[embed]` 显式安装重依赖。  
2) **临时（环境侧绕过）**：直接在该虚拟环境里安装 Stage-2 依赖：`py -m pip install -e .[embed]`（或 `py -m pip install chromadb`）。缺点是把 CI/Stage-1 环境变重，并且更容易在不同机器上出现依赖漂移。
3) **实际项目中已修复**

### Step 4：构建层（build）失败如何定位
**做什么**：若 build 报错，按错误类型处理：
- **导入类**（cannot import / __dict__）：优先检查 tools 脚本版本是否包含 sys.modules 注册修复
- **KeyError/IndexError**：通常是 build 脚本对 shared chunking 返回值结构理解不一致
- **CUDA OOM**：调 `embed_batch`，必要时切 CPU
- **写入期内存高/卡顿**：调 `upsert_batch`  
**为何（因果）**：build 是重计算阶段，错误类型高度集中；按类型处理比“全局怀疑”效率高。  
**快速验证**：把完整 traceback 前 30 行 + 最后 30 行保存到 `data_processed/build_reports/` 便于复盘。

### Step 4a：`ModuleNotFoundError: No module named 'tools'`（tools 包导入失败）
**做什么**：如果你在 `tools/` 子目录里运行 `python -m tools.probe_llm_server ...` 报 `No module named 'tools'`，先 `cd` 回仓库根目录再运行同一命令：
`python -m tools.probe_llm_server ...`。或直接在仓库根目录运行 wrapper：`python tools/probe_llm_server.py ...`。
同理：`python -m tools.verify_single_report_output ...` 也要求 cwd 在仓库根目录。 
**为何（因果）**：当你以“脚本路径”运行 `tools\xxx.py` 时，Python 会把 `tools\` 目录放到 `sys.path[0]`，此时 `import tools.*` 会去找 `tools\tools\` 这类不存在的包路径，从而触发导入失败；用 `-m tools.xxx` 则会把项目根目录作为模块搜索起点，包解析稳定。  
**快速验证**：`python -c "import tools, tools.reporting; print('OK')"` 应输出 `OK`；随后重跑 `python -m tools.probe_llm_server --base ... --timeout 5` 应能看到 200 探测结果。

### Step 5：一致性层（check）必须以 plan 为准
**做什么**：运行：
`python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json`  
**为何（因果）**：check 负责给出“是否可继续”的二值结论。若 FAIL，说明 build 未完成或 plan/build 口径不一致；不要进入检索与模型阶段。  
**快速验证**：看到 `PASS` 且输出 `count == planned_chunks`。

### Step 5b：看到 `rag-status` 提示 Step6/check.json 为 STALE 时如何分流（避免误报）
**做什么**：先区分“语义上游变化”与“读库触发的 mtime 噪声”。优先检查是否存在 `data_processed/index_state/db_build_stamp.json`：存在则以它作为 DB 的稳定信号；缺失则按旧库迁移流程补写一次 stamp。随后只在 `plan.mtime` 或 `stamp.mtime` 晚于 `check.json.mtime` 的情况下重跑 `rag-check --json-out data_processed\build_reports\check.json`，否则不要为了消除 STALE 去反复跑 check。执行动作时建议用固定落盘路径：`data_processed/build_reports/check.json`，便于回归对比。
**为何（因果）**：Windows + SQLite/Chroma 在仅查询（read）时也可能触发 WAL/元数据写入，使 DB 目录 mtime 变化；如果把 DB 目录 mtime 当成上游输入，`check.json` 会被误判为 STALE，导致“重复无效回归”。引入 build stamp 的目的，是让 STALE 判定只对“写库成功”敏感，从系统层面把“读触发噪声”从依赖图里剥离。
**快速验证**：
- `dir data_processed\index_state\db_build_stamp.json` 是否存在且时间是否与最近一次 build 接近；
- `dir data_processed\build_reports\check.json` 是否晚于 `chunk_plan.json` 与 `db_build_stamp.json`；
- 若 stamp 缺失：执行一次 `python tools\write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json`，再重跑一次 `rag-check --json-out data_processed\build_reports\check.json`。


### Step 6：检索层（retriever）先做“结构回归”
**做什么**：运行固定 query 的 `retriever_chroma.py`，检查 top-k 是否能命中相关 source。Scheme B 下媒体 stub 出现是预期；若要回归文本质量，应临时只看 md（where 过滤或逻辑过滤）。  
**为何（因果）**：检索问题会被 LLM 的生成掩盖；先确认“召回能否提供正确证据”才能评价问答质量。  
**快速验证**：输出的 `source_uri/source_type` 与问题主题一致。

### Step 7：RAG pipeline 层（不接 LLM）
**做什么**：运行 `check_rag_pipeline.py`，重点检查：
- `retrieved` 数量
- `context_length` 是否超限
- `messages` 是否符合你的 LLM API 期望格式  
**为何（因果）**：该脚本能把“检索+拼接”从 LLM 调用中剥离，使错误定位更干净。  
**快速验证**：不出现 `[ERROR]`，messages 结构完整。

### Step 8：LLM 层（最后再接入）
**做什么**：配置 `rag_config.py` 的 `LLM_BASE_URL/LLM_MODEL`，再运行 `answer_cli.py`。若失败，优先用 `python -m tools.probe_llm_server ...`（OpenAI-compatible）验证端点可用性与返回格式；若你用的是 Ollama，再用 `check_llm_http.py --mode ollama` 做兼容探测。  
**为何（因果）**：LLM 失败与 RAG 失败是不同故障域；只有在上游都 PASS 时，LLM 才值得排查。  
**快速验证**：HTTP 200，返回 JSON 格式正确。

---

## 2) 常见错误速查表

- `ModuleNotFoundError: No module named 'tools'`：从 `tools\` 目录直接运行导致包解析失败 → 在项目根目录使用 `python -m tools.<script>` 运行，并确认存在 `tools/__init__.py`  
- `KeyError: 0`（metadata 索引）：build 脚本误把 base_md 当 per-chunk metas → 更新 build 脚本  
- `CUDA out of memory`：embed_batch 过大 → 32→16→8 或 CPU  
- `count != planned`：中断/口径漂移/写入失败 → 先确认 plan/build 参数一致，再决定重建或续跑

---

## 3) 日志与证据保全建议
- 每次失败都保存：
  - traceback（全量）
  - 当前 profile JSON（或命令行）
  - `data_processed/env_report.json` 与 `data_processed/chunk_plan.json`
- 统一放到：`data_processed/build_reports/`，文件名建议带时间戳

---

## Chroma 构建专项（常见卡点与处理）

# Chroma 构建常见问题排查（本项目视角）

本文件只覆盖与本仓库脚本相关的高频故障模式，完整背景请参考 [2025-12-26 复盘](../postmortems/2025-12-26_chroma_build_postmortem.md)。

## 1. count 不一致：expected_chunks 告警

### 现象

- `check_chroma_build.py` 显示：`STATUS: FAIL (count mismatch ...)`。

### 根因（常见）

1) **口径变化**：plan/build/check 的 `include_media_stub` 不一致。
2) **chunk 参数变化**：`chunk_chars/overlap_chars/min_chunk_chars` 有任一不同。
3) **输入变化**：`inventory.csv` 或 `data_processed/text_units.jsonl` 发生了增量/删减。

### 处理

- 只使用 `check_chroma_build.py --plan data_processed/chunk_plan.json` 做强校验。
- 若 mismatch：先重跑 `tools/plan_chunks_from_units.py`，确认 `planned_chunks` 是否与你预期一致；再对比 build 输出的 `include_media_stub` 与 `chunk_conf`。
- 若你希望把 md 优先作为回归基线，可在检索侧增加 where 过滤（例如 `source_type=md`）。

## 2. 元数据写入报错：Expected metadata value to be a str/int/float/bool

### 现象

- build 过程中 upsert 抛异常：metadata value 是 list/dict。

### 根因

Chroma record metadata 值要求是标量类型，list/dict 不被接受。

### 处理

- 保持 `build_chroma_index.py` 的策略：将复杂结构序列化为 JSON 字符串（例如 `asset_refs_json`）。
- 若你新增了 metadata 字段，务必在写入前做一次“标量化”过滤。

## 3. 模型下载卡住 / 速度极慢（HuggingFace cache）

### 现象

- 下载 `model.onnx_data` / `model.safetensors` 长时间无输出。

### 处理（本项目建议）

- 在 Windows 上优先观察磁盘写入/文件大小增长，再判断是否“真卡住”。
- 可预先把 embedding 模型下载到本地目录，然后将 `--embed-model` 指向该目录（SentenceTransformer 支持本地路径）。

## 4. 诊断工具

建议按优先级使用：

1) `tools/capture_rag_env.py`：落盘依赖/硬件信息（便于复现）。
2) `tools/plan_chunks_from_units.py`：确认 planned_chunks 与 type_breakdown。
3) `check_chroma_build.py --plan ...`：强校验 count。
4) `tools/diff_units_sources_vs_chroma_sources.py`：对比 units 中的 source_uri 与向量库元数据里出现的 source_uri（定位缺失来源）。
5) `tools/smoke_test_pipeline.py`：从 units 到检索与 prompt 构造的一键冒烟。


---

## 模型机验收清单（快速通过条件）

通过标准：

- 有非空检索结果；
- `context_length` 未明显超限；
- `messages` 结构完整、未抛异常。

此阶段仍不依赖 LLM，只验证「问题 → 检索 → 上下文 → ChatCompletion 请求体」链路。

---

## 4. 接入本地 Qwen 服务并验证闭环

### 4.1 准备 OpenAI 兼容接口

在模型机上，以任一方式把 Qwen2.5 模型暴露为 OpenAI 兼容接口，例如：

- 自建 API Server（`/v1/chat/completions`）；
- 使用 vLLM / LM Studio / 其他兼容工具。

假设服务地址为：

```text
http://localhost:8000/v1
模型名为 qwen2.5-7b-instruct
```

### 4.2 配置 rag_config.py

打开 `rag_config.py`，确认：

```python
LLM_BASE_URL = "http://localhost:8000/v1"
LLM_API_KEY = "EMPTY"                # 若服务要求，可改为实际 key
LLM_MODEL = "qwen2.5-7b-instruct"    # 与服务中模型名称一致
LLM_MAX_TOKENS = 1024
```

保存后不需改动其他脚本。

也可通过环境变量注入（优先 `LLM_API_KEY`，其次 `OPENAI_API_KEY`）；示例见 `.env.example`。

### 4.3 验证完整 RAG 闭环

运行：

```bash
python answer_cli.py --q "存档导入与导出怎么做"
```

预期流程：

1. 打印 `=== RETRIEVED SOURCES (...) ===`，列出若干 `S1/S2/...` 段落；  
2. 打印 `=== ANSWER ===`；  
3. 输出由 Qwen 生成的回答，内部按照系统提示使用 `[Sx]` 标注引用来源。

通过标准（闭环算“跑通”）：

- 程序执行过程中无 Python 异常（尤其是 HTTP / JSON 解析错误）；  
- 终端能看到一个结构化的回答文本；  
- 回答内容能明显看出利用了检索出来的文档（例如引用了存档导入导出的步骤）。

若出现 `[LLM ERROR] ...`，应从以下方向排查：

- `LLM_BASE_URL` 是否写错；  
- 服务是否运行、端口是否可达；  
- `LLM_MODEL` 名称是否与服务端一致；  
- 请求体是否被服务端认可（有时需要查看服务端日志）。

---

## 5. 判定“可以进入下一步”的条件

当以下检查均通过时，可认为当前 RAG 骨架在模型机上已跑通，可进入下一步（检索优化 / 评测集构建 / UI 接入等）：

1. `list_chroma_collections.py` 能找到 `rag_chunks`，状态为 OK；
2. `retriever_chroma.py` 对典型问题（例如“存档导入与导出怎么做”“如何自定义资产”）检索到的文档与预期一致；
3. `check_rag_pipeline.py` 对上述问题产生的 `context_length` 正常、`messages` 结构完整；
4. `answer_cli.py` 在已配置好的本地 Qwen 服务上能输出无错误的回答文本。

之后即可开展的下一步包括但不限于：

- 基于问题集（`../tests/questions_dev.jsonl`）做批量检索/回答评测；
- 引入 rerank 层提升检索精度；
- 增加前端或上层 UI，将 `answer_cli.py` 封装为服务接口。

