---
title: Changelog
version: 0.1
last_updated: 2026-01-09
---

# Changelog

本文件记录本项目对外可感知的“重要变更”（兼容性、行为、接口、依赖策略等）。  
格式参考 *Keep a Changelog* 的分类（Added/Changed/Deprecated/Removed/Fixed/Security）。

## [Unreleased]

### Added
- 新增 `CITATION.cff`（引用元数据，便于他人引用本仓库/软件）。
- 新增 `.editorconfig`（统一基础格式约定，减少 diff 噪音）。
- 新增 `CODE_OF_CONDUCT.md`（行为准则与专用举报渠道）。
- 新增 `docs/reference/REPORT_OUTPUT_CONTRACT.md`（报告输出契约 v2 定义）。

### Changed
- 升级核心报告工具 (`run_eval_retrieval`, `run_eval_rag`, `probe_llm_server` 等) 输出格式至 schema_version=2 (Items Model)。
- 优化报告诊断体验：VS Code 可点击路径、severity_level 排序、自动 Summary 统计。

### Deprecated

### Removed

### Fixed

### Security

## [0.1.0] - 2026-01-09

### Added
- 初始公开版本（仓库结构、基础脚本与文档入口）。

