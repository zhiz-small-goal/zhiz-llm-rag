---
title: check_public_release_hygiene.py 使用说明（Public Release Hygiene Audit v3）
version: v3.0
last_updated: 2026-01-11
tool_id: check_public_release_hygiene

impl:
  wrapper: tools/check_public_release_hygiene.py

entrypoints:
  - python tools/check_public_release_hygiene.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_public_release_hygiene.py 使用说明（Public Release Hygiene Audit v3）


> 适用目标：**公开发布/开源前**，对“将进入发布包的内容”做最小安全卫生检查（大文件/二进制/敏感信息/绝对路径指纹等）。

## 目录
- [1. 关键改动（v3）](#1-关键改动v3)
- [2. 放置位置](#2-放置位置)
- [3. 运行（推荐）](#3-运行推荐)
- [4. 文件范围选择（重要）](#4-文件范围选择重要)
- [5. 需要检查历史时（更慢）](#5-需要检查历史时更慢)
- [6. 输出](#6-输出)
- [7. 命令行参数](#7-命令行参数)
- [8. 扫描项与风险等级](#8-扫描项与风险等级)
- [9. 输出报告结构](#9-输出报告结构)
- [10. 退出码](#10-退出码)
- [11. 配置文件（public_release_check_config.json）](#11-配置文件public_release_check_configjson)
- [12. 常见问题与限制](#12-常见问题与限制)

## 1. 关键改动（v3）
- ✅ **支持按 Git 语义选择扫描文件**，避免把本地已忽略的数据资产（如 `data_raw/`、`chroma_db/`）误判为发布风险。
- ✅ 默认输出改为 **repo 内部** `data_processed/build_reports/`，避免在日志中暴露用户桌面路径。
- ✅ 提供 `--file-scope` / `--respect-gitignore` 以在“发布卫生”与“本地严格全盘扫描”之间做取舍。

## 2. 放置位置
- `tools/check_public_release_hygiene.py`
- `tools/run_public_release_audit.cmd`（可选）
- `tools/public_release_check_config.json`（可选）
- `tools/check_public_release_hygiene_README.md`（本说明）

## 3. 运行（推荐）
```bat
cd <REPO_ROOT>
python tools\check_public_release_hygiene.py --repo . --history 0
```

## 4. 文件范围选择（重要）
> 该工具的“内容扫描”（大文件/图片/绝对路径/可能 secrets）默认按 Git 语义选取文件：**tracked + 未跟踪但未被 gitignore 忽略的文件**。

- **默认（推荐）：发布卫生视角**
  - `--file-scope tracked_and_untracked_unignored --respect-gitignore`
  - 含义：扫描“可能会被你一起打包/提交”的内容；**跳过** gitignore 已明确忽略的本地数据资产。

- **只扫 tracked：最小发布输入集**
  - `--file-scope tracked`
  - 含义：只关注 `git ls-files` 中的文件；适合“发布包≈仓库 tracked 内容”的团队约定。

- **全盘扫描 worktree：本地最严格**
  - `--file-scope worktree_all`
  - 含义：遍历工作区所有文件（不看 gitignore）；适合你想把“工作区里任何大文件/敏感痕迹”都揪出来的场景（会更吵）。

示例：
```bat
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope tracked
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope tracked_and_untracked_unignored --respect-gitignore
python tools\check_public_release_hygiene.py --repo . --history 0 --file-scope worktree_all
```

## 5. 需要检查历史时（更慢）
```bat
python tools\check_public_release_hygiene.py --repo . --history 1 --max-history-lines 200000
```

## 6. 输出
- 默认输出到：`data_processed/build_reports/public_release_hygiene_report_YYYYMMDD_HHMMSS.md`
- 可用 `--out` 覆盖输出路径，例如输出到桌面：
  ```bat
  python tools\check_public_release_hygiene.py --repo . --out "%USERPROFILE%\Desktop\public_release_hygiene_report.md"
  ```
- 若 repo 内无法写入，脚本会回退到桌面路径。

## 7. 命令行参数
| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--repo` | `.` | 仓库根目录 |
| `--config` | *(空)* | 配置文件（JSON）；为空则使用内置默认配置 |
| `--history` | `0` | 是否启用历史扫描：`0/1` |
| `--max-history-lines` | `200000` | 历史扫描最大行数（<=0 表示不限制） |
| `--file-scope` | `tracked_and_untracked_unignored` | 内容扫描的文件范围：`tracked`/`tracked_and_untracked_unignored`/`worktree_all` |
| `--respect-gitignore` / `--no-respect-gitignore` | `--respect-gitignore` | 是否对未跟踪文件应用 gitignore（默认启用） |
| `--out` | *(空)* | 报告输出路径；为空则输出到 repo 内 build_reports |

## 8. 扫描项与风险等级
- **HIGH**
  - Git 跟踪的禁用路径（基于 `git ls-files`）
  - Git 历史中出现禁用路径（`--history 1`）
  - 可能的密钥/Token 命中
- **MED**
  - 绝对路径/环境指纹
  - 二进制文件或大文件
  - 图片附件存在（提示人工复核）
  - OSS 基础文件缺失
  - 绝对路径默认覆盖 Windows `<REPO_ROOT><user>`、macOS `/Users/<user>`
- **INFO**
  - CI workflow 启发式提示
  - 正则编译失败导致的扫描降级提示

定位展示统一为 `file:line:col`（`DIAG_LOC_FILE_LINE_COL`）。
为保证在 VS Code 的“报告文件（Markdown）”中可点击跳转，该工具会把 Locations 渲染为
`[file:line:col](vscode://file/<abs_path>:line:col)` 的形式（保留原显示串，新增可点击 URI）。

## 9. 输出报告结构
报告为 Markdown，包含：
- YAML 元信息：`generated_at` / `repo` / `config` / `git_available` / `history_scan`
- `# 概要`：HIGH/MED/LOW/INFO 统计
- `# 发现清单`：每条包含 Facts / Inference / Locations / Remediation
- `# 附录：配置摘要`：当前生效的关键配置字段

报告生成后会打印：`[OK] report_written=<path>`。

## 10. 退出码
- `0`：未发现 HIGH
- `2`：发现 HIGH（适合 CI 门禁）

## 11. 配置文件（public_release_check_config.json）
配置为 JSON，与内置默认配置做**浅合并**（仅顶层键覆盖）。
列表型字段需提供完整列表。

常用字段：
- `forbidden_tracked_paths`
- `text_extensions` / `image_extensions` / `binary_extensions`
- `max_file_size_mb_warn` / `max_file_size_mb_high`
- `scan_roots` / `exclude_dirs`
- `exclude_files_globs`
- `absolute_path_regexes` / `secret_regexes`
- `oss_files_required_any_of` / `oss_files_required_exact`
- `ci_workflow_glob` / `ci_heuristic_patterns`

最小示例：
```json
{
  "forbidden_tracked_paths": ["data_raw/", "data_processed/", "chroma_db/"],
  "exclude_dirs": [".git", ".venv", "node_modules"],
  "exclude_files_globs": ["tools/check_public_release_hygiene.py"],
  "max_file_size_mb_warn": 5,
  "max_file_size_mb_high": 20
}
```

注意：配置文件**不会自动加载**，必须显式传入 `--config`。

## 12. 常见问题与限制
- `--history` 基于**路径名**启发式扫描，不解析历史内容。
- 未安装 Git 或不在仓库根目录时，跟踪/历史扫描会跳过并给 INFO 提示。
- 若 Git 不可用且 `--file-scope` 不是 `worktree_all`，会降级为 `worktree_all` 并给出 INFO。
- 正则编译失败会降级为 INFO，并跳过该类扫描。
- 二进制/大文件判断基于扩展名与大小阈值，不做内容级检测。
- Locations 会做截断（不同扫描项上限不同），报告中会标注截断数量。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_public_release_hygiene`
> entrypoints: `python tools/check_public_release_hygiene.py`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--config` | — | None | optional json config path |
| `--file-scope` | — | 'tracked_and_untracked_unignored' | file selection scope for content scans (default=tracked_and_untracked_unignored) |
| `--history` | — | 0 | type=int；history scan 0/1 (default=0) |
| `--max-history-lines` | — | 200000 | type=int；max lines for history scan (default=200000; <=0 means no limit) |
| `--out` | — | None | output report path (default: repo-local build_reports) |
| `--repo` | — | '.' | repo path (default=.) |
| `--respect-gitignore` | — | True | action=argparse.BooleanOptionalAction；when including untracked files, exclude paths ignored by gitignore (default=True) |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
