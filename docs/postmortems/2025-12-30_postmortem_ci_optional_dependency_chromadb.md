# 2025-12-30_postmortem_ci_optional_dependency_chromadb.md目录：

> 注：本文记录的当时环境可能包含 Python 3.10；当前仓库已提升基线为 Python >= 3.11（issue1 方案B），以降低 pyproject/TOML 解析类故障。
- [0) 元信息](#0-元信息)
  - [0.1 基本信息](#01-基本信息)
  - [0.2 外部参考（规范/官方/原始材料）](#02-外部参考规范官方原始材料)
- [1) 现象与触发](#1-现象与触发)
  - [1.1 现象：在 .venv_ci 中运行 rag-plan/plan_chunks_from_units.py 失败](#11-现象在-venv_ci-中运行-rag-planplan_chunks_from_unitspy-失败)
  - [1.2 触发：plan 阶段 import 复用逻辑时拉入 chromadb](#12-触发plan-阶段-import-复用逻辑时拉入-chromadb)
  - [1.3 误导性线索：已删除向量库目录（与本错误无因果）](#13-误导性线索已删除向量库目录与本错误无因果)
- [2) 问题定义](#2-问题定义)
- [3) 关键证据与排查过程](#3-关键证据与排查过程)
- [4) 根因分析（RCA）](#4-根因分析rca)
- [5) 修复与处置（止血→稳定修复→工程固化）](#5-修复与处置止血稳定修复工程固化)
  - [5.1 止血：让 plan 先跑通](#51-止血让-plan-先跑通)
  - [5.2 稳定修复：可选依赖 + 懒加载（lazy import）](#52-稳定修复可选依赖--懒加载lazy-import)
  - [5.3 工程固化：把分层作为门禁](#53-工程固化把分层作为门禁)
- [6) 预防与回归测试](#6-预防与回归测试)
- [7) 最小可复现（MRE）](#7-最小可复现mre)
- [8) 一句话复盘](#8-一句话复盘)
- [9) 方法论迁移（可选但推荐）](#9-方法论迁移可选但推荐)
  - [9.1 可复用工程思维：分层 + 证据链 + 门禁化](#91-可复用工程思维分层--证据链--门禁化)
  - [9.2 “以后遇到类似情况”的执行清单（Preflight Checklist）](#92-以后遇到类似情况的执行清单preflight-checklist)
  - [9.3 类比迁移：把同一套思维用到其他工程问题](#93-类比迁移把同一套思维用到其他工程问题)


## 0) 元信息

### 0.1 基本信息
- 发生日期：2025-12-30（默认：以你本次日志发生当天计）
- 影响范围：Stage-1/CI 轻量环境（`.venv_ci`）中 **计划分块（plan）阶段**无法执行；Stage-2（embedding/chroma build）不一定受影响，但会被 CI 阶段阻断。
- 影响命令（已观测）：
  - `python tools\plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub true --out data_processed\chunk_plan.json`
- 实际报错（关键片段）：
  - `[FATAL] cannot import chunking logic from mhy_ai_rag_data.build_chroma_index: No module named 'chromadb'`
- 预期结果：在不安装 `chromadb` 的 `.venv_ci` 中，**plan 阶段应可运行**并产出 `data_processed/chunk_plan.json`（因为它不读写向量库）。
- 已尝试动作（输入线索）：你已删除向量库目录/集合（例如 `chroma_db`），但该动作对本报错不构成修复。

> 说明：本复盘严格区分“依赖缺失导致 import-time 失败”与“删除/重建向量库导致的运行期数据问题”，避免在两个故障域之间来回试错。

### 0.2 外部参考（规范/官方/原始材料）
以下参考用于支撑“业界成熟方案”的选型（可选依赖/extra、pip 安装方式、Chroma 包拆分与升级风险）。每条均给出可定位锚点。

1) URL：https://packaging.python.org/en/latest/guides/writing-pyproject-toml/  
   - 日期/版本：访问日期 2025-12-30（页面近期更新）  
   - 来源类型：PyPA 官方文档（primary）  
   - 定位：`[project] optional-dependencies` 段落（Writing your pyproject.toml）  

2) URL：https://pip.pypa.io/en/stable/cli/pip_install/  
   - 日期/版本：访问日期 2025-12-30（pip 文档 v25.x 页面）  
   - 来源类型：pip 官方文档（primary）  
   - 定位：`pip install` 用法示例（包含 `.[extra]` / `pkg[extra]` 安装语义）  

3) URL：https://cookbook.chromadb.dev/core/install/  
   - 日期/版本：访问日期 2025-12-30  
   - 来源类型：Chroma 官方文档（primary）  
   - 定位：Installation：`chromadb` 与 `chromadb-client` 拆分说明  

4) URL：https://pypi.org/project/chromadb/  
   - 日期/版本：访问日期 2025-12-30（用于固定/对齐安装版本与发布日期）  
   - 来源类型：PyPI 官方项目页（primary）  
   - 定位：页面顶部版本与 release date 信息  

冲突裁决规则：当“博客/帖子”与“官方规范/官方文档/项目页”不一致时，以后者为准；优先检查是否为版本差异导致的冲突。


## 1) 现象与触发

### 1.1 现象：在 .venv_ci 中运行 rag-plan/plan_chunks_from_units.py 失败
- [Fact] 你在 `.venv_ci` 环境执行 plan 命令后，程序在启动阶段直接失败，错误为 `No module named 'chromadb'`，并由脚本封装成 `[FATAL] cannot import chunking logic ...`。
- [Fact] 失败发生在 **import 阶段**（尚未进入“读取 text_units / 输出 chunk_plan”的业务流程），因此与磁盘上的向量库目录是否存在无直接关系。
- [Inference] `.venv_ci` 是刻意保持轻量的环境（仅用于 inventory/extract/validate/plan 等），并未安装 `chromadb`；该推断可通过 `python -m pip show chromadb` 证伪/证实。

### 1.2 触发：plan 阶段 import 复用逻辑时拉入 chromadb
- [Fact] 报错信息明确指向：`tools/plan_chunks_from_units.py` 试图从 `mhy_ai_rag_data.build_chroma_index` 导入（复用）chunking 逻辑。
- [Fact] `build_chroma_index.py` 是 Stage-2（embedding + chroma build）相关模块；若它在模块顶层 import `chromadb`，则任何复用它的 Stage-1 命令都会被“重依赖”拖入。
- [Inference] 当前实现属于“代码复用路径穿透分层”：为了保证 plan/build 规则一致而复用 build 模块，但复用点未隔离重依赖。

### 1.3 误导性线索：已删除向量库目录（与本错误无因果）
- [Fact] 你此前删除了向量库（例如 `chroma_db` 目录或集合）。
- [Fact] 这类动作只会影响“运行期访问向量库”的步骤（build/check/query），不会导致 Python 在 import-time 报 `ModuleNotFoundError`。
- [Inference] 该误导线索常见于“把所有失败都归为数据产物问题”，但本次属于“依赖/分层”问题；区分故障域可显著降低排查成本。


## 2) 问题定义
- 目标（正确行为）：Stage-1/CI 的 plan 阶段在未安装 `chromadb` 的前提下应能运行（因为它只需要 chunking 规则与 units 文件）。
- 实际（错误行为）：plan 阶段通过 import 复用 build 模块时触发 `chromadb` 的缺失，导致 **无关功能被可选依赖阻断**。
- 约束：
  - 不希望把 `chromadb` 强行安装进 `.venv_ci`（会破坏分层、增加 CI 依赖体积与不确定性）。
  - 希望 plan 与 build 共用同一套 chunking 规则，避免“规则漂移”（plan 与 build 产物不一致）。


## 3) 关键证据与排查过程
1) [Fact] 复现命令与报错：
   - 命令：`python tools\plan_chunks_from_units.py ...`
   - 报错：`No module named 'chromadb'`
   - 结论：在 import-time 失败。

2) [Fact] 失败点定位（从报错链可直接推断 import 路径）：
   - 触发点：plan 脚本尝试 import `mhy_ai_rag_data.build_chroma_index`（目的：复用 chunking 逻辑）。
   - 失败点：Python 解释器找不到 `chromadb`，因此在加载 build 模块时中断。

3) [Inference] 环境分层确认：
   - 证伪方式：在 `.venv_ci` 执行 `python -m pip show chromadb`。
   - 预期：未安装（符合“CI 轻量环境”的设计）。
   - 若已安装仍失败，则需要进一步检查“安装名 ≠ 导入名”或 `sys.path` 指向错误解释器（但这不符合你当前报错文案的主路径）。

4) [Fact] “删除向量库”线索排除：
   - 因为错误发生在 import-time，与 `chroma_db` 目录是否存在无因果；本次故障域固定为“依赖管理/模块边界”。


## 4) 根因分析（RCA）
- [Fact] 直接根因（Root Cause）：Stage-1 的 `plan_chunks_from_units.py` 复用 `build_chroma_index.py` 中的 chunking 逻辑，但 `build_chroma_index.py` 在模块顶层引入了 `chromadb`（或等价重依赖），导致 `.venv_ci` 在 import-time 因缺少 `chromadb` 失败。
- [Fact] 机制层根因（Mechanism）：Python 的 import 是“执行模块顶层代码”的过程；一旦顶层 import 了可选依赖，则任何间接 import 都会被迫要求该依赖存在。
- [Inference] 系统性根因（Why it escaped）：
  1) 之前的门禁覆盖更偏向“数据产物一致性”（例如 chunk/embedding/chroma 数量对齐），而未覆盖“入口点在不同 venv 的可运行性”；
  2) 代码复用的目标是避免规则漂移，但缺少“分层边界（Stage-1 不得依赖 Stage-2）”的自动化约束，导致依赖泄漏未被即时发现。


## 5) 修复与处置（止血→稳定修复→工程固化）

### 5.1 止血：让 plan 先跑通
- 做法 A（环境侧绕过）：在 `.venv_ci` 安装 `chromadb` 或安装项目的 embed extra（如 `pip install -e .[embed]`）。
- [Fact] 这能立刻消除 `ModuleNotFoundError`，使 plan 进入业务逻辑。
- 风险：破坏分层，使 CI 环境变重；同时引入 Chroma 升级/迁移的不确定性（应通过版本 pin 管控）。
- 验收：plan 命令能生成 `data_processed/chunk_plan.json`，且文件内 planned_chunks 字段存在、值非 0。

### 5.2 稳定修复：可选依赖 + 懒加载（lazy import）
- 方案（业界成熟）：
  1) 把 `chromadb` 作为 **optional dependency（extra）**，不属于 Stage-1 默认安装集；
  2) 在 `build_chroma_index.py` 中移除顶层 `import chromadb`，改为仅在真正需要向量库的函数（build/query/get_collection）中导入；若未安装则抛出“可操作的错误提示”（指向 `pip install -e .[embed]`）。
