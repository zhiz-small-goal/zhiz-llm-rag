# `suggest_expected_sources.py` 使用说明（expected_sources 取证与推荐：基于 Chroma topK）


> **脚本位置建议**：`tools/suggest_expected_sources.py`  
> **适用日期**：2025-12-28  
> **目标**：当你不熟资料内容、无法确认某个 query 应绑定到哪篇文档时，用“检索证据”生成稳定的 `expected_sources`

---

## 1) 你问的两个关键点（先回答）

### 1.1 Step3 + Step4 是否是“完整使用流程”？
**在“只解决 expected_sources 不明确”这个子问题上**，是完整流程：  
- Step3：用检索 topK 生成候选与推荐 `expected_sources`  
- Step4：对 `eval_cases.jsonl` 做结构/路径门禁校验，避免用例集本身引入噪声

但如果你问的是“Stage-2 评测的完整流程”，还需要在 Step4 之后继续：  
- `run_eval_retrieval.py`（先稳检索）  
- `run_eval_rag.py`（再稳端到端）

---

## 2) expected_sources 的工程定义（复述一遍，避免误用）

- `expected_sources` 是“检索回归的金标准来源集合”，用于判定 hit@k。  
- 最推荐写法：**仓库内相对路径的文件级标识**（例如 `data_raw/教程/xx.md`）。  
- 为了抗检索排序抖动：允许写 **top1 + top2** 两条文件路径。  
- 不推荐：绝对路径、chunk id、行号、临时缓存路径（跨机器不稳定）。

---

## 3) 快速开始（最常用命令）

```bash
python tools/suggest_expected_sources.py --root . --query "存档导入与导出怎么做？" --db chroma_db --collection rag_chunks --k 8 --pick 2 --embed-model BAAI/bge-m3 --device cpu
```

输出包括：
- topK 列表：`rank / distance / source / snippet`
- 推荐：`recommended expected_sources`（JSON 数组，可直接复制进 eval case）

---

## 4) 参数总表（完整列出 + 是否生效的解释）

> 结论：**只有脚本 argparse 里声明的参数会生效**；输入未声明的 `--xxx` 会直接报错退出。  
> 你可以随时运行 `python tools/suggest_expected_sources.py -h` 查看实时参数列表（以脚本为准）。

| 参数 | 类型 | 默认值 | 作用 | 何时调整 |
|---|---|---:|---|---|
| `--root` | str | `.` | 项目根目录 | 不在根目录运行时必填 |
| `--query` | str | 必填 | 生成/评测的问题 | 每条用例不同 |
| `--db` | str | `chroma_db` | Chroma 持久化目录（相对 root） | 你改了 db 目录名时 |
| `--collection` | str | `rag_chunks` | Chroma collection 名 | 你 collection 名不同 |
| `--k` | int | 8 | topK 检索数量（证据窗口） | 证据分散时可增大 |
| `--pick` | int | 2 | 推荐 expected_sources 的数量（去重后取前 N） | 想更稳可用 2；证据很集中可用 1 |
| `--meta-field` | str | `source_uri|source|path|file` | 从 metadata 里取来源字段的优先级 | 你的 metadata 字段名不同 |
| `--embed-backend` | enum | `auto` | embedding 后端：`auto/flagembedding/sentence-transformers` | 依赖安装不全或你要强制某后端 |
| `--embed-model` | str | `BAAI/bge-m3` | embedding 模型名（应与建库一致） | 你建库用的不是这个模型 |
| `--device` | str | `cpu` | embedding 设备：`cpu` 或 `cuda` | 有 GPU 且模型支持时 |
| `--out` | str | 空 | 写出一份 JSON（包含 hits + 推荐） | 想归档证据或做批处理 |
| `--append-to` | str | 空 | 直接追加“用例骨架”到 jsonl | 想边取证边写用例 |
| `--must-pick` | int | 2 | 追加用例时建议写入的 must_include 数量 | 想更细或更粗时 |
| `--auto-must-include` | bool | false | 追加用例时强制写入建议 must_include（即使为空也不写 TODO） | 你希望严格自动化时 |
| `--tags` | str | `suggested` | 追加用例时的 tags | 你想分类用例 |
| `--show-snippet-chars` | int | 260 | 每条命中打印多少 snippet 字符 | 需要看更多上下文时 |

