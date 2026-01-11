---
title: Public Release Hygiene 审计与修复（索引）
version: v2.1
last_updated: 2026-01-11
---

# Public Release Hygiene 审计与修复（索引）

## 目录
- [1. 快速入口](#1-快速入口)
- [2. 文档拆分说明](#2-文档拆分说明)
- [3. 推荐流程](#3-推荐流程)

## 1. 快速入口

- [修复文档](fix_public_release_hygiene_README.md)
- [审计文档](check_public_release_hygiene_README.md)

## 2. 文档拆分说明

为减少职责混杂，本说明已拆分为两份：
- `check_public_release_hygiene.py`（只读审计）
- `fix_public_release_hygiene.py`（可选修复）

本文作为索引保留，避免既有链接失效。

## 3. 推荐流程

1) 先跑审计：
```bat
cd <REPO_ROOT>
python tools\check_public_release_hygiene.py --repo . --history 0
```

2) 阅读报告，处理 HIGH

3) 需要自动修复时再执行：
```bat
python tools\fix_public_release_hygiene.py --repo .
```

4) 确认动作后再 apply：
```bat
python tools\fix_public_release_hygiene.py --repo . --apply --quarantine ".public_release_quarantine"
```