- [Fact] 该方案符合 PyPA 对 optional-dependencies 的定义，且与 pip 的 extras 安装语义一致（见 0.2 参考资料）。
- 验收口径：
  - `.venv_ci`（无 chromadb）运行 `rag-plan`/`plan_chunks_from_units.py` 成功；
  - `.venv_rag`（有 chromadb）运行 build/check 不退化；
  - 两边产物对齐：build 使用的 chunking 规则与 plan 输出一致（不引入规则漂移）。

### 5.3 工程固化：把分层作为门禁
- 做法：在 Stage-1 的 CI 流程/测试中显式加入 `rag-plan`（或等价 `python tools\plan_chunks_from_units.py ...`）作为必跑门禁。
- [Fact] 这样任何未来再次把 `chromadb`（或其他重依赖）漏进 Stage-1 import 链，都能在 PR 阶段被立即发现。
- 验收：CI 在全新 venv（仅安装 `.[ci]`）中可以完成 `inventory→extract→validate→plan` 链路；并在日志中明确写出输出文件路径。


## 6) 预防与回归测试
- 回归矩阵（分层验证）：
  1) Stage-1（`.venv_ci`，不装 chromadb）：
     - `rag-inventory`
     - `rag-extract-units`
     - `rag-validate-units`
     - `rag-plan`（本次新增/强化）
     - Pass：生成 `data_processed/chunk_plan.json`，无 `ModuleNotFoundError`。
  2) Stage-2（`.venv_rag` 或模型机，安装 embed/chroma 依赖）：
     - `rag-build`
     - `rag-check`
     - Pass：集合条目数与计划一致（或满足你项目约定的不变量）。

