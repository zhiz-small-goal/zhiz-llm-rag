---
title: rag_status.py 使用说明（RAG 状态/新鲜度检查）
version: v1.0
last_updated: 2026-01-16
---

# rag_status.py 使用说明

> 目标：基于本地真实产物+报告，给出当前状态与下一步建议，解决"多机/重复构建后忘记进度"的痛点。

## 快速开始

```cmd
python tools\rag_status.py --root .
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | *(auto)* | 项目根目录 |
| `--profile` | *(auto)* | 构建 profile JSON |
| `--strict` | *(flag)* | 严格模式（任何 MISS/FAIL/STALE 返回 FAIL）|
| `--json-out` | *(空)* | JSON 报告输出路径 |

## 退出码

- `0`：PASS（strict 模式下无 MISS/FAIL/STALE）或 INFO（非 strict）
- `2`：FAIL（strict 模式下有问题）

## 示例

```cmd
rem 查看状态
python tools\rag_status.py --root .

rem 严格模式（用于 CI）
python tools\rag_status.py --root . --strict --json-out data_processed\build_reports\status.json
```

---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/rag_status.py`。
