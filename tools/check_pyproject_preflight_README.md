---
title: check_pyproject_preflight.py 使用说明（pyproject.toml 预检）
version: v1.0
last_updated: 2026-01-16
tool_id: check_pyproject_preflight

impl:
  wrapper: tools/check_pyproject_preflight.py

entrypoints:
  - python tools/check_pyproject_preflight.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_pyproject_preflight.py 使用说明


> 目标：在 pip install 前验证 pyproject.toml 是 UTF-8 编码、无可疑 Unicode 字符、可解析的 TOML，防止 PEP 517 构建失败。

## 目的

TOML v1.0 要求 UTF-8 文档，非 UTF-8 或隐形 Unicode 常导致 pip/PEP 517 失败。本工具预检：

1. **UTF-8 严格解码**
2. **可疑字符扫描**（智能引号、全角减号、零宽空格等）
3. **TOML 解析**（stdlib `tomllib`）

## 快速开始

```cmd
python tools\check_pyproject_preflight.py --path pyproject.toml
```

期望输出：
```
[INFO] pyproject_path = f:\zhiz-c++\zhiz-llm-rag\pyproject.toml
[PASS] pyproject.toml preflight OK (UTF-8 + sane chars + TOML parse)
[HINT] Windows CMD interactive mode does not stop after failures. Use "&&" to chain commands, or run tools\run_ci_gates.cmd.
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--path` | `pyproject.toml` | TOML 文件路径 |
| `--ascii-only` | *(flag)* | 禁止任何非 ASCII 字符 |

## 退出码

- `0`：PASS
- `2`：FAIL（非 UTF-8/可疑字符/TOML 解析失败）

## 可疑字符列表

| 类别 | 示例 Codepoint | Unicode Name |
|---|---|---|
| 智能引号 | U+2018, U+2019, U+201C, U+201D | LEFT/RIGHT SINGLE/DOUBLE QUOTATION MARK |
| 减号变体 | U+2212, U+2013, U+2014, U+FF0D | MINUS SIGN, EN/EM DASH, FULLWIDTH HYPHEN-MINUS |
| 不可见字符 | U+00A0, U+200B, U+FEFF | NBSP, ZWSP, BOM |

## 示例

### 1) 检查 pyproject.toml
```cmd
python tools\check_pyproject_preflight.py
```

### 2) 强制 ASCII
```cmd
python tools\check_pyproject_preflight.py --ascii-only
```

### 3) CI 门禁中使用
```cmd
python tools/check_pyproject_preflight.py && pip install -e .
```

## 常见失败与处理

### 1) `[FATAL] not UTF-8 (strict decode failed)`
**处理**：用支持编码检测的编辑器（如 VS Code）转换为 UTF-8

### 2) `[FAIL] suspicious characters detected: U+2019 RIGHT SINGLE QUOTATION MARK`
**原因**：复制粘贴时引入智能引号

**处理**：替换为普通引号 `'`
```toml
# 错误（智能引号）
description = "It's a tool"

# 正确
description = "It's a tool"
```

### 3) `[FATAL] TOML parse failed: (at line 10, column 5)`
**处理**：打开 pyproject.toml 定位到该行，修复 TOML 语法错误

---

**注意**：本工具是**仓库专用工具（REPO-ONLY TOOL）**，仅用于本仓库门禁/审计。
