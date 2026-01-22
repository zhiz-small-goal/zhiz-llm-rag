---
title: "Chroma 索引断点续跑（方案 B）推进计划"
version: "v0.2"
last_updated: "2026-01-22"
timezone: "America/Los_Angeles"
owner: "zhiz"
status: "draft"
---

# Chroma 索引断点续跑（方案 B）推进计划


> 目标：中断后再次运行时，不重复处理已确认完成写入的文档；仅处理剩余部分；并把“能否续跑/为什么不能”以可核验输出表达出来。  
> 适用范围：`tools/build_chroma_index_flagembedding.py build` 及其生成的 `index_state.json` / `index_state.stage.jsonl`。  
> 约定：对外“生效口径”以 `index_state.json` 为准；`index_state.stage.jsonl` 属于构建过程的旁路工件（用于恢复与审计），成功结束后可清理。  

## 目录
- [结论](#结论)
- [假设](#假设)
- [进度记录](#进度记录)
- [1) 详细指导](#1-详细指导)
  - [Step1（已完成）— 引入 stage 事件流并实现基础续跑](#step1已完成—-引入-stage-事件流并实现基础续跑)
  - [Step2 — checkpoint 语义与写盘策略收敛](#step2-—-checkpoint-语义与写盘策略收敛)
  - [Step3 — changed/deleted 的可重入顺序与幂等](#step3-—-changeddeleted-的可重入顺序与幂等)
  - [Step4 — 一致性校验与故障可复盘](#step4-—-一致性校验与故障可复盘)
  - [Step5 — 测试矩阵与回归（含中断注入）](#step5-—-测试矩阵与回归含中断注入)
  - [Step6（可选）— 警告收敛与门禁策略固化](#step6可选—-警告收敛与门禁策略固化)
- [自检](#自检)
- [失败模式与缓解](#失败模式与缓解)
- [MRE](#mre)
- [替代方案](#替代方案)
- [引用与依据](#引用与依据)

## 结论
采用“`index_state.stage.jsonl` 作为 append-only 进度事件流 + 以 doc 完成事件作为唯一可跳过依据”的方案，可实现“不中断重跑、忽略已成功写入、继续跑剩余”，整体可行；剩余工作主要集中在（1）changed/deleted 场景的事件序列与恢复规则固化、（2）写盘/崩溃窗口的可测边界、（3）自动化回归覆盖。

## 假设
1. **默认假设：单写入者**。同一 `db_path + collection + schema_hash` 同时只有一个 writer 进程；若无法保证，需要显式加锁或用 `run_id` 协议拒绝并发写入。  
2. **默认假设：DONE 的含义是“已完成本 doc 的写入副作用”**。即：`DOC_DONE` 发生前，该 doc 对应的 upsert/delete 已按约定顺序执行，并且“可观察到的写入”已落到 Chroma（至少 flush 到持久化层/可在重启后读取）。  
3. **默认假设：续跑只在严格匹配时启用**。仅当 `db_path + collection + schema_hash` 完全一致且 collection 非空时才使用 stage 的 skip 集合；否则降级为不续跑，并输出原因。  
4. **默认假设：Windows CMD 为主**。本文所有命令默认以 Windows CMD 为准；若你在 WSL/Linux 运行，需要自行替换路径分隔符与删除命令。

## 进度记录
> 记录格式：日期 / Step / 状态 / 产出（补丁包或仓库路径）/ 备注  
> 状态枚举：`DONE` / `IN_PROGRESS` / `TODO` / `BLOCKED`

| 日期 | Step | 状态 | 产出 | 备注 |
|---|---:|---|---|---|
| 2026-01-22 | 1 | DONE | `build-chroma-resume-stage-step1.zip` | 基础续跑已落地；后续聚焦边界与回归 |

## 1) 详细指导

### Step1（已完成）— 引入 stage 事件流并实现基础续跑
【做什么】引入 `index_state.stage.jsonl`（append-only），记录 `RUN_START/RUN_RESUME/DOC_DONE/RUN_FINISH` 事件；重启时基于 `content_sha256` 构造 `done_docs` 集合并跳过已完成文档；同时在“缺 state 但 collection 非空”与“schema-change reset”路径上优先使用 stage，避免误 reset。  
【为何】`index_state.json` 采用原子写，意味着“成功结束才会出现 state”，首次建库中断时无法从 state 判定进度；引入旁路事件流可把“已完成集合”在构建过程中持续落盘，从而支持中断恢复与审计。  
【关键参数/注意】续跑仅在 `db_path + collection + schema_hash` 严格匹配且 collection 非空时启用；失败或 strict mismatch 时保留 stage 以便复盘与再次续跑；成功结束后 best-effort 清理 stage（仅清理旁路文件，不影响 state）。

---

### Step2 — checkpoint 语义与写盘策略收敛 [CON]
【做什么】把“什么算 DONE、何时写入 stage、flush/fsync 频率如何影响崩溃窗口”写成可测规则，并把策略暴露为参数（同时给出默认值）。建议把 `--stage-fsync` 细分为 `off/doc/interval`，并补齐 stage 事件字段最小集合（含 `stage_version`），对不匹配版本做降级处理（不启用 resume，并输出明确原因）。  
【为何】续跑正确性依赖于“DOC_DONE 与真实写入副作用一致”；若 doc 事件过早落盘，则崩溃后可能跳过未真正写入的 doc；若每 doc 强制 fsync，可能造成 IO 放大并影响吞吐。将边界与策略固化成参数 + 回归测试，可以把取舍从口头经验变成可验证行为。  
【关键参数/注意】默认策略建议“doc 边界确保 flush；fsync 走 interval（可配置条数/时间）”；读取 stage 时需容忍尾部截断（忽略最后一行坏行并继续）；当 `stage_version` 不兼容时，默认降级为 `--resume off`，并打印推荐动作（例如：清理 stage 或 reset）。  

**验收（可核验输出）**：  
- `done_docs > 0` 时日志必须同时输出：`done_docs/total_docs/skipped_docs/schema_hash/run_id`；  
- 10k+ docs 场景下，`--stage-fsync off` 与 `--stage-fsync interval` 的吞吐差异可量化（至少输出 flush/fsync 次数计数）；  
- stage 尾部截断时，`resume-status`（见 Step4）能报告“截断被忽略”，但仍可继续续跑。

---

### Step3 — changed/deleted 的可重入顺序与幂等 [CON]
【做什么】为 `changed_uris` 引入两阶段事件序列（例如 `DOC_BEGIN → DELETE_OLD_DONE → UPSERT_NEW_DONE → DOC_DONE`），并明确恢复规则：若存在 `UPSERT_NEW_DONE` 则跳过 delete 与 upsert；若仅 `DELETE_OLD_DONE` 则仅执行 upsert；若仅 `DOC_BEGIN` 则重做 delete+upsert（要求 delete 幂等、upsert 可重入）。为 `deleted_uris` 记录 `DELETE_STALE_DONE` 并允许重复 delete（幂等）。必要时增加 writer lock（锁文件或 `run_id` 协议）拒绝并发写入。  
【为何】changed 场景的风险在于：中断发生在 delete 与 upsert 之间或之后，恢复时若无“已完成到哪一步”的证据，可能重复 delete 从而把新写入内容误删。把流程分解为事件序列并对每个阶段定义可重入规则，可以在恢复时精确跳过已完成阶段，降低误删概率。  
【关键参数/注意】事件的 key 必须包含可判定唯一性的字段（至少 `uri/doc_id/old_sha/new_sha`）；若 chunk_id 策略可能复用，需要确保 delete 的 target 能区分 old/new（例如基于 content_sha 或 build_stamp 前缀）；并发写入保护需要覆盖“同一 collection 不同进程同时跑”的场景，否则 stage 会交错导致恢复规则失效。  

**验收（可核验输出）**：  
- 在 changed 场景下，于 `DELETE_OLD_DONE` 与 `UPSERT_NEW_DONE` 之间注入中断，恢复后最终 `collection.count()` 与期望一致；  
- 日志应输出恢复决策：对每个 uri 选择了“跳过/补做 delete/补做 upsert/重做全流程”的原因摘要（可采样输出，避免日志爆炸）。

---

### Step4 — 一致性校验与故障可复盘 [CON]
【做什么】把失败时的“可行动信息”做成固定输出：strict_sync 失败时打印期望/实际/差值，并抽样输出差异 uri（或输出差异摘要文件路径）；将 `RUN_FINISH` 语义扩展为 `ok=true/false` + `reason`，并规定：仅当 `ok=true` 且 `index_state.json` 原子写成功后，才允许清理 stage；失败一律保留 stage。新增 `--resume-status`（只读）命令：打印 stage 状态、done_docs、last_event、run_id、是否可 resume、建议动作（继续/清理/reset）。  
【为何】续跑策略一旦出现 strict mismatch，需要能快速回答两个问题：① 当前状态是否允许继续续跑？② 若不允许，应该清理旁路还是走 reset？把诊断信息做成结构化输出（stdout 或 JSON）能让排障从“猜测”变成“按证据决策”，并可被 CI/门禁脚本消费。  
【关键参数/注意】`--resume-status` 必须保证无写入副作用；差异抽样需要稳定可复现（固定 seed）；若输出差异文件，需明确产物路径与命名规则，避免覆盖旧输出。  

**验收（可核验输出）**：  
- strict_sync 失败时 stdout 至少包含：`expected_chunks/actual_chunks/delta` 与 `schema_hash/run_id`；  
- `--resume-status` 在 stage 不存在/存在/版本不兼容/尾部截断四种情况下，都能给出单句建议动作，并且退出码固定（建议 0 表示“命令成功执行”，非 0 仅用于工具自身异常）。

---

### Step5 — 测试矩阵与回归（含中断注入） [CON]
【做什么】把续跑语义固化为自动回归：单测覆盖 stage 读写、尾部截断容错、版本降级；集成测试用 toy 文档集 + 持久化 `db_path`，第一次运行写入一半后注入异常，第二次运行验证 skip 与最终一致性；在 changed/deleted 场景中分别在 delete 与 upsert 中间注入中断，验证 Step3 恢复规则。补充性能基线（非强门禁）：记录耗时、skip 率、flush/fsync 次数，供趋势观察。  
【为何】续跑属于“状态机 + 副作用”的组合问题，靠人工验证会在后续重构中失真；把关键边界（首次中断恢复、changed 恢复）做成测试矩阵，可把风险从运行时转移到 CI。性能基线不作为硬门禁，但能在策略调整（例如 fsync 间隔）后提供定量回归依据。  
【关键参数/注意】中断注入要可重复（例如基于计数器触发异常）；toy 数据集需要稳定（固定输入顺序与 content_sha）；测试应明确清理目录策略，避免残留状态影响后续用例。  

**验收（可核验输出）**：  
- 至少覆盖 2 个用例：`first_run_interrupt_resume` 与 `changed_interrupt_resume`；  
- 每个用例输出固定的“证据点”（done_docs、skipped_docs、count 对齐、stage 是否保留/清理），便于定位回归来源。

---

### Step6（可选）— 警告收敛与门禁策略固化 [CON]
【做什么】汇总现有 warning，按“功能性（需修复/可升级为 fail）”与“提示性（可文档化/可静默但不改默认）”分类；为功能性 warning 给出可执行修复或门禁升级策略；为提示性 warning 给出明确解释与触发条件，避免误判。若有门禁脚本（例如 CI lite），则把关键 warning 作为可机器消费字段输出。  
【为何】续跑相关 warning 往往与数据一致性高度相关；若把它们与提示性 warning 混在一起，会削弱排障信号。分类治理可以把“需要动作的风险”从噪声中分离出来，并为后续自动化（门禁/报警）提供稳定接口。  
【关键参数/注意】分类需绑定触发条件与建议动作；默认不改变已有行为，只增强可观测性与治理入口；若新增静默开关，应确保默认值保持当前输出强度，以免隐藏真实问题。

---

## 自检
1. 本文默认“单写入者”与“严格匹配才续跑”，但你的实际环境若存在并发或跨 schema 复用需求，需要在 Step3/Step2 前先确认约束，否则后续验证结论不成立。  
2. 对“DOC_DONE 的真实含义”目前是默认假设；建议在 Step2 明确“写入副作用到达持久化层”的证据点（例如重启后可读/collection.count 可核验），并把证据点写入测试。  
3. `resume-status` 的退出码语义需要提前统一：到底用 stdout 文本还是 JSON 输出作为 SSOT；建议先用 stdout+稳定字段，再逐步引入 JSON（避免一次性扩展接口面）。  

## 失败模式与缓解
1. **现象**：恢复后 `skipped_docs` 很大但最终 `collection.count()` 低于期望。  
   **原因**：DOC_DONE 过早写入 stage（写入副作用尚未持久化）。  
   **缓解**：Step2 明确 doc_done 前的 flush 证据点；必要时将 `--stage-fsync doc` 作为排障选项；并用中断注入测试覆盖该窗口。  
   **备选**：临时关闭 resume（`--resume off`）并重新构建到稳定状态后再启用。  
2. **现象**：changed 场景恢复后出现“新数据缺失”或疑似误删。  
   **原因**：delete/upsert 事件未分段记录，恢复重跑导致重复 delete 命中新 chunk。  
   **缓解**：按 Step3 引入 `DELETE_OLD_DONE/UPSERT_NEW_DONE`；确保 delete target 可区分 old/new；必要时 chunk_id 引入 build_stamp 前缀。  
   **备选**：对 changed_uris 暂时降级为“全量 reset 后再写”，以确保一致性。  
3. **现象**：stage 存在但工具提示“不可 resume”。  
   **原因**：`schema_hash` 或 `stage_version` 不匹配；或 stage 文件尾部损坏超过容忍范围。  
   **缓解**：使用 `--resume-status` 获取原因；确认 db/collection/schema 是否匹配；若仅尾部截断，允许继续；若版本不兼容，按建议清理 stage 或走 reset。  
   **备选**：导出差异摘要后执行 reset，避免在未知状态上叠加写入。

## MRE
**运行环境（示例）**：Windows 11 + Python 3.11.x；工作目录为仓库根目录。  
**核心依赖**：以 `pip freeze` 为准；若你启用了 Stage-2 相关 extras，需要在输出中同时记录 extras 名称。  

1) 准备输入（toy 文档集）  
```cmd
python tools/extract_units.py --root . --out data_processed/units/toy.units.jsonl --limit 200
python tools/validate_rag_units.py --in data_processed/units/toy.units.jsonl
```

2) 首次构建（注入中断：示意，具体以 Step5 的注入开关为准）  
```cmd
python tools/build_chroma_index_flagembedding.py build --root . --db data_processed/chroma/toy --collection toy
```

3) 再次运行（期望出现 skip，并最终一致）  
```cmd
python tools/build_chroma_index_flagembedding.py build --root . --db data_processed/chroma/toy --collection toy
```

**期望观察**：stdout 出现 `done_docs/skipped_docs` 统计；最终 `collection.count()` 与期望一致；成功结束后 `index_state.json` 存在，stage 文件被 best-effort 清理（或保留并给出原因）。

## 替代方案
1. **方案 A：完全重跑（reset）**  
   **适用场景**：schema_hash 变化、writer 并发无法约束、或 stage/version 不兼容导致恢复风险不透明。  
   **代价/限制**：耗时与成本上升；对长任务不利；但一致性路径清晰，排障成本可控。  
2. **方案 C：chunk 级事务/两阶段提交**  
   **适用场景**：需要把恢复精度提升到 chunk 级、并把“写入副作用”做成严格事务语义。  
   **代价/限制**：实现面扩大（需要更细粒度的事件与回滚策略），并可能引入更多 I/O 与状态复杂度；建议在 Step3/Step5 之后再评估是否进入。  

## 引用与依据
- 文档写作作为“系统接口/证据优先/How-to 模板”的规范：`docs/explanation/documentation_principles.md`  
- 增量状态与写库戳的契约口径（避免用 DB mtime 充当 SSOT）：`docs/reference/index_state_and_stamps.md`  
- stage/state 原子写与状态文件作为“对外口径”的约定：`src/mhy_ai_rag_data/tools/index_state.py` 与 `src/mhy_ai_rag_data/tools/index_state_README.md`