- 预防性规则（可执行、可审计）：
  - 规则 1：Stage-1 可导入的模块不得在顶层 import `chromadb`/`sentence_transformers` 等重依赖；必须通过函数内懒加载。
  - 规则 2：任何“跨 stage 的代码复用”必须满足：复用模块的顶层 import 不引入 Stage-2 依赖（否则拆分出纯逻辑模块）。
  - 规则 3：新增/重构入口点后，必须在“最轻量 venv”里跑一遍 `--help` 与一次最小 smoke（捕获 import-time 失败）。


## 7) 最小可复现（MRE）
> 目标：任何人在一台新机器上按此步骤即可复现“旧版问题”，并验证“修复后行为”。

- 环境：Windows；Python 版本（未知/默认假设：>= 3.10）；新建 venv（`.venv_ci`）
- 安装（旧版/问题存在时）：仅安装 CI/轻量依赖（默认假设存在 `.[ci]` 或等价最小依赖集）
  - `python -m pip install -e .[ci]`
- 复现命令：
  - `python tools\plan_chunks_from_units.py --root . --units data_processed/text_units.jsonl --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub true --out data_processed\chunk_plan.json`
- 预期旧版输出：
  - 失败：`No module named 'chromadb'`
- 修复后预期：
  - 成功生成 `data_processed/chunk_plan.json`（且包含 planned_chunks/type_breakdown 等关键字段）
  - 在未安装 chromadb 的情况下不再报错


