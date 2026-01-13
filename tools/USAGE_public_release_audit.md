---
title: Public Release Hygiene Audit (v3) - 使用说明（索引）
version: v3.0
last_updated: 2026-01-11
---

# Public Release Hygiene Audit (v3) - 使用说明（索引）


> 适用目标：**公开发布/开源前**，对“将进入发布包的内容”做最小安全卫生检查（大文件/二进制/敏感信息/绝对路径指纹等）。

## 目录
- [1. 关键改动（v3）](#1-关键改动v3)
- [2. 快速入口](#2-快速入口)
- [3. 文档拆分说明](#3-文档拆分说明)
- [4. 运行（推荐）](#4-运行推荐)
- [5. 修复脚本文档](#5-修复脚本文档)

## 1. 关键改动（v3）
- ✅ **支持按 Git 语义选择扫描文件**，避免把本地已忽略的数据资产（如 `data_raw/`、`chroma_db/`）误判为发布风险。
- ✅ 默认输出改为 **repo 内部** `data_processed/build_reports/`，避免在日志中暴露用户桌面路径。
- ✅ 提供 `--file-scope` / `--respect-gitignore` 以在“发布卫生”与“本地严格全盘扫描”之间做取舍。

## 2. 快速入口
- [修复文档](fix_public_release_hygiene_README.md)
- [审计文档](check_public_release_hygiene_README.md)

## 3. 文档拆分说明

为减少职责混杂，本说明已拆分为两份：
- `check_public_release_hygiene.py`（只读审计）
- `fix_public_release_hygiene.py`（可选修复）

本文作为索引保留，避免既有链接失效。

## 4. 运行（推荐）

```bat
cd <REPO_ROOT>
python tools\check_public_release_hygiene.py --repo . --history 0
```

### 文件范围选择（重要）
> 详细说明请见 `tools/check_public_release_hygiene_README.md` 的“文件范围选择”一节。[文件选择范围](check_public_release_hygiene_README.md#4-文件范围选择重要)

示例：
```bat
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope tracked
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope tracked_and_untracked_unignored --respect-gitignore
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope worktree_all
```

## 5. 修复脚本文档

如需自动修复（dry-run / apply），请阅读：`tools/fix_public_release_hygiene_README.md`
