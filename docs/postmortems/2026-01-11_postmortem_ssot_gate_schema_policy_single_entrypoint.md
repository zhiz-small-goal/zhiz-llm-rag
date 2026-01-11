---
title: "Postmortem｜门禁治理架构：SSOT → Gate 单入口 → JSON Schema →（可选）Conftest Policy"
version: 1.0
last_updated: 2026-01-11
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "gate 架构（SSOT / schema / policy / CI 单入口）"
  severity: P2
---

# Postmortem｜门禁治理架构：SSOT → Gate 单入口 → JSON Schema →（可选）Conftest Policy

## 目录（TOC）
- [0) 元信息（YAML）](#0-元信息yaml)
- [1) 总结（Summary）](#1-总结summary)
- [2) 预期 vs 实际（Expected vs Actual）](#2-预期-vs-实际expected-vs-actual)
- [3) 证据账本（Evidence Ledger）](#3-证据账本evidence-ledger)
- [4) 复现（MRE：最小可复现）](#4-复现mre最小可复现)
- [5) 排查过程（Investigation）](#5-排查过程investigation)
- [6) 根因分析（RCA）](#6-根因分析rca)
- [7) 修复与处置（Mitigation & Fix）](#7-修复与处置mitigation--fix)
- [8) 回归测试与门禁（Regression & Gates）](#8-回归测试与门禁regression--gates)
- [9) 行动项（Action Items）](#9-行动项action-items)
- [10) 方法论迁移（可迁移资产）](#10-方法论迁移可迁移资产)
- [11) 信息缺口与补采计划（Gaps & Next Evidence）](#11-信息缺口与补采计划gaps--next-evidence)
- [12) 输出自检（Quality Gates）](#12-输出自检quality-gates)

---

## 0) 元信息（YAML）

```yaml
date: "2026-01-11"
mode: "solo_debug"
repo_path: "zhiz-llm-rag"
incident_type: "入口漂移风险治理 / 门禁体系收敛"
affected_area:
  - "CI 只认 gate 单入口"
  - "SSOT（machine-readable）驱动 gates"
  - "gate_report JSON Schema 校验"
  - "（可选）Conftest/Rego 语义策略"
```

---

## 1) 总结（Summary）

- **发生了什么（Facts）**：在“公开发布/门禁治理”推进中，明确采用 **SSOT（machine-readable）→ Gate 单入口 → JSON Schema 校验 →（可选）Conftest Policy → CI 只认 gate** 的治理链路作为主方案（E1），并已在仓库内落地：`docs/reference/reference.yaml` 作为 SSOT（E2），`tools/gate.py` 作为 CI 单入口（E3/E4），`schemas/` 作为结构校验（E5/E3），`policy/`（Conftest/Rego）作为跨文件语义约束（E6/E7）。
- **影响（Inference，可证伪）**：
  - 收敛“入口不一致/参数口径分散”导致的门禁不可信问题：CI 与本地复跑更容易得到一致信号；
  - 将“经验/规则”从聊天/记忆迁移到可执行 SSOT，使新手/LLM 修改更难绕过。
  - 证伪方式：若 CI 仍存在绕过 gate 的路径（例如 workflow 直接调用脚本而不跑 gate），或 SSOT 与实际执行步骤不一致，则此收益不成立。

---

## 2) 预期 vs 实际（Expected vs Actual）

| 项 | 预期 | 实际 |
|---|---|---|
| 单一真源（SSOT） | 规则/步骤/版本只写一份，所有入口读取 | 已集中到 `docs/reference/reference.yaml`（E2） |
| 单入口 Gate | CI/PR/本地回归都走同一路径 | CI 已只运行 `python tools/gate.py --profile ci`（E4），gate 读取 SSOT 并执行 profile steps（E3） |
| 结构化产物契约 | `gate_report.json` 可被机器校验、可归档 | gate 生成 `gate_report.json`，并进行自校验（E3/E5）；CI 上传产物（E4） |
| 语义策略（可选） | 跨文件不变量（如“CI 必须跑 gate”）可被机器拦截 | 已提供 `policy/ci_workflow.rego` 强制 workflow 包含 gate 步骤（E6） |
| 本地提交前门禁 | pre-commit 尽量复用 gate（fast profile） | 当前 pre-commit 仍是“挑选的轻量脚本集合”，未直接调用 gate（E8）；属于待收敛项（见第 9 节） |

---

## 3) 证据账本（Evidence Ledger）

> 说明：只记录可定位的事实（文件 + 行号）。推断放在 RCA/迁移节。

- **E1（Facts）方案选择（对话记录）**
  - 来源：`ChatGPT-项目方案选择与实施.md:L25-L27`
  - 证明点：明确把“SSOT→Gate→Schema→Policy→CI 只认 gate”作为最稳路径。

- **E2（Facts）SSOT（machine-readable）落地**
  - 来源：`docs/reference/reference.yaml:L1-L55`
  - 证明点：SSOT 明确 exit_codes/paths/schemas/policy/gates（profiles + steps）的权威配置。

- **E3（Facts）Gate 单入口实现（SSOT 驱动 + 自校验）**
  - 来源：`src/mhy_ai_rag_data/tools/gate.py:L1-L18`（设计目标与退出码契约）
  - 来源：`src/mhy_ai_rag_data/tools/gate.py:L331-L421`（加载 SSOT、按 profile 执行 steps、写 report、自校验、输出统一汇总行）

- **E4（Facts）CI 工作流只认 gate（并上传结构化产物）**
  - 来源：`.github/workflows/ci.yml:L33-L53`
  - 证明点：CI 通过 `Gate (single entry)` 运行 gate，并 `Upload gate report (always)` 上传 `gate_report.json` 与 logs。

- **E5（Facts）JSON Schema（gate_report）**
  - 来源：`schemas/gate_report_v1.schema.json:L1-L20`
  - 证明点：schema 声明为 draft 2020-12，且 `schema_version=1` 等 required 字段固定。

- **E6（Facts）Policy：CI workflow 必须包含 gate 步骤**
  - 来源：`policy/ci_workflow.rego:L1-L16`
  - 证明点：缺 gate 步骤或缺产物上传时会 `deny`。

- **E7（Facts）Policy：reference.yaml 不变量校验**
  - 来源：`policy/reference.rego:L1-L28`
  - 证明点：对 exit code/paths/schema 指向等关键字段施加不变量，防 SSOT 漂移。

- **E8（Facts）pre-commit 当前未直接调用 gate**
  - 来源：`.pre-commit-config.yaml:L1-L22`
  - 证明点：pre-commit 目前执行的是若干单步脚本，而不是 `tools/gate.py --profile fast`。

---

## 4) 复现（MRE：最小可复现）

### 环境
- 任意 OS（Windows/Linux/macOS），Python 3.11+（CI matrix 亦为 3.11/3.12）（E4）。

### 命令
```bash
# repo root
python tools/gate.py --profile ci --root .

# 只跑轻量 profile（建议用于提交前）
python tools/gate.py --profile fast --root .
```

### 期望输出
- 控制台出现统一汇总行：`[gate] profile=... status=... rc=... report=...`（E3）。
- 产物存在：
  - `data_processed/build_reports/gate_report.json`
  - `data_processed/build_reports/gate_logs/*.log`（E3/E4）。

---

## 5) 排查过程（Investigation）

- Step 1：识别治理目标是“入口一致性 + 可观测 + 可回归”，而不是给每个脚本单独加一层 CI（避免入口漂移）。
- Step 2：将“规则/步骤/路径/版本”集中到 `docs/reference/reference.yaml`，把它作为机器可读 SSOT，并允许后续策略（schema/policy）引用同一真源（E2）。
- Step 3：实现 `tools/gate.py` 作为单入口 runner：按 profile 执行 SSOT steps，产出结构化 report 与 logs，并在生成后用 JSON Schema 自校验（E3/E5）。
- Step 4：在 CI 工作流中只调用 gate，并始终上传 `gate_report.json` 与 logs，保证失败也能取证（E4）。
- Step 5（可选）：引入 Conftest/Rego policy，将“跨文件语义不变量”（如 workflow 必须跑 gate）从文档转为机器拦截（E6/E7）。

---

## 6) 根因分析（RCA）

1) **Trigger（直接触发）**
- 当项目进入“公开发布 + 门禁固化”的阶段，原先“多脚本多入口”的方式在 CI/本地/新手操作中出现高概率口径漂移风险：同一条规则可能被不同入口以不同默认参数执行。

