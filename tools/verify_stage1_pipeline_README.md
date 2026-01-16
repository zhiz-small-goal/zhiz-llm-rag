# `verify_stage1_pipeline.py` 使用说明（Stage-1 一键验收/回归）


> **适用日期**：2025-12-28  
> **适配脚本**：`tools/verify_stage1_pipeline.py`（已将该脚本放入 `tools/` 目录）  
> **用途定位**：在进入“下一阶段”之前，快速回答一个问题：**阶段一闭环链路是否仍然完整可复现**（产物齐全、Chroma 写入完整、LLM 端点可用）。

---

## 1. 背景与目标

在阶段一，已经分别验证过：

- **数据处理中间产物**：`data_processed/text_units.jsonl`、`data_processed/chunk_plan.json`
- **向量库落盘**：`chroma_db/` + `rag_chunks` collection
- **LLM 服务可用**：LM Studio 提供 OpenAI-compatible endpoint（如 `http://localhost:8000/v1`）

随着工程进入下一阶段（更多批量文档、更多脚本协作、更多人/机器环境），最常见的问题不是“功能是否存在”，而是“**改动后是否退化**”。  
本工具将上述关键点合并为一条命令执行的“回归/验收门禁”，并固化为可审计的 JSON 报告。

---

## 2. 工具做什么、不做什么

### 2.1 做什么（Checks）

运行一次命令，会执行三类检查（其中后两类为可选）：

1) **Artifacts 检查（必做）**  
- 检查以下文件是否存在：  
  - `data_processed/text_units.jsonl`  
  - `data_processed/chunk_plan.json`
- 输出轻量统计：  
  - `text_units.jsonl` 行数（行计数，不解析内容）  
  - `chunk_plan.json` 计划 chunk 数（支持 `{"chunks":[...]}` 或 list 形态）

2) **Chroma 一致性检查（可选，依赖 `chromadb`）**  
- 打开 `<root>/<db>`（默认 `chroma_db/`）  
- 读取 `<collection>`（默认 `rag_chunks`）并取 `collection.count()`  
- 将 `collection.count()` 与 `chunk_plan.json` 的 planned_chunks 对比  
- 目标：保证 **expected_chunks == embeddings_in_collection**（阶段一核心完整性约束）

3) **LLM 端点探测（可选，依赖 `requests`）**  
- `GET {base_url}/models`（例如 `http://localhost:8000/v1/models`）  
- `POST {base_url}/chat/completions` 发送极小请求（`ping` + `max_tokens=8`）  
- 目标：保证 OpenAI-compatible 协议链路可用，尽早暴露 502/timeout/端口错误等问题

### 2.2 不做什么（Non-goals）

- 不评估“答案质量”，不做自动打分；它验证的是 **链路完整性与可用性**  
- 不重建 Chroma、不生成 text_units / chunk_plan；只做验收  
- 不解析 `text_units.jsonl` 的具体字段正确性（仅计数/存在性）  
- 不尝试纠正你本地 LLM 的模型名兼容性（只要端点能返回有效响应即可）

---

## 3. 目录约定与前置条件

### 3.1 典型目录结构

以项目根目录（`--root`）为基准：

```
<root>/
  data_processed/
    text_units.jsonl
    chunk_plan.json
    build_reports/
      stage1_verify.json        # 本工具生成
  chroma_db/                     # 可选：存在则可做 Chroma 检查
  tools/
    verify_stage1_pipeline.py    # 本工具（你已放到 tools/）
```

### 3.2 前置条件

- Python 3.x（建议与你们项目 venv 一致）
- 若要启用 **Chroma 检查**：环境中可 `import chromadb`
- 若要启用 **LLM 探测**：环境中可 `import requests`，且 LLM 服务已启动

---

## 4. 快速开始（推荐工作流）

### Step 1：在项目根目录运行（最常用）

> Windows PowerShell / cmd 均可；示例以 PowerShell 为例。  
> 关键点：`--root .` 代表“以当前目录作为项目根目录”。

```bash
python tools/verify_stage1_pipeline.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --timeout 10
```

