---
title: OPERATION GUIDE（运行手册）
version: v1.0
last_updated: 2026-01-13
---

# OPERATION_GUIDE目录：


- [OPERATION\_GUIDE目录：](#operation_guide目录)
  - [1) 详细指导（按 Step 组织）](#1-详细指导按-step-组织)
    - [Step 0：环境与依赖安装（core vs embed）——避免在 Python 3.13 及以上误装 Stage-2](#step-0环境与依赖安装core-vs-embed避免在-python-313-及以上误装-stage-2)
    - [Step 1：理解 Scheme B 的“口径契约”（先明确你要建的是什么库）](#step-1理解-scheme-b-的口径契约先明确你要建的是什么库)
  - [**数目漂移**: 详情见补充说明](#数目漂移-详情见补充说明)
    - [Step 2：目录与产物约定（避免“查错库/混用旧产物”）](#step-2目录与产物约定避免查错库混用旧产物)
    - [Step 3：从 inventory.csv 生成 units（extract）并做硬校验（validate 必须 PASS）](#step-3从-inventorycsv-生成-unitsextract并做硬校验validate-必须-pass)
    - [Step 4：plan（dry-run）——用“同参数计划数”取代手填 expected](#step-4plandry-run用同参数计划数取代手填-expected)
    - [Step 5：build（向量化 + upsert 入库）——建议用 profile 固化参数并可调 batch](#step-5build向量化--upsert-入库建议用-profile-固化参数并可调-batch)
    - [Step 6：check（强校验）——以 plan 为准做 PASS/FAIL 判定](#step-6check强校验以-plan-为准做-passfail-判定)
    - [Step 7：质量回归（检索层）——Scheme B 下要学会“隔离变量”](#step-7质量回归检索层scheme-b-下要学会隔离变量)
    - [Step 8：闭环（RAG pipeline + 本地模型）——先验证请求体，再验证 LLM](#step-8闭环rag-pipeline--本地模型先验证请求体再验证-llm)
    - [Step 9：Stage-1 一键验收（verify）——把“能否进入下一阶段”变成门禁](#step-9stage-1-一键验收verify把能否进入下一阶段变成门禁)
    - [Step 10：Stage-1 基线快照（snapshot）——为“漂移归因”留证据](#step-10stage-1-基线快照snapshot为漂移归因留证据)
    - [Step 11：Stage-2 评测体系（cases → 取证 → 门禁 → 评测 → 汇总）](#step-11stage-2-评测体系cases--取证--门禁--评测--汇总)
    - [Step 12：文档工程门禁（docs 规范与链接可用性）](#step-12文档工程门禁docs-规范与链接可用性)
    - [Step 13：JSON 报告 schema 自检（用于回归/CI）](#step-13json-报告-schema-自检用于回归ci)
  - [2) 替代方案（1–2 个：适用场景 + 代价/限制）](#2-替代方案12-个适用场景--代价限制)
    - [方案 A：文本-only（include\_media\_stub=false）](#方案-a文本-onlyinclude_media_stubfalse)
    - [方案 C：双库分层（文本库 + 全量库）](#方案-c双库分层文本库--全量库)
  - [计时与报告落盘](#计时与报告落盘)
  - [LLM 服务探测（probe）](#llm-服务探测probe)
  - [inventory.csv 补充说明](#inventorycsv-补充说明)


---

## 1) 详细指导（按 Step 组织）

> 注意：本仓库已切换为 **src-layout**。`src/mhy_ai_rag_data/` 是权威实现位置；根目录与 `tools/` 下同名脚本是 wrapper（兼容旧用法）。
> 推荐 `pip install -e .` 后使用 `rag-plan / rag-build / rag-check / rag-check-all` 等命令，或使用 `python -m mhy_ai_rag_data...`。



### Step 0：环境与依赖安装（core vs embed）——避免在 Python 3.13 及以上误装 Stage-2
**做什么**：把安装与运行分成两条“可审计的路径”。**core/Stage-1**（inventory→units→plan→validate 等轻逻辑）允许在较新 Python 上安装：在仓库根目录执行 `python -m pip install -e .` 即可；**embed/Stage-2**（embedding/chroma/检索闭环）仅在 **Python 3.12（<3.13）** 安装与运行：建议单独创建 `.venv_embed` 后执行 `python -m pip install -e ".[embed]"`。本仓库对 `.[embed]` 增加了 fail-fast 保护：在 Python 3.13 及以上请求 `.[embed]` 会在安装期直接失败（避免回溯到无 wheel 版本并触发本地编译）。
失败时最小排查清单[详细问题信息](../postmortems/2025-12-30_postmortem_pip_embed_py314_numpy_meson_fail.md)

**为何（因果）**：embedding/chroma 依赖链会牵涉 NumPy/pandas 等编译型包；在最新 Python 次版本（如 3.14）生态过渡期，解析器回溯可能把你带到“只能源码构建”的组合，进而被本机编译器链路击穿。将 **core 与 embed 分层**可以把不稳定性限制在可选 extra 内：你仍可在新 Python 上跑 Stage-1 工具链，但 Stage-2 永远在“wheel 覆盖成熟”的解释器上执行，从而把安装失败从“长日志排障”变成“安装期明确拒绝”。

**关键参数/注意**：始终用 `python -m pip ...`（避免 PATH 抢占导致用错解释器）；执行任何安装前先 `python -V` 与 `python -m pip -V` 确认正在使用目标 venv。若你想彻底禁止源码构建，可在 Stage-2 安装时加 `--only-binary=:all:` 作为硬护栏。

**如需 GPU**：先安装 PyTorch 官方 CUDA 版 torch（见下方示例），再安装 `.[embed]`；否则会默认拉取 CPU-only torch。
装完使用 `python tools\verify_torch_cuda.py` 检测, 如果出现 `torch_cuda_buidl=<版本号>` `[RESULT] PASS` 即视为安装通过, GPU 可用.

**推荐命令（Windows CMD）**：
```cmd
:: core / Stage-1（当前解释器即可）
python -m pip install -U pip setuptools wheel
python tools\check_pyproject_preflight.py --ascii-only
python -m pip install -e .

:: embed / Stage-2（推荐 Python 3.12 venv）
py -3.12 -m venv .venv_embed
.\.venv_embed\Scripts\activate
python -m pip install -U pip setuptools wheel
python tools\check_pyproject_preflight.py --ascii-only

:: GPU（CUDA）：先装 CUDA 版 torch（示例：CUDA 13.0 / cu130 无代理直连）
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:ALL_PROXY=""
python -m pip install --upgrade --force-reinstall --no-cache-dir --retries 5 --timeout 120 torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple

:: 走代理稳定下载
$env:HTTP_PROXY="http://127.0.0.1:7890"; $env:HTTPS_PROXY="http://127.0.0.1:7890"
python -m pip install --upgrade --force-reinstall --no-cache-dir --retries 10 --timeout 180 torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple --proxy http://127.0.0.1:7890
:: 下载完检查
python tools\verify_torch_cuda.py

python -m pip install -e ".[embed]"
```
**常见依赖冲突（pip resolver 提示）**：若出现 `datasets ... requires fsspec[http]<=2025.10.0` 之类警告，通常是 CUDA 版 torch 的依赖链把 `fsspec` 升到 `2025.12.0` 导致上限不满足。推荐用**单指令**一次性装齐并锁住 `fsspec` 上限（避免冲突）：
```cmd
python -m pip install --upgrade --force-reinstall --no-cache-dir ^
  torch torchvision torchaudio "fsspec[http]<=2025.10.0,>=2023.1.0" ^
  --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple
python -m pip check
```
若你确认 `datasets` 已升级并允许更高版本，也可以改为升级 `datasets`；否则以限制 `fsspec` 为准更稳。

使用这个指令验证是否安装通过:
```cmd
python -c "import sys; print(sys.executable)"
python -m pip show chromadb
python -c "import chromadb; import sentence_transformers; print('embed imports OK')"
```
期望输出 `embed imports ok` 为通过.


### Step 1：理解 Scheme B 的“口径契约”（先明确你要建的是什么库）
**做什么**：在开始跑任何命令前，先确认这次构建的口径是 **Scheme B**：即图片/视频等媒体文件不做 OCR/ASR，但会以 **stub 文本**（例如 `[IMAGE] 文件名/路径...`）进入向量库；同时 `md` 文档与其它文本依然按 chunk 规则切分入库。  
**为何（因果）**：Scheme B 的核心价值是“检索能覆盖媒体文件的存在”，即便暂时没有内容语义；代价是库规模更大、构建耗时更长、召回结果中可能出现媒体 stub（这是预期行为，不应误判为噪声）。因此后续的检查与回归要明确区分：**结构正确**（count 对齐/来源可解释）与 **质量回归**（只看 md 或分层召回）。  
**关键参数/注意**：Scheme B 的开关必须在 **plan/build/check** 三处一致：`include_media_stub=true`。你不应再使用历史常量 `expected_chunks=705`；“expected”应来自同参数的 plan 产物。

**数目漂移**: 详情见[补充说明](#inventorycsv-补充说明)
---

### Step 2：目录与产物约定（避免“查错库/混用旧产物”）
**做什么**：确认你在项目根目录运行（与 `inventory.csv` 同级）。重要目录与文件约定如下：  
- `inventory.csv`：资产清单（扫描产物）；  
- `data_processed/text_units.jsonl`：units（每个 source 一条记录）；  
- `data_processed/chunk_plan.json`：plan 产物（planned_chunks、type_breakdown、chunk 参数）；  
- `chroma_db/`：Chroma 向量库持久化目录；  
- `data_processed/build_reports/`：构建/计时等报告落盘目录（建议保留用于复盘对比）。  
**为何（因果）**：你遇到过“以为卡住/以为漏写/以为没生效”，根因往往是输出目录没对上或旧库混入。强制统一“根目录运行 + 固定相对路径”能把此类问题压到最低。  
**关键参数/注意**：重跑前建议用“目录版本化”策略（例如把旧的 `chroma_db` 改名为 `chroma_db_YYYYMMDD`），以免误把旧库当新库验收；或至少清空 `data_processed/build_reports/`，保证报告一眼可追溯。

---

### Step 3：从 inventory.csv 生成 units（extract）并做硬校验（validate 必须 PASS）
**做什么**：以 `inventory.csv` 为输入，执行 `extract_units.py` 刷新 `data_processed/text_units.jsonl`，随后执行 `validate_rag_units.py` 做结构/对齐/引用完整性检查，必须 PASS 才继续。  
**为何（因果）**：units 是下游 plan/build 的唯一输入集合；如果 units 不稳定或有缺字段/空文本/引用断链，下游会表现为“召回跑偏、数量异常、检查误报”，排障成本指数上升。把 validate 设为硬闸，就是把错误尽可能留在最便宜的阶段解决。  
**关键参数/注意**：`validate_rag_units.py` 的统计项（尤其 md refs）是你验证数据处理正确性的最直接证据。它的 PASS 仅表示“结构可继续”，并不等于“检索质量已达标”，但它是后续讨论的必要前提。  
**推荐命令（Windows CMD）**：
```cmd
python extract_units.py
python validate_rag_units.py --max-samples 50

:: 可选：落盘 JSON 报告（回归/CI 推荐，固定路径）
python validate_rag_units.py --max-samples 50 --json-out data_processed\build_reports\units.json

:: 可选：只把 JSON 打到 stdout（不落盘，适合 CI 日志）
python validate_rag_units.py --max-samples 50 --json-stdout
```

---

### Step 4：plan（dry-run）——用“同参数计划数”取代手填 expected
**做什么**：运行 `tools/plan_chunks_from_units.py` 生成 `data_processed/chunk_plan.json`。该脚本会调用项目内的 chunking 逻辑，按 Scheme B 口径计算 planned_chunks，并输出按 `source_type` 的 breakdown。  
**为何（因果）**：你此前的争议点是“为什么 694 而不是 705”，本质是 expected 来自手填常量且不可追溯。plan 的价值是：把 expected 变成**可复现的计算结果**，并且与 build 共享同参数（chunk_chars/overlap/min/include_media_stub），从源头消灭误报。  
**关键参数/注意**：plan 与 build 的 chunk 参数必须完全一致；如果你只改了 build 的参数而没改 plan，那么 check 将必然 FAIL，这种 FAIL 是健康的（它在提醒你口径漂移）。  
**推荐命令**：
```cmd
python tools\plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl ^
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 ^
  --include-media-stub true --out data_processed\chunk_plan.json
```

---

### Step 5：build（向量化 + upsert 入库）——建议用 profile 固化参数并可调 batch
**做什么**：执行 build 阶段时建议以 profile 固化参数（见下方入口选择），或直接调用 `tools/build_chroma_index_flagembedding.py build ...`。建议优先用 profile 方式，因为它能把“device/embed_batch/upsert_batch/chunk 参数/include_media_stub/db/collection”固化，减少手敲漂移。  
**为何（因果）**：build 阶段是全流程最重的计算：embedding（可能走 GPU）+ 写入 Chroma。把参数固化到 profile，可以让你后续对比耗时/质量时具有可比性；同时一旦失败（OOM/中断），你能明确知道“当时的 batch/设备/口径是什么”。  
**关键参数/注意**：  
- `embed_batch` 主要影响 embedding 显存/内存峰值：OOM 时优先 32→16→8；  
- `upsert_batch` 影响写入期内存峰值：写入期内存高则 256→128→64；  
- Scheme B 会显著放大规模（image/video stub 也入库），因此慢机器上先保稳定再谈吞吐。  
**入口选择（必读，二选一）**：下面 Option A / Option B **二选一执行**，不要同时运行。  
- 若你需要“分步计时 + 全流程 +（可选）smoke”，选 **Option A**（推荐）。  
- 若你只想“构建一次，不生成分步计时报表”，选 **Option B**。  
- 若你确实要并行对比参数（不推荐默认并行），必须复制 profile 并隔离至少 `db` 与 `state_root`（建议也隔离 `collection`），否则会出现并发写库/写状态竞争，导致结果不可复核。  

**Option A（推荐：计时 wrapper + build + check + 可选 smoke）**：
```cmd
python tools\run_profile_with_timing.py --profile build_profile_schemeB.json --smoke
```
- 生成的时间报告在 `JSON 报告：data_processed/build_reports/time_report_*.json`
- 
**Option B（仅 build：不生成 time_report）**：
```cmd
python tools\run_build_profile.py --profile build_profile_schemeB.json
```



**新增（2025-12-29）：增量同步（index_state/manifest）**  
**做什么**：build 脚本默认启用 `--sync-mode incremental`，会在 `data_processed/index_state/` 下写入索引状态；后续重复运行时：  
- 只对新增/内容变更文件做 embedding + upsert；  
- 对删除/内容变更文件先按 doc 粒度 delete 旧 chunk，避免 “count mismatch”；  
- schema 变化（embed_model/chunk_conf/include_media_stub）会触发自动 reset（默认策略），保证口径一致。

**关键参数**：  
- `--sync-mode incremental|delete-stale|none`（推荐 `incremental`）；  
- `--on-missing-state reset`（state 缺失但库非空时，自动重置）；  
- `--schema-change reset`（口径变更时自动重置）；  
- `--strict-sync true`（构建后若 `count!=expected` 直接 FAIL）。

**产物**：`data_processed/index_state/<collection>/<schema_hash>/index_state.json` + `LATEST` 指针文件。  




**新增（2026-01-02）：DB 构建戳（db_build_stamp.json）**  （契约详见：[`../reference/index_state_and_stamps.md`](../reference/index_state_and_stamps.md)）  
**做什么**：在 `data_processed/index_state/db_build_stamp.json` 写入一份“写库完成”的稳定戳，用于 `rag-status` 的 STALE 判定。该戳只应在 build/upsert/sync 成功后更新（写库），而不应在 query/eval 等读库行为中变化。  
**为何（因果）**：Windows + SQLite/Chroma 可能在只读查询时更新 DB 目录 mtime，若仅用目录 mtime 推导依赖关系，会让 `check.json` 被误判 STALE，造成重复无效回归。引入 build stamp 相当于给 DB 增加一个“稳定 freshness basis”，从系统角度把“读触发的 mtime 噪声”与“写库导致的语义变化”分离开来。  
**关键参数/注意**：新版本 build 脚本会自动写入该戳；若你已有旧库（缺此文件），只需手动补一次，然后再重跑一次 Step 6 的 check 生成新的 `check.json`。  
**推荐命令（CMD）**：
```cmd
rag-stamp --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json

:: 无 rag-stamp entrypoint 时
python tools\write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json
```
---

### Step 6：check（强校验）——以 plan 为准做 PASS/FAIL 判定
**做什么**：执行 `check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json`。该检查的核心判据是：`collection.count == planned_chunks`。  
**为何（因果）**：你需要一个“可落地的稳定验收信号”，而不是凭感觉看日志。check 的定位非常明确：若 FAIL，则要么 build 未完成/被中断，要么 plan/build 参数不一致（口径漂移），要么写库发生异常。它把问题域收敛到可操作的范围。  
**关键参数/注意**：不要再维护任何手填 `expected_chunks` 常量；若你确实要临时覆盖 expected，应明确标注“覆盖值”，并且不建议作为长期流程。  
**推荐命令**：
```cmd
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json

:: 可选：落盘 JSON 报告（回归/CI 推荐，固定路径）
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-out data_processed\build_reports\check.json

:: 可选：只把 JSON 打到 stdout（不落盘，适合 CI 日志）
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-stdout
```

---

### Step 7：质量回归（检索层）——Scheme B 下要学会“隔离变量”
**做什么**：先用 `retriever_chroma.py` 对固定 query 做 top-k 检索回归。Scheme B 下你可能会看到媒体 stub 进入 top-k；若你要回归“文本质量”，应在检索时加元数据过滤，只保留 `source_type=md`（或你认可的文本类型集合）。本仓库的 `retriever_chroma.py` CLI 支持 `--where`（键值对逗号分隔），用于把过滤条件透传给 Chroma。
**为何（因果）**：Scheme B 引入了新的证据类型（媒体 stub），它会改变候选集合与排序；如果你不把变量隔离（例如“只看 md”与“全量证据”混在一起比较），就会把口径变化误判为质量变化。把 where 作为回归入口的一部分固化下来，能让每次对比的证据域一致。
**关键参数/注意**：`--where` 当前采用最小语法：`k=v,k2=v2`（仅等值过滤，值按字符串处理）；如果你需要更复杂的过滤（区间/AND-OR/数组），建议改用 `build_chroma_index.py query --where ...` 或在上层代码把返回结果按 meta 二次过滤后再评估。
**推荐命令**：
```cmd
:: 只回归 md 文档（隔离变量）
python retriever_chroma.py --q "存档导入与导出怎么做" --k 5 --where "source_type=md"

:: 对照：全量证据（含媒体 stub）
python retriever_chroma.py --q "存档导入与导出怎么做" --k 5
```

---

### Step 8：闭环（RAG pipeline + 本地模型）——先验证请求体，再验证 LLM
**做什么**：
1) 先运行 `check_rag_pipeline.py`（不依赖 LLM），确认“检索→上下文→messages”结构与截断策略正确；
2) 再运行 `answer_cli.py` 接入本地模型，验证端到端响应与失败落盘。。  
**为何（因果）**：单纯看控制台日志无法稳定提取耗时；计时 wrapper 能把“不同机器/不同 batch/不同 device”的成本对比变成数据，而不是感觉。你后续调 `embed_batch/upsert_batch` 时，这份报告是最直接的决策依据。  
**关键参数/注意**：  
- 计时 wrapper **不是** “只 smoke”；它仍会执行 build（向量化 + 写库）。  
- 命令入口已与 build 入口收敛到同一处，避免重复执行：请在 Step 5 选择 **Option A**（计时版）。  
- 并发运行两套构建作业时，务必隔离 `db/collection/state_root`（否则会写库与状态互踩）。  

（性能计时与成本观测请见 Step 5（build）的“计时版 Option”，闭环步骤只保留正确性路径。）  [性能观测计时 Option](#step-5build向量化--upsert-入库建议用-profile-固化参数并可调-batch)

**建议读报告时优先看**：  
- `total_seconds`（总耗时）  
- 每一步 `seconds` + `returncode`（瓶颈在哪、是否有中断）  
- 参数快照（`device/embed_batch/upsert_batch/chunk_conf/include_media_stub`），用于横向对比  


**推荐指令**
- 先自检“检索→上下文→messages”不依赖 LLM：
```cmd
python check_rag_pipeline.py --q "存档导入与导出怎么做"
```
- 再接入 LLM（若只看检索结果可加 --only-sources）：
```cmd
python answer_cli.py --q "存档导入与导出怎么做"
```

---

### Step 9：Stage-1 一键验收（verify）——把“能否进入下一阶段”变成门禁
**做什么**：当你完成 Step3–Step6（units/plan/build/check）后，建议立即跑一次 `tools/verify_stage1_pipeline.py`，把“关键产物是否齐全、Chroma count 是否与 plan 对齐、LLM 端点是否可用”合并成一次命令，并落盘一份可审计的报告。  
**为何（因果）**：你当前项目的高频问题并非“脚本不存在”，而是“改动后链路退化/口径漂移/模型端点不稳”。Stage-1 verify 将最常见的三类退化（产物缺失、count mismatch、端点不可达）提前暴露，并用退出码形成可自动化门禁；这样你不会在 Stage-2 才发现“其实 Stage-1 已经不可信”。  
**关键参数/注意**：  
- 默认会尝试做三类检查：artifacts（必做）/chroma（可选）/llm（可选）；  
- 在没有模型机或 CI 环境中，使用 `--skip-llm`；在资料机没有 chromadb 时使用 `--skip-chroma`；  
- 建议把输出固定为 `data_processed/build_reports/stage1_verify.json` 作为回归入口。  
**推荐命令**：
```cmd
python tools\verify_stage1_pipeline.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --timeout 10

:: 资料机/CI：不要求本机有 LLM
python tools\verify_stage1_pipeline.py --root . --skip-llm
```
**进一步说明**：参数、输出字段与 FAIL 归因详见：[`tools/verify_stage1_pipeline_README.md`](../../tools/verify_stage1_pipeline_README.md)

---

### Step 10：Stage-1 基线快照（snapshot）——为“漂移归因”留证据
**做什么**：当 Stage-1 verify 通过后，建议生成一份“基线快照”并保存（或版本化归档）。使用 `tools/snapshot_stage1_baseline.py` 会对 `data_processed/text_units.jsonl` 与 `chunk_plan.json` 计算 SHA-256，并对 `chroma_db/` 生成轻量 manifest（文件清单 + size/mtime；小文件可带 sha256），从而把“本次构建到底是什么状态”固化成可比对证据。  
**为何（因果）**：后续你会频繁遇到“本次重建后为什么召回/答案不一样”。若没有基线快照，你只能凭感觉猜是数据变了、参数变了、还是落盘状态变了。快照的作用是把漂移归因变成确定性：先看 artifacts 指纹是否变化（输入侧），再看 chroma manifest 是否变化（落盘侧），最后看 git/依赖（代码/环境侧）。  
**关键参数/注意**：默认只对 ≤50MB 文件算 sha256（避免过慢）；若你需要更强指纹，可在脚本中调整阈值。建议至少保留“上一版快照”和“当前快照”两份。  
**推荐命令**：
```cmd
python tools\snapshot_stage1_baseline.py --root . --db chroma_db

:: 对比“新旧快照”（门禁：有差异则 exit code=2）
python tools\compare_stage1_baseline_snapshots.py ^
  --a data_processed\build_reports\stage1_baseline_snapshot.json ^
  --b data_processed\build_reports\stage1_baseline_snapshot_prev.json ^
  --out data_processed\build_reports\baseline_diff.json
```
**进一步说明**：详见：[`tools/snapshot_stage1_baseline_README.md`](../../tools/snapshot_stage1_baseline_README.md) 与 [`tools/compare_stage1_baseline_snapshots_README.md`](../../tools/compare_stage1_baseline_snapshots_README.md)

**一键验收（推荐）**：如果你希望把 Step9-10 与严格状态检查固化成一个命令，可直接使用 `rag-accept`。  
默认只跑核心序列（stamp -> check -> snapshot -> rag-status --strict），其它步骤需显式开启。  
详见：[`rag-accept 使用说明`](rag_accept.md)

---

### Step 11：Stage-2 评测体系（cases → 取证 → 门禁 → 评测 → 汇总）
**做什么**：Stage-2 的目标是把“检索是否退化、端到端是否退化”变成可度量结果。推荐工作流是：先用 `init_eval_cases.py` 初始化用例集；对每条 query 用 `suggest_expected_sources.py` 基于 Chroma topK 取证并填充 `expected_sources`；再用 `validate_eval_cases.py` 做用例集门禁；最后运行检索回归（hit@k）与端到端回归（must_include），并用 `view_stage2_reports.py` 一键汇总关键指标。  
**为何（因果）**：没有 Stage-2，你只能用少量人工 query 做“感觉回归”，容易被随机性/排序抖动误导。Stage-2 将“检索”和“生成”拆成两层：若 hit@k 稳定但 must_include 退化，优先看 prompt/context/LLM；若 hit@k 也退化，则优先看 embedding/分块/索引口径。  
**关键参数/注意**：  
- `expected_sources` 推荐用仓库相对路径（文件级标识），避免绝对路径/临时路径导致跨机不稳定；  
- `must_include` 只做“最小断言”，不要写成完整答案；  
- 运行端到端评测时，建议把 `--timeout` 提高到 120–180，并使用 `--trust-env auto` 避免本地代理劫持 127.0.0.1。  
**推荐命令（最小闭环）**：
```cmd
:: 1) 初始化（只生成/维护用例集骨架）
python tools\init_eval_cases.py --root .
或者新增的:
rag-init-eval-cases

:: 2) 取证：为某条 query 推荐 expected_sources（可复制进用例）
python tools\suggest_expected_sources.py --root . --query "存档导入与导出怎么做？" --db chroma_db --collection rag_chunks --k 8 --pick 2 --embed-model BAAI/bge-m3 --device cpu

:: 3) 用例集门禁（强烈建议每次评测前跑）
python tools\validate_eval_cases.py --root . --check-sources-exist

:: 4) 检索回归（hit@k）
python tools\run_eval_retrieval.py --root . --db chroma_db --collection rag_chunks --k 5 --embed-model BAAI/bge-m3

:: 5) 端到端回归（must_include）
python tools\run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --k 5 --embed-model BAAI/bge-m3 --timeout 120 --trust-env auto

:: 6) 汇总解读（可落盘 Markdown）
python tools\view_stage2_reports.py --root . --md-out data_processed\build_reports\stage2_summary.md
```
**进一步说明**：分别见工具自带说明：  
- [`tools/init_eval_cases_README.md`](../../tools/init_eval_cases_README.md)  
- [`tools/suggest_expected_sources_README_v2.md`](../../tools/suggest_expected_sources_README_v2.md)  
- [`tools/validate_eval_cases_README.md`](../../tools/validate_eval_cases_README.md)  
- [`tools/run_eval_retrieval_README.md`](../../tools/run_eval_retrieval_README.md)  
- [`tools/run_eval_rag_README.md`](../../tools/run_eval_rag_README.md)  
- [`tools/view_stage2_reports_README.md`](../../tools/view_stage2_reports_README.md)

---

### Step 12：文档工程门禁（docs 规范与链接可用性）
**做什么**：当你批量处理 `docs/`（例如自动插入目录 TOC、统一标题、迁移文件）后，建议用两个脚本做门禁：  
1) `tools/check_docs_conventions.py`：检查每个 docs Markdown 的“首个标题必须为 `# {文件名}目录：`”以及目录标题后“两行空行”等工程约定；  
2) `tools/verify_postmortems_and_troubleshooting.py`：全仓库 Markdown 链接扫描，支持自动修复唯一候选断链，必要时用 `--strict` 作为 CI 失败门禁。  
**为何（因果）**：文档是你后续 RAG 的数据源和排障入口；一旦标题/链接漂移，会同时破坏 GitHub 可点击性与后续脚本解析口径，属于“隐性高成本”问题。把它们当成门禁处理，会比事后补救更稳。  
**关键参数/注意**：`verify_postmortems_and_troubleshooting.py` 默认不以断链退出非 0（便于交互调试）；需要严格失败时加 `--strict`。  
**推荐命令**：
```cmd
python tools\check_docs_conventions.py --root . --docs-dir docs

python tools\verify_postmortems_and_troubleshooting.py
python tools\verify_postmortems_and_troubleshooting.py --strict
```

---

### Step 13：JSON 报告 schema 自检（用于回归/CI）
**做什么**：当你把 `validate_rag_units.py`、`check_chroma_build.py`、`tools/probe_llm_server.py` 的 `--json-out` 固定落盘用于回归时，建议在 CI 或批处理脚本中增加 `tools/verify_reports_schema.py` 作为最小 schema 校验，避免“报告格式变化导致下游聚合脚本崩溃”。  
**为何（因果）**：你当前报告采用 `schema_version=2` 的 item 模型；若某次改动意外破坏 JSON 结构（例如缺少 `items/summary`、某条结果缺 `severity_level`、或顶层字段名漂移），下游渲染/聚合将出现误判或崩溃。schema 自检把这类问题提前收敛为明确 FAIL。  
**关键参数/注意**：该脚本默认做 v2 的最小键与类型检查（不评价指标）；`--step` 用于校验期望的 `tool` 名称；如需更严格可用 `--schema` 指定 v2 JSON Schema。  
**推荐命令**：
```cmd
python tools\verify_reports_schema.py --report data_processed\build_reports\units.json --step units
python tools\verify_reports_schema.py --report data_processed\build_reports\check.json --step check
python tools\verify_reports_schema.py --report data_processed\build_reports\llm_probe.json --step llm_probe

:: 更严格（需要安装 jsonschema）
python tools\verify_reports_schema.py --report data_processed\build_reports\units.json --schema schemas\build_report_v2.schema.json
```


## 2) 替代方案（1–2 个：适用场景 + 代价/限制）

### 方案 A：文本-only（include_media_stub=false）
**适用场景**：你当前主要目标是“稳定验证 RAG 链路与文本召回质量”，希望库更小、构建更快、召回更干净；媒体资源暂时只通过路径/文件名旁路检索。  
**代价/限制**：图片/视频不会进入向量库；后续如要支持媒体内容检索，要么重建，要么维护第二个索引。

### 方案 C：双库分层（文本库 + 全量库）
**适用场景**：既要保留媒体 stub 的覆盖，又希望文本质量回归稳定；用两套库把“文本回归”和“全量覆盖”分离。  
**代价/限制**：双倍构建/存储；工具调用需显式指定 `--db/--collection`，否则会混用；`answer_cli.py` 默认读取 `rag_config.py`，切库需改配置或改用带参数的查询/评测工具。

**推荐做法**：
- 文本库：`include_media_stub=false`，`--db chroma_db_text --collection rag_chunks_text`
- 全量库：`include_media_stub=true`，`--db chroma_db --collection rag_chunks`

---

## 计时与报告落盘

构建完成后你通常需要回答两件事：**这次跑了什么参数**、**花了多久**。建议每次构建至少保留以下三类产物：

- `data_processed/env_report.json`：环境快照（Python/依赖/torch/cuda 等）
- `data_processed/chunk_plan.json`：plan 结果（planned_chunks、type_breakdown、chunk 参数、include_media_stub）
- `data_processed/build_reports/time_report_*.json`：分步计时（validate/plan/build/check），用于比较不同 batch/device 的成本

推荐使用计时 wrapper（可选）：
```cmd
python tools\run_profile_with_timing.py --profile build_profile_schemeB.json --smoke
```

补充说明：`tools/smoke_test_pipeline.py` 是“一键冒烟”脚本，主要以 **退出码** 作为健康信号；它不会额外输出 JSON 报告。若你需要机器可读回归数据，请对 `validate_rag_units.py` / `check_chroma_build.py` / `tools.probe_llm_server` 分别使用 `--json-out` 固定路径落盘。

## LLM 服务探测（probe）

密钥注入：服务要求 key 时，优先通过环境变量 `LLM_API_KEY`（或 `OPENAI_API_KEY`）配置；示例见 `.env.example`。本仓库不自动加载 `.env`。

推荐（模块方式）：

```cmd
python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed\build_reports\llm_probe.json

:: 可选：只把 JSON 打到 stdout（不落盘，适合 CI 日志）
python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-stdout

python -m tools.verify_single_report_output --glob \"llm_probe_report_*.json\"
```

说明：若提供 `--json-out`，将只生成一份报告文件（固定路径），用于回归/CI；并且推荐用 `python -m tools.probe_llm_server` 运行（避免在 `tools\` 目录直接运行导致 `ModuleNotFoundError: No module named 'tools'`）。

## inventory.csv 补充说明
**补充：inventory.csv 的生成与“稳定性契约”（解释你遇到的行数波动）**

- `inventory.csv` 由 `make_inventory.py` 生成，它定义了本次流水线的“输入文件集合”。只要输入集合漂移，下游 units/plan/build/check 的数量与召回都可能变化，因此漂移归因应从建表开始，而不是从向量库或 LLM 开始。
- 默认会排除常见易变噪声：`**/~$*`、`**/*.tmp`、`**/*.temp`、`**/*.part`、`**/Thumbs.db`、`**/.DS_Store`。它们通常由 Office/系统/下载器生成，表现为“你没改资料但行数在多次运行间抖动”。
- 需要全量对照或怀疑误伤时：使用 `--no-default-excludes` 回退到“全收录”口径（以脚本 `-h` 输出为准），并对照 report 的 `excluded_samples` 来确认差异来源。
- 追加排除：用 `--exclude-glob`（可重复）追加规则；匹配使用 **posix 相对路径**（`/` 分隔）以避免 Windows `\` 导致规则失效。
- build report（强烈建议保留）：默认落盘到 `data_processed/build_reports/inventory_build_report.json`，包含：
  - `root/raw_dir/out_csv`：确认没有跑错仓库副本或目录；
  - `scanned_files/included_rows/excluded_files/errors`：解释本次行数与上次差异；
  - `excluded_samples/error_samples`：给出具体样例，便于直接定位噪声文件或锁文件。
- 严格模式：`--strict` 会在发生任何扫描/哈希错误时返回非 0（适合排查“同步中间态/锁文件/权限”导致的隐性跳过）。

**推荐命令（建表 + extract/validate）**：
```cmd
python make_inventory.py
python extract_units.py
python validate_rag_units.py --max-samples 50
```

> 当你再次遇到 `Wrote XXXX rows ... (scanned=..., excluded=..., errors=...) | report: ...` 时，优先看 report 的 `root/raw_dir` 与 `excluded_samples/error_samples`，这一步通常能直接解释“为什么行数不同”。  
> 更细的增删对比可用 `tools/check_inventory_build.py --snapshot-out/--compare-snapshot`（如果你已经引入该工具）。