---

## 5) 参数示例大全（按目的给出可直接复制的命令）

### 5.1 只看证据（不写文件）
```bash
python tools/suggest_expected_sources.py --root . --query "如何检查 Chroma 向量库是否构建完整？"
```

### 5.2 强制使用 GPU（仅影响 embedding；需要你环境支持）
```bash
python tools/suggest_expected_sources.py --root . --query "LLM 超时如何排查？" --embed-backend flagembedding --embed-model BAAI/bge-m3 --device cuda
```

### 5.3 强制 sentence-transformers 后端（当你没装 FlagEmbedding 或想对齐 ST）
```bash
python tools/suggest_expected_sources.py --root . --query "如何检查 docs 目录格式约定？" --embed-backend sentence-transformers --embed-model BAAI/bge-m3 --device cpu
```

### 5.4 meta 字段名不一致时（例如你的 metadata 用的是 `src`）
```bash
python tools/suggest_expected_sources.py --root . --query "存档导入与导出怎么做？" --meta-field "src|source_uri|source|path|file"
```

### 5.5 证据分散时：扩大 topK，并多取一个 expected_sources
```bash
python tools/suggest_expected_sources.py --root . --query "向量库落盘与回滚怎么做？" --k 12 --pick 3
```

### 5.6 打印更长的片段（便于你肉眼确认归属）
```bash
python tools/suggest_expected_sources.py --root . --query "verify_stage1_pipeline.py 通过后下一步做什么？" --show-snippet-chars 800
```

### 5.7 把证据写到 JSON（可归档）
```bash
python tools/suggest_expected_sources.py --root . --query "如何访问本地模型的 OpenAI 兼容端点？" --out data_processed/build_reports/sources_probe_local_llm.json
```

### 5.8 直接追加用例骨架到 eval_cases.jsonl
```bash
python tools/suggest_expected_sources.py --root . --query "如何检查 Chroma 向量库是否构建完整？" --append-to data_processed/eval/eval_cases.jsonl --tags "retrieval,stage2"
```

补充：`--append-to` 会生成建议的 `must_include`；可用 `--must-pick` 调整数量，或用 `--auto-must-include` 强制不写 TODO。

---

## 6) “--device cpu” 是否一定生效？哪些参数可能看起来生效但实际没影响？

### 6.1 生效范围说明（Facts）
- `--device` **只影响 embedding 过程**（生成 query 向量），不影响 Chroma 查询本身。  
- 对 FlagEmbedding：脚本内部用 `("cuda" in device.lower())` 来决定 `use_fp16`，并不会显式设置 torch device；如果你传 `cuda` 但环境不支持，可能会在模型加载阶段报错。  
- 对 sentence-transformers：`device` 直接传给 `SentenceTransformer(..., device=...)`，一般行为更直观。

### 6.2 结论
- `--device cpu` 是确定生效的（它会走 CPU 路径）。  
- `--device cuda` 是否生效取决于你的运行环境与依赖是否支持（否则会报错）。

---

## 7) 常见故障（与参数关联）

1) `collection not found`  
- 处理：检查 `--collection` 名称是否与你建库一致。

2) 输出 `source=<EMPTY>`  
- 处理：说明 metadata 没有 `source_uri/source/path/file` 字段；调整 `--meta-field` 或回到建库流程修 metadata 写入。

3) `embed error`（模型不存在/依赖缺失）  
- 处理：确认 `--embed-model` 与本机缓存一致；或切换 `--embed-backend` 到已安装后端。

---

## 8) 与 Stage-2 完整流程的衔接（你问的“下一步”）

建议顺序（强约束→弱约束）：

1) 用本脚本确定 `expected_sources`  
2) 用 `validate_eval_cases.py --check-sources-exist` 做门禁  
3) 跑 `run_eval_retrieval.py`（hit@k）  
4) 再跑 `run_eval_rag.py`（must_include）
