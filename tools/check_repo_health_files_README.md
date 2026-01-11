---
title: check_repo_health_files.py 使用说明（Public Release Repo Health）
version: v1.0
last_updated: 2026-01-11
---

# check_repo_health_files.py 使用说明（Public Release Repo Health）

> 目标：在公开发布/开源前，校验仓库“社区/治理文件”的存在性与占位符风险，避免遗漏 CHANGELOG/CITATION/.editorconfig/CoC 等关键文件。

## 目录
- [描述](#描述)
- [适用范围](#适用范围)
- [检查项](#检查项)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [输出与报告](#输出与报告)
- [常见失败](#常见失败)
- [关联文档](#关联文档)

## 描述

该脚本为 **stdlib-only**，用于 Public Release Preflight 的固定检查项：
- 检查必需文件是否缺失。
- 扫描已存在文件是否含占位符（如 CoC 联系方式未替换）。
- 输出可审计 JSON 报告，并在控制台打印 `result=...` 与 `report_written=...`。

## 适用范围

- 公开发布/开源前的“最小治理文件”自检。
- CI 或本地 preflight。

## 检查项

**必需（缺失=FAIL）**
- `CHANGELOG.md`
- `.editorconfig`

**可选（缺失=WARN）**
- `CITATION.cff`
- `CODE_OF_CONDUCT.md`

**占位符**
默认识别占位符（不区分大小写）：
`[INSERT CONTACT METHOD]`、`project-contact@example.com`、`TODO`、`TBD`、`CHANGE_ME` 等。
> `--mode public-release` 下，**占位符将导致 FAIL**。

## 快速开始

```cmd
python tools\check_repo_health_files.py --repo . --mode public-release --out data_processed\build_reports\repo_health_report.json
```

## 参数说明

| 参数 | 必填 | 说明 |
|---|:---:|---|
| `--repo <path>` | 否 | 仓库根目录（默认自动探测） |
| `--mode public-release\|draft` | 否 | `public-release`：占位符=FAIL；`draft`：占位符=WARN |
| `--out <path>` | 否 | 输出 JSON 报告路径（相对 repo root） |
| `--placeholder <token>` | 否 | 额外占位符标记（可重复） |

## 退出码

| 退出码 | 含义 |
|---:|---|
| 0 | PASS |
| 1 | WARN（仅可选文件缺失或占位符） |
| 2 | FAIL（必需缺失或 public-release 占位符） |

## 输出与报告

控制台关键字段：
- `result=PASS|WARN|FAIL`
- `required_missing=<n>` / `optional_missing=<n>` / `placeholders=<n>`
- `report_written=<path>`（仅当提供 `--out`）

JSON 报告（schema: `repo_health_report_v1`）包含：
`summary`、`required_missing`、`optional_missing`、`placeholders`、`files` 等字段。

## 常见失败

1) **必需文件缺失（FAIL）**
   - 处理：补齐 `CHANGELOG.md`、`.editorconfig`。
2) **占位符未替换（public-release FAIL）**
   - 处理：替换 `CODE_OF_CONDUCT.md` 中的联系人占位符或模板字段。
3) **路径错误**
   - 处理：确认在仓库根目录或通过 `--repo` 指定正确路径。

## 关联文档

- Preflight Checklist：`docs/howto/PREFLIGHT_CHECKLIST.md`
- Lessons：`docs/explanation/LESSONS.md`
- Postmortem：`docs/postmortems/2026-01-09_postmortem_open_source_repo_health_files.md`
