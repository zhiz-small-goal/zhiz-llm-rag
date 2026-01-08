# 2026-01-04_retrieval_evolution_summary.md（最终版：口语 vs 官方术语断桥 → 可演进检索体系）

> 截至日期：2026-01-04（America/Los_Angeles）  
> 适用范围：Stage-2 Retrieval（检索与评测）  
> 输入材料：  
> - 问题记录（你提供）：`2026-01-03 口语与术语不一致导致未命中`  
> - 对话导出（你提供）：`ChatGPT-口语与术语匹配方案.md`、`ChatGPT-问题理解与思路分析.md`  
> - 仓库快照（你提供）：`Mhy_AI_RAG_data.zip`（以下 “Facts” 以该快照为准）  
>
> 说明：  
> - **Facts**：可在仓库快照中直接定位到的事实，或可由明确的外部一手资料支持。  
> - **Inference**：工程建议/推断，需要你用评测数据与回归门禁进一步验证。  
> - “成熟方案”按裁决顺序：官方/论文/源码 > 官方文档回链声明 > 多权威二手一致 > 单人解读；若冲突，优先检查是否**版本不一致**。

---

<a id="toc"></a>
## 目录
- [结论](#conclusion)
- [假设](#assumptions)
- [详细指导](#detailed-guide)
  - [Step 1 把现象固化为可复现证据](#step-1)
  - [Step 2 核验当前系统能力边界与缺口](#step-2)
  - [Step 3 机制解释：为何“口语 vs 术语”会让 dense 单路召回漏掉](#step-3)
  - [Step 4 止血：QueryNormalizer（口语→术语映射层）与可追踪证据链](#step-4)
  - [Step 5 兜底：Hybrid Retrieval + RRF 融合](#step-5)
  - [Step 6 增强：Rerank 放在 topK 之后](#step-6)
  - [Step 7 评测门禁与分桶策略](#step-7)
  - [Step 8 演进式架构：低不可逆优先与触发器](#step-8)
  - [Step 9 文档正确性与完整性核验清单](#step-9)
- [自检](#self-check)
- [失败模式与缓解](#failure-modes)
- [MRE 最小可复现](#mre)
- [替代方案](#alternatives)
- [关键结论引用字段](#references)
- [下一步行动清单](#next-actions)

---

<a id="conclusion"></a>
## 结论
要解决“口语 query 与资料内官方术语 chunk 不一致导致漏召回”，工程上**可行**的成熟路线是：先把失败现象固化为可回归用例，再用 **QueryNormalizer（术语映射/同义词扩展）**补“表达断桥”，随后以 **Hybrid（dense+keyword）+ RRF** 做召回兜底，最后再按成本引入 **rerank** 提升排序与稳定性（把每一步变成可测、可回滚的演进点）。

<a id="assumptions"></a>
## 假设
1)（默认假设）你当前 Stage-1（分块/embedding/Chroma build）已通过 `check_chroma_build.py` 或同等校验，集合与落盘一致性基本可控。  
2)（默认假设）当前 Stage-2 的主链路是“dense-only”：query → bge-m3 dense embedding → Chroma topK → hit@k 评测；尚未常驻使用 BM25/keyword 候选。  
3)（默认假设）你希望优先单机/本地可运行（Windows CMD/PowerShell），并把“引入常驻服务/分布式组件”延后到触发器命中之后。  
4)（默认假设）你能接受为关键链路补充少量结构化资产（例如 `concept_lexicon.yml`）与报告工件（例如 `eval_retrieval_report.json` 的增强字段），以换取长期可回归与可演进。

---

<a id="detailed-guide"></a>
## 详细指导

<a id="step-1"></a>
### Step 1 把现象固化为可复现证据
**做什么**：把“地图边界（口语）不命中，但用官方术语能命中”从聊天描述升级为**可复现用例**与**落盘报告**。建议先在同一环境下，用 `python -m mhy_ai_rag_data.query_cli ...` 固定 `--db/--collection/--k`，分别跑 `q_oral="如何设定地图边界？"` 与 `q_official="关卡设置 场景生效范围 可编辑范围"`，并把输出重定向到文件；随后把该用例写入 `eval_cases.jsonl`（或你现有用例集）并用 `run_eval_retrieval.py` 生成 `eval_retrieval_report.json`。  
**为何**：没有“同一索引、同一 topK、同一版本”的复现证据，就无法裁决问题发生在**召回**还是**排序**，也无法把后续修复变成回归门禁，最终会重复“修一次、漂一次”。  
**关键参数/注意**：[OFF]（仓库快照事实）`query_cli` 当前只输出 dense 检索结果与 meta 字段（doc_id/source_uri/locator）；因此你需要在报告中额外记录 “是否有映射扩展”“扩展后 query 是什么”“融合前后 topK 是什么”，否则无法定位断桥位置（映射缺失 vs 候选缺失 vs 融合无效）。

<a id="step-2"></a>
### Step 2 核验当前系统能力边界与缺口
**做什么**：用“仓库快照可定位证据”把现状边界写清楚，避免后续方案建立在错误前提上。你需要明确：  
- Stage-2 工具链是否已存在（例如 `tools/run_eval_retrieval_README.md` 描述的 hit@k 回归脚本）。  
- 当前 embedding 是否只取 `dense_vecs`（而不是 sparse/lexical weights）。  
- 当前是否存在 query 术语映射层、BM25/keyword 候选层、融合器（RRF）与 reranker。  
**为何**：同一个“口语→术语”问题，在不同底座（仅 dense / 已 hybrid / 已 rerank）上的最佳解完全不同；如果版本不一致，容易出现“对话里说要新增脚本，但仓库里其实已有入口”的反复返工。  
**关键参数/注意**：[OFF]（仓库快照事实）快照中 `mhy_ai_rag_data.embeddings_bge_m3.embed_query()` 与 `mhy_ai_rag_data.query_cli` 只使用 `outputs["dense_vecs"]`；仓库内未检出 `bm25` 相关实现与 QueryNormalizer 之类模块，因此“止血层/兜底层/融合层”应按增量方式补齐，而不是假设已存在。

<a id="step-3"></a>
### Step 3 机制解释：为何“口语 vs 术语”会让 dense 单路召回漏掉
**做什么**：把“漏召回”拆成可验证的三类缺口，并为每类缺口定义你要观测的证据字段：  
1) **表达断桥**：口语词汇与文档术语在 embedding 空间距离较远，dense 相似度不足以把目标 chunk 推进 topK。  
2) **词法断桥**：如果引入 keyword/BM25 兜底，但 query 与文档**几乎无 token 交集**（例如口语是“地图边界”，文档只写“场景生效范围/可编辑范围”），keyword 也无法制造链接。  
3) **候选窗断桥**：即使 rerank 很强，但 rerank 只能重排候选；若目标 chunk 没进入候选窗（topK/topN），rerank 无法把它“从无到有”召回。  
**为何**：这三类缺口对应三套不同投入：表达断桥优先靠映射/改写；词法断桥靠概念词典与同义词；候选窗断桥靠 hybrid 或扩大候选窗、分桶门禁。把缺口拆开后，你就能用数据决定“先做哪一层、阈值是什么”。  
**关键参数/注意**：[CON]（推断）对“地图边界”这类口语，如果文档未出现近义短语，dense-only 召回很可能受限；但是否“受限到漏召回”必须用 Step 1 的可复现实验确认（同一索引、同一 K、同一 embed 版本）。

<a id="step-4"></a>
### Step 4 止血：QueryNormalizer（口语→术语映射层）与可追踪证据链
**做什么**：实现一个**可控、可观测、可回滚**的 QueryNormalizer 层，最小化地把口语 query 扩展为“口语 + 官方术语”的组合查询，并把扩展过程写入 `retrieval_report`。推荐资产形态：`data_processed/concepts/concept_lexicon.yml`（或 json），每个 concept 至少包含：`canonical_terms`（官方术语）、`aliases`（口语别名）、`negative_terms`（避免误扩展）、`priority`（强规则/弱规则）。检索时：  
- 先对 query 做规范化（大小写、全半角、常见标点、空白）；  
- 再做 alias 匹配（可先用子串/正则起步，后续再升级分词）；  
- 若命中强规则，则追加 canonical terms；若命中弱规则，则追加但标注为“suggested”；  
- 把“命中的 concept_id、扩展后的 query、扩展置信度”写入报告。  
**为何**：同义词/术语映射是业界常见的“检索前扩展”能力，能直接修复“表达断桥”，且成本远低于训练式方案；关键在于必须可追踪，否则你无法解释“为什么这次命中了/下次又没命中”，也无法把错误映射快速回滚。  
**关键参数/注意**：[STD]/[OFF] 同义词扩展在搜索系统中通常作为索引或查询侧能力存在（例如 Azure AI Search 的 synonym map），其效果依赖于“映射表质量与作用范围”；因此你要把它当作**受控资产**管理（版本化、可 diff、可禁用），而不是散落在代码里的 if-else。

<a id="step-5"></a>
### Step 5 兜底：Hybrid Retrieval + RRF 融合
**做什么**：在保持 Chroma dense 检索不动的前提下，引入一个“keyword 候选生成器”，并用 RRF 做结果融合，形成 v2（hybrid）链路，同时保留 v1（dense-only）以便 Strangler Fig 双跑回归。实施上建议：  
1) 以 chunk 文本为语料构建一个轻量 BM25（或等价 keyword）索引（本地库或轻量服务均可，按你的资源约束选择）；  
2) 对每个 query 同时得到 `dense_topN` 与 `keyword_topN`；  
3) 用 RRF 融合得到 `fusion_topK`，并在报告中分别落盘三份列表，方便定位“谁贡献了召回”。  
**为何**：Hybrid 的价值在于让 dense 擅长的语义相似与 keyword 擅长的术语/关键词匹配互补；RRF 属于不需要训练数据、实现简单且在信息检索实验中表现稳定的融合基线，适合作为默认工程兜底。  
**关键参数/注意**：[STD]/[OFF] Weaviate 将 hybrid 定义为融合 vector search 与 BM25F keyword search，并允许配置融合权重/方法；Pinecone 文档也建议分别检索 dense 与 sparse 后再融合/（可选）rerank。你在本地实现时要保持同样的控制流：**并行召回 → 融合去重 →（可选）重排**，而不是用“keyword 结果替换 dense 结果”的互斥策略。

<a id="step-6"></a>
### Step 6 增强：Rerank 放在 topK 之后
**做什么**：当 `hit@K(fusion)` 稳定后，再把 rerank 作为“排序增强层”加在 fusion 之后（典型：fusion_top50 → rerank_top10）。优先选择能本地运行的 cross-encoder reranker（或你已有的 LLM 评分器）作为可插拔模块，并在报告中记录 rerank 前后名次变化与耗时。  
**为何**：rerank 的作用边界是“在候选窗内提高相关性排序”，对“把目标文档拉进候选窗”几乎无能为力；因此先做 hybrid/映射把 recall 稳住，再谈排序优化，能避免把算力花在“重排一堆无关候选”上。  
**关键参数/注意**：[OFF] BGE-M3 资料明确强调 reranker（cross-encoder）通常比 bi-encoder 更准，但应放在检索后作为过滤/重排；此外 BGE-M3 还支持产生类似 BM25 的 token 权重，可用于 hybrid 方案的一部分（但是否适配你的索引底座需单独验证）。

<a id="step-7"></a>
### Step 7 评测门禁与分桶策略
**做什么**：把“口语场景”从评测层显式建模，避免只用官方术语导致低估风险。推荐分桶：  
- `bucket=official`：资料术语问法（验证索引覆盖与术语召回）  
- `bucket=oral`：口语/非规范问法（验证断桥修复效果）  
- `bucket=ambiguous`：多义/短 query（验证鲁棒性与误召回风险）  
对每桶分别计算 `hit@K`、`hit@K(fusion)`、`MRR@K`、延迟 p95，并设置门禁：例如 “oral 桶 hit@20 不得低于 X、且退化不超过 Y”。  
**为何**：同一个系统在“术语桶”与“口语桶”的失败模式不同；把它们混在一起会掩盖真实用户风险。分桶后，你可以把投资目标从“整体指标更好”改为“口语桶不再系统性漏召回”，这更符合你描述的真实痛点。  
**关键参数/注意**：[CON]（推断）你可以把当前失败的“地图边界”作为 oral 桶的种子用例，并要求每个 concept 至少覆盖一对（口语/术语）query，从而让映射层与 hybrid 的收益可量化。

<a id="step-8"></a>
### Step 8 演进式架构：低不可逆优先与触发器
**做什么**：把架构投入分成“低不可逆（优先做）”与“高不可逆（触发器命中再做）”，并把触发器写成可回归的 fitness functions。  
- **低不可逆优先**：检索链路接口化（QueryNormalizer/CandidateGenerator/Fuser/Reranker/Reporter）、报告契约版本化、分桶门禁、双跑与可回滚。  
- **高不可逆延后**：引入常驻搜索服务（Elastic/OpenSearch/Weaviate）、全栈可观测（OTel/Prom）、分片/多机、训练型方案（SPLADE/微调/大规模标注）。  
触发器示例：当 `N_chunks`、`QPS`、`p95_latency`、`RAM` 超过阈值，或“离线构建耗时/失败率”超过阈值，再考虑更换底座或引入服务。  
**为何**：你要同时满足“当前资源有限”与“未来不被锁死”；低不可逆投入的核心价值是降低未来迁移成本（接口不变、组件可替换、报告可回归），而不是提前堆叠所有能力。  
**关键参数/注意**：[CON]（推断）阈值不要凭感觉定，先把 metrics 文件化并跑一段时间收集分布，再固化阈值；否则很容易把未来风险前置成当前负担。

<a id="step-9"></a>
### Step 9 文档正确性与完整性核验清单
**做什么**：针对你最初的“问题记录”文本，本节给出逐条核验与建议补全项，确保文档既正确又可落地复现。  
1) “索引覆盖与后端一致性正常”——**部分成立但证据不足**：仓库快照中确实存在 Stage-1 一致性检查脚本与 Stage-2 hit@k 评测脚本（Facts），但你提供的摘要未附带任何 run 输出或报告工件（缺口）。建议把本次失败用例加入 eval_cases，并在报告里记录 `db/collection/embed_model/k` 与 topK 列表。  
2) “问题是口语 vs 术语导致语义召回不足”——**作为 Inference 合理**：单从现象描述可推断为表达断桥，但仍需排除“过滤条件 where/metadata”“collection 名不一致”“k 太小”等工程因素；因此需要 Step 1 的同环境复现与报告字段。  
3) “评测只用官方术语会低估真实风险”——**成立**：该结论不依赖具体实现细节，属于评测设计层面事实（只要真实用户会用口语表达，就应分桶）。建议在文档中把“口语桶/术语桶”的定义与门禁阈值写为契约。  
**为何**：把“判断”拆成“已证据化的事实 + 仍需补证据的推断”，能避免文档在后续版本中漂移成“看起来正确但不可复现”的描述性总结。  
**关键参数/注意**：建议把“证据（摘要）”段落改为“证据（可定位工件）”：至少包含命令行、输出文件路径、报告 schema 版本号与一次完整 run 的时间戳。

---

<a id="self-check"></a>
## 自检
1) 我是否默认了“dense-only”而忽略了你可能已在别分支试过 hybrid？快速验证：全文搜索仓库是否存在 `bm25`/`hybrid`/`rrf` 实现与配置开关，并以实际运行日志为准。  
2) 我是否把“口语映射”当作必需，但你的领域也许更适合“结构化知识图谱/ontology”？快速验证：统计失败 query 是否集中在少量高频概念；若是，词典映射收益更高；若概念分散且长尾，可能需要学习式 rewrite。  
3) 我是否低估了“误扩展”的风险？快速验证：在 concept_lexicon 中为每条 alias 配置 negative_terms，并对 ambiguous 桶设置“误召回”指标（例如 topK 中错误文档比例）。  
4) 我是否忽略了 BGE-M3 自带 sparse/lexical 能力可作为中间过渡？快速验证：用官方示例启用 `return_sparse=True`，在候选窗内计算 lexical score 观察是否能提升“术语桶”排序，但不要把它误当作“解决口语断桥”的万能钥匙。

<a id="failure-modes"></a>
## 失败模式与缓解
1) **映射误召回上升**：现象是 oral 桶 hit@K 上升但 unrelated 文档进入 topK。原因通常是 alias 过宽或未配置 negative_terms。缓解：把规则分级（强/弱）、加黑名单、记录命中链路；备选：改为“候选扩展但低权重融合”，而不是直接替换 query。  
2) **Hybrid 融合无收益**：现象是 fusion 与 dense 结果几乎相同。原因可能是 keyword 候选质量差（分词/停用词/语料过短）或 query 与文档 token 交集过低。缓解：先用“术语桶”验证 keyword 能否在有交集时贡献召回；备选：把 keyword 改为“领域词典倒排”或“手工概念标签检索”。  
3) **Rerank 成本过高**：现象是 p95 延迟显著上升。原因是候选窗过大或 reranker 模型过重。缓解：缩小候选窗（top50→top20）、缓存热门 query、批处理；备选：只对 oral 桶启用 rerank，或使用更轻量的 reranker。  
4) **报告不可对比导致漂移**：现象是“修复后看起来更好但无法解释”。原因是 report schema/字段随意变更。缓解：为报告定义 schema 版本号与必填字段；备选：把报告输出写成独立工具并在 CI 门禁中校验格式。

