---
title: fix_public_release_hygiene.py 使用说明（Public Release Hygiene Fix）
version: v2.0
last_updated: 2026-01-11
---

# fix_public_release_hygiene.py 使用说明（Public Release Hygiene Fix）

## 目录
- [1. 目标与安全边界](#1-目标与安全边界)
- [2. 推荐流程](#2-推荐流程)
- [3. 修复行为说明](#3-修复行为说明)
- [4. 命令行参数](#4-命令行参数)
- [5. 动作细节与默认规则](#5-动作细节与默认规则)
- [6. 报告输出](#6-报告输出)
- [7. 退出码](#7-退出码)
- [8. 注意事项](#8-注意事项)

## 1. 目标与安全边界

该脚本用于**尝试自动修复** `check_public_release_hygiene.py` 报告中的常见问题，默认不修改文件（dry-run）。
脚本路径：`tools/fix_public_release_hygiene.py`

明确不会做的事：
- 不改写 Git 历史
- 不默认删除文件（只移动/取消跟踪）

说明：修复脚本不读取 `public_release_check_config.json`，规则来自脚本内的 `DEFAULTS`。

## 2. 推荐流程

1) 先跑审计，确认问题范围
2) 运行修复脚本（默认 dry-run）
3) 复核动作清单与 `git diff`
4) 再用 `--apply` 执行实际修改
5) 重跑审计确认 HIGH 清零

## 3. 修复行为说明

- **默认 dry-run**：不加 `--apply` 即为 dry-run，只输出动作清单
- **apply**：执行实际修改

当使用 `--apply` 时，脚本可能执行：
- 更新 `.gitignore`（追加 hygiene 区块）
- 取消跟踪禁用文件（`git rm --cached`，保留本地文件）
- 绝对路径脱敏（替换为 `<REPO_ROOT>`）
- 隔离根目录截图（移动到隔离目录）
- 生成 OSS 占位文件（LICENSE/SECURITY/CONTRIBUTING/CoC）

## 4. 命令行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--repo` | `.` | 仓库根目录 |
| `--apply` | false | 执行实际修改（默认不加 --apply 即 dry-run） |
| `--quarantine` | `.public_release_quarantine` | 隔离目录（相对 repo） |
| `--out` | *(空)* | 修复报告输出路径（默认桌面） |
| `--skip-git` | false | 跳过 `git rm --cached` |
| `--skip-gitignore` | false | 跳过 `.gitignore` 更新 |
| `--skip-redact` | false | 跳过绝对路径脱敏 |
| `--skip-screenshots` | false | 跳过根目录截图隔离 |
| `--skip-oss` | false | 跳过 OSS 占位文件生成 |

示例：
```bat
python tools\fix_public_release_hygiene.py --repo .
python tools\fix_public_release_hygiene.py --repo . --apply --quarantine ".public_release_quarantine"
python tools\fix_public_release_hygiene.py --repo . --apply --skip-git --skip-gitignore
```

## 5. 动作细节与默认规则

- **.gitignore 更新**
  - 只在未发现“public-release hygiene”标记块时追加

- **取消跟踪（git rm --cached）**
  - 扫描 Git 已跟踪文件
  - 命中默认 denylist 的路径会被取消跟踪
  - 使用批量 `git rm --cached -r --force --`，避免命令行过长

- **绝对路径脱敏**
  - 仅对 `DEFAULTS.text_extensions` 中的文本文件生效
  - 使用 `DEFAULTS.absolute_path_regexes` 进行替换

- **隔离根目录截图**
  - 默认关注 `image.png`、`image-1.png`
  - 移动到隔离目录（若同名存在则追加时间戳）

- **OSS 占位文件生成**
  - 仅在文件不存在时创建
  - 模板为最小 TODO 提示，不等价于正式授权声明

默认规则与清单详见脚本内 `DEFAULTS` 常量（必要时手动调整）。

## 6. 报告输出

输出为 Markdown 修复报告，包含：
- YAML 元信息（时间、repo、模式）
- 动作清单（计划与执行结果）

默认输出到桌面；失败时回退到仓库根目录。

## 7. 退出码

- 始终为 `0`（dry-run 与 apply 均如此）
- 若出现局部错误，记录在报告中，不会强制失败

## 8. 注意事项

- 运行 `--apply` 前建议确认 `git status` 并准备好回滚方案
- `.gitignore` 自动追加为一次性动作，已有标记则跳过
- 生成的 OSS 占位文件需要**人工替换为正式内容**
