---
title: update_postmortems_index_README
version: v1.0
last_updated: 2026-01-20
tool_id: update_postmortems_index

impl:
  module: mhy_ai_rag_data.tools.update_postmortems_index
  wrapper: tools/update_postmortems_index.py

entrypoints:
  - python tools/update_postmortems_index.py
  - python -m mhy_ai_rag_data.tools.update_postmortems_index

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# update_postmortems_index_README


目的：把 `docs/postmortems/INDEX.md` 从“手工维护”变为“可再生产产物（generated）”，以脚本保证：

- 新增/重命名/补写日期时，索引不会漂移
- 链接不会因手工截断导致断链
- CI/PR 可用 `--check` 做门禁；本地可用 `--write` 自动更新

---

## 适用场景

- 你刚新增一个 `docs/postmortems/*.md`，希望自动插入到 INDEX。
- 你批量重命名/补充 YAML 元信息，希望 INDEX 统一重排。
- 你希望把“索引必须同步”纳入 PR/CI gate，避免遗漏。

---

## 与项目契约的对齐点

- **tools/ 分层**：SSOT 在 `src/mhy_ai_rag_data/tools/`；`tools/*.py` 是 wrapper（见 `tools/README.md` 与 `tools/check_tools_layout.py`）。
- **退出码**：0=PASS；2=FAIL；3=ERROR（见 `docs/reference/REFERENCE.md` 的 3.1）。
- **诊断格式**：尽量输出 `file:line:col: message`，便于 IDE 点击定位（见 `AGENTS.md` 7）。

---

## 输入 / 输出

### 输入
- 默认扫描：`docs/postmortems/*.md`
- 默认忽略：`docs/postmortems/INDEX.md`、`docs/postmortems/README.md`

### 输出
- 默认写回：`docs/postmortems/INDEX.md`
- 自动生成区间会被包裹在以下标记之间（头部与“相关资产”段落会保留）：

```md
<!-- AUTO-GENERATED:BEGIN postmortems-index -->
... generated ...
<!-- AUTO-GENERATED:END postmortems-index -->
```

---

## 元信息提取规则（优先级）

1) **date**：YAML `date` 或 `last_updated` → 文件名前缀 `YYYY-MM-DD` → `YY-MM-DD` 自动补 `20YY-...`
2) **title**：YAML `title` → 第一个非“目录：”的 `# H1` → 文件名兜底
3) **关键字**：YAML `keywords/tags` → 文档头部 `[关键词] ...` / `[关键字] ...` → 从标题与文件名派生（兜底）

---

## 运行命令

### 1) 本地自动更新（推荐）
```sh
python tools/update_postmortems_index.py --write
```

### 2) CI/门禁检查（不写回）
```sh
python tools/update_postmortems_index.py --check
```

### 3) 严格模式（缺 date/关键字 则 FAIL）
```sh
python tools/update_postmortems_index.py --write --strict
```

> 说明：`--strict` 仍会更新索引（如果需要），但会返回 exit code 2，便于你把“元信息质量”也纳入门禁。

### 4) 输出 JSON 报告（可选）
```sh
python tools/update_postmortems_index.py --check --json-out data_processed/build_reports/postmortems_index.json
# 或打印到 stdout
python tools/update_postmortems_index.py --check --json-stdout
```

---

## 集成建议

### A) Git hook（新增 postmortem 时自动更新并随提交带上）
示例 `.githooks/pre-commit`：

```sh
#!/usr/bin/env sh
set -e

if git diff --cached --name-only | grep -qE '^docs/postmortems/.*\.md$'; then
  python tools/update_postmortems_index.py --write
  git add docs/postmortems/INDEX.md || true
fi
```

并启用：
```sh
git config core.hooksPath .githooks
```

### B) PR/CI gate（只检查）
在你的 gates 脚本中添加：
- `python tools/update_postmortems_index.py --check`

---

## 常见失败与处理

1) `.../INDEX.md:1:1: index out-of-date`
- 原因：新增/重命名了 postmortem，但未运行 `--write`。
- 处理：本地执行 `python tools/update_postmortems_index.py --write`，提交索引变更。

2) `missing date ...`（strict 下为 FAIL）
- 原因：文档缺少 YAML `date/last_updated` 且文件名不含日期前缀。
- 处理：补齐 YAML 字段或按 `YYYY-MM-DD_*.md` 命名。

3) 关键字缺失导致索引可检索性下降
- 原因：未提供 `keywords/tags` 或 `[关键词]` 行；兜底派生可能不稳定。
- 处理：为新文档补齐显式关键字；把派生仅当兼容策略。

---

## 设计取舍（为何不做“增量 append”）

- “增量 append”在重命名、补写历史复盘、回填日期时容易出现重复/乱序。
- 本脚本采用“全量重建自动区”策略，保证幂等与可门禁性。
