# `snapshot_stage1_baseline.py` 使用说明（Stage-1 基线快照：产物指纹 + Chroma 落盘状态）

> **适用日期**：2025-12-28  
> **脚本位置建议**：`tools/snapshot_stage1_baseline.py`  
> **输出位置**：默认写入 `data_processed/build_reports/stage1_baseline_snapshot.json`

---

## 1. 目的与适用场景

该脚本用于在 **Stage-1 已验收通过（PASS）** 后，固化一份“可审计、可对比”的基线快照，用于后续 Stage-2 的漂移定位与回归对比。

典型用途：

- 你重建了 `chroma_db/`，想确认本次构建与上次是否一致（至少在产物指纹/落盘清单层面可对比）。
- 你修改了分块参数、数据抽取逻辑、元数据字段，想为“变更前后”留下一份不可抵赖证据。
- 你准备多人协作或跨机器迁移，想确认“输入产物 + 索引落盘”是否按预期同步。

---

## 2. 工具做什么 / 不做什么

### 2.1 做什么（Facts）

1) 对关键产物计算 **SHA-256**：
- `data_processed/text_units.jsonl`
- `data_processed/chunk_plan.json`

2) 为 `chroma_db/` 生成目录 **manifest**（轻量可审计清单）：
- 对每个文件记录：相对路径、大小（bytes）、mtime（秒级时间戳）
- 对 **≤ 50MB** 的文件额外记录 SHA-256（避免对巨大文件做全量哈希导致耗时过高）

3) 可选采集（若可用）：
- Git commit（`git rev-parse HEAD`）与 dirty 状态
- `pip freeze`（用于依赖对齐；若你已有 `capture_rag_env.py` 作为环境快照，可在后续裁剪此字段避免重复）

### 2.2 不做什么（Non-goals）

- 不重建 `text_units`、不生成 `chunk_plan`
- 不连接 Chroma 读取 collection（它关注“落盘状态”，不关注“库内 count 对齐”）
- 不评估召回质量（评测属于 Stage-2）

---

## 3. 前置条件与目录约定

### 3.1 必需文件（否则会 FAIL）
- `data_processed/text_units.jsonl`
- `data_processed/chunk_plan.json`

### 3.2 可选目录（不存在也可运行，但 manifest 会标记 error）
- `<root>/chroma_db/`（默认）

---

## 4. 快速开始（推荐）

在项目根目录运行：

```bash
python tools/snapshot_stage1_baseline.py --root . --db chroma_db
```

成功后会输出：

- 控制台：`[snapshot] OK out=...`
- 文件：`data_processed/build_reports/stage1_baseline_snapshot.json`

---

## 5. 参数详解

| 参数 | 默认值 | 说明 | 注意事项 |
|---|---:|---|---|
| `--root` | `.` | 项目根目录 | 建议显式指定，避免在子目录误跑 |
| `--db` | `chroma_db` | Chroma 落盘目录名（相对 root） | 仅用于生成 manifest，不连接 DB |
| `--out` | 空 | 覆盖输出 JSON 路径（绝对或相对） | 不填则写入 build_reports |

---

## 6. 输出 JSON 字段说明（核心字段）

输出文件：`stage1_baseline_snapshot.json`

- `timestamp`：生成时间
- `root`：项目根目录绝对路径
- `python` / `platform`：运行时解释器与平台信息
- `artifacts.text_units` / `artifacts.chunk_plan`：
  - `path`、`size`、`sha256`
- `chroma_db_manifest`：
  - `path`：manifest 根路径
  - `files[]`：每个文件包含 `rel`、`size`、`mtime`，小文件可含 `sha256`
  - `note`：sha256 的阈值说明
- `git`：commit 与 dirty（若可用）
- `pip_freeze`：冻结依赖（若可用）

---

## 7. 退出码与错误处理

- 退出码 `0`：成功写出快照
- 退出码 `2`：关键产物缺失（脚本会打印 missing 列表）

常见错误：

1) `missing required artifacts`  
原因：未生成产物或 `--root` 指错。  
处理：回到项目根目录，先完成 Stage-1 产物生成。

2) `git error`  
原因：机器未安装 git 或目录不是 git 仓库。  
处理：可忽略，不影响快照的主体价值。

---

## 8. 工程化建议

- 建议在 **每次重建 Chroma** 后执行一次快照，并将输出 commit 到分支或作为构建产物归档。
- 若你已将环境快照统一交由 `tools/capture_rag_env.py` 管理，可将本脚本裁剪为“只含 artifacts + chroma manifest + git”，避免重复采集依赖信息。