2) **Root Cause（根因）**
- **入口与规则缺少单一真源**：当“规则散落在多脚本/多文档/多 workflow step”时，入口会漂移，门禁的 PASS/FAIL 语义变得不可置信（E1 体现了对该风险的明确规避诉求）。

3) **Contributing Factors（促成因素）**
- **缺少结构化产物契约**：若只靠控制台文本输出，失败时很难自动聚合与长期追踪；且“写盘成功”信号可能掩盖“规则失败”的本质（与 2026-01-11 hygiene 事件的模式一致，可互为回链）。
- **语义规则需要跨文件表达**：例如“CI 必须只认 gate”无法仅靠 JSON Schema 表达，需要 policy 层（E6）。

4) **Missing Controls（缺失控制点/门禁）**
- MC1：pre-commit 仍未收敛到 gate（fast profile），存在“提交前与 CI 入口不一致”的残余风险（E8）。
- MC2：Conftest 在 Windows CI 尚未固定/安装（当前 workflow 仅 Linux 安装 conftest），policy 覆盖范围存在环境差异风险（E4/E2）。

---

## 7) 修复与处置（Mitigation & Fix）

- **最终修复（已落地）**
  1) SSOT：`docs/reference/reference.yaml`（集中 exit_codes/paths/schemas/gates/policy）（E2）
  2) Gate：`tools/gate.py` 单入口（按 profile 执行 + 产物输出 + JSON Schema 自校验）（E3/E5）
  3) CI：workflow 仅调用 gate，并上传结构化产物与 logs（E4）
  4) Policy（可选）：Conftest/Rego 对 SSOT 不变量与 workflow 关键步骤做语义校验（E6/E7）