<a id="mre"></a>
## MRE 最小可复现
**运行环境（示例）**：Windows 10/11 + Python（以你项目实际 venv 为准）+ 已构建的 Chroma DB（`--db chroma_db --collection rag_chunks`）。  
**核心命令**：  
1) 口语 query：  
   - `python -m mhy_ai_rag_data.query_cli --db chroma_db --collection rag_chunks --k 20 --q "如何设定地图边界？"`  
2) 术语 query：  
   - `python -m mhy_ai_rag_data.query_cli --db chroma_db --collection rag_chunks --k 20 --q "关卡设置 场景生效范围 可编辑范围"`  
3) 评测落盘（若已准备 eval_cases）：  
   - `python -m mhy_ai_rag_data.tools.run_eval_retrieval --cases data_processed/eval_cases.jsonl --out data_processed/build_reports/eval_retrieval_report.json`  
**期望输出**：在未引入 QueryNormalizer/hybrid 前，oral 用例可能 `hit@20=false`；术语用例应更可能 `hit@20=true`。引入映射/融合后，应能观察到 oral 桶 hit@K 的稳定提升，并能在报告中解释“是映射贡献还是 keyword 贡献”。

<a id="alternatives"></a>
## 替代方案

### 替代方案 A：最低改动的“规则化映射 + 单机 Hybrid + RRF”（推荐作为工程基线）
**适用场景**：本地单机、数据规模中小、你需要快速把口语断桥变成可回归并逐步稳定。  
**代价/限制**：需要维护 concept_lexicon 资产；keyword 索引需要额外构建与更新；对极长尾口语表达，规则覆盖有限。  
**优势**：完全可控、可回滚、无需训练数据；符合“低不可逆优先”的演进路线。

