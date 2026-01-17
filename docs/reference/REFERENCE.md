---
title: 参考与契约（REFERENCE）
version: v1.2
last_updated: 2026-01-15
---

> SSOT（机器可读）: `docs/reference/reference.yaml`。CI 与 gate runner 以此为准。


# 参考与契约（口径、产物、架构）

本文件收敛三类稳定口径：

- 构建口径契约（Scheme A/B、关键参数、验收标准）
- 产物/报告契约（JSON/env/plan/time）
- RAG 闭环骨架（模块职责与调用流程）

## 目录
- [参考与契约（口径、产物、架构）](#参考与契约口径产物架构)
- [目录](#目录)
- [1. 参考入口与导航](#1-参考入口与导航)
- [2. Index State 与 Stamps（写库完成戳）](#2-index-state-与-stamps写库完成戳)
- [3. JSON 报告契约（v1，2025-12-27）](#3-json-报告契约v12025-12-27)
- [4. 构建口径契约（Scheme A/B，2025-12-27）](#4-构建口径契约scheme-ab2025-12-27)
- [5. 报告文件说明（env-plan-time，2025-12-27）](#5-报告文件说明env-plan-time2025-12-27)
- [6. RAG 闭环骨架（工程参考）](#6-rag-闭环骨架工程参考)
- [7. 环境与依赖契约（可安装性基线）](#7-环境与依赖契约可安装性基线)
- [8. 关联文档（解释类与 SSOT）](#8-关联文档解释类与-ssot)
- [9. 术语与缩写（Glossary）](#9-术语与缩写glossary)

---

## 1. 参考入口与导航

- 报告输出契约（schema_version=2）：[`REPORT_OUTPUT_CONTRACT.md`](REPORT_OUTPUT_CONTRACT.md)
- 依赖策略（默认/可选 extras）：[`deps_policy.md`](deps_policy.md)
- Index State 与 Stamps：[`index_state_and_stamps.md`](index_state_and_stamps.md)
- Stage-2 评测契约：[`EVAL_CASES_SCHEMA.md`](EVAL_CASES_SCHEMA.md)
- Postmortem 模板（诊断复盘）：[`postmortem_prompt_template.md`](postmortem_prompt_template.md)
- 审查规范（Review Spec：SSOT/生成/模板）：[`review/README.md`](review/README.md)

---

## 2. Index State 与 Stamps（写库完成戳）

- 统一契约页：[`index_state_and_stamps.md`](index_state_and_stamps.md)
- 关键点：`db_build_stamp.json` 只在写库成功后更新，用于让 `rag-status` 的 STALE 判定不受“读库刷新 mtime”噪声影响；`index_state/` 记录增量同步状态，用于复盘与续跑。

---

## 3. JSON 报告契约（v1，2025-12-27）

> 目标：让“步骤验收”既有人类可读输出，也能在回归/CI 中被机器稳定消费；同时避免 `*_report_<ts>.json` 这类默认文件污染目录。  
> 核心规则：**当提供 `--json-out` 时，只写该路径（只产出一份报告），不再额外生成默认时间戳报告文件。**

### 3.1 退出码（Exit Code）
- `0`：PASS（或 INFO/WARN 但不强制失败）
- `2`：FAIL（门禁不通过/前置条件不满足/强校验失败）
- `3`：ERROR（脚本异常/未捕获异常）

### 3.2 Report 结构（schema_version=1）
所有实现契约的脚本，在启用 JSON 输出时，应至少包含以下字段（允许扩展字段）：

```json
{
  "schema_version": 1,
  "step": "units|check|llm_probe|...",
  "ts": 1730000000,
  "status": "PASS|FAIL|ERROR|INFO",
  "inputs": {},
  "metrics": {},
  "errors": [{"code":"...", "message":"...", "detail":{}}]
}
```

字段含义：
- `step`：报告所属步骤名（用于回归聚合与路由）
- `status`：与退出码映射（见上）
- `inputs/metrics/errors`：分别承载入参快照、关键计数/指标、结构化错误列表

### 3.3 落盘规则与路径约定
- 推荐把所有 JSON 报告落在 `data_processed/build_reports/`，并使用固定文件名作为“回归基线入口”。
- `--json-stdout`：部分脚本支持将同一份 JSON 打印到 stdout（不落盘），适合把报告留在 CI 日志中。
- `tools` 下脚本推荐用模块方式运行：`python -m tools.<module>`，避免 import 路径问题。

补充：落盘顺序（人类可读约定）
- **汇总块优先**：若报告包含 `summary/metrics/buckets/counts/totals`，这些字段在 JSON 文件顶部优先展示。
- **明细按严重度排序**：常见明细列表（如 `results/cases/items`）在落盘时优先将 `ERROR/FAIL` 项放前、`PASS/OK` 放后。
  - 说明：这只影响 JSON 序列化的 key/数组顺序，用于 VS Code/差异对比的人类阅读；字段语义不变。
  - **路径分隔符**：所有落盘报告（JSON/MD）内出现的文件路径字符串，一律使用 `/`（Windows 盘符写作 `C:/...`），以便 VSCode 点击跳转；建议在落盘入口（`reporting.write_report()`）统一归一化。

### 3.4 当前已实现契约的脚本入口

| step | 脚本 | 推荐命令（Windows CMD） | 说明 |
|---|---|---|---|
| `units` | `validate_rag_units.py` | `python validate_rag_units.py --max-samples 50 --json-out data_processed\build_reports\units.json` | 人类可读摘要 +（可选）JSON 报告 |
| `check` | `check_chroma_build.py` | `python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-out data_processed\build_reports\check.json` | 以 plan 驱动 expected，强校验 count |
| `llm_probe` | `tools/probe_llm_server.py` | `python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed\build_reports\llm_probe.json` | **必须用模块方式**（见 [排障手册](../howto/TROUBLESHOOTING.md)） |

### 3.5 不纳入契约的辅助自检脚本（无需同步）
以下脚本主要用于**交互式诊断/人工观察**，不作为“回归闸门”的机器可读输入，因此不强制同步 `--json-out` 契约：
- `check_llm_http.py`：兼容 OpenAI/Ollama 的快速 HTTP 探测（更偏手动排障）；若你要回归/固定落盘，优先使用 `tools/probe_llm_server.py`。
- `check_rag_pipeline.py`：检索 + prompt 构造自检（不调用 LLM），输出以人工阅读为主。
- `rag-status`：只读扫描本地产物/报告，输出 OK/MISS/STALE/FAIL 并给出下一步命令建议；默认 INFO，不作为门禁（可用 `--strict` 作为门禁）。
- `rag-stamp`：写入/更新 `data_processed/index_state/db_build_stamp.json`（仅在写库完成后更新），用于让 `rag-status` 的 STALE 判定不受“读库刷新 mtime”噪声影响。
- `tools/smoke_test_pipeline.py`：一键串联多个步骤的“冒烟脚本”，其可靠信号是**退出码**；若你需要机器可读回归数据，建议对各子步骤分别使用 `--json-out` 落盘。

---

## 4. 构建口径契约（Scheme A/B，2025-12-27）

> 目的：把“这次到底建的是什么库”写成**可核验的契约**，用于：复现、验收、排障与对比性能。  
> 原则：**plan-driven**（以 plan 的 planned_chunks 作为 expected），禁止长期使用手填 expected 常量。

### 4.1 输入产物
- `inventory.csv`：资料扫描清单（每行对应一个 source；包含 uri/path、type 等）
- `data_processed/text_units.jsonl`：单位文本（units），通常 1 个 source 对应 1 个 unit
  - unit 必须至少包含：`source_uri`、`source_type`、`text`（或可推导的内容字段）、`doc_id`（可稳定生成）

### 4.2 中间产物（计划）
- `data_processed/chunk_plan.json`：plan 输出（dry-run）
  - `planned_chunks`：计划写入 chunks 总数（== expected）
  - `type_breakdown`：按 `source_type` 统计 indexed/skipped/chunks
  - `chunk_conf`：chunk 参数快照（chars/overlap/min）
  - `include_media_stub`：本次口径开关

### 4.3 结果产物（向量库）
- `chroma_db/`：Chroma 持久化目录
- collection：`rag_chunks`（默认）
- 每条 record 的推荐 metadata（标量化后）：
  - `doc_id` / `source_uri` / `source_type`
  - `chunk_index` / `chunk_chars`
  - 可选：`source_relpath`、`mtime`、`size`（均建议标量或 JSON 字符串）

### 4.4 Scheme A：文本-only（默认保守）
- `include_media_stub = false`
- 行为：
  - `source_type=md`、纯文本类：进入 chunking → embedding → upsert
  - `source_type=image/video`：默认 **跳过**
- 适用：你要做文本召回质量回归、快速构建、低噪声检索

### 4.5 Scheme B：媒体 Stub 入库（当前方案）
- `include_media_stub = true`
- 行为：
  - 文本类同 Scheme A
  - 媒体类（image/video）：不做 OCR/ASR，但生成 stub 文本进入库（例如包含文件名/路径/占位符）
- 预期变化：
  - `unique_source_uri` 与 `planned_chunks` **显著增大**（媒体数量级通常远高于 md）
  - 检索 top-k 可能出现媒体 stub（这是预期行为）

### 4.6 关键参数（plan/build/check 必须一致）

#### 4.6.1 Chunking 参数
- `chunk_chars`：单 chunk 最大字符数（默认 1200）
- `overlap_chars`：相邻 chunk 重叠字符数（默认 120）
- `min_chunk_chars`：太短的 chunk 丢弃阈值（默认 200）

#### 4.6.2 Embedding / 写入参数
- `device`：`cpu` 或 `cuda:0`
- `embed_batch`：影响 embedding 峰值显存/内存（OOM 时 32→16→8）
- `upsert_batch`：影响写入期内存峰值（内存高时 256→128→64）
- `hnsw:space`：建议 `cosine`（与归一化 embedding 口径一致）

### 4.7 验收（Acceptance Criteria）

#### 4.7.1 硬验收（必须 PASS）
- `validate_rag_units.py`：PASS
- `check_chroma_build.py --plan chunk_plan.json`：PASS
  - 核心判据：`collection.count == planned_chunks`

#### 4.7.2 软验收（推荐）
- 固定 query 集的检索回归（top-k 命中与主题相关）
- `check_rag_pipeline.py`：能构造合理 messages/context，不超限

### 4.8 变更与记录要求（用于可复现）
- 每次构建必须落盘：
  - `data_processed/env_report.json`
  - `data_processed/chunk_plan.json`
  - （可选）`data_processed/build_reports/time_report_*.json`
- 推荐：把 `build_profile_*.json` 纳入版本控制；构建时在日志中打印 profile 摘要（路径 + 关键字段）

### 4.9 禁止项（为减少误报与排障成本）
- 禁止长期维护手填 `expected_chunks=xxx`
- 禁止只改 build 参数不改 plan（会导致 check 失真）
- 禁止在非项目根目录运行关键脚本（容易查错库/错产物）

---

## 5. 报告文件说明（env-plan-time，2025-12-27）

> 目的：让“这次跑了什么、跑到哪、花了多久、为什么变化”都能落盘复核。  
> 建议：所有报告统一放到 `data_processed/build_reports/`（或同目录体系）。

### 5.1 Step 1：env_report.json（环境快照）
**做什么**：通过 `tools/capture_rag_env.py` 生成 `data_processed/env_report.json`。建议每次构建前都生成一次。  
**为何（因果）**：依赖版本/驱动差异会导致性能与行为差异（尤其 GPU/torch/transformers）。环境快照能让你后续回答“为什么这次慢/为什么结果不同”。  
**字段建议**：python 版本、pip freeze、torch/cuda 信息、OS 信息、生成时间。

### 5.2 Step 2：chunk_plan.json（计划数/口径快照）
**做什么**：通过 `tools/plan_chunks_from_units.py` 生成 `data_processed/chunk_plan.json`。  
**为何（因果）**：这是 expected 的唯一合法来源；任何参数变化都应导致新的 plan。  
**关键字段**：
- `planned_chunks`（expected）
- `include_media_stub`
- `chunk_conf`
- `type_breakdown`（用来解释“为什么 source 数/块数变化”）

### 5.3 Step 3：time_report_*.json（分步计时）
**做什么**：使用计时 wrapper 生成 `data_processed/build_reports/time_report_*.json`（命令入口见 [`../howto/OPERATION_GUIDE.md` Step 5](../howto/OPERATION_GUIDE.md#step-5build向量化--upsert-入库建议用-profile-固化参数并可调-batch) 的 **Option A**）。  
**为何（因果）**：你要比较不同 `device/embed_batch/upsert_batch` 的成本时，必须有分步耗时；否则无法判断瓶颈在 embedding 还是写入。  
**关键参数/注意**：  
- Option A（计时版）与 Option B（仅 build）**二选一**，不要同时运行；若并行对比参数，必须隔离 `db/collection/state_root`。  
- `time_report_*.json` 属于时间戳文件：建议按日期归档到 `data_processed/build_reports/`，用于横向对比。  

**关键字段**：
- `total_seconds`
- 每一步 `seconds` + returncode
- 本次参数快照（device/batch/chunk 参数/include_media_stub）

### 5.4 Step 4：构建日志与失败 traceback（证据保全）
**做什么**：任何 FAIL 都将控制台输出保存为文本（含时间戳），与 `env/plan/time` 放在一起。  
**为何（因果）**：traceback + 参数 + 口径 是排障最小证据集；缺任一项都会导致“只能猜”。  
**命名建议**：`fail_build_*.txt`、`fail_check_...txt` 等。

### 5.5 对比与复盘建议（最小模板）
- 横向对比（不同机器）：
  - `device`、`embed_batch`、`total_seconds`、`build_step_seconds`
- 纵向对比（同机器不同参数）：
  - planned_chunks 是否变化（口径/数据变了？）
  - build 耗时是否按 batch 变化（瓶颈在哪？）

---

## 6. RAG 闭环骨架（工程参考）

本章说明 RAG 闭环的代码结构与调用流程，作为工程级参考。

### 6.1 目标与前提

**目标**：在不修改既有数据处理与建库脚本的前提下，构建一套 **可维护、可替换 LLM** 的 RAG 骨架，包括：

- 向量检索层（BGE-M3 + Chroma）
- Prompt 构造层（带 `[Sx]` 证据标记）
- LLM 调用层（OpenAI 兼容 `/v1/chat/completions`）
- CLI 与自检工具

**前提**：
- 已存在 Chroma 向量库：`chroma_db/`
- Collection 名称：`rag_chunks`
- 建库时使用的向量模型为：`BAAI/bge-m3`
- 当前目录为项目根目录，虚拟环境 `.venv_rag` 已激活

### 6.2 新增脚本与职责划分

| 文件名 | 职责说明 |
|---|---|
| `rag_config.py` | 全局配置：Chroma 路径、模型名、LLM 接口地址、top_k、上下文长度等 |
| `embeddings_bge_m3.py` | 封装 BGE-M3 embedding，提供 `embed_query()` |
| `retriever_chroma.py` | 使用 Chroma 检索，封装为 `retrieve(question, k)` |
| `prompt_rag.py` | 拼接检索结果为上下文，构造 ChatCompletion 格式的 `messages` |
| `llm_client_http.py` | 通过 OpenAI 兼容 `/v1/chat/completions` 接口调用本地/远程 LLM |
| `check_rag_pipeline.py` | 管线自检：检索 + 上下文 + messages（不调用 LLM） |
| `answer_cli.py` | 闭环入口：问题 → 检索 →（可选）LLM 回答 |

### 6.3 配置中心：rag_config.py

`rag_config.py` 用于集中管理所有可调参数：

```python
# Chroma 向量库配置
CHROMA_DB_PATH = "chroma_db"
CHROMA_COLLECTION = "rag_chunks"

# 向量模型配置（需要与建库时保持一致）
EMBED_MODEL_NAME = "BAAI/bge-m3"
EMBED_DEVICE = "cpu"     # 或 "cuda:0"
EMBED_BATCH = 32

# LLM 调用配置（假定为 OpenAI 兼容接口）
LLM_BASE_URL = "http://localhost:8000/v1"  # 本地/远程服务地址
LLM_API_KEY = "EMPTY"                      # 本地服务通常忽略，但字段需存在
LLM_MODEL = "qwen2.5-7b-instruct"          # 按实际模型名称调整
LLM_MAX_TOKENS = 1024

# RAG 检索与上下文拼接配置
RAG_TOP_K = 5
RAG_MAX_CONTEXT_CHARS = 12000
```

典型使用方式：
- 调整 `CHROMA_DB_PATH` / `CHROMA_COLLECTION` 即可切换不同向量库；
- 将 `LLM_BASE_URL` 指向本地 Qwen 服务 / LM Studio / vLLM 等提供的 OpenAI 兼容端点；
- `LLM_API_KEY` 可通过环境变量 `LLM_API_KEY` / `OPENAI_API_KEY` 覆盖，示例见 `.env.example`（未设置时回退为 `"EMPTY"`）；
- 调整 `RAG_TOP_K` 和 `RAG_MAX_CONTEXT_CHARS` 控制证据数量与上下文长度。

### 6.4 向量层与检索层

#### 6.4.1 向量模型封装：embeddings_bge_m3.py

职责：
- 懒加载 `BGEM3FlagModel(EMBED_MODEL_NAME, use_fp16=True, device=EMBED_DEVICE)`；
- 封装 `embed_query(text: str) -> list[float]`，用于 query embedding；

核心逻辑（示意）：

```python
from FlagEmbedding import BGEM3FlagModel
from rag_config import EMBED_MODEL_NAME, EMBED_DEVICE, EMBED_BATCH

def embed_query(text: str) -> list[float]:
    model = _get_model()  # 单例缓存
    outputs = model.encode([text], batch_size=EMBED_BATCH)
    vec = outputs["dense_vecs"][0]
    return vec.tolist()
```

#### 6.4.2 检索封装：retriever_chroma.py

职责：
- 建立 `PersistentClient(path=CHROMA_DB_PATH)`；
- 获取 `CHROMA_COLLECTION` 对应的 collection；
- 提供 `retrieve(question: str, k: int) -> List[SourceChunk]` 接口。

关键数据结构：

```python
@dataclass
class SourceChunk:
    sid: str            # 例如 "S1"、"S2"，用于回答中的 [Sx] 标记
    doc_id: str | None
    source_uri: str | None
    locator: str | None
    text: str
```

使用方式（调试）：

```bash
python retriever_chroma.py --q "存档导入与导出怎么做" --k 5
```

输出会列出每个 chunk 的标识与文本预览，便于人工评估检索效果。

### 6.5 Prompt 构造层：prompt_rag.py

#### 6.5.1 上下文拼接：build_context()

职责：
- 将若干 `SourceChunk` 拼接为一段上下文字符串；
- 每个片段以 `[Sx]` 为逻辑单位，附带 `doc_id` / `source_uri` / `locator`；
- 控制总长度不超过 `RAG_MAX_CONTEXT_CHARS`。

示意：

```python
def build_context(sources: List[SourceChunk]) -> str:
    parts = []
    total = 0
    for s in sources:
        header = f"[{s.sid}] doc_id={s.doc_id} source_uri={s.source_uri} locator={s.locator}\n"
        body = (s.text or "").strip()
        piece = header + body + "\n"

        if parts and total + len(piece) > RAG_MAX_CONTEXT_CHARS:
            break
        parts.append(piece)
        total += len(piece)
    return "\n\n".join(parts)
```

#### 6.5.2 ChatCompletion 消息构造：build_messages()

职责：
- 包装 RAG 上下文与问题为 ChatCompletion 风格的 `messages` 列表；

结构：
- `system`：定义助手角色与引用规范（只能用资料回答、用 `[Sx]` 标引用等）；
- `user`：包含上下文片段和用户问题。

示意：

```python
def build_messages(question: str, sources: List[SourceChunk]) -> list[dict]:
    context = build_context(sources)
    system = "...系统提示..."
    user = (
        "下面是与问题相关的资料片段，每个片段以 [Sx] 开头：\n\n"
        f"{context}\n\n"
        f"问题：{question}\n\n"
        "要求：...只基于上述资料回答...使用 [Sx] 标注引用..."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

### 6.6 LLM 调用层：llm_client_http.py

#### 6.6.1 协议选择：OpenAI 兼容 `/v1/chat/completions`

本项目采用 OpenAI Chat Completions 协议作为**通用接口格式**：
- 不要求使用 OpenAI 官方云模型；
- 可以指向任何提供兼容接口的服务（如本地 Qwen、LM Studio、Ollama、vLLM 等）。

#### 6.6.2 调用逻辑：call_llm()

职责：
- 将 `messages` 发送至 `LLM_BASE_URL` 指定的 `/v1/chat/completions`；
- 使用 `LLM_MODEL` 字段选择具体模型；
- 返回 `choices[0].message.content` 作为回答文本。

示意：

```python
def call_llm(messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": LLM_MAX_TOKENS,
    }
    # 使用 requests.post 发送，并处理 HTTP / JSON 错误
```

### 6.7 自检与闭环 CLI

#### 6.7.1 管线自检：check_rag_pipeline.py

用途：
- 验证“检索 + 上下文拼接 + messages 构造”流程是否正常；
- 不依赖 LLM 服务，可在未部署 LLM 时使用。

示例：

```bash
python check_rag_pipeline.py --q "存档导入与导出怎么做"
```

检查点：
- `retrieved=...`：有检索结果；
- `context_length=... (limit=12000)` 和 `STATUS: OK`；
- `messages_count=2`，并标出各 message 的内容长度。

#### 6.7.2 闭环 CLI：answer_cli.py

用途：
- 打通完整 RAG 闭环：问题 → 检索 →（可选）LLM 回答。

用法一：只看检索（不调 LLM）

```bash
python answer_cli.py --q "如何自定义资产" --only-sources
```

用法二：完整闭环（需已有 LLM 服务）

```bash
python answer_cli.py --q "如何自定义资产"
```

执行流程：
1. 使用 `retrieve()` 从 Chroma 检索 top-k 证据块；
2. 打印每个 `SourceChunk` 的 sid/doc_id/source_uri/locator 与文本预览；
3. 使用 `build_messages()` 构造 RAG prompt；
4. 使用 `call_llm()` 调用本地/远程 LLM；
5. 输出最终回答（按 system 提示使用 `[Sx]` 标引用）。

### 6.8 推荐的调试顺序

1. **先跑自检**（无 LLM）：

   ```bash
   python check_rag_pipeline.py --q "存档导入与导出怎么做"
   ```

2. **再人工检查检索结果**：

   ```bash
   python answer_cli.py --q "如何自定义资产" --only-sources
   ```

3. **最后接上 LLM，跑完整闭环**：

   ```bash
   python answer_cli.py --q "如何自定义资产"
   ```

当这三步都通过后，RAG 骨架即为“可用状态”，后续可在此基础上做：

- 检索层优化（chunk 策略、metadata 过滤、rerank）；
- LLM 侧优化（模型替换、参数调节、few-shot 增强等）。

---

## 7. 环境与依赖契约（可安装性基线）

> 目标：把“能不能装、在哪个解释器上装”写成工程契约，而不是只靠操作建议。

### 7.1 Python 版本范围（core vs embed）
- **core（Stage-1）**：仓库基线 Python >= 3.11（推荐 3.12），以确保 stdlib tomllib 可用并减少解释器差异
- **embed（Stage-2）**：**仅支持 Python < 3.13**（推荐 3.12）
- 解释：embed 依赖链包含 NumPy/pandas 等编译型包；在最新 Python 次版本过渡期，wheel 覆盖不完整会触发源码构建，导致不可预期失败。

### 7.2 wheel-only 优先策略（推荐）
- **建议**：在 embed 安装时优先使用 `--only-binary=:all:`，确保没有 wheel 就直接失败。
- **原因**：在 Windows 上源码构建常需要完整编译链路（MSVC/MinGW/Meson 等），失败会发生在深层编译阶段，定位成本高；wheel-only 能把失败前置为“契约不满足”。

### 7.3 “Defaulting to user installation...” 的含义与风险
- 含义：pip 检测到当前 site-packages 不可写，自动转为用户目录安装（通常是未激活可写 venv 或权限不足）。
- 风险：
  - 包落在用户目录，容易与 venv/系统 Python 混用；
  - 依赖版本不可控，导致“同一命令在不同 shell 行为不一致”。
- 最小规避：安装前固定解释器与 pip：
  - `python -V`
  - `python -m pip -V`
  - 在 venv 内执行 `python -m pip install ...`

### 7.4 契约性结论（必须保持）
- embed 安装入口只面向 **Python < 3.13**；
- embed 默认遵循 **wheel-only 优先**，不鼓励进入本地编译；
- 若出现 `Defaulting to user installation...`，必须先修正解释器与 venv 指向，再继续安装。

---

## 8. 关联文档（解释类与 SSOT）

- [`../explanation/HANDOFF.md`](../explanation/HANDOFF.md)：单一真源（SSOT），记录当前阶段基线口径与 workstreams；属于“当前状态快照”，不替代长期稳定契约。
- [`../explanation/handoffs/`](../explanation/handoffs/)：历史快照归档，仅用于追溯。

---

## 9. 术语与缩写（Glossary）

- Scheme A/B：构建口径的两种模式（是否对媒体类生成 stub 并入库）。
- plan：`data_processed/chunk_plan.json`，用于定义 expected 的唯一来源（`planned_chunks`）。
- stamp：`data_processed/index_state/db_build_stamp.json`，仅在写库成功后更新的完成信号。
- index_state：增量同步状态记录，用于续跑与复盘（不等同于写库完成戳）。
- SoT/SSOT：Source of Truth / Single Source of Truth，判定与基线的唯一依据。
