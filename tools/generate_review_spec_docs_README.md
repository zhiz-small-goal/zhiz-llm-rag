---
title: generate_review_spec_docs 使用说明
version: v1.0
last_updated: 2026-01-12
tool_id: generate_review_spec_docs

impl:
  wrapper: tools/generate_review_spec_docs.py

entrypoints:
  - python tools/generate_review_spec_docs.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# generate_review_spec_docs 使用说明


## 目的
将审查规范的 SSOT（`docs/reference/review/review_spec.v1.json`）生成成人类可读的 Reference 文档（`docs/reference/review/REVIEW_SPEC.md`），并提供 `--check` 用于门禁校验，避免双写漂移。

## 输入 / 输出
- 输入：`docs/reference/review/review_spec.v1.json`
- 输出：`docs/reference/review/REVIEW_SPEC.md`

## 运行命令
```bash
# 检查生成产物是否与 SSOT 一致（不写文件）
python tools/generate_review_spec_docs.py --check

# 写入/刷新生成产物
python tools/generate_review_spec_docs.py --write

# 显式指定仓库根目录（建议在非根目录执行时使用）
python tools/generate_review_spec_docs.py --root . --write
```

## 期望结果
- `--check`：一致时退出码 0；不一致时退出码 2，并给出“需要运行 --write”的提示
- `--write`：写入成功退出码 0，并打印写入路径

## 常见失败与处理
1) 现象：`output does not exist`  
   原因：生成产物尚未落盘或被删除  
   缓解：运行 `python tools/generate_review_spec_docs.py --write` 生成文件  
   备选：在 CI 中保持该文件纳入版本控制以便审查 diff

2) 现象：`JSON parse failed`（含 `path:line:col`）  
   原因：SSOT JSON 语法错误  
   缓解：按定位修复 JSON，确保 UTF-8 与合法结构  
   备选：先用 `python -m json.tool <file>` 做快速语法检查

3) 现象：`output is out-of-date`  
   原因：SSOT 已变更但未刷新生成产物  
   缓解：运行 `--write` 刷新，并把生成文件一并提交  
   备选：在 gate 中启用 `tools/validate_review_spec.py` 强制一致性
