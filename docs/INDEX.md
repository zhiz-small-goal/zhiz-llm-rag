---
title: 文档导航（Diátaxis）
version: v1.0
last_updated: 2026-01-12
---

# 文档导航（Diátaxis）


> 目标：按“用途”而不是按“文件名”组织文档，降低重复与漂移，提升可维护性与可操作性。

## 目录
- [Tutorials（教程：从 0 到 1）](#tutorials教程从-0-到-1)
- [How-to（操作指南：如何完成具体任务）](#how-to操作指南如何完成具体任务)
- [Reference（参考：契约/参数/格式）](#reference参考契约参数格式)
- [Explanation（解释：架构/取舍/演进）](#explanation解释架构取舍演进)
- [Project Meta（开源与治理）](#project-meta开源与治理)
- [Postmortems（复盘：事故记录与证据链）](#postmortems复盘事故记录与证据链)
- [Archive（归档：仅重定向，不再维护）](#archive归档仅重定向不再维护)

## Tutorials（教程：从 0 到 1）
- [Getting Started：跑通 Stage-1 + PR/CI Lite 回归](tutorials/01_getting_started.md)

## How-to（操作指南：如何完成具体任务）
- [日常操作主线（管线 + 参数 + 验收）](howto/OPERATION_GUIDE.md)
- [rag-status：跨机续跑/重复构建的进度自检](howto/rag_status.md)
- [rag-accept：一键验收入口](howto/rag_accept.md)
- [建立“口语 vs 官方术语”检索回归（分桶）](howto/ORAL_OFFICIAL_RETRIEVAL_REGRESSION.md)
- [PR/CI Lite 门禁（快速回归）](howto/ci_pr_gates.md)
- [在本项目执行审查（Review Workflow）](howto/review_workflow.md)
- [完全离线运行 Policy Gate（Vendoring conftest / 内部镜像源）](howto/offline_conftest.md)
- [Preflight Checklist（重构/换机/换环境后必跑）](howto/PREFLIGHT_CHECKLIST.md)
- [Postmortem 工作流（写回协议：模板 → LESSONS → PREFLIGHT → HANDOFF）](howto/POSTMORTEM_WORKFLOW.md)
- [排障手册（Runbook）](howto/TROUBLESHOOTING.md)

## Reference（参考：契约/参数/格式）
- [参考与契约（口径、产物、架构）](reference/REFERENCE.md)
- [审查规范（Review Spec：SSOT/生成/模板）](reference/review/README.md)
- [Policy（Conftest/Rego）](../policy/README.md)
- [Stage-2 评测契约：eval_cases.jsonl / eval_retrieval_report.json](reference/EVAL_CASES_SCHEMA.md)
- [Index State 与 Stamps（db_build_stamp.json 等）](reference/index_state_and_stamps.md)
- [Postmortem 提示词模板（清晰/准确/必要）](reference/postmortem_prompt_template.md)

## Explanation（解释：架构/取舍/演进）
- [文档体系第一性原理与写作规范（可复用）](explanation/documentation_principles.md)
- [检索系统演进摘要（Stage-2 retrieval evolution）](explanation/2026-01-04_retrieval_evolution_summary.md)

- [Lessons / 经验库（可迁移）](explanation/LESSONS.md)

## Project Meta（开源与治理）
- [LICENSE（授权条款）](../LICENSE)
- [CHANGELOG（变更记录）](../CHANGELOG.md)
- [CITATION（引用信息）](../CITATION.cff)
- [Code of Conduct（行为准则）](../CODE_OF_CONDUCT.md)
- [Contributing（贡献说明）](../CONTRIBUTING.md)
- [Security Policy（安全策略）](../SECURITY.md)
- [Support Policy（支持与沟通）](../SUPPORT.md)
- [.editorconfig（格式约定）](../.editorconfig)

## Postmortems（复盘：事故记录与证据链）
- [INDEX](postmortems/INDEX.md)

## Archive（归档：仅重定向，不再维护）
- [PACKAGED_USAGE_GUIDE（Deprecated）](archive/PACKAGED_USAGE_GUIDE.md)
