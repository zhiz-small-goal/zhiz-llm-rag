---
title: gen_doc_inventory.py 使用说明
version: v0.1
last_updated: 2026-01-25

tool_id: gen_doc_inventory
cli_framework: argparse

impl:
  wrapper: tools/gen_doc_inventory.py

entrypoints:
  - python tools\gen_doc_inventory.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
owner: zhiz
status: draft
---

# gen_doc_inventory.py 使用说明

## 目录
- [1. 目的](#1-目的)
- [2. 输入与输出](#2-输入与输出)
- [3. 运行命令](#3-运行命令)
- [4. 期望结果](#4-期望结果)
- [5. 常见失败与处理](#5-常见失败与处理)
- [6. 设计说明](#6-设计说明)

## 1. 目的

本工具用于执行 Level 3 文档体系重构计划的 **Step1（Inventory + Map）**：

1) 全量枚举仓库内 `*.md`（优先以 `git ls-files "*.md"` 为准）
2) 为每份文档提取：front-matter、标题、角色（role）、关键字命中位置、仓内链接
3) 生成两个工件：
   - `docs/explanation/doc_inventory.md`（人类可读清单）
   - `docs/explanation/doc_map.json`（机器可读图谱，用作后续门禁输入）

## 2. 输入与输出

### 2.1 输入

- 仓库根目录（`--root`，默认自动推断）
- `git`（可选但推荐）：用于稳定枚举 `*.md` 与获取 `git_last_commit_date`

### 2.2 输出

默认输出路径（相对 repo root）：

- Markdown：`docs/explanation/doc_inventory.md`
- JSON：`docs/explanation/doc_map.json`

可通过参数覆盖：

- `--out-md <path>`
- `--out-json <path>`

## 3. 运行命令

### 3.1 Dry-run（不落盘）

```cmd
python tools\gen_doc_inventory.py --root .
```

### 3.2 Write（生成并写入工件）

```cmd
python tools\gen_doc_inventory.py --root . --write
```

### 3.3 自定义输出路径

```cmd
python tools\gen_doc_inventory.py --root . --write --out-md docs\explanation\doc_inventory.md --out-json docs\explanation\doc_map.json
```

## 4. 期望结果

执行 `--write` 后：

1) `docs/explanation/doc_inventory.md` 存在且可打开
2) `docs/explanation/doc_map.json` 存在且为合法 JSON
3) `doc_inventory.md` 的 `md_files_total` 与 `git ls-files "*.md"` 数量一致
4) `doc_map.json.meta.keywords` 为 Step1 固定关键字集合（用于后续一致性检查输入）

## 5. 常见失败与处理

### 5.1 coverage mismatch（退出码=2）

含义：脚本枚举到的 `*.md` 数量与内部处理数量不一致（通常是读取/路径异常）。

处理：
1) 确认在仓库根目录运行（`--root .`）
2) 确认文件编码异常（极少数情况下可能触发读取失败）；可用 `--write` 前先 dry-run 观察控制台输出
3) 若仓库未包含 `.git/` 或 `git` 不可用，脚本会 fallback 到 `rglob("*.md")`；此时输出可能包含未追踪文件（可接受，但需在后续门禁口径中显式说明）

### 5.2 ImportError: mhy_ai_rag_data

含义：脚本无法导入 `mhy_ai_rag_data.md_refs`。

处理：
1) 确认 repo 结构包含 `src/`
2) 脚本已自动把 `<root>/src` 加到 `sys.path`；若仍失败，检查是否在错误目录运行

## 6. 设计说明

### 6.1 role 约束

为了满足 Step1“每份文档必须有唯一角色标签”的验收，本工具把 `role` 收敛为以下枚举：

- `reference|guide|runbook|README|archive|postmortem`

并额外输出 `role_hint`（分类依据：path/name/default），用于后续人工复核。

### 6.2 action 规则

- 无关键字命中：`no_action`
- 命中且属于 `archive/postmortem`：`only_note`
- 其余命中：`need_align`

该规则仅用于 Step1 标注，不代表 Step4 的最终迁移策略。
