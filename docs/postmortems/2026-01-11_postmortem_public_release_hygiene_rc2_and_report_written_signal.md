---
title: "Postmortem｜check_public_release_hygiene：rc=2（FAIL）与 report_written 信号误读"
version: 1.0
last_updated: 2026-01-11
language: zh-CN
mode: solo_debug
scope:
  repo: zhiz-llm-rag
  component: "gate / check_public_release_hygiene（public release hygiene）"
  severity: P3
---

# Postmortem｜check_public_release_hygiene：rc=2（FAIL）与 report_written 信号误读


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
repo_path: "zhiz-llm-rag（本地 Windows repo）"
env:
  os: "Windows（用户本机）"
  python: "项目 venv（.venv_embed）"
  key_tools:
    - "python tools/gate.py --profile ci"
    - "python tools/check_public_release_hygiene.py"
scope:
  incident_type: "信号误读 + 证据采集不足"
  affected_step: "check_public_release_hygiene"
```

---

## 1) 总结（Summary）

- **发生了什么**：`gate` 执行到 `check_public_release_hygiene` 时返回 `rc=2`，因此在 `gate_report.json` 里被归类为 `FAIL`；同时日志出现 `[OK] report_written=...`，被误当成“检查通过”。（Facts：E1/E2/E4/E6）
- **影响**：排查方向偏离（先纠结“是否写到 Desktop”而不是定位 `HIGH` 命中项），并存在把包含用户名的 Desktop 绝对路径带入分享/截图的风险。（Inference：E2/E5/E6）
- **当前状态**：已明确“权威结果=退出码/门禁状态”，但缺少 `public_release_hygiene_report_*.md` 的具体命中项证据，无法对 `rc=2` 的内容性根因下结论。（Facts：E4；Gaps：见第 11 节）

---

## 2) 预期 vs 实际（Expected vs Actual）

| 项 | 预期 | 实际 |
|---|---|---|
| gate 结果 | `check_public_release_hygiene` 为 PASS（rc=0） | `rc=2` → gate 归一为 `FAIL`（E1/E3） |
| 人类可读信号 | 控制台输出能直接说明“通过/失败 + 原因入口” | 出现 `[OK] report_written=...`，但未同时输出 `HIGH` 统计或明确的 `[RESULT] FAIL`，容易误读（E2/E4） |
| 报告落盘路径 | repo 内 `data_processed/build_reports/` | 观测到落到 Desktop（E2）；结合源码推断为写盘失败触发 fallback（Inference：E5/E6） |

---

## 3) 证据账本（Evidence Ledger）

> 说明：E# 必须可定位（文件路径 + 行号）。任何推断必须引用至少一个 E#，并给出可证伪方式。

### E1（Facts）gate 结果片段（用户提供）
- 来源：`ChatGPT-项目方案选择与实施.md:L3265-L3271`
```text
3265: ## Prompt:
3266: 这个错误是什么意思:  "rc": 2,
3267:       "status": "FAIL",
3268:       "elapsed_ms": 2659,
3269:       "log_path": "D:/zhiz-c++/zhiz-llm-rag/data_processed/build_reports/gate_logs/check_public_release_hygiene.log",
3270:       "start_ts": "2026-01-11T09:37:33.564317Z",
3271:       "end_ts": "2026-01-11T09:37:36.223610Z"
```

### E2（Facts）日志里出现 report_written（用户提供）
- 来源：`ChatGPT-项目方案选择与实施.md:L3396-L3400`
```text
3396: 
3397: ## Prompt:
3398: 日志写的是这样的:[OK] report_written=C:\Users\<USER>\Desktop\public_release_hygiene_report_20260111_173736.md
3399: 
3400: ## Response:
```

### E3（Facts）gate 的退出码→状态映射（rc=2 → FAIL）
- 来源：`src/mhy_ai_rag_data/tools/gate.py:L65-L73`
```text
0064: 
0065: def _norm_status(rc: int) -> str:
0066:     if rc == 0:
0067:         return "PASS"
0068:     if rc == 2:
0069:         return "FAIL"
0070:     if rc == 3:
0071:         return "ERROR"
0072:     # unexpected rc -> treat as ERROR (but keep original rc in report)
0073:     return "ERROR"
```

### E4（Facts）hygiene 脚本：打印 report_written，但以 HIGH 数量决定退出码
- 来源：`tools/check_public_release_hygiene.py:L882-L889`
```text
0876:         out_path.write_text(report, encoding="utf-8")
0877:     except Exception:
0878:         fallback = _desktop_dir() / f"public_release_hygiene_report_{_now_tag()}.md"
0879:         fallback.write_text(report, encoding="utf-8")
0880:         out_path = fallback
0881: 
0882:     try:
0883:         shown = _rel(out_path, repo_root)
0884:     except Exception:
0885:         shown = str(out_path)
0886:     print(f"[OK] report_written={shown}")
0887: 
0888:     highs = sum(1 for f in findings if f.severity == "HIGH")
0889:     return 2 if highs > 0 else 0
```

### E5（Facts）hygiene 脚本：写入失败时 fallback 到 Desktop
- 来源：`tools/check_public_release_hygiene.py:L870-L880`
```text
0870:     try:
0871:         out_path.parent.mkdir(parents=True, exist_ok=True)
0872:     except Exception:
0873:         pass
0874: 
0875:     try:
0876:         out_path.write_text(report, encoding="utf-8")
0877:     except Exception:
0878:         fallback = _desktop_dir() / f"public_release_hygiene_report_{_now_tag()}.md"
0879:         fallback.write_text(report, encoding="utf-8")
0880:         out_path = fallback
```

### E6（Facts）hygiene 脚本：file-scope 与 respect-gitignore 的 Git 语义
- 来源：
  - `tools/check_public_release_hygiene.py:L735-L769`（参数默认值）
  - `tools/check_public_release_hygiene.py:L283-L323`（选取文件范围的实现）
```text
0735: def main(argv: Optional[List[str]] = None) -> int:
0736:     ap = argparse.ArgumentParser()
0737:     ap.add_argument("--repo", default=".", help="repo path (default=.)")
0738:     ap.add_argument("--config", default=None, help="optional json config path")
0739:     ap.add_argument("--history", type=int, default=0, help="history scan 0/1 (default=0)")
0740:     ap.add_argument(
0741:         "--max-history-lines",
0742:         type=int,
0743:         default=200000,
0744:         help="max lines for history scan (default=200000; <=0 means no limit)",
0745:     )
0746:     ap.add_argument(
0747:         "--file-scope",
0748:         default="tracked_and_untracked_unignored",
0749:         choices=["tracked", "tracked_and_untracked_unignored", "worktree_all"],
0750:         help="file selection scope for content scans (default=tracked_and_untracked_unignored)",
0751:     )
0752:     ap.add_argument(
0753:         "--respect-gitignore",
0754:         default=True,
0755:         action=argparse.BooleanOptionalAction,
0756:         help="when including untracked files, exclude paths ignored by gitignore (default=True)",
0757:     )
0758:     ap.add_argument("--out", default=None, help="output report path (default: repo-local build_reports)")
0759:     args = ap.parse_args(argv)
0760: 
0761:     repo = Path(args.repo).resolve()
0762:     cfg_path = Path(args.config).resolve() if args.config else None
0763:     cfg = load_config(cfg_path)
0764: 
0765:     # Prefer scanning at repo toplevel for stable relative paths.
0766:     top = git_toplevel(repo)
0767:     repo_root = top if top else repo
0768: 

