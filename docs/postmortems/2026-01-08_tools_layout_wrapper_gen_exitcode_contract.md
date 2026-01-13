---
title: "Postmortem: tools/分层与全量 wrapper 生成门禁自举失败 + 退出码契约对齐"
version: 1.0
date: "2026-01-08"
mode: "solo_debug"
repo: "zhiz-llm-rag (public)"
scope:
  - "tools/ 与 src/ 的工具分层（SSOT / wrapper / repo-only）"
  - "全量 wrapper 生成器（gen_tools_wrappers.py）一致性门禁"
  - "退出码契约（PASS/FAIL/ERROR = 0/2/3）"
severity: "P2"
status: "done (复盘文档完成；代码落地以仓库 commit 为准)"
last_updated: "2026-01-08"
---

## 目录


- [0) 元信息](#0-元信息)
- [1) 总结（Summary）](#1-总结summary)
- [2) 预期 vs 实际（Expected vs Actual）](#2-预期-vs-实际expected-vs-actual)
- [3) 证据账本（Evidence Ledger）](#3-证据账本evidence-ledger)
- [4) 复现（MRE：最小可复现）](#4-复现mre最小可复现)
- [5) 排查过程（Investigation）](#5-排查过程investigation)
  - [5.1 Timeline](#51-timeline)
  - [5.2 Response/Comms](#52-responsecomms)
  - [5.3 Investigation Steps](#53-investigation-steps)
- [6) 根因分析（RCA）](#6-根因分析rca)
- [7) 修复与处置（Mitigation & Fix）](#7-修复与处置mitigation--fix)
- [8) 回归测试与门禁（Regression & Gates）](#8-回归测试与门禁regression--gates)
- [9) 行动项（Action Items）](#9-行动项action-items)
- [10) 方法论迁移（可迁移资产）](#10-方法论迁移可迁移资产)
- [11) 信息缺口与补采计划（Gaps & Next Evidence）](#11-信息缺口与补采计划gaps--next-evidence)
- [12) 输出自检（Quality Gates）](#12-输出自检quality-gates)

---

## 0) 元信息

- 环境（观测到的最小集合）：
  - OS：Windows（CMD）
  - venv：`.venv_embed`（从提示符推断）
  - Python 版本：**缺口**（见第 11 节）
- 触发命令（核心）：
  - `python tools\gen_tools_wrappers.py --check`
- 影响范围：
  - 目标是把 wrapper 生成器接入 CI/PR gates 作为“入口层确定性”门禁
  - 但自举脚本被纳入 wrapper 受管集合，导致门禁永远 FAIL
- 契约约束：
  - `docs/REFERENCE.md` 定义退出码：PASS=0 / FAIL=2 / ERROR=3（本事件涉及“异常退出码”一致性）

---

## 1) 总结（Summary）

**现象**  
运行 `python tools\gen_tools_wrappers.py --check` 时出现：

- `wrappers with missing SSOT`：要求 `tools/gen_tools_wrappers.py` 对应存在 `src/mhy_ai_rag_data/tools/gen_tools_wrappers.py`
- 同时列出大量 `wrappers not up-to-date`

**影响**  
- “全量 wrapper 一致性门禁”无法稳定通过（自举问题导致永久 FAIL）
- 若退出码不对齐（尤其异常退出码），CI 会把“工具异常”与“规则失败”混淆，排障成本上升

**一句话结论**  
这不是“缺实现很多”，而是“治理对象集合选择错误 + 缺少规则层硬隔离”，外加“退出码契约需要入口处显式映射”。

---

## 2) 预期 vs 实际（Expected vs Actual）

**预期**  
1) repo-only 工具（尤其是 wrapper 生成器本体）不应被当作“wrapper→SSOT 映射”的受管对象。  
2) `--check` 的失败语义清晰：
   - 规则不满足：FAIL=2
   - 脚本异常：ERROR=3（按 REFERENCE 契约）
3) 全量启用时，首次出现大量 `not up-to-date` 属可预期，但应可通过 `--write` 收敛。

**实际**  
1) 生成器自身被纳入“受管 wrapper 集合”，触发 `missing SSOT`。  
2) 由于 `missing SSOT` 属结构性阻断，导致你即使想用 `--write` 收敛 wrapper，也会先被卡住。  
3) 退出码契约存在，但工具入口未必显式做到“异常→3”，存在契约偏差风险。

