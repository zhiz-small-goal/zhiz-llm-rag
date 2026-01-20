---
title: check_md_refs_contract.py 使用说明（检查 Markdown 引用契约）
version: v1.0
last_updated: 2026-01-16
tool_id: check_md_refs_contract

impl:
  wrapper: tools/check_md_refs_contract.py

entrypoints:
  - python tools/check_md_refs_contract.py

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# check_md_refs_contract.py 使用说明


> 目标：Gate `md_refs.extract_refs_from_md` 函数签名与调用契约稳定性，防止参数位置漂移导致的运行时错误。

## 目的

本仓库多处使用 `extract_refs_from_md` 提取 Markdown 文件引用。为防止重构时：

- 签名参数顺序变化
- 调用方使用位置参数（positional args）导致绑定错误

本工具检查：

1. **签名验证**：`extract_refs_from_md(md_path, md_text, project_root, preset=...)`
2. **Smoke 调用**：用关键字参数调用，确保可正常工作
3. **调用站点检查**：所有调用必须使用关键字参数（禁止位置参数）

## 快速开始

```cmd
python tools\check_md_refs_contract.py --root .
```

期望输出：
```
[INFO] repo_root = f:\zhiz-c++\zhiz-llm-rag
[INFO] signature OK: (md_path, md_text, project_root, preset='commonmark')
[PASS] md_refs contract appears stable
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | *(auto-detect)* | 仓库根目录（默认自动检测） |

## 退出码

- `0`：PASS（签名与调用站点均符合契约）
- `2`：FAIL（签名不匹配或调用站点使用位置参数）
- `3`：ERROR（脚本异常）

## 检查内容

### 1) 签名检查
要求参数包含：`md_path`, `md_text`, `project_root`

### 2) Smoke 调用
```python
extract_refs_from_md(
    md_path=Path("temp.md"),
    md_text="# hello",
    project_root=Path("/tmp"),
    preset="commonmark"
)
```

### 3) 调用站点检查
扫描所有 `.py` 文件，禁止以下模式：
```python
# ❌ 错误：位置参数
extract_refs_from_md(md_path, md_text, project_root)

# ✅ 正确：关键字参数
extract_refs_from_md(
   md_path=md_path,
    md_text=md_text,
    project_root=project_root
)
```

## 常见失败与处理

### 1) 签名参数缺失
```
[FAIL] signature missing required params: ['md_path']
```

**原因**：`extract_refs_from_md` 函数签名被修改

**处理**：恢复必需参数或更新契约检查

### 2) 调用站点使用位置参数
```
path/to/file.py: positional args are not allowed for extract_refs_from_md
```

**处理**：改为关键字参数：
```python
# 修改前
result = extract_refs_from_md(p, text, root)

# 修改后
result = extract_refs_from_md(md_path=p, md_text=text, project_root=root)
```

---

**注意**：本工具是**仓库专用工具（REPO-ONLY TOOL）**，仅用于本仓库门禁/审计。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `check_md_refs_contract`
> entrypoints: `python tools/check_md_refs_contract.py`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--root` | — | None | Repo root (default: auto-detect from this script location) |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