- **回滚点**
  - 若 policy 引入学习成本过高，可先把 policy 设为 `enabled=false` 或在 profile 中移除 `policy_conftest`，保留 SSOT+Gate+Schema 三层（E2/E3）。

---

## 8) 回归测试与门禁（Regression & Gates）

- 本地回归（推荐）：
  - `python tools/gate.py --profile ci --root .`
  - `python tools/gate.py --profile fast --root .`
- CI 门禁（现状）：
  - `.github/workflows/ci.yml` 只跑 gate，失败也上传 gate_report + logs（E4）。
- PASS 条件（基线）：
  - `gate_report.json.summary.overall_rc == 0` 且 schema 自校验无 `gate_report_schema_invalid` warning（E3/E5）。

---

## 9) 行动项（Action Items）

| action_id | 类型 | 改动点（文件/脚本/配置） | owner | due | 验证方式（命令 + PASS 条件） | 回滚策略 |
|---|---|---|---|---|---|---|
| A1 | 收敛入口 | `.pre-commit-config.yaml`：新增/替换为 `python tools/gate.py --profile fast --root .`（或保证等价且引用同一 SSOT） | zhiz | TBD | `pre-commit run -a`，且输出与 `gate --profile fast` 一致 | 保留旧 hooks 并并行一段时间 |
| A2 | 收敛入口 | `tools/run_ci_gates.cmd`：改为调用 `python tools/gate.py --profile ci`（减少重复实现） | zhiz | TBD | Windows 上 `tools\run_ci_gates.cmd` 产出 gate_report 且 rc=0 | 保留旧脚本为 `run_ci_gates_legacy.cmd` |
| A3 | 覆盖一致性 | CI：Windows runner 也安装/使用 conftest 或将 policy 明确标记为 Linux-only（避免“同 PR 不同 OS 语义不同”） | zhiz | TBD | Windows job 上 policy step 结果可观测且一致 | policy 设 required=false 或先禁用 |

---

## 10) 方法论迁移（可迁移资产）

- **治理链路（推荐默认）**：SSOT（machine-readable）→ Gate 单入口 → JSON Schema（结构）→ Policy（语义，可选）→ CI 只认 gate。
- **关键取舍**：
  - Schema（JSON）擅长“结构不变量”，Policy（Rego）擅长“跨文件语义不变量”；两者组合能把“规则”从文档/经验迁移到机器执行（E5/E6）。
  - Policy 学习与版本锁定有成本，适合在规则数量/复杂度上来后再启用；但“workflow 必须跑 gate”这种强语义，优先级较高（E6）。

---

## 11) 信息缺口与补采计划（Gaps & Next Evidence）

- G1：pre-commit 与 gate fast profile 的口径一致性尚未落地（E8）。
- G2：Windows CI 上 policy 的启用策略（安装 conftest vs 跳过）需要明确，并写入 SSOT（E2/E4）。
- G3：若要把“SSOT 变更”做得更硬，可追加：对 `reference.yaml` 的 JSON Schema 校验（当前用 rego 做了关键字段不变量，但未覆盖全部字段）。

---

## 12) 输出自检（Quality Gates）

- [x] 覆盖 0–12 小节，且每节可独立阅读。
- [x] Evidence Ledger 每条都可定位到文件+行号（E1–E8）。
- [x] 推断（Inference）均给出可证伪方式。
- [x] 行动项表包含验证方式与回滚策略。