## 8) 一句话复盘
把 Stage-2 的重依赖在 import-time 泄漏到 Stage-1，是“分层边界未门禁化”的典型问题；用 **optional dependency + lazy import + CI 门禁** 可以稳定修复并防止回归。


## 9) 方法论迁移（可选但推荐）

### 9.1 可复用工程思维：分层 + 证据链 + 门禁化
- 分层（Layering）：先画清楚“哪些命令属于 Stage-1（不需要向量库）/哪些属于 Stage-2（需要 chroma）”，并让依赖随分层而变化，而不是随“某个模块是否被复用”而变化。
- 证据链（Evidence chain）：
  - import-time 错误 → 首先定位到 import 链与缺失模块；
  - 运行期错误 → 才去看磁盘产物（chroma_db、jsonl、缓存）。
  把故障域拆开，减少误导线索（例如“我删了向量库”）带来的试错。
- 门禁化（Gating）：把“分层边界”写进自动化测试/CI；依赖泄漏不靠人记忆，而靠机器拒绝合并。

### 9.2 “以后遇到类似情况”的执行清单（Preflight Checklist）
1) 先判定故障域：
   - 报 `ModuleNotFoundError`/import error → 先查 `pip show`、`sys.executable`、import 链。
   - 报 count 不一致/数据缺失 → 再查产物目录与数据一致性脚本。
2) 复用逻辑前先做“边界审查”：
   - 被复用模块是否引入重依赖？若是，先拆出纯逻辑模块或做 lazy import。
3) 新入口点/重构后必跑：
   - 在最轻量 venv 中运行 `--help` + 一次最小 smoke（捕获 import-time 崩溃）。
4) 依赖策略：
   - 重依赖（向量库/深度学习框架）必须放在 extras；默认安装集只覆盖 Stage-1。
5) 回归矩阵固定化：
   - Stage-1 与 Stage-2 各自一套最小命令序列，任何一次改动都必须至少通过对应序列。

### 9.3 类比迁移：把同一套思维用到其他工程问题
1) 插件化/可选特性：例如“导出 PDF/图表渲染/可视化 UI”依赖很重，默认路径不应强制安装；把依赖放到 extra，并在调用时再导入。
2) 多后端实现：例如同时支持 SQLite/PostgreSQL/Redis，把具体后端驱动作为可选依赖；核心层只暴露抽象接口与纯逻辑，避免后端驱动在 import-time 被拉入。
3) 多平台差异：Windows-only 的依赖（如某些 DLL/COM 组件）不得污染 Linux CI；用环境标记或 extras 分离，并在 CI 中各跑一条最小链路。
4) 多 venv/多设备协作：把“哪个 venv 跑哪些命令”的规程写入文档与脚本（并在脚本启动时打印 `sys.executable` 与关键包版本），减少“装了但 import 不到”的错位问题。