0282: 
0283: def select_scan_files(
0284:     repo_root: Path,
0285:     cfg: dict,
0286:     file_scope: str,
0287:     respect_gitignore: bool,
0288:     tracked_list: Optional[List[str]],
0289: ) -> Tuple[List[Path], Dict[str, int]]:
0290:     """Select files to scan based on git scope and gitignore rules.
0291: 
0292:     file_scope:
0293:       - tracked: only files in `git ls-files`
0294:       - tracked_and_untracked_unignored: tracked + untracked but NOT ignored by gitignore
0295:       - worktree_all: existing behavior (walk the worktree regardless of git)
0296: 
0297:     Returns (files, meta_counts).
0298:     """
0299:     exclude = set(cfg.get("exclude_dirs", []))
0300: 
0301:     if file_scope == "worktree_all" or tracked_list is None:
0302:         files = list(iter_repo_files(repo_root, cfg))
0303:         return files, {
0304:             "tracked": 0,
0305:             "untracked_total": 0,
0306:             "untracked_ignored": 0,
0307:             "untracked_unignored": 0,
0308:             "scanned": len(files),
0309:         }
0310: 
0311:     tracked_set = {p.replace("\\", "/") for p in tracked_list}
0312: 
0313:     untracked_all: List[str] = []
0314:     untracked: List[str] = []
0315:     ignored: set[str] = set()
0316:     if file_scope != "tracked":
0317:         untracked_all = git_status_untracked(repo_root)
0318:         untracked = list(untracked_all)
0319:         if respect_gitignore:
0320:             ignored = git_check_ignore(repo_root, untracked)
0321:             untracked = [p for p in untracked if p not in ignored]
0322: 
0323:     # De-dupe and filter by scan_roots/exclude_dirs
0324:     candidates = set(tracked_set) | set(untracked)
0325: 
0326:     files: List[Path] = []
0327:     for rel in sorted(candidates):
0328:         rel = rel.replace("\\", "/")
0329:         if not _under_scan_roots(rel, cfg):
0330:             continue
0331:         if any(part in exclude for part in Path(rel).parts):
0332:             continue
```

---

## 4) 复现（MRE：最小可复现）

> 目标：复现“rc=2 且出现 report_written”的形态，并能定位到 `HIGH` 命中项。

### 环境
- Windows（CMD）
- 在 repo 根目录执行（避免 repo_root 解析漂移）

### 命令（建议）
```bat
python tools/check_public_release_hygiene.py --repo . --history 0 --file-scope tracked_and_untracked_unignored --respect-gitignore
echo %ERRORLEVEL%
```

### 期望 vs 实际
- 期望（PASS）：`%ERRORLEVEL%` 为 `0`；报告 `HIGH=0` 且 `MED=0`。
- 实际（FAIL）：`%ERRORLEVEL%` 为 `2`（E4）；控制台仍可能打印 `report_written=...`（E4）。

---

## 5) 排查过程（Investigation）

1) **先确认权威信号**：以 `rc`/gate 状态为准，而不是以 `report_written` 为准。（Facts：E1/E3/E4）  
2) **再定位“内容性失败”的证据入口**：打开 `public_release_hygiene_report_*.md`，搜索 `[HIGH]` 标题块。（Inference：E4；可证伪：提供报告文件即可验证）  
3) **若报告落到 Desktop**：说明写入 repo 默认路径失败，触发 fallback。（Inference：E5；可证伪：在 log/异常栈中寻找 write_text 的异常或复现为只读目录）  
4) **确认扫描口径**：使用默认 `tracked_and_untracked_unignored` + `--respect-gitignore`，避免把已忽略的本地数据目录当成发布输入集。（Facts：E6）

---

## 6) 根因分析（RCA）

### 6.1 直接原因（Direct Cause）
- **门禁失败的直接原因**：脚本统计到 `HIGH > 0`，因此返回 `rc=2`。（Facts：E4）

> 信息缺口：具体哪些 `HIGH` 触发（如 secrets/绝对路径/大文件/二进制/图片等）缺失，无法进一步定因。（见第 11 节）

### 6.2 促成因素（Contributing Factors）
1) **信号歧义**：`[OK] report_written=...` 在 FAIL 情况下同样会打印，且与最终 `rc=2` 不在同一行输出，增加误读概率。（Facts：E4；Inference：误读发生于本事件 E2）  
2) **输出路径隐私/可复现性风险**：写入失败会 fallback 到 Desktop，可能携带用户名绝对路径，影响可复现与对外分享。（Facts：E5；Inference：本事件 Desktop 即由 fallback 触发，证伪方式见 5.3）  

### 6.3 根因（Root Cause）
- **根因（信号层）**：工具输出缺少“单一权威结果行”（例如 `[RESULT] status=FAIL rc=2 highs=N`），导致人类在缺证据时用次要信号（report_written）替代判断。（Inference：E2/E4；可证伪：补充一行汇总后观察误读是否显著下降）

---

## 7) 修复与处置（Mitigation & Fix）

### 7.1 立即止血（无需改代码）
- **按退出码判断**：跑完 hygiene 后立刻 `echo %ERRORLEVEL%`；非 0 直接当 FAIL。（Facts：E4）
- **按报告定位**：在报告中搜 `[HIGH]`，逐条处理，直到 `HIGH=0`。（Inference：E4；证伪：提供报告可验证）
- **避免 Desktop 路径扩散**：若 `report_written` 指向 Desktop，优先排查 repo 内 `data_processed/build_reports/` 的权限/路径问题，并改用 `--out` 指定 repo 内路径。（Facts：E5；Inference：E2）

### 7.2 中期修复（建议改代码，但本次仅记录）
- 输出末尾增加 **权威汇总行**（示例）：`[RESULT] status=FAIL rc=2 highs=N meds=M report=...`，并在 fallback 时加 `[WARN] fallback_desktop=... reason=...`。（Inference：E4/E5）

---

## 8) 回归测试与门禁（Regression & Gates）

### 8.1 回归测试：hygiene 单步
```bat
python tools/check_public_release_hygiene.py --repo . --history 0 --file-scope tracked_and_untracked_unignored --respect-gitignore
echo %ERRORLEVEL%
```
**PASS 条件**
- `%ERRORLEVEL%` 为 `0`
- 报告 `HIGH=0` 且 `MED=0`

### 8.2 回归测试：gate（profile=ci）
```bash
python tools/gate.py --profile ci --root .
```
**PASS 条件**
- gate 进程退出码为 0
- `gate_report.json` 中 `check_public_release_hygiene` 为 PASS（rc=0）（E3）

---

## 9) 行动项（Action Items）

| ID | 动作 | 类型 | 验收标准 | Owner |
|---|---|---|---|---|
| A1 | 将“退出码为准、report_written 非 PASS 信号”写入 Preflight | Doc | checklist 更新合并 | zhiz |
| A2 | 在 postmortem 中补齐 `public_release_hygiene_report_*.md` 的 HIGH 证据 | Evidence | Evidence Ledger 新增 E7+，并能复现具体命中项 | zhiz |
| A3 | （可选）为 hygiene 输出增加 `[RESULT] ...` 汇总行 | Code | 控制台单行可判断结果；误读显著减少 | zhiz |

---

## 10) 方法论迁移（可迁移资产）

### 10.1 This time（事件级公式）
- **先定权威信号**（退出码/结构化报告）→ 再看人类可读输出 → 最后才看“写盘成功/耗时”等辅助信号。（Facts：E1/E3/E4）

### 10.2 Recurring pattern（模式级归类）
- 失败模式标签：`不可观测`（信号歧义）、`契约漂移`（对退出码契约理解不一致）

### 10.3 Principles（原则级规则）
1) **单一权威行（Single-line SSOT）**：CLI 必须在最后输出一行可机器/人类共同判读的结果汇总。
2) **“写盘成功”与“检查通过”分离**：I/O 成功是必要非充分条件，必须显式区分。

### 10.4 Engineering → Life（跨域类比）
- 不用“过程指标”（写盘成功）替代“结果指标”（退出码/高优先级风险清零）；先对齐判定口径，再投入时间优化过程。

---

## 11) 信息缺口与补采计划（Gaps & Next Evidence）

### 缺口
- 缺少本次 `public_release_hygiene_report_*.md` 的内容（至少：Summary + 所有 `[HIGH]` 标题）。
- 缺少 `data_processed/build_reports/gate_logs/check_public_release_hygiene.log` 的关键段落（前 50 行 + 触发项附近）。

### 补采计划（最小）
1) 附上报告文件（或粘贴：Summary + `[HIGH]` 段落）。
2) 附上 log 的前 50 行与任何异常栈。
3) 若 Desktop 为 fallback：尝试在只读目录复现写入失败，以确认触发路径。（对应 E5 的证伪）

---

## 12) 输出自检（Quality Gates）
- [x] Facts 与 Inference 已区分，且每条推断引用了至少一个 E#。
- [x] 关键契约（rc→status、HIGH→rc=2、fallback→Desktop、file-scope 语义）均有源码定位证据（E3/E4/E5/E6）。
- [x] 明确列出信息缺口，避免把“未采集证据的内容性根因”写成事实。
