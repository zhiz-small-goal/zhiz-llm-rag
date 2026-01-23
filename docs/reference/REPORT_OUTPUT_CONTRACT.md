---
title: 报告输出契约（兼容入口）
version: 1.0.0
last_updated: 2026-01-23
timezone: America/Los_Angeles
owner: zhiz
status: active
redirect_to: REPORT_OUTPUT_ENGINEERING_RULES.md
---

# 报告输出契约（兼容入口）

> **注意**：本文档是兼容性别名。完整内容与 SSOT 请参阅：[`REPORT_OUTPUT_ENGINEERING_RULES.md`](REPORT_OUTPUT_ENGINEERING_RULES.md)

## 快速导航

本文档提供向后兼容入口，所有规则与约束请参阅：

- **SSOT（单一真源）**：[`REPORT_OUTPUT_ENGINEERING_RULES.md`](REPORT_OUTPUT_ENGINEERING_RULES.md)
  - schema_version=2 的统一输出契约
  - items/summary 模型
  - 文件输出规则（JSON/Markdown）
  - 控制台输出规则（stdout）
  - VS Code 可点击链接规则
  - 长跑任务：进度（stderr）与 events（jsonl）

## 核心要点摘要

### Report v2 最小字段

```json
{
  "schema_version": 2,
  "generated_at": "2026-01-23T08:00:00Z",
  "tool": "tool_name",
  "root": "c:/repo/zhiz-llm-rag",
  "summary": {
    "overall_status": "PASS|WARN|FAIL|ERROR",
    "overall_rc": 0,
    "counts": {"PASS": 10, "FAIL": 2}
  },
  "items": [...]
}
```

### Item 最小字段

```json
{
  "tool": "tool_name",
  "key": "unique_id",
  "title": "Item title",
  "status_label": "PASS|INFO|WARN|FAIL|ERROR",
  "severity_level": 3,
  "message": "Human-readable message",
  "loc": "src/file.py:12:34",
  "loc_uri": "vscode://file/c:/repo/zhiz-llm-rag/src/file.py:12:34"
}
```

### 关键约束

1. **反斜杠禁用**：所有路径与字符串字段使用 `/` 分隔符（Windows 盘符：`c:/...`）
2. **文件输出排序**：items 按 `severity_level` **从高到低**（最严重在上）
3. **控制台输出排序**：items 按 `severity_level` **从低到高**（最严重在下，summary 最后）
4. **定位双表示**：同时提供 `loc`（纯文本）和 `loc_uri`（VS Code 链接）

## 工具入口

- **渲染器**：`python tools/view_report.py --root . --report <path> --md-out <path>`
- **契约校验**：`python tools/verify_report_output_contract.py --root . --report <path>`

## 历史与迁移

- **v1 → v2 迁移**：参见 REPORT_OUTPUT_ENGINEERING_RULES.md 的兼容策略章节
- **状态元数据纳入 v2**：`index_state.json` 和 `db_build_stamp.json` 也必须满足 v2 envelope

---

**完整规则与实现建议**：请参阅 [`REPORT_OUTPUT_ENGINEERING_RULES.md`](REPORT_OUTPUT_ENGINEERING_RULES.md)
