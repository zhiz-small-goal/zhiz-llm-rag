---
title: reset_chroma_db.py 使用说明（重置 Chroma 数据库）
version: v1.0
last_updated: 2026-01-16
---

# reset_chroma_db.py 使用说明


> 目标：备份并重置 Chroma DB 目录，确保下次 build 是干净构建，用于解决 collection count 与期望不一致问题。

## 快速开始

```cmd
python tools\reset_chroma_db.py --root . --db chroma_db --backup-dir data_processed\db_backups
```

输出：
```
[INFO] moving db: f:\zhiz-c++\zhiz-llm-rag\chroma_db -> f:\zhiz-c++\zhiz-llm-rag\data_processed\db_backups\chroma_db_bak_20260116_120000
[OK] reset db dir created: f:\zhiz-c++\zhiz-llm-rag\chroma_db
[OK] backup at: f:\zhiz-c++\zhiz-llm-rag\data_processed\db_backups\chroma_db_bak_20260116_120000
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--db` | `chroma_db` | Chroma 持久化目录 |
| `--backup-dir` | `data_processed/db_backups` | 备份根目录 |

## 退出码

- `0`：PASS（备份并重置成功）
- `2`：FAIL（db 目录不存在或移动失败）
- `3`：ERROR（脚本异常）

## 策略

1. 将 `--db` 目录移动到 `backup-dir/chroma_db_bak_<timestamp>`
2. 重新创建空的 `--db` 目录

## 示例

### 1) 重置 Chroma DB
```cmd
python tools\reset_chroma_db.py
```

### 2) 自定义备份目录
```cmd
python tools\reset_chroma_db.py --db chroma_db --backup-dir backups\db
```

## 常见问题

### 1) 报错：`[FAIL] db path not found`
**原因**：chroma_db 目录不存在（已经是空的）

**处理**：无需重置，直接构建即可

### 2) 备份占用空间太大
**处理**：定期清理旧备份
```cmd
rem 删除7天前的备份（使用 PowerShell 实现）
rem powershell "Get-ChildItem data_processed\db_backups -Filter 'chroma_db_bak_*' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Recurse -Force"
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/reset_chroma_db.py`。
