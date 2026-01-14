---
title: "Postmortem｜审查规范（Review Spec）优先级覆盖门禁 + 写回 HANDOFF（SSOT）"
version: 1.0
last_updated: 2026-01-13
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "Review Spec（SSOT/生成/校验）+ priority_order 覆盖门禁 + SSOT(HANDOFF) 写回"
  severity: P2
---

# Postmortem｜审查规范（Review Spec）优先级覆盖门禁 + 写回 HANDOFF（SSOT）

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
date: "2026-01-13"
mode: "solo_debug"
repo_path: "zhiz-llm-rag"
env:
  os: "Linux-4.4.0-x86_64-with-glibc2.36"
  python: "3.11.2"
scope:
  component: "Review Spec（SSOT/生成/校验）+ priority_order 覆盖门禁 + HANDOFF 写回"
  severity: "P2"
```

---

## 1) 总结（Summary）

本次复盘主题是把“审查规范（Review Spec）”作为长期治理资产稳定化，并把关键结论与门禁入口写回 `docs/explanation/HANDOFF.md`（SSOT）。问题触发点不是线上事故，而是“治理资产已落盘，但接手口径缺少复盘记录与 SSOT 写回”，导致新会话/新设备接手时对审查规范的入口、生成一致性、优先级覆盖不变量等信息需要重复推导。处置方式是：补齐 postmortem（证据账本 + 门禁验收），更新 postmortems 索引、LESSONS、PREFLIGHT，并在 HANDOFF 中固化门禁与复现命令。

---

## 2) 预期 vs 实际（Expected vs Actual）

- 预期：
  - Review Spec 作为 SSOT（JSON）+ 生成文档（MD）+ 校验门禁（exit code 0/2/3）被纳入 `reference.yaml` 的 `fast/ci/release` profiles，并且在 HANDOFF 中有稳定入口与“写回协议”说明。
  - `scope.priority_order` 中新增维度时，必须同步补齐 `checklists[].area`，否则门禁阻断（FAIL=2），避免出现“有优先级但无清单”的漂移。
- 实际：
  - Review Spec 已在仓库内存在且已接入 `docs/reference/reference.yaml`，但缺少针对该治理资产的 postmortem 与 HANDOFF 写回，导致“门禁存在但缺少接手口径/回滚策略/演进接口”。
  - Review Spec 的“生成一致性校验”曾出现渲染细节不一致导致误判（同一份 SSOT 与生成文档被校验为 out-of-date），需要把校验器与生成器的渲染规则对齐为单一口径。

---

## 3) 证据账本（Evidence Ledger）

> 说明：只记录可定位事实（文件 + 行号）。推断放在 RCA/迁移节。

- **E1（Facts）Review Spec SSOT 已落盘**
  - 来源：`docs/reference/review/review_spec.v1.json:L15-L106`（字段：`scope.priority_order` 与 `checklists[].area`）
  - 证明点：优先级维度与清单域是显式结构化字段，可被门禁程序直接校验。

- **E2（Facts）priority_order 覆盖门禁实现**
  - 来源：`tools/validate_review_spec.py:L240-L280`（函数：`_validate_priority_coverage`）
  - 证明点：当 `priority_order` 中存在未被 `checklists[].area` 覆盖的维度时，门禁产生 FAIL（exit code=2），阻断合并。

- **E3（Facts）Review Spec 校验门禁已接入 Gate profiles**
  - 来源：`docs/reference/reference.yaml:L34-L116`（`profiles.fast/ci/release` 均包含 `validate_review_spec`）
  - 证明点：Review Spec 一致性检查成为默认回归路径的一部分，不依赖人工记忆。

- **E4（Facts）生成文档一致性验证命令与 PASS 信号**
  - 来源：运行输出（命令）：`python tools/generate_review_spec_docs.py --root . --check`
  - 退出码：0
  - 摘要输出：
    ```
    [INFO] repo_root = /mnt/data/zhiz_llm_rag_work
    [INFO] in = /mnt/data/zhiz_llm_rag_work/docs/reference/review/review_spec.v1.json
    [INFO] out = /mnt/data/zhiz_llm_rag_work/docs/reference/review/REVIEW_SPEC.md
    [PASS] Review Spec doc is up-to-date
    ```

- **E5（Facts）Review Spec 总体验证命令与 PASS 信号**
  - 来源：运行输出（命令）：`python tools/validate_review_spec.py --root .`
  - 退出码：0
  - 摘要输出：
    ```
    [INFO] repo_root = /mnt/data/zhiz_llm_rag_work
    [INFO] ssot = /mnt/data/zhiz_llm_rag_work/docs/reference/review/review_spec.v1.json
    [INFO] out  = /mnt/data/zhiz_llm_rag_work/docs/reference/review/REVIEW_SPEC.md
    [PASS] Review Spec SSOT + generated doc are consistent
    ```

---

## 4) 复现（MRE：最小可复现）

```bash
# 1) 生成文档一致性检查（只检查，不写入）
python tools/generate_review_spec_docs.py --root . --check