### 替代方案 B：更高成本的“学习式 reranker +（可选）学习式 query rewrite/ontology”
**适用场景**：口语表达长尾明显、概念词典维护成本过高、且你能获得标注数据或可靠的合成数据。  
**代价/限制**：需要标注/合成与评测体系，训练与部署复杂度显著上升；若候选窗不稳，模型收益被上游掩盖。  
**优势**：在长尾与多义场景更有潜力；可与 hybrid 叠加提升整体相关性。

<a id="references"></a>
## 关键结论引用字段
> 注：以下为“一手资料”引用字段，供你在设计文档/工单中直接粘贴；日期为本次整理时的访问日期或文档发布时间。

1) **Hybrid Search（向量 + BM25F 融合）**  
- URL：`https://docs.weaviate.io/weaviate/search/hybrid`  
- 日期/版本：访问于 2026-01-04（Weaviate Docs）  
- 来源类型：官方文档（OFF）  
- 定位：页面标题 *Hybrid search*（说明“vector + keyword(BM25F) + fusion 可配置”）

2) **Hybrid Search 的推荐控制流（dense 与 sparse 分开检索后融合/可选 rerank）**  
- URL：`https://docs.pinecone.io/guides/search/hybrid-search`  
- 日期/版本：访问于 2026-01-04（Pinecone Docs）  
- 来源类型：官方文档（OFF）  
- 定位：页面标题 *Hybrid search*（说明“separate dense and sparse indexes → combine/deduplicate → optional rerank”）