---

## 3) 证据账本（Evidence Ledger）

> 说明：本节只记录“可核验事实”，推断放在 RCA 或方法论迁移。

- **E1：临时扫描脚本输出**
  - 载体：CMD 输出（`tmp_scan_tools_wrappers.py`）
  - 关键字段：`non_wrapper_tools_py` + `name_conflicts_tools_vs_src`
  - 证明点：`tools/` 中混有非 wrapper 脚本；并存在 `tools/` 与 `src/` 同名冲突（漂移风险面真实存在）

- **E2：全量 wrapper 生成器 check 输出**
  - 载体：CMD 输出（`python tools\gen_tools_wrappers.py --check`）
  - 关键字段：
    - `[FAIL] wrappers with missing SSOT: ... tools\gen_tools_wrappers.py ...`
    - `[FAIL] wrappers not up-to-date ...`（长列表）
  - 证明点：生成器自身被视为 wrapper；且存在大量 wrapper 内容未对齐模板

- **E3：退出码契约 SSOT**
  - 载体：仓库 `docs/REFERENCE.md`
  - 关键字段：PASS/FAIL/ERROR 的退出码定义为 0/2/3
  - 证明点：退出码不是“自由发挥”，是项目契约；异常退出码必须显式映射

---

## 4) 复现（MRE：最小可复现）

### 环境
- Windows CMD
- 仓库根目录（示例）：`D:\zhiz-c++\zhiz-llm-rag`
- venv：`.venv_embed`（推断）

### 命令
```bat
cd D:\zhiz-c++\zhiz-llm-rag
python tools\gen_tools_wrappers.py --check
```

### 期望
- 不应出现“生成器自身 missing SSOT”
- 若 wrapper 内容漂移，应可通过 `--write` 清零
- 退出码：规则失败为 2；脚本异常为 3（按契约）

### 实际
- 出现 `missing SSOT` 指向 `gen_tools_wrappers.py`
- 同时出现大量 `not up-to-date`

---

## 5) 排查过程（Investigation）

### 5.1 Timeline
- N/A（solo_debug，未记录精确时间戳）

### 5.2 Response/Comms
- N/A（solo_debug）

### 5.3 Investigation Steps

1) **先确认问题类型不是业务逻辑，而是“入口与结构治理”**  
   通过扫描输出看到 `tools/` 同时存在 wrapper、repo-only、以及与 `src/` 同名冲突的迹象（E1）。结论：应从“分层契约/门禁控制点”入手，而不是逐个脚本改细节。

2) **运行生成器门禁，定位结构性阻断点**  
   `--check` 先失败在 `missing SSOT`（E2）。这说明“受管集合包含了不该纳入的对象”（生成器自身），属于自举选择错误。

3) **对照项目契约，识别“退出码”属于硬约束**  
   即便结构问题修了，若退出码未对齐，CI 信号仍会失真（E3）。因此退出码对齐应作为门禁类脚本的共性修复。

---

## 6) 根因分析（RCA）

### 6.1 Trigger（直接触发）
尝试把 wrapper 生成器扩展到更大/全量覆盖并运行 `--check`，导致自举脚本进入受管集合（E2）。

### 6.2 Root Cause（根因）
**缺少规则层硬隔离**：没有在“受管对象选择逻辑”层面排除 repo-only 工具/生成器自身，导致它被强制套用 wrapper→SSOT 映射契约，从而产生 `missing SSOT` 并永久阻断（E2）。

### 6.3 Contributing Factors（促成因素）
- `tools/` 中历史脚本角色混杂（wrapper vs repo-only），缺少统一 marker/分类信号或缺少强制门禁（E1）。
- 首次全量启用时 `not up-to-date` 清单极长，噪声掩盖了“真正阻断点”（missing SSOT）（E2）。

### 6.4 Missing Controls（缺失控制点）
- 未在生成器中实现“排除 self / 排除 repo-only marker / 排除列表”的硬控制点。
- 门禁脚本入口未统一实现“异常→ERROR=3”的退出码映射（存在契约风险）（E3）。

---