**为什么这样做**：  
- `artifacts` 作为真源（`text_units`、`chunk_plan`）先验收；  
- 若 `chroma_db/` 存在则对齐 `planned_chunks`；  
- LLM 探测把“端点不通”在最外层提前暴露，避免你到 RAG CLI 才发现问题。

### Step 2：查看控制台结果与 JSON 报告

运行结束后你会看到类似：

- `overall=PASS/FAIL`
- 每个检查项的 PASS/FAIL
- 报告路径：`data_processed/build_reports/stage1_verify.json`

---

## 5. 命令行参数详解

| 参数 | 默认值 | 作用 | 关键注意 |
|---|---:|---|---|
| `--root` | `.` | 项目根目录（包含 `data_processed/`） | 建议始终显式指定，避免误在子目录运行 |
| `--db` | `chroma_db` | Chroma 持久化目录名 | 是目录名而不是绝对路径（相对于 `--root`） |
| `--collection` | `rag_chunks` | Chroma collection 名称 | 需与你构建索引时一致 |
| `--base-url` | `http://localhost:8000/v1` | OpenAI-compatible base URL | 建议固定为你团队统一约定 |
| `--timeout` | `10` | HTTP timeout（秒） | 端点冷启动时可适当增大 |
| `--skip-chroma` | false | 跳过 Chroma 检查 | 当 chromadb 未安装或 db 不在本机时使用 |
| `--skip-llm` | false | 跳过 LLM 探测 | 当 LM Studio 未启动或你只想验收索引侧时使用 |

---

## 6. 输出说明（stdout + JSON）

### 6.1 标准输出（stdout）

脚本会打印：

- 总体结果：`overall=PASS/FAIL`
- 报告文件位置
- 三个检查项各自的 PASS/FAIL

你可以用**退出码**做自动化门禁：

- `0`：全部检查通过（PASS）
- `2`：任一检查失败（FAIL）

### 6.2 JSON 报告（`data_processed/build_reports/stage1_verify.json`）

报告顶层结构（简化示意）：

```json
{
  "timestamp": "2025-12-28T12:34:56+0800",
  "root": "...",
  "overall": "PASS",
  "checks": {
    "artifacts": { "ok": true, "details": { ... } },
    "chroma":    { "ok": true, "details": { ... } },
    "llm":       { "ok": true, "details": { ... } }
  }
}
```

#### artifacts.details 常见字段
- `required`: 必需文件清单
- `missing`: 缺失文件
- `text_units_lines`: `text_units.jsonl` 行数
- `planned_chunks`: 从 `chunk_plan.json` 推导的 chunks 数

#### chroma.details 常见字段
- `enabled`: 是否启用（db 存在且 `chromadb` 可 import）
- `db_path`: 实际 db 路径
- `collection`: collection 名
- `planned_chunks`: 计划 chunks 数
- `collection_count`: Chroma collection 实际 count
- `match`: 是否对齐（planned_chunks 不为空时）

#### llm.details 常见字段
- `enabled`: 是否启用（`requests` 可 import）
- `get_models_status`: `GET /models` 状态码
- `chat_status`: `POST /chat/completions` 状态码
- `chat_has_choices`: 是否返回 choices（协议层 sanity）

---

## 7. 常用场景（建议直接复制）

### 7.1 只验收中间产物（不要求本机有 db/llm）
当你在“资料处理机”或“仅处理文本的环境”：

```bash
python tools/verify_stage1_pipeline.py --root . --skip-chroma --skip-llm
```

### 7.2 只验收 Chroma（LLM 不在本机）
当你只关注索引落盘是否完整：

```bash
python tools/verify_stage1_pipeline.py --root . --skip-llm
```

### 7.3 只探测 LLM（用于模型机健康检查）
当你只想确认 LM Studio endpoint 可用：

```bash
python tools/verify_stage1_pipeline.py --root . --skip-chroma
```

### 7.4 在 CI 或脚本门禁里使用（基于退出码）
示意（伪代码）：

```bash
python tools/verify_stage1_pipeline.py --root . --skip-llm
if [ $? -ne 0 ]; then
  echo "Stage-1 verify failed"
  exit 1
fi
```

> 说明：CI 环境通常不适合下载/加载大模型，因此常见做法是 `--skip-llm` 或使用 mock endpoint。

---

## 8. 设计原理（为什么这样检查）

