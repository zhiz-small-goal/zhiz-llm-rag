---
title: check_all.py 使用说明（一键自检/工程门禁脚本）
version: v1.0
last_updated: 2026-01-16
tool_id: check_all

impl:
  module: mhy_ai_rag_data.tools.check_all
  wrapper: tools/check_all.py

entrypoints:
  - python tools/check_all.py
  - python -m mhy_ai_rag_data.tools.check_all

contracts:
  output: report-output-v2

generation:
  options: static-ast
  output_contract: ssot

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_all.py 使用说明


> 目标：一键自检仓库健康度，覆盖结构/语法/入口/文档等关键不变量，适用于重构后、换机后、合并补丁后的快速回归验证。

## 目录
- [目的](#目的)
- [适用场景](#适用场景)
- [检查内容](#检查内容)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [示例](#示例)
- [常见失败与处理](#常见失败与处理)
- [相关文档](#相关文档)

## 目的

本工具提供一键自检（fast 模式），用于：

- **src-layout 验证**：确认 `pyproject.toml`、`src/mhy_ai_rag_data/` 结构完整
- **语法检查**：compileall 编译所有 `.py` 文件，避免 import-time 崩溃
- **入口点测试**：对关键模块执行 `python -m <module> -h`，确保可正常调用
- **文档规范**：检查 README.md / docs/OPERATION_GUIDE.md 目录头与 TOC 链接

## 适用场景

- **重构后自检**：src-layout 迁移、模块重命名后快速验证
- **换机后验证**：克隆仓库、安装依赖后确认环境正常
- **合并补丁后**：git merge / 手工覆盖文件后排查导入路径问题
- **CI 门禁**：作为轻量 preflight，在 ruff/mypy/pytest 之前跑

## 检查内容

### fast 模式（默认）

1. **结构检查**
   - `pyproject.toml` 存在
   - `src/mhy_ai_rag_data/__init__.py` 存在
   - 关键模块文件存在（`index_state.py`、`build_chroma_index_flagembedding.py` 等）

2. **语法检查**
   - `compileall` 编译 `src/` 下所有 `.py`（force=True）

3. **入口点测试**
   - 对以下模块执行 `python -m <module> -h`：
     - `mhy_ai_rag_data.make_inventory`
     - `mhy_ai_rag_data.extract_units`
     - `mhy_ai_rag_data.validate_rag_units`
     - `mhy_ai_rag_data.tools.plan_chunks_from_units`
     - `mhy_ai_rag_data.tools.build_chroma_index_flagembedding`
     - `mhy_ai_rag_data.check_chroma_build`
     - `mhy_ai_rag_data.tools.index_state`

4. **文档 TOC 检查**
   - `README.md` / `docs/OPERATION_GUIDE.md` 目录头格式：`# <文件名>目录：`
   - 至少包含一条目录链接（`- [文本](#锚点)`）

## 快速开始

```cmd
python tools\check_all.py --root .
```

期望输出：
```
PASS: exists pyproject.toml
PASS: exists src/mhy_ai_rag_data/__init__.py
...
PASS: python -m mhy_ai_rag_data.make_inventory -h
...
PASS: TOC present in README.md

STATUS: PASS
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 仓库根目录 |
| `--mode` | `fast` | 检查模式（当前仅支持 fast） |
| `--ignore-toc` | `[]` | 忽略 TOC 检查的文件列表（如 README.md） |

## 忽略列表设置

如果你有部分文档不希望遵循严格的 TOC 检查（例如 README 格式特殊或 OPERATION_GUIDE 已迁移），可以通过以下两种方式忽略：

### 1) 命令行临时忽略
```cmd
python tools\check_all.py --ignore-toc README.md docs\OPERATION_GUIDE.md
```

### 2) 代码内永久忽略
修改 `src/mhy_ai_rag_data/tools/check_all.py` 中的 `CODE_IGNORE_LIST` 变量：
```python
    # 代码内忽略列表
    CODE_IGNORE_LIST = [
        "README.md",
        "docs/OPERATION_GUIDE.md",
    ]
```

## 退出码

- `0`：PASS（所有检查通过）
- `2`：FAIL（结构缺失/语法错误/入口点失败/文档 TOC 不规范）

## 示例

### 1) 本地自检
```cmd
python tools\check_all.py --root .
```

### 2) CI 门禁中使用
```cmd
rem 安装依赖后先跑 check_all
pip install -e .
python tools\check_all.py --root .
rem 通过后再跑其他门禁
python tools\check_ruff.py --root .
python tools\check_mypy.py --root .
```

## 常见失败与处理

### 1) `FAIL: MISSING: src/mhy_ai_rag_data/__init__.py`
**原因**：src-layout 结构不完整或路径错误

**处理**：确认 `src/mhy_ai_rag_data/` 目录存在且包含 `__init__.py`

### 2) `FAIL: compileall src (see output above)`
**原因**：Python 文件存在语法错误

**处理**：查看 compileall 输出，定位具体文件和行号，修复语法错误

### 3) `FAIL: python -m mhy_ai_rag_data.make_inventory -h (rc=1)`
**原因**：模块 import-time 崩溃（缺少依赖、循环导入等）

**处理**：
- 手动运行该命令查看完整错误：
  ```bash
  python -m mhy_ai_rag_data.make_inventory -h
  ```
- 检查是否缺少依赖：
  ```bash
  pip install -e .
  ```

**处理**：
- 如果确定该文档不符合规范，请使用 `--ignore-toc` 忽略，或编辑 `src/mhy_ai_rag_data/tools/check_all.py` 中的 `CODE_IGNORE_LIST`。
- 如果愿意遵循规范，编辑 `README.md / docs/OPERATION_GUIDE.md`，确保首行为：
```markdown
# README目录：
```

### 5) `FAIL: TOC links not found near top of docs/OPERATION_GUIDE.md`
**原因**：文档缺少目录链接或格式不对

**处理**：在文档开头添加目录，格式如下：
```markdown
## 目录
- [章节1](#章节1)
- [章节2](#章节2)
```

## 相关文档

- [docs/howto/PREFLIGHT_CHECKLIST.md](../docs/howto/PREFLIGHT_CHECKLIST.md) - 完整预检清单
- [tools/check_docs_conventions_README.md](check_docs_conventions_README.md) - 文档规范检查
- [tools/check_tools_layout_README.md](check_tools_layout_README.md) - 工具布局审计


---

**注意**：本工具是**包装器（AUTO-GENERATED WRAPPER）**，实际实现位于 `src/mhy_ai_rag_data/tools/check_all.py`。推荐使用 console script `rag-check-all` 或 `python -m mhy_ai_rag_data.tools.check_all`。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_all`
> entrypoints: `python tools/check_all.py`, `python -m mhy_ai_rag_data.tools.check_all`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--ignore-toc` | — | [] | nargs='+'；List of filenames to ignore during TOC check (e.g. README.md) |
| `--md-out` | — | None | optional report.md path (relative to root); default: <out>.md |
| `--mode` | — | 'fast' | Check mode (currently only fast). |
| `--out` | — | 'data_processed/build_reports/check_all_report.json' | output report json (relative to root) |
| `--root` | — | '.' | Repo root (default: current directory) |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `report-output-v2`
- `schema_version`: `2`
- 关闭落盘: `--out ""`（空字符串）
- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`
- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