## 7) 修复与处置（Mitigation & Fix）

> 本节描述目标态修复策略；具体代码以仓库落地为准。

1) **规则层兜底排除自举脚本**
   - 在生成器里强制 `exclude_self=true`
   - 支持 `exclude_wrappers` 配置
   - 若文件含 `REPO-ONLY TOOL` 标记，则不进入 wrapper 受管集合
   - 预期效果：`missing SSOT` 不再出现，门禁从“结构阻断”退化为“可写回收敛”

2) **全量对齐 wrapper 内容（一次性大 diff，但可控）**
   - 执行 `python tools\gen_tools_wrappers.py --write`
   - 再执行 `--check` 应 PASS
   - 要求：wrapper 不承载业务逻辑；若历史 wrapper 有逻辑，必须下沉到 `src/mhy_ai_rag_data/tools/<stem>.py`

3) **退出码契约对齐（0/2/3）**
   - 门禁类脚本应显式捕获未捕获异常并返回 `3`
   - 规则失败返回 `2`
   - PASS 返回 `0`

---

## 8) 回归测试与门禁（Regression & Gates）

### 建议门禁顺序（本地/CI一致）
1) `python tools\gen_tools_wrappers.py --check`（入口层确定性）
2) `python tools\check_tools_layout.py --mode fail`（结构契约：分类/同名冲突）
3) 现有 gates：entrypoints/md refs/pytest 等

### 验收标准
- `--check`：
  - 无 `missing SSOT`
  - `--write` 后无 `not up-to-date`
  - 退出码遵循 0/2/3
- `check_tools_layout --mode fail`：
  - 无同名冲突、无 unknown 分类、无违反 marker 规则

---

## 9) 行动项（Action Items）

| action_id | 类型 | 改动点 | owner | 截止 | 验证方式 | 回滚策略 |
|---|---|---|---|---|---|---|
| A1 | prevent | 生成器：排除 self + repo-only marker + exclude list | zhiz | 2026-01-09 | `gen_tools_wrappers --check` 无 `missing SSOT` | 回到清单模式分批推进 |
| A2 | prevent | 全量统一 wrapper：执行 `--write` 并提交产物 | zhiz | 2026-01-10 | `--check` PASS 且 diff 仅集中 tools wrapper | 分批纳入（10-20 个/批） |
| A3 | prevent | 退出码统一：异常→3，规则失败→2 | zhiz | 2026-01-10 | 人为造异常/规则失败并验证退出码 | 先只对核心门禁脚本强制 |
| A4 | doc | 文档：Golden Path / Preflight / CI gates 写入新门禁命令 | zhiz | 2026-01-11 | 从零按文档复现 PASS | 保留最小文档，只给链接 |

---

## 10) 方法论迁移（可迁移资产）

1) **分类先于自动化**：先让每个对象“可判定为 wrapper 或 repo-only”，再做全量自动化；否则自动化会选错对象（自举问题）。  
2) **门禁必须区分 FAIL 与 ERROR**：退出码是 CI 的信号通道；若异常退出码不对齐，排障会退化为人工猜测。  
3) **全量治理要先探测影响面**：先 `--check` 得到清单，再 `--write` 执行收敛；并在第一次大 diff 时拆分提交，避免掩盖真实风险。

---

## 11) 信息缺口与补采计划（Gaps & Next Evidence）

- 缺口：
  - Python 版本与解释器路径（将影响可复现性与兼容性结论）
  - 本次修复实际落地的 commit SHA / 文件列表（用于可审计回滚）
  - 修复后实际退出码观测值（CMD `%errorlevel%`）
- 补采命令：
```bat
python -V
python -c "import sys; print(sys.executable)"
python tools\gen_tools_wrappers.py --check
echo %errorlevel%
```
- 落盘建议：
  - 将输出写入 `data_processed/build_reports/` 作为 evidence artifact

---

## 12) 输出自检（Quality Gates）

- 是否按模板包含 Evidence Ledger、RCA、行动项、门禁建议：**Yes**
- Facts 与推断是否分离：**Yes**（证据 E1-E3 仅做证明点；推断仅出现在 RCA/迁移）
- 是否给出 MRE：**Yes**
- 是否明确列出信息缺口与补采命令：**Yes**
