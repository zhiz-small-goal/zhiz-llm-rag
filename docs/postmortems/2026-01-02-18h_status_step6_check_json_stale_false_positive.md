# 2026-01-02-18h_status_step6_check_json_stale_false_positive.md目录：


> 注：本文记录的当时环境可能包含 Python 3.10；当前仓库已提升基线为 Python >= 3.11（issue1 方案B），以降低 pyproject/TOML 解析类故障。
- [2026-01-02-18h_status_step6_check_json_stale_false_positive.md目录：](#2026-01-02-18h_status_step6_check_json_stale_false_positivemd目录)
  - [0) 元信息](#0-元信息)
  - [1) 现象与触发](#1-现象与触发)
    - [1.1 现象：check.json 反复被判定为 STALE](#11-现象checkjson-反复被判定为-stale)
    - [1.2 触发：只做“读库/评测”也会导致 DB mtime 前进](#12-触发只做读库评测也会导致-db-mtime-前进)
  - [2) 问题定义](#2-问题定义)
  - [3) 关键证据与排查过程](#3-关键证据与排查过程)
    - [3.1 强校验本身是 PASS（expected==count）](#31-强校验本身是-passexpectedcount)
    - [3.2 无并发写入进程（排除“后台 build 仍在跑”）](#32-无并发写入进程排除后台-build-仍在跑)
    - [3.3 STALE 的直接原因：status 以 DB 目录 mtime 作为上游输入](#33-stale-的直接原因status-以-db-目录-mtime-作为上游输入)
    - [3.4 外部机制证据：WAL/Checkpoint 会引入额外文件与落盘行为](#34-外部机制证据walcheckpoint-会引入额外文件与落盘行为)
  - [4) 根因分析（RCA）](#4-根因分析rca)
    - [4.1 根因（机制层）](#41-根因机制层)
    - [4.2 为什么“重复跑 check”无法稳定消除 STALE](#42-为什么重复跑-check无法稳定消除-stale)
  - [5) 修复与处置（止血→稳定修复→工程固化）](#5-修复与处置止血稳定修复工程固化)
    - [5.1 止血：把命令落盘固定化，并将 STALE 的含义显式化](#51-止血把命令落盘固定化并将-stale-的含义显式化)
    - [5.2 稳定修复：引入“写库完成戳（db_build_stamp.json）”作为唯一权威信号](#52-稳定修复引入写库完成戳db_build_stampjson作为唯一权威信号)
    - [5.3 工程固化：门禁化 + 文档契约化](#53-工程固化门禁化--文档契约化)
    - [5.4 成熟但改动成本更高的替代方案（建议下次新项目优先考虑）](#54-成熟但改动成本更高的替代方案建议下次新项目优先考虑)
  - [6) 预防与回归测试](#6-预防与回归测试)
  - [7) 最小可复现（MRE）](#7-最小可复现mre)
  - [8) 一句话复盘](#8-一句话复盘)
  - [9) 方法论迁移（可复用工程经验）](#9-方法论迁移可复用工程经验)


## 0) 元信息

- [Fact] 发生时间（日志时间）：2026-01-02 18:07–18:08（同一会话内）。【8:9†cmd_outoup_results.txt†L10-L27】【8:0†cmd_outoup_results.txt†L5-L28】
- [Fact] 仓库根目录：`<REPO_ROOT>
- [Fact] Chroma DB 路径：`<REPO_ROOT>
- [Fact] plan：`data_processed\chunk_plan.json`；check 报告：`data_processed\build_reports\check.json`。【8:4†cmd_outoup_results.txt†L6-L15】
- [Fact] 本文结构/输出约束遵循用户模板（目录 + 0–8 必选 + 9 可选）。fileciteturn8file8

---

## 1) 现象与触发

### 1.1 现象：check.json 反复被判定为 STALE

- [Fact] `rag-status` 显示：
  - `check.json` 的 `report=PASS`，但状态为 `[STALE]`；
  - STALE 判定依据隐含为“check 报告比其上游输入旧”。【8:0†cmd_outoup_results.txt†L24-L28】【8:1†cmd_outoup_results.txt†L17-L21】
- [Fact] 在同一次会话中，`check.json` mtime=18:07:26，而 DB 目录 mtime 在后续变为 18:08:08，导致 status 把 check 判旧。【8:0†cmd_outoup_results.txt†L24-L28】

### 1.2 触发：只做“读库/评测”也会导致 DB mtime 前进

- [Fact] 你执行了评测命令 `python tools\run_eval_rag.py ...`，输出 `OK pass_rate=0.600` 并落盘 `eval_rag_report.json`。【8:2†cmd_outoup_results.txt†L23-L26】
- [Fact] 随后再次 `rag-status` 时，DB 目录 mtime=18:08:08，但 check.json mtime 仍是 18:07:26，于是出现 STALE。【8:0†cmd_outoup_results.txt†L24-L28】

---

## 2) 问题定义

- [Fact] 你要的“状态机语义”是：当且仅当 **影响检索/质量的语义输入发生变化**（例如 plan 参数变化、DB 被写入/重建），才要求重跑 Step6 的强校验（expected==count）。【8:1†cmd_outoup_results.txt†L17-L21】【8:4†cmd_outoup_results.txt†L9-L15】
- [Fact] 现实表现是：即使你已经重跑 `rag-check` 并得到 PASS，只要后续某个动作让 `chroma_db/` 目录的 mtime 前进（哪怕是“读库/评测”），`rag-status` 就会继续判定 check 过期，从而进入“重复 check 的自我阻塞环”。【8:0†cmd_outoup_results.txt†L24-L28】
- [Inference] 因此问题不是“check 算错”，而是“**新旧判定的上游信号选错了**”：把不稳定的文件系统时间戳（目录 mtime）当成语义写库信号，导致误报。

---

## 3) 关键证据与排查过程

### 3.1 强校验本身是 PASS（expected==count）

- [Fact] `rag-check ... --plan data_processed\chunk_plan.json --json-out ...\check.json` 输出：
  - `expected_chunks=3693 (from plan: ...chunk_plan.json)`
  - `embeddings_in_collection=3693`
  - `STATUS: PASS (count matches expected_chunks)`
  - 并写出 `Wrote report: data_processed\build_reports\check.json`。【8:4†cmd_outoup_results.txt†L6-L15】【8:13†cmd_outoup_results.txt†L14-L15】

> 结论：**check 的内容正确**，不应因“内容问题”而反复重跑。

### 3.2 无并发写入进程（排除“后台 build 仍在跑”）

- [Fact] `tasklist | findstr /i python` 无输出，`wmic ... python.exe` 显示“没有可用实例”。【8:6†cmd_outoup_results.txt†L16-L25】
- [Inference] 排除“另一个 python 进程持续写 DB 导致 mtime 前进”的常见原因后，STALE 更可能来自：1) status 判定逻辑本身；2) 底层存储的文件触碰行为（例如自动 checkpoint）。

### 3.3 STALE 的直接原因：status 以 DB 目录 mtime 作为上游输入

- [Fact] 先前方案文档明确指出：旧逻辑把 check 的输入视为 `(plan, chroma_db_dir)`；修复把输入改为 `(plan, db_build_stamp.json)`，从机制上切断“重跑仍 stale”的环路。【8:10†ChatGPT-解决多设备工作流困扰.md†L4-L7】

> 这条证据同时解释了“为什么你已经反复生成 check.json 仍被判 stale”：只要 `chroma_db_dir` 的 mtime 比 check 新，status 就会持续判 stale。

### 3.4 外部机制证据：WAL/Checkpoint 会引入额外文件与落盘行为

- [Fact] SQLite WAL 模式会伴随额外的 `-wal` 与 `-shm` 文件，并且 checkpoint 过程虽默认自动，但仍是应用需要留意的落盘行为（即“仅把数据库当作一个单文件格式”会遇到额外复杂度）。  
  - 这意味着：**目录 mtime** 可能因 WAL/SHM/Checkpoint 行为被更新，而不等价于“业务层写库完成”。（外部原始材料见下方“关键引用”。）

---

## 4) 根因分析（RCA）

### 4.1 根因（机制层）

- [Fact] `rag-status` 的 STALE 判定把 `chroma_db/` 目录 mtime 当作 DB 的“语义新旧”信号之一，而目录 mtime 在 Windows 上会因多种非语义事件前进（例如 WAL/SHM 文件写入、自动 checkpoint、杀软/索引服务触碰元数据等）。【8:0†cmd_outoup_results.txt†L24-L28】【8:10†ChatGPT-解决多设备工作流困扰.md†L4-L7】
- [Inference] 该设计把“**易变的操作层信号**”（filesystem timestamps）当作“**稳定的语义层信号**”（写库完成），因此任何后续动作只要触发 DB 目录变更，就会让 check 失效，即使 DB 的语义并未改变（或仅发生读操作）。

### 4.2 为什么“重复跑 check”无法稳定消除 STALE

- [Fact] 在 18:07:25 的一次 status 中，DB=18:07:25，check=18:07:26，状态 OK；但稍后 DB=18:08:08，check 仍为 18:07:26，就变为 STALE。【8:2†cmd_outoup_results.txt†L4-L8】【8:0†cmd_outoup_results.txt†L24-L28】
- [Inference] 只要“DB mtime 会在你运行评测/查询后前进”，你就会不断遇到“check 跑完→做别的→status 又 stale→再跑 check”的循环；这不是操作问题，而是状态机输入选择错误。

---

## 5) 修复与处置（止血→稳定修复→工程固化）

### 5.1 止血：把命令落盘固定化，并将 STALE 的含义显式化

**目标**：在稳定修复合入前，减少误跑与无效重复。

- [Fact] 统一使用“强校验”命令（必须带 `--plan` 且固定 `--json-out`），避免生成非强校验报告或落到临时路径：  
  ```cmd
  rag-check --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-out data_processed\build_reports\check.json
  ```  
  该命令在你的日志中已验证 PASS 并成功写出报告。【8:4†cmd_outoup_results.txt†L6-L15】
- [Inference] 将 STALE 的解释写入文档/README：当 status 的上游输入包含 DB mtime 时，任何触碰 DB 目录的行为都可能造成“过期”；把这当作“提示”，不要把它当作“check 本身失败”。

### 5.2 稳定修复：引入“写库完成戳（db_build_stamp.json）”作为唯一权威信号

**目标**：把“语义写库完成”从不稳定的 mtime 抽象为一个只由写入流程更新的、可审计的单文件信号。

- [Fact] 修复方案核心是：将 check 的输入从 `(plan, chroma_db_dir)` 改为 `(plan, db_build_stamp.json)`；`db_build_stamp.json` 只在 build 成功或你显式执行 `rag-stamp` 时更新，因此“重跑 check 仍 stale”的环路被切断。【8:10†ChatGPT-解决多设备工作流困扰.md†L4-L7】【8:12†ChatGPT-解决多设备工作流困扰.md†L10-L20】
- [Fact] 行为验收要点（最小闭环）：
  1) 生成/补写 stamp：`python tools\write_db_build_stamp.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json`  
  2) 重跑 `rag-check ... --json-out ...\check.json`  
  3) `rag-status` 中 check 不再因“读库动作”反复 STALE（除非你确实写库并刷新了 stamp）。【8:12†ChatGPT-解决多设备工作流困扰.md†L10-L20】【8:11†ChatGPT-解决多设备工作流困扰.md†L1-L6】

### 5.3 工程固化：门禁化 + 文档契约化

- [Fact] 将 `rag-status --strict` 作为门禁退出码（PASS=0，否则非 0），让“状态机”具备可自动化验收的接口；并配套一键验收 `rag-accept` 把 stamp→check→baseline→strict status 固化成一次执行。【8:10†ChatGPT-解决多设备工作流困扰.md†L11-L19】
- [Inference] 文档层必须把“DB 新旧判定依据”写成契约页（Reference），并在 How-to / Tutorial 里只给最小动作与链接，避免多入口口径漂移（你本次的问题就是口径漂移造成的重复动作成本）。

### 5.4 成熟但改动成本更高的替代方案（建议下次新项目优先考虑）

> 这部分强调“更成熟/更稳”，但确实比 stamp 文件更重；适合你“下次创建项目少走弯路”。

**替代方案 A（更成熟）：Chroma 采用 Client/Server 模式，状态信号从“文件系统”迁移到“服务 API”**  
- 做法：把 Chroma 作为单独进程/容器运行（server 管理持久化目录），应用侧使用 HttpClient；`rag-status` 用 API（count、collection 元信息）作为新旧信号，避免直接观察 `chroma_db/` 目录 mtime。  
- 为什么更稳：[Fact] Chroma 官方将 Client/Server 作为适配“多进程/多机器”的运行方式；相比把 DB 目录当作共享文件格式，更能隔离并发与文件细节。  
- 代价：需要引入服务部署（本机常驻/容器/端口治理）、增加运维面与故障模式（端口不可达、服务重启、版本兼容）。  

**替代方案 B（构建系统级成熟）：用“哈希/锁文件”驱动过期判定（DVC / Bazel 思路）**  
- 做法：把每一步产物（units/plan/db/check/baseline）都定义成“输入闭包 + 输出闭包”，过期判定由“输入哈希/参数值”决定，而不是 mtime；例如 DVC 的 `dvc.lock` 捕获依赖与参数哈希，Bazel 将稳定状态写入 stable-status 并驱动 action 失效。  
- 为什么更稳：[Fact] DVC 明确使用 `dvc.lock` 捕获依赖/参数哈希来判断 stage 是否过期；Bazel 的 workspace status 也是通过稳定键值变化触发重跑。  
- 代价：需要引入工具链与结构化 pipeline（学习成本、改造成本、CI 集成成本），但长期收益是“可复现、可缓存、可分布式”。

---

## 6) 预防与回归测试

1) **状态判定回归**：新增用例验证“只读动作（eval/query）不会让 check 无意义地过期”。  
   - 验收口径：执行 eval 后，如果 stamp 未更新，`check.json` 不应从 OK 变 STALE。  
2) **单写入者约束**：对 build/sync 过程加互斥（lockfile 或进程锁），并在日志中打印“写库开始/写库完成/写 stamp”三个边界事件，便于审计。  
3) **门禁最小序列**：固化 `rag-accept`（或等价脚本）输出单一退出码；CI 只关注退出码与产物落盘位置。

---

## 7) 最小可复现（MRE）

**环境**：Windows 10；Python 3.10.11；仓库根目录 `<REPO_ROOT>
**步骤（CMD）**：

1) 生成强校验：
```cmd
cd /d <REPO_ROOT>
rag-check --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json --json-out data_processed\build_reports\check.json
```

2) 观察 status（应为 OK）：
```cmd
rag-status
```

3) 做一次“读库/评测”：
```cmd
python tools\run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://127.0.0.1:8000/v1 --k 5 --embed-model BAAI/bge-m3 --timeout 120 --trust-env auto
```

4) 再看 status（旧逻辑下容易变 STALE）：
```cmd
rag-status
```

**期望（与日志一致）**：`rag-check` PASS，但第二次 `rag-status` 可能出现 `DB mtime > check.json mtime` 进而判 STALE。【8:4†cmd_outoup_results.txt†L6-L15】【8:0†cmd_outoup_results.txt†L24-L28】

---

## 8) 一句话复盘

把“易变的文件系统目录 mtime”误用为“语义写库完成信号”，导致状态机输入抖动与自我阻塞；改为“写库成功后写入的单文件 stamp/或服务 API 信号”即可稳定闭环。

---

## 9) 方法论迁移（可复用工程经验）

1) **区分语义信号与操作噪声**  
   - 语义信号：plan 参数、依赖哈希、写库成功边界。  
   - 操作噪声：目录 mtime、临时文件、杀软/索引触碰、自动 checkpoint。  
   - 经验：状态机/门禁只吃“语义信号”；操作噪声只能作为观测指标，不能作为判定依据。

2) **用“显式状态文件”替代“隐式推断”**  
   - `db_build_stamp.json` / `dvc.lock` / `stable-status.txt` 的共同点：它们是“单点、可审计、可复用”的状态载体。  
   - 经验：只要你发现自己在用“遍历目录 + mtime”来推断流程阶段，几乎都可以替换为 stamp/lockfile。

3) **把门禁做成可组合的最小序列**  
   - 经验：把“补信号 → 强校验 → 生成基线 → strict status”做成一个 `rag-accept`，并给出单一退出码；能显著降低多设备/多 venv 的操作熵。

4) **契约优先（文档与代码同改）**  
   - 经验：像“stale 判定输入是什么”这种规则，必须进入 Reference（契约）；How-to 只给动作与链接，Tutorial 只给闭环。否则下一次换机/换人会重复踩坑。

---

### 关键结论的可核验证据（外部原始材料）

> 按“URL + 日期/版本 + 来源类型 + 定位”列出，便于下次新项目直接复用设计依据。

1) Chroma Client/Server 模式用于多进程/多机器（建议将状态信号转到服务层）  
- URL：https://docs.trychroma.com/guides/deploy/client-server-mode  
- 日期/版本：页面抓取 2026-01-02（以当日在线文档为准）  
- 来源类型：官方文档  
- 定位：标题 “Client-Server Mode”  

2) Chroma 运行模式与约束（Standalone vs Client/Server）  
- URL：https://cookbook.chromadb.dev/core/system_constraints/  
- 日期/版本：页面抓取 2026-01-02  
- 来源类型：官方 Cookbook  
- 定位：章节 “Operational Modes”  

3) SQLite WAL 机制会引入 -wal / -shm 文件与 checkpoint 行为（文件系统层不适合作为稳定语义信号）  
- URL：https://sqlite.org/wal.html  
- 日期/版本：页面抓取 2026-01-02  
- 来源类型：官方文档  
- 定位：段落 “There is an additional quasi-persistent '-wal' file and '-shm' ... checkpointing ...”  

4) DVC 用 dvc.lock 捕获依赖/参数哈希决定是否过期（更成熟的“哈希驱动过期”思路）  
- URL：https://doc.dvc.org/start/data-pipelines/data-pipelines  
- 日期/版本：页面抓取 2026-01-02  
- 来源类型：官方文档  
- 定位：段落 “dvc repro ... uses dvc.lock ... captures hashes ... parameters ...”  

5) Bazel workspace status 脚本（成熟的“构建状态写入/驱动失效”机制）  
- URL：https://bazel.googlesource.com/bazel/+/master/tools/buildstamp/get_workspace_status  
- 日期/版本：抓取 2026-01-02（master）  
- 来源类型：官方源码  
- 定位：脚本头部注释 “generate key-value information that represents the status of the workspace”  