### 8.1 “Artifacts 是单一真源”
`text_units.jsonl` 与 `chunk_plan.json` 是你们阶段一从源文档到索引构建的关键中间产物。  
将其作为验收起点，可以把“数据层失败”与“索引层失败”分离：缺产物则直接 FAIL，不必进入后续检查。

### 8.2 “planned_chunks == collection.count 是最小完整性约束”
该约束不评价召回质量，但能排除最常见的“漏写/中断/collection 名错/参数不一致”等基础故障。  
在你们体系中，它等价于你之前已使用的验收口径：`expected_chunks == embeddings_in_collection`。

### 8.3 LLM 探测只验证“协议链路”，不验证“模型语义”
对阶段门禁而言，LLM 探测的最重要信号是：  
- 端点是否能稳定响应（无 502/timeout）  
- 协议格式是否成立（是否能返回 choices）  
语义质量属于下一阶段的评测体系（回归题集/评分规则）的范畴。

---

## 9. 故障排查（现象 → 原因 → 处理）

### 9.1 artifacts FAIL：missing 文件
- **现象**：`missing` 列表里出现 `text_units.jsonl` 或 `chunk_plan.json`
- **原因**：未生成；或 `--root` 指错；或你在子目录运行
- **处理**：回到项目根目录；确认产物生成流程已跑完；必要时显式指定 `--root <path>`

### 9.2 chroma FAIL：db path not found
- **现象**：`reason: db path not found: ...`
- **原因**：本机没有 `chroma_db/`；或目录名不同
- **处理**：确认 `--db` 与实际目录一致；若本机不需要，使用 `--skip-chroma`

### 9.3 chroma FAIL：chromadb import failed
- **现象**：`reason: chromadb import failed: ...`
- **原因**：环境未安装 `chromadb`
- **处理**：安装依赖；或使用 `--skip-chroma`

### 9.4 llm FAIL：timeout / 非 2xx
- **现象**：`get_models_error` 或 `chat_error`，或 status 不是 2xx
- **原因**：LM Studio 未启动；端口/base_url 不对；代理/防火墙；冷启动超时
- **处理**：确认 base URL；提高 `--timeout`；先用你们已有 `tools.probe_llm_server` 单测；必要时 `--skip-llm`

---

## 10. 与现有工具/脚本的关系（推荐用法）

| 目的 | 原有做法 | 本工具的角色 |
|---|---|---|
| 验证 Chroma 构建完整性 | `check_chroma_build.py` | 将一致性检查纳入一键门禁（仍建议保留原脚本做深度排障） |
| 验证 LLM 端点可用 | `tools.probe_llm_server.py` | 提供轻量探测，减少手工步骤；深度探测仍建议用 probe 脚本 |
| 验证检索命中 | `retriever_chroma.py` | 本工具不做语义命中；命中验证属于下一阶段的评测/回归题集 |

---

## 11. 最小可复现（MRE）

**环境**：Python 3.x；项目根目录存在 `data_processed/`  
**命令**：

```bash
python tools/verify_stage1_pipeline.py --root . --skip-chroma --skip-llm
```

**期望**：生成 `data_processed/build_reports/stage1_verify.json`，且 `artifacts` 为 PASS。

---

## 12. 变更建议（进入下一阶段前可选）

若希望把“构建参数/模型版本/collection 元信息”固化进报告（用于 drift 定位），建议在后续版本中加入：

- 记录 chunking 参数（chunk_chars 等）与 embed 模型标识（含本地文件 hash 或下载信息）
- 将 `build_chroma_index.py` 的关键参数写入同一份 build report
- 为 LLM probe 加入服务端模型列表摘要（只记录 id，不记录大文本）

这些属于“可审计构建记录”的工程化增强，不影响当前阶段一门禁的基本有效性。

## 代理与超时（重要）
- 新增参数：
  - `--connect-timeout`：连接超时（默认 10）
  - `--timeout`：读取超时（默认 10；若模型生成慢建议 60~120）
  - `--trust-env`：是否信任环境代理（auto/true/false）。默认 auto：回环地址自动不走代理。

示例：
```bash
python tools/verify_stage1_pipeline.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --connect-timeout 10 --timeout 10 --trust-env auto
```