# 2) Review Spec 全体验证（含 priority_order 覆盖关系 + 生成一致性）
python tools/validate_review_spec.py --root .
```

**期望结果**
- 两条命令退出码均为 0；
- 任意一处出现 FAIL 时，`validate_review_spec` 退出码为 2，且提示修复路径（例如 `--write`）。

---

## 5) 排查过程（Investigation）

1) 确认 Review Spec 是否为“已纳入默认回归”的治理资产：定位 `docs/reference/reference.yaml` 中 profiles 的 steps 列表，并确认包含 `validate_review_spec`。
2) 复核 Review Spec 的不变量是否已可执行化：定位 `tools/validate_review_spec.py` 是否包含对 `scope.priority_order` 与 `checklists[].area` 的覆盖检查（避免“新增优先级维度但忘记补清单”进入主分支）。
3) 对比生成器与校验器的渲染口径：若生成器 `--check` PASS，但校验器判断 out-of-date，则说明渲染规则存在偏差；此类偏差需要在工具层收敛为单一口径，否则会导致门禁误报与重复返工。

---

## 6) 根因分析（RCA）

- 直接原因（Facts）：
  - Review Spec 作为治理资产已存在，但缺少“复盘 → LESSONS → PREFLIGHT → HANDOFF”链路写回，导致 SSOT（HANDOFF）未携带接手口径，复用价值被削弱。
- 机制原因（Inference，推断）：
  - 治理类资产的“可发现性”与“可执行性”若不在 SSOT（HANDOFF）与入口文档中固化，会在换机/新会话时退化为经验性操作，增加漂移概率。
  - 生成器与校验器若各自持有渲染逻辑，会因细节差异导致一致性误判；应把渲染规则视作契约的一部分并保持单一口径。

---

## 7) 修复与处置（Mitigation & Fix）

- 已处置项（本次落盘）：
  - 新增本 postmortem，并计划通过索引更新脚本写入 `docs/postmortems/INDEX.md`。
  - 在 HANDOFF（SSOT）中新增 Review Spec 门禁入口与复现命令，并记录本次复盘链接与变更点。
- 关键修复点（工具一致性）：
  - 对齐 Review Spec 生成器与校验器的渲染规则，使 `validate_review_spec` 对同一份 `review_spec.v1.json` 与 `REVIEW_SPEC.md` 产生确定性一致判断（PASS/FAIL）。

---

## 8) 回归测试与门禁（Regression & Gates）

- Gate/CI Lite（单入口）：
  - `python tools/gate.py --profile fast --root .`
  - 或 Windows：`tools\run_ci_gates.cmd`
- 关键门禁点：
  - `validate_review_spec`：检查 `priority_order` 覆盖关系 + 生成文档一致性（FAIL=2）
- 典型故障注入（用于验证门禁确实阻断）：
  - 在 `review_spec.v1.json` 的 `scope.priority_order` 追加一个新维度但不新增同名 `checklists[].area`，期望 `validate_review_spec` FAIL 并提示 missing areas。

---

## 9) 行动项（Action Items）

- A1：更新 `docs/explanation/HANDOFF.md`（SSOT）  
  - 内容：新增 Review Spec 的入口/命令/修复路径，并在变更日志记录本次复盘（回链到本文件）。
  - 验收：新会话按 HANDOFF 的 Read→Derive→Act→Write-back 可直接定位到 Review Spec 与门禁命令。
- A2：更新 `docs/explanation/LESSONS.md`  
  - 内容：沉淀“优先级维度必须与清单域覆盖门禁化”的可迁移规则，并写明适用/不适用边界与验收命令。
- A3：更新 `docs/howto/PREFLIGHT_CHECKLIST.md`  
  - 内容：Quick Path 增加 Review Spec 一致性门禁的最小命令与 PASS 判据。

---

## 10) 方法论迁移（可迁移资产）

- 可迁移规则：
  - 任何“多枚举维度 + 多规则集合”的治理机制，都必须有“覆盖关系门禁”（例如：priority_order ↔ checklists.area；bucket 枚举 ↔ 聚合报表字段）。
  - 任何“SSOT → 生成产物”的链路，都必须有一致性校验与单一渲染口径，避免双实现导致的门禁误报。
- 资产落点（本仓库）：
  - SSOT：`docs/explanation/HANDOFF.md`、`docs/reference/reference.yaml`、`docs/reference/review/review_spec.v1.json`
  - 工具：`tools/validate_review_spec.py`、`tools/generate_review_spec_docs.py`
  - 清单：`docs/howto/PREFLIGHT_CHECKLIST.md`
  - 原则库：`docs/explanation/LESSONS.md`

---

## 11) 信息缺口与补采计划（Gaps & Next Evidence）

- 缺口清单：无（本次为治理落地型复盘，证据均来自仓库工件与本地门禁运行输出）。
- 补采命令/文件：N/A
- 预期看到什么：N/A

---

## 12) 输出自检（Quality Gates）

- Q1：Yes（结构包含 TOC + 0–12 小节）
- Q2：Yes（Evidence 为可定位工件/命令输出；推断已标注）
- Q3：Yes（包含可复制 MRE 与期望结果）
- Q4：Yes（行动项可执行且有验收命令）
- Q5：Yes（写回协议覆盖 postmortem → LESSONS → PREFLIGHT → HANDOFF）
- Q6：Yes（没有把外部资料当作关键结论唯一依据）
