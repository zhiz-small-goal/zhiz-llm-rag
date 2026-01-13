---
title: "Postmortem：开源项目补齐仓库健康文件（CHANGELOG/CITATION/.editorconfig + CoC 联系方式）"
version: 0.1
last_updated: 2026-01-09
scope: "public release readiness / repo health files"
owner: zhiz
status: done
---

# 2026-01-09_postmortem_open_source_repo_health_files.md 目录


- [0. 事件概述](#0-事件概述)
- [1. 影响范围](#1-影响范围)
- [2. 时间线](#2-时间线)
- [3. 根因分析](#3-根因分析)
- [4. 做得好的](#4-做得好的)
- [5. 做得不好的](#5-做得不好的)
- [6. 行动项](#6-行动项)
- [7. 验证方式](#7-验证方式)
- [8. 参考资料](#8-参考资料)
- [9. 附录](#9-附录)

---

## 0. 事件概述

**背景**：准备将仓库公开/开源时，需要确保“对外可用、对外可理解、对外可协作”。在本次补齐过程中，识别出仓库缺少若干基础治理文件（CHANGELOG、CITATION、.editorconfig），以及 Code of Conduct 的“专用联系渠道”尚未工程化落地（邮箱/转发/归档）。

**触发点**：在一次“公开发布前置检查”梳理里，显式列出了缺失项（CHANGELOG/CITATION/.editorconfig），并提出“专用渠道怎么加入文件、邮箱转发是否足够”等具体问题（见证据锚点）。

**处置目标**：把“开源补齐”从一次性手工行为，升级为：
- 可复制的文件模板（仓库根目录治理文件）；
- 可执行的检查（preflight + 脚本），在 push/public 前即可发现缺口；
- 可迁移经验沉淀（LESSONS/HANDOFF）。

**结论**：本次以“最小可用”为原则，新增/补齐了 CHANGELOG.md、CITATION.cff、.editorconfig 三类文件模板，并提供了一个 stdlib-only 的 `tools/check_repo_health_files.py` 作为 Public Release Preflight 的固定检查项；同时把经验写回 `docs/howto/PREFLIGHT_CHECKLIST.md` 与 `docs/explanation/LESSONS.md`。

**证据锚点（本仓库内）**：
- `docs/howto/PREFLIGHT_CHECKLIST.md`（新增 3.5）
- `docs/explanation/LESSONS.md`（扩展“公开发布前置检查”条目）
- `tools/check_repo_health_files.py`（新增）

---

## 1. 影响范围

- **对外用户理解成本上升**：缺少 CHANGELOG 时，外部用户难以判断变更与兼容性，升级/回滚决策依赖 commit diff（噪声大）。
- **引用场景不可用或不友好**：缺少 CITATION.cff 时，GitHub 的引用入口与机器可读引用信息缺失，降低学术/引用可用性。
- **协作/Review 噪声**：缺少 .editorconfig 时，不同 IDE/平台会制造换行/缩进/末尾空格差异，导致无意义 diff。
- **治理渠道不清晰**：Code of Conduct 的举报/联系渠道若使用个人邮箱或不稳定邮箱，可能导致处理不可追踪、权限/交接困难。
- **历史修复成本**：当错误提交已经推到受保护 main 时，不能依赖强推/重写历史，需要用 revert 走可审计回滚链路（更符合公开仓库的预期）。

---

## 2. 时间线

- T0：列出缺失项（CHANGELOG/CITATION/.editorconfig）并确认这是“公开项目补齐文件”工作清单的一部分。
- T1：讨论专用联系渠道的工程化方式（新邮箱 + 转发到主邮箱是否足够、是否需要更干净的邮箱提供商等）。
- T2：出现“main 拒绝强制推送”的约束，提示需要用 revert 回滚噪音提交，而不是重写公开历史。
- T3：形成“写回三处 SSOT（LESSONS/PREFLIGHT/HANDOFF）”的固定流程诉求。

---

## 3. 根因分析

### 3.1 直接根因

- **“公开发布前置检查”缺少对 repo health 文件的系统化检查项**：以前的 preflight 覆盖了数据面（hygiene）、控制面（secrets）、workflow-plane（CI 可解析），但没有把 CHANGELOG/CITATION/.editorconfig/CoC 联系方式作为可执行门禁的一部分。

### 3.2 促成因素

- **信息散落**：缺失项清单、邮箱方案、回滚策略分散在对话与临时笔记中，没有固化为 repo 内的可执行检查。
- **默认假设不可见**：例如“CITATION 是否必须”“.editorconfig 是否会造成大量格式化 diff”“CoC 联系方式用什么邮箱”，这些决策如果不写入，会在下次发布前再次被重复讨论。

### 3.3 根因（系统层）

- **缺少“发布准备”的显式不变量定义**：把“对外可用”拆成可检验项之前，团队/个人会倾向于凭经验补齐，导致遗漏与返工。

---

## 4. 做得好的

- **尽早在公开前发现缺口**：在公开前暴露缺失项，成本低于公开后由外部 Issue 触发。
- **分离“模板文件”和“检查脚本”**：把内容（CHANGELOG/CITATION/.editorconfig）与控制点（check_repo_health_files）分开，便于复用与演进。
- **尊重 main 保护策略**：受保护分支拒绝强推，反而帮助保持公开历史的可审计性；用 revert 更可追踪。

---

## 5. 做得不好的

- **缺少一个统一的“Definition of Done”**：开源补齐的完成标准没有一开始固化为 preflight 项，导致“补齐到什么程度算完成”反复确认。
- **支持渠道未被工程化为“可维护资产”**：例如邮箱注册受限、广告邮箱体验不佳，这类现实约束应当在模板中明确“允许占位，但必须在公开前替换”。

---

## 6. 行动项

> 约定：行动项优先满足“可回滚、可观测、可复用”。

### 6.1 立即行动（已完成）

- [x] 新增：`CHANGELOG.md`（Keep a Changelog 风格，含 Unreleased 区块）
- [x] 新增：`CITATION.cff`（GitHub CITATION file）
- [x] 新增：`.editorconfig`（跨编辑器的最小一致性约定）
- [x] 新增：`tools/check_repo_health_files.py`（Public Release 前置检查脚本）
- [x] 写回：`docs/howto/PREFLIGHT_CHECKLIST.md`（新增 3.5）
- [x] 写回：`docs/explanation/LESSONS.md`（扩展“公开发布前置检查”条目）

### 6.2 下一步行动（建议）

- [ ] 将 Code of Conduct 的 `[INSERT CONTACT METHOD]` 占位符替换为“专用渠道”（建议：独立邮箱 + 转发到主邮箱 + 归档/工单化）。
- [ ] 如仓库进入稳定发布节奏：在 GitHub Release 发布时同步更新 CHANGELOG 并加版本标签。
- [ ] 将“噪音提交回滚”固化为操作手册：受保护 main 一律使用 `git revert`，并附带验证命令。

---

## 7. 验证方式

### 7.1 Public Release Preflight（新增项）

在仓库根目录（独立快照）执行：

```cmd
python tools\check_repo_health_files.py --repo . --mode public-release --out data_processed\build_reports\repo_health_report.json
```

PASS 判据：
- `result=PASS`
- `required_missing=0` 且未检测到 placeholder
- 控制台出现 `report_written=...`，且对应 JSON 文件可打开解析

### 7.2 补充校验（变更噪声控制）

- 若新增 `.editorconfig` 导致大范围 diff：建议先以“只对新改动生效”为默认策略（保持历史文件不强制重排），并在 PR 描述中说明。

---

## 8. 参考资料

- GitHub Docs：About CITATION files（要求 `CITATION.cff` 位于仓库根目录，并用于生成引用信息）
  - https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files
- Keep a Changelog（建议在文档顶部维护 `Unreleased`，并按 Added/Changed/Fixed 等分类）
  - https://keepachangelog.com/zh-CN/1.1.0/
- EditorConfig（跨编辑器的核心属性：indent_style、end_of_line、trim_trailing_whitespace、insert_final_newline、root 等）
  - https://editorconfig.org/ （规范入口）
  - https://learn.microsoft.com/zh-cn/visualstudio/ide/create-portable-custom-editor-options?view=visualstudio
- Contributor Covenant Code of Conduct 2.1（Enforcement 联系方式占位符 `[INSERT CONTACT METHOD]`）
  - https://www.contributor-covenant.org/version/2/1/code_of_conduct/

---

## 9. 附录

### 9.1 文件放置约定（建议）

- 仓库根目录：`CHANGELOG.md`、`CITATION.cff`、`.editorconfig`（以及 LICENSE/README 等）
- 文档：`docs/howto/PREFLIGHT_CHECKLIST.md`、`docs/explanation/LESSONS.md`、`docs/explanation/HANDOFF.md`

### 9.2 placeholder 策略

- 允许占位符存在于私有阶段，但 **Public Release Preflight 必须为 PASS**（占位符会导致 FAIL）。
- 占位符应遵循统一模式（如 `project-contact@example.com`），便于脚本稳定识别。