3) **同义词映射用于查询扩展（synonym map）**  
- URL：`https://learn.microsoft.com/en-us/azure/search/search-synonyms`  
- 日期/版本：页面显示 *Last updated on 2025-04-14*，访问于 2026-01-04  
- 来源类型：官方文档（OFF）  
- 定位：页面标题 *Add synonyms to expand queries for equivalent terms*（说明“query 可以命中 synonym map 中等效术语”）

4) **RRF（Reciprocal Rank Fusion）作为无监督融合基线**  
- URL：`https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf`  
- 日期/版本：SIGIR 2009（论文），访问于 2026-01-04  
- 来源类型：论文（STD/Primary）  
- 定位：论文标题 *Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods*（提出 RRF 并报告其作为融合基线的效果）

5) **BGE-M3 支持稀疏检索与 lexical weights（可用于 hybrid 的 token 权重）**  
- URL：`https://huggingface.co/BAAI/bge-m3`  
- 日期/版本：访问于 2026-01-04（Hugging Face model card）  
- 来源类型：模型卡/官方说明（OFF/Primary）  
- 定位：*Some suggestions for retrieval pipeline in RAG* 与 *Sparse Embedding (Lexical Weight)* 小节（明确提到“hybrid retrieval + re-ranking”、以及“token weights (similar to the BM25)”）

<a id="next-actions"></a>
## 下一步行动清单
1) 把“地图边界”用例加入 eval_cases，并跑出一份可对比的 `eval_retrieval_report.json`（先不改算法）。  
2) 先实现 QueryNormalizer（最小词典 + 报告落盘），把“映射命中链路”变成可观测字段。  
3) 引入 keyword 候选与 RRF 融合，双跑 v1/v2，先以 `hit@K(fusion)` 作为首要门禁。  
4) 分桶上线（official/oral/ambiguous），并把门禁阈值写入 CI/PR gates（先宽后严）。  
5) 在 recall 稳定后再加 rerank，并为延迟/资源成本设置约束（例如 p95 预算）。  
6) 采集一段时间 metrics 分布后，固化“何时升级底座”的触发器阈值（避免凭感觉迁移）。
