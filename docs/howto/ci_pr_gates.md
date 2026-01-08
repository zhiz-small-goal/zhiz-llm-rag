# How-to：PR/CI Lite 门禁（快速回归）

> 目标：在不触发 embedding/chroma 的情况下，对“入口点/契约/最小集成”做快速回归，用于重构后自检与 PR gate。

## 目录
- [1) 适用场景](#1-适用场景)
- [2) 一键命令（推荐）](#2-一键命令推荐)
- [3) 每个门禁到底在检查什么](#3-每个门禁到底在检查什么)
- [4) 常见失败与处理](#4-常见失败与处理)

## 1) 适用场景
- 刚做完重构，担心 `rag-*` 命令不可达、`md_refs` 契约漂移、或最小链路回归失败
- PR/CI 需要低成本、低噪声的确定性信号

## 2) 一键命令（推荐）

### 2.1 Windows CMD（最不易误用：FAIL 会自动停止后续步骤）
```cmd
tools\run_ci_gates.cmd
```

可选：如果你想把 Stage-2 的 embed 依赖也顺手装上（不推荐放进 PR/CI Lite，但本地自测可用）：
```cmd
tools\run_ci_gates.cmd --with-embed
```

### 2.2 如果你坚持手动逐条跑（务必用 && 串联实现 fail-fast）
```cmd
python tools\check_pyproject_preflight.py --ascii-only ^
  && pip install -e ".[ci]" ^
  && python tools\check_cli_entrypoints.py ^
  && python tools\check_md_refs_contract.py ^
  && pytest -q
```

## 3) 每个门禁到底在检查什么
- `check_cli_entrypoints.py`：console_scripts 元数据 → venv Scripts wrapper → PATH 可见性的证据链
- `check_md_refs_contract.py`：`extract_refs_from_md` 的签名绑定与调用点规范（强制关键字参数）
- `pytest -q`：最小轻集成（tmp_path 生成最小目录树，验证 inventory/units/validate 的关键不变量）

## 4) 常见失败与处理
- `rag-* not found`：优先检查当前解释器与 Scripts 是否在 PATH；必要时重新 `pip install -e ...`
- `contract gate FAIL`：按输出定位违规调用点，改为 `md_path=.../md_text=...` 的关键字参数
- `pytest FAIL`：查看失败的断言与临时目录产物，通常是路径/产物名/入口点问题

## 5) 