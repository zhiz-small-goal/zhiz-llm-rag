---
title: check_exit_code_contract.py 使用说明（检查退出码契约）
version: v1.0
last_updated: 2026-01-16
---

# check_exit_code_contract.py 使用说明


> 目标：静态扫描仓库中的 Python 和 Batch 文件，检测不符合项目退出码契约（0/2/3）的代码模式，减少退出码漂移。

## 目录
- [目的](#目的)
- [契约说明](#契约说明)
- [检查内容](#检查内容)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [退出码](#退出码)
- [示例](#示例)
- [常见违规与处理](#常见违规与处理)

## 目的

本仓库标准化退出码为 `{0, 2, 3}`：
- `0`：PASS
- `2`：FAIL（门禁失败/契约违反）
- `3`：ERROR（运行异常）

本工具静态检查代码，标记以下模式：
- `sys.exit(<非 0/2/3>)`
- `exit(<非 0/2/3>)`
- `SystemExit(<非 0/2/3>)`
- `sys.exit(str)` / `exit(str)` / `SystemExit(str)`（映射到 rc=1）
- Batch: `exit /b 1`

## 契约说明

本项目统一退出码：

| 退出码 | 含义 | 适用场景 |
|---:|---|---|
| 0 | PASS | 测试通过、门禁通过、处理成功 |
| 2 | FAIL | 门禁失败、预条件不满足、契约违反 |
| 3 | ERROR | 脚本异常、未捕获异常、环境错误 |

## 检查内容

### Python (.py)
- `sys.exit(<literal int>)` 其中 int ∉ {0,2,3}
- `exit(<literal int>)` 其中 int ∉ {0,2,3}
- `SystemExit(<literal int>)` 其中 int ∉ {0,2,3}
- 以上任一形式使用字符串/f-string（Python 映射 `SystemExit(str)` 到 rc=1）

### Batch (.cmd/.bat)
- `exit /b 1`（及变体如 `exit   /b   01`）

**注意**：检查刻意保守，只标记字面量；动态值不解释。

## 快速开始

```cmd
python tools\check_exit_code_contract.py --root .
```

期望输出（无违规时）：
```
[PASS] exit-code contract
```

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 仓库根目录 |

## 退出码

- `0`：PASS（无违规）
- `2`：FAIL（发现违规）
- `3`：ERROR（工具运行失败）

## 示例

### 1) 检查退出码契约
```cmd
python tools\check_exit_code_contract.py --root .
```

### 2) CI 门禁中使用
```cmd
python tools\check_exit_code_contract.py --root .
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
```

## 常见违规与处理

### 1) Python: `sys.exit(1)`
**违规示例**：
```python
sys.exit(1)  # 错误
```

**修复**：
```python
sys.exit(2)  # FAIL
# 或
sys.exit(3)  # ERROR
```

### 2) Python: `sys.exit("error message")`
**违规示例**：
```python
sys.exit("Missing file")  # 映射到 rc=1
```

**修复**：
```python
print("[FATAL] Missing file", file=sys.stderr)
sys.exit(2)
```

### 3) Batch: `exit /b 1`
**违规示例**：
```cmd
exit /b 1
```

**修复**：
```cmd
exit /b 2
```

### 4) 报告格式
违规输出格式（VS Code 可点击）：
```
path\to\file.py:42:10 [FAIL] ECS012: sys.exit(1) is outside allowed exit codes [0, 2, 3]
    sys.exit(1)
```

---

**注意**：本工具是**仓库专用工具（REPO-ONLY TOOL）**，仅用于本仓库门禁/审计，不作为可安装库 API。
