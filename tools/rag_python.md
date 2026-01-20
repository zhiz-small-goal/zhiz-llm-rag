---
title: rag_python.py 作为 pre-commit 入口中转
version: "1.0"
last_updated: "2026-01-14"
---

## 目录


- [目标](#目标)
- [设计要点](#设计要点)
- [使用方式](#使用方式)
- [环境变量](#环境变量)
- [常见失败与处理](#常见失败与处理)
- [示例：把现有 hooks 迁移到 .py 中转](#示例把现有-hooks-迁移到-py-中转)

## 目标
在 `language: system/unsupported` 的 pre-commit 本地 hook 中，让 `entry` 固定为一个稳定的入口（`python`），
但实际执行项目脚本时，使用仓库内某个 `venv_*` 的 Python 解释器，从而复用该 venv 的依赖环境。

`entry` 在 pre-commit 的定义是“要执行的可执行命令”；并且允许附带固定参数（例如 `entry: autopep8 -i`）。
`pass_filenames` 若为 `false` 则不会向 hook 传递任何文件名。

参考：pre-commit 官方文档 *Creating new hooks*（`entry` / `pass_filenames` 字段说明）。

## 设计要点
1. **解释器选择**：优先 `RAG_PYTHON`；其次尝试使用“已激活终端环境”的解释器（`VIRTUAL_ENV` / `CONDA_PREFIX`）；最后按 glob 递归搜索（默认包含 `**/venv_*/Scripts/python.exe` 等）。
2. **确定性**：多候选默认报错（exit 2），避免静默选错；可用 `RAG_VENV_PICK=first` 强制选择。
3. **参数透传**：wrapper 自身不解析业务参数，直接把后续 argv 全量交给目标 python（含 pre-commit 追加的 filenames）。

## 使用方式
完整的本地 pre-commit 使用流程见 [本地 pre-commit 使用指南](../docs/howto/pre_commit.md)。

### 直接运行
```bash
python tools/rag_python.py tools/gate.py --profile fast --root .
```

### pre-commit 配置（推荐）
把原来 `entry: tools\rag_python.cmd` 改为 `entry: python`，并把 wrapper 放到 `args` 最前面：
```yaml
- repo: local
  hooks:
    - id: rag-gate-fast
      name: rag-gate --profile fast
      entry: python
      args: [tools/rag_python.py, tools/gate.py, --profile, fast, --root, .]
      language: system
      pass_filenames: false
```

## 环境变量
- `RAG_PYTHON`：显式指定解释器路径（绝对路径或相对仓库根）。
- `VIRTUAL_ENV`：若当前终端已激活 venv，则通常会设置该变量为环境前缀路径；wrapper 会优先使用其对应的 `Scripts/python.exe`（Windows）或 `bin/python`（macOS/Linux）。
- `CONDA_PREFIX`：若当前终端已激活 conda 环境，则通常会设置该变量为环境前缀路径；wrapper 会尝试在该前缀下解析解释器（best-effort）。
- `RAG_VENV_GLOBS`：用 `;` 或 `:` 分隔的 glob 列表（相对仓库根）。
- `RAG_VENV_PICK`：多候选时的策略，`error`（默认）或 `first`。
- `RAG_PY_DEBUG`：设为 `1` 输出调试信息到 stderr。

> 说明：当你在终端里通过 `venv` 的 `activate` 脚本激活环境后，通常会设置 `VIRTUAL_ENV` 并调整 `PATH`，使 `python` 指向该环境的解释器。

## 常见失败与处理
1. **找不到解释器**
   - 现象：提示 `No venv python interpreter found`。
   - 处理：设置 `RAG_PYTHON` 指向你期望的 `python.exe` / `bin/python`；或调整 `RAG_VENV_GLOBS`。

2. **找到多个解释器**
   - 现象：提示 `Multiple venv python interpreters found` 并列出候选。
   - 处理：用 `RAG_PYTHON` 明确指定；或临时设 `RAG_VENV_PICK=first`（会按路径排序选择）。

3. **GUI 与终端行为不一致**
   - 处理：设 `RAG_PY_DEBUG=1`，对比两种触发方式的输出（repo root / 选择到的 python / exec 命令）。

## 示例：把现有 hooks 迁移到 .py 中转
- ruff（需要 filenames）：
```yaml
- repo: local
  hooks:
    - id: rag-ruff
      name: check_ruff --format
      entry: python
      args: [tools/rag_python.py, tools/check_ruff.py, --root, ., --format]
      language: system
      pass_filenames: true
      types: [python]
```

- mypy（不传 filenames，全仓由脚本控制）：
```yaml
- repo: local
  hooks:
    - id: rag-mypy
      name: check_mypy --root .
      entry: python
      args: [tools/rag_python.py, tools/check_mypy.py, --root, .]
      language: system
      pass_filenames: false
```
