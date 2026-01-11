---
title: check_public_release_hygiene.py 使用说明（Public Release Hygiene Audit）
version: v2.0
last_updated: 2026-01-11
---

# check_public_release_hygiene.py 使用说明（Public Release Hygiene Audit）

## 目录
- [1. 目标与适用场景](#1-目标与适用场景)
- [2. 扫描项与风险等级](#2-扫描项与风险等级)
- [3. 使用方式](#3-使用方式)
- [4. 命令行参数](#4-命令行参数)
- [5. 输出报告结构](#5-输出报告结构)
- [6. 退出码](#6-退出码)
- [7. 配置文件（public_release_check_config.json）](#7-配置文件public_release_check_configjson)
- [8. 常见问题与限制](#8-常见问题与限制)
- [9. v2 变更点](#9-v2-变更点)

## 1. 目标与适用场景

该脚本用于公开发布前的**只读审计**，帮助发现：
- 数据/构建产物误入仓库
- 绝对路径与环境指纹泄露
- 密钥/Token 等敏感信息
- 二进制或大文件
- 截图类附件
- OSS 基础治理文件缺失
- CI 门禁可能缺口（启发式）

脚本路径：`tools/check_public_release_hygiene.py`

## 2. 扫描项与风险等级

- **HIGH**
  - Git 跟踪的禁用路径（基于 `git ls-files`）
  - Git 历史中出现禁用路径（`--history 1`）
  - 可能的密钥/Token 命中
- **MED**
  - 绝对路径/环境指纹
  - 二进制文件或大文件
  - 图片附件存在（提示人工复核）
  - OSS 基础文件缺失
- **INFO**
  - CI workflow 启发式提示
  - 正则编译失败导致的扫描降级提示

定位格式统一为 `file:line:col`（`DIAG_LOC_FILE_LINE_COL`），便于 VS Code 直接跳转。

## 3. 使用方式

推荐（本地快速审计）：
```bat
cd <REPO_ROOT>
python tools\check_public_release_hygiene.py --repo . --history 0
```

启用历史扫描（更慢）：
```bat
python tools\check_public_release_hygiene.py --repo . --history 1 --max-history-lines 200000
```

使用自定义配置：
```bat
python tools\check_public_release_hygiene.py --repo . --config tools\public_release_check_config.json
```

指定报告输出路径：
```bat
python tools\check_public_release_hygiene.py --repo . --out data_processed\build_reports\public_release_hygiene.md
```

默认输出到桌面：
`%USERPROFILE%\Desktop\public_release_hygiene_report_YYYYMMDD_HHMMSS.md`

## 4. 命令行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--repo` | `.` | 仓库根目录 |
| `--config` | *(空)* | 配置文件（JSON）；为空则使用内置默认配置 |
| `--history` | `0` | 是否启用历史扫描：`0/1` |
| `--max-history-lines` | `200000` | 历史扫描最大行数（<=0 表示不限制） |
| `--out` | *(空)* | 报告输出路径；为空则输出到桌面 |

## 5. 输出报告结构

报告为 Markdown，包含：
- YAML 元信息：`generated_at` / `repo` / `config` / `git_available` / `history_scan`
- `# 概要`：HIGH/MED/LOW/INFO 统计
- `# 发现清单`：每条包含 Facts / Inference / Locations / Remediation
- `# 附录：配置摘要`：当前生效的关键配置字段

报告生成后会打印：`[OK] report_written=<path>`。

## 6. 退出码

- `0`：未发现 HIGH
- `2`：发现 HIGH（适合作为 CI 门禁）

## 7. 配置文件（public_release_check_config.json）

配置为 JSON，与内置默认配置做**浅合并**（仅顶层键覆盖）。
列表型字段需提供完整列表。

常用字段：
- `forbidden_tracked_paths`
- `text_extensions` / `image_extensions` / `binary_extensions`
- `max_file_size_mb_warn` / `max_file_size_mb_high`
- `scan_roots` / `exclude_dirs`
- `absolute_path_regexes` / `secret_regexes`
- `oss_files_required_any_of` / `oss_files_required_exact`
- `ci_workflow_glob` / `ci_heuristic_patterns`

最小示例：
```json
{
  "forbidden_tracked_paths": ["data_raw/", "data_processed/", "chroma_db/"],
  "exclude_dirs": [".git", ".venv", "node_modules"],
  "max_file_size_mb_warn": 5,
  "max_file_size_mb_high": 20
}
```

注意：配置文件**不会自动加载**，必须显式传入 `--config`。

## 8. 常见问题与限制

- `--history` 基于**路径名**启发式扫描，不解析历史内容。
- 未安装 Git 或不在仓库根目录时，跟踪/历史扫描会跳过并给 INFO 提示。
- 正则编译失败会降级为 INFO，并跳过该类扫描。
- 二进制/大文件判断基于扩展名与大小阈值，不做内容级检测。
- Locations 会做截断（不同扫描项上限不同），报告中会标注截断数量。

## 9. v2 变更点

- 简化绝对路径正则，避免 `re.error` 崩溃。
- 正则编译失败降级为 INFO。
- CMD 包装器改为 ASCII-only，避免 cmd.exe 编码误判。
