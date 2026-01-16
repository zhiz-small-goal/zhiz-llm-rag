---
title: run_rag_eval_batch.py 使用说明（批量 RAG 评估）
version: v2.0
last_updated: 2026-01-16
---

# run_rag_eval_batch.py 使用说明


> 目标：批量运行多个查询的 RAG 评估任务，支持检索、管道和答案生成的端到端测试，生成结构化评估报告。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [输入文件格式](#输入文件格式)
- [输出报告说明](#输出报告说明)
- [退出码](#退出码)
- [示例](#示例)
- [评估维度](#评估维度)
- [常见问题](#常见问题)

## 目的

本工具用于批量评估 RAG 系统性能，通过运行多个预定义查询并收集结果，帮助你：

- **批量检索测试**：对一组查询进行检索召回测试
- **管道完整性检查**：验证整个 RAG 管道是否正常工作
- **答案生成评估**：可选地测试 LLM 答案生成质量
- **性能基线建立**：记录每个步骤的耗时和返回码
- **关键词覆盖检查**：启发式验证结果是否包含预期关键词

## 适用场景

- **回归测试**：代码变更后验证 RAG 系统是否退化
- **性能监控**：定期运行以跟踪检索和生成性能
- **A/B 测试**：对比不同配置（k值、模型等）的效果
- **问题排查**：通过批量测试快速定位问题查询

## 前置条件

1. **依赖脚本**（需在项目根目录可用）：
   - `retriever_chroma.py` - Chroma 检索器
   - `check_rag_pipeline.py` - RAG 管道检查（可选）
   - `answer_cli.py` - 答案生成（可选）

2. **查询文件**：JSON 格式的查询定义文件（见下文格式说明）

3. **Chroma DB**：已构建的向量数据库

## 快速开始

### 1) 仅检索评估
```cmd
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 5
```

### 2) 检索 + 管道检查
```cmd
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 5 --pipeline
```

### 3) 完整评估（包含答案生成）
```cmd
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 5 --pipeline --answer
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--queries` | `tests/rag_queries_v1.json` | 查询定义文件（JSON 格式） |
| `--k` | `5` | 检索返回的 top-k 文档数量 |
| `--pipeline` | *(flag)* | 是否运行管道完整性检查 |
| `--answer` | *(flag)* | 是否运行答案生成评估 |

## 输入文件格式

查询文件为 JSON 格式，支持两种结构：

### 格式 1：直接数组（推荐）

```json
[
  {
    "id": "query_001",
    "q": "如何配置 RAG 系统？",
    "expect_keywords": ["配置", "RAG", "参数"]
  },
  {
    "id": "query_002",
    "q": "向量数据库的工作原理是什么？",
    "expect_keywords": ["向量", "数据库", "embedding"]
  }
]
```

### 格式 2：带 items 字段的对象

```json
{
  "items": [
    {
      "id": "query_001",
      "query": "如何配置 RAG 系统？",
      "expect_keywords": ["配置", "RAG", "参数"]
    },
    {
      "id": "query_002",
      "query": "向量数据库的工作原理是什么？",
      "expect_keywords": ["向量", "数据库", "embedding"]
    }
  ]
}
```

**字段说明**：
- `id`：查询唯一标识符
- `q` 或 `query`：待评估的查询文本（两者都支持）
- `expect_keywords`：（可选）预期在输出中出现的关键词列表，用于启发式验证
- `k`：（可选）单个查询的 top-k 设置，会覆盖命令行的 `--k` 参数
- `notes`：（可选）备注信息

## 输出报告说明

报告生成在 `data_processed/build_reports/rag_eval_<timestamp>.json`

### 报告结构

```json
{
  "generated_at": "2026-01-16T14:30:00",
  "queries_file": "tests/rag_queries_v1.json",
  "k": 5,
  "pipeline": false,
  "answer": false,
  "results": [
    {
      "id": "query_001",
      "query": "如何配置 RAG 系统？",
      "expect_keywords": ["配置", "RAG", "参数"],
      "steps": {
        "retriever": {
          "cmd": ["python", "retriever_chroma.py", "--q", "...", "--k", "5"],
          "returncode": 0,
          "seconds": 1.23,
          "stdout": "retrieved=5\nS0: doc_id=... source_uri=...\n..."
        }
      },
      "retrieval": {
        "retrieved": 5,
        "hits": [
          {"doc_id": "...", "source_uri": "...", "distance": "0.123"}
        ]
      },
      "heuristic": {
        "keywords_in_output": {
          "hit": 2,
          "total": 3,
          "misses": ["参数"]
        }
      }
    }
  ]
}
```

### 关键字段解释

- `steps.<step_name>`：每个步骤的执行详情
  - `cmd`：实际执行的命令
  - `returncode`：退出码（0 表示成功）
  - `seconds`：执行耗时
  - `stdout`：标准输出内容

- `retrieval`：检索结果解析
  - `retrieved`：实际召回数量
  - `hits`：召回文档列表及其元数据

- `heuristic.keywords_in_output`：关键词匹配
  - `hit`：命中的关键词数量
  - `total`：预期关键词总数
  - `misses`：未命中的关键词列表

## 退出码

- `0`：PASS（所有查询已处理，报告已生成）
- `2`：FAIL（查询文件不存在或读取失败）

**注意**：即使某些查询的检索或生成失败，脚本仍会返回 0，具体失败信息记录在报告的 `returncode` 字段中。

## 示例

### 示例 1：基础检索评估

```cmd
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 3
```

**输出**：
```
[OK] query_001: retriever rc=0 (1.23s)
[OK] query_002: retriever rc=0 (0.98s)
[OK] query_003: retriever rc=0 (1.45s)
REPORT: F:\zhiz-c++\zhiz-llm-rag\data_processed\build_reports\rag_eval_20260116_143000.json
```

### 示例 2：不同 k 值对比

```cmd
rem 测试 k=3
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 3

rem 测试 k=10
python tools\run_rag_eval_batch.py --queries tests\rag_queries_v1.json --k 10

rem 对比两份报告，查看检索召回差异
```

### 示例 3：完整端到端评估

```cmd
python tools\run_rag_eval_batch.py --queries tests\rag_queries_comprehensive.json --k 5 --pipeline --answer
```

## 评估维度

### 1. 检索性能
- **召回率**：实际返回的文档数 vs 期望数量
- **响应时间**：检索耗时（`seconds` 字段）
- **成功率**：`returncode=0` 的查询比例

### 2. 关键词覆盖（启发式）
- **命中率**：`heuristic.keywords_in_output.hit / total`
- **缺失关键词**：`heuristic.keywords_in_output.misses`

### 3. 管道完整性（可选）
- **管道状态**：`steps.pipeline.returncode`
- **端到端耗时**：检索 + 管道处理总时间

### 4. 答案生成（可选）
- **生成状态**：`steps.answer.returncode`
- **生成耗时**：LLM 调用时间

## 常见问题

### 1) `[FATAL] queries not found`
**原因**：查询文件路径不存在

**处理**：
```cmd
rem 检查文件是否存在
dir tests\rag_queries_v1.json

rem 或使用绝对路径
python tools\run_rag_eval_batch.py --queries F:\path\to\queries.json
```

### 2) 部分查询失败（`returncode != 0`）
**处理**：
1. 查看报告中的 `steps.retriever.stdout` 定位错误信息
2. 单独运行失败的查询进行调试：
   ```cmd
   python retriever_chroma.py --q "失败的查询文本" --k 5
   ```

### 3) 所有查询的关键词 `hit=0`
**可能原因**：
- 关键词定义过于严格或拼写错误
- 检索结果质量不佳
- `expect_keywords` 与实际返回内容不匹配

**处理**：检查报告中的 `retrieval.hits` 和 `heuristic.misses`，调整关键词列表

### 4) 想查看中间过程的详细日志
**处理**：报告中的 `steps.<step>.stdout` 包含完整的标准输出，可直接查看

### 5) 评估速度太慢
**优化**：
- 减少查询数量（拆分成多个小批次）
- 降低 `--k` 值
- 去掉 `--answer` 选项（LLM 生成通常最耗时）

## 与其他工具的关系

- **依赖**：`retriever_chroma.py`、`check_rag_pipeline.py`、`answer_cli.py`
- **输入**：查询 JSON 文件（可用工具生成或手工编写）
- **输出**：结构化报告（可用 `jq` 或自定义脚本分析）
- **下游**：报告可用于生成可视化图表、监控仪表板等

## 最佳实践

1. **版本化查询集**：将查询文件纳入版本控制，便于追踪评估历史
2. **定期运行**：在 CI 中定期运行基础查询集，建立性能基线
3. **逐步加载**：先运行 `--k 5` 快速验证，再根据需要增加 `--pipeline` 或 `--answer`
4. **保留报告**：定期归档评估报告，用于长期性能趋势分析
5. **关键词维护**：根据实际检索结果持续更新 `expect_keywords`

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/run_rag_eval_batch.py`。
