---
title: "tools/gen_tools_wrappers.py 使用说明"
version: "v1.0"
last_updated: "2026-01-10"
---

## 目录
- [目的与边界](#目的与边界)
- [契约与输入输出](#契约与输入输出)
- [快速使用](#快速使用)
- [对比策略与-strict-模式](#对比策略与-strict-模式)
- [常见失败与处理](#常见失败与处理)
- [退出码](#退出码)

## 目的与边界
`tools/gen_tools_wrappers.py` 是 **repo-only** 工具，用于管理 `tools/` 目录下的“受管 wrapper”（入口 shim）。
目标是让 wrapper 模板一致、可机检，避免入口漂移/双实现。

该工具不负责：
- 修改 `src/mhy_ai_rag_data/tools/` 下的 SSOT 实现文件；
- 决定哪些 wrapper 应该被管理（清单由配置文件控制）。

## 契约与输入输出
### 输入
- 配置：`tools/wrapper_gen_config.json`
  - `managed_wrappers`: 受管 wrapper 列表（相对 `tools/` 的文件名）
  - `src_tools_dir`: SSOT 根目录（默认 `src/mhy_ai_rag_data/tools`）
  - `tools_dir`: wrapper 根目录（默认 `tools`）

### 输出
- `--check`：不改文件；若发现不一致，会输出：
  - 列表：`[FAIL] wrappers not up-to-date ...`
  - 诊断：以 `file:line:col` 行首输出首差位置，并附带截断 unified diff（默认最多 80 行）
- `--write`：重写受管 wrapper，使其与模板一致（需要提交到仓库）

## 快速使用
在仓库根目录运行：

- 校验（CI/PR Gate 常用）：
```bash
python tools/gen_tools_wrappers.py --check
```

- 刷新（本地修复，需提交）：
```bash
python tools/gen_tools_wrappers.py --write
```

- 允许创建缺失的受管 wrapper（谨慎使用）：
```bash
python tools/gen_tools_wrappers.py --write --bootstrap-missing
```

## 对比策略与 strict 模式
默认 `--check` 使用 **canonical compare**：
- 忽略 CRLF/LF 差异
- 忽略 UTF-8 BOM
- 默认忽略行尾空白（可用 `--keep-trailing-ws` 关闭）
- 统一确保文件末尾单个换行

严格模式 `--strict`：
- 保留磁盘真实换行（不会做 universal newline 归一）
- 期望模板按当前 OS 的换行约定逐字一致（Windows 通常为 CRLF）
- 适合迁移期结束后“收紧门禁”使用

diff 控制：
- 默认打印 unified diff（截断）
- `--diff-max-lines N` 调整最大输出行数
- `--no-diff` 关闭 diff（仍输出 `file:line:col`）

## 常见失败与处理
1) `wrappers not up-to-date`
- 原因：受管 wrapper 被手工修改、或模板更新后未刷新
- 处理：运行 `python tools/gen_tools_wrappers.py --write`，提交生成的变更

2) `UTF-8 decode failed`
- 原因：wrapper 文件编码被改成非 UTF-8 或含异常字节
- 处理：优先用 `--write` 重写；如仍失败，检查编辑器保存编码设置

3) strict 模式失败但默认模式通过
- 原因：仅存在换行/空白风格差异
- 处理：迁移期建议保持默认模式；如要收紧，先统一 EOL 策略再启用 strict

## 退出码
- 0：PASS
- 2：FAIL（不一致/缺失/配置错误）
- 3：ERROR（脚本异常）
