---
title: How-to：PR/CI Lite 门禁（快速回归）
version: v1.3
last_updated: 2026-01-14
---

# How-to：PR/CI Lite 门禁（快速回归）


> 目标：在不触发 embedding/chroma 的情况下，对“入口点/契约/最小集成”做快速回归，用于重构后自检与 PR gate。

## 目录
- [1) 适用场景](#1-适用场景)
- [2) 一键命令（推荐）](#2-一键命令推荐)
- [3) 每个门禁到底在检查什么](#3-每个门禁到底在检查什么)
- [4) 常见失败与处理](#4-常见失败与处理)
- [5) 可选：附加门禁与收紧策略](#5-可选附加门禁与收紧策略)

## 1) 适用场景
- 刚做完重构，担心 `rag-*` 命令不可达、`md_refs` 契约漂移、或最小链路回归失败
- PR/CI 需要低成本、低噪声的确定性信号

## 2) 一键命令（推荐）


### 新增：单入口 Gate（推荐）

从 2026-01-11 起，CI/本地可以用单入口统一执行 Gate：

```bash
pip install -e ".[ci]"

# 推荐：安装后用 console script
rag-gate --profile ci --root .

# 或兼容入口
python tools/gate.py --profile ci --root .
# 产物：data_processed/build_reports/gate_report.json (+ gate_logs/)

# 可选:发布之前跑:
python tools/gate.py --profile release --root .
```

人类可读报告（可选）：
- 运行 `python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md`
- 产物：`data_processed/build_reports/gate_report.md`（从 `gate_report.json` 派生）

- profile=fast：不含 public release hygiene / policy（更快）
- profile=ci：CI 默认（包含 policy_conftest；Linux runner 会安装 conftest）

进一步说明：
- [Gate runner 使用说明](../../tools/gate_README.md)
- [view_gate_report 使用说明](../../tools/view_gate_report_README.md)
- [pSSOT（门禁顺序/输出/inputs）](../reference/reference.yaml)
- [Policy（Conftest/Rego）](../../policy/README.md)

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
python tools\check_pyproject_preflight.py --ascii-only && pip install -e ".[ci]" && python tools\gen_tools_wrappers.py --check && python tools\check_tools_layout.py --mode fail && python tools\check_exit_code_contract.py --root . && python tools\check_cli_entrypoints.py && python tools\check_md_refs_contract.py && python tools\check_ruff.py --root . && python tools\check_mypy.py --root . && python tools\validate_review_spec.py --root . && pytest -q
```

## 3) 每个门禁到底在检查什么
- `check_tools_layout.py`：tools/ 入口层是否按 contract 分层（wrapper vs repo-only），并检测 tools↔src 同名冲突
- `gen_tools_wrappers.py --check`：受管 wrapper 是否与模板一致（避免手工编辑导致的“SSOT 漂移”）
- `check_exit_code_contract.py`：静态扫描 `sys.exit(1)` / `SystemExit("...")` / `exit /b 1` 等高频漂移点，保证退出码口径收敛到 {0,2,3}
- `check_cli_entrypoints.py`：console_scripts 元数据 → venv Scripts wrapper → PATH 可见性的证据链
- `check_md_refs_contract.py`：`extract_refs_from_md` 的签名绑定与调用点规范（强制关键字参数）
- `check_readme_code_sync.py`：tools/ README ↔ 源码对齐门禁（AUTO blocks：options/output-contract/artifacts；`--write` 可刷新）
- `check_ruff.py`：Ruff lint（可选 format --check），用于静态问题与风格一致性
- `check_mypy.py`：mypy 类型检查（可选 strict）
- `validate_review_spec.py`：审查规范 SSOT 与生成文档一致性（防止审查口径漂移）
- `pytest -q`：最小轻集成（tmp_path 生成最小目录树，验证 inventory/units/validate 的关键不变量）

可选开关（用于本地/CI 灵活收紧）：
- `RAG_RUFF_FORMAT=1`：启用 `ruff format --check`
- `RAG_MYPY_STRICT=1`：启用 `mypy --strict`

## 4) 常见失败与处理
- `rag-* not found`：优先检查当前解释器与 Scripts 是否在 PATH；必要时重新 `pip install -e ...`
- `tools layout FAIL`：通常是新增脚本缺 marker，或 tools↔src 出现同名但 tools 侧不是 wrapper；优先按 `check_tools_layout` 输出修复 marker/转发关系
- `contract gate FAIL`：按输出定位违规调用点，改为 `md_path=.../md_text=...` 的关键字参数
- `check_ruff FAIL`：若为 format 相关，先执行 `python -m ruff format .`（或 `ruff format .`）再重跑 `check_ruff`
- `pytest FAIL`：查看失败的断言与临时目录产物，通常是路径/产物名/入口点问题

## 5) 可选：附加门禁与收紧策略

### 5.1 迁移期 vs 门禁期：什么时候用 warn / fail
- `check_tools_layout` 支持两种模式：
  - `--mode warn`：退出码 0，但输出问题清单（用于迁移期，避免阻断开发）
  - `--mode fail`：检测到问题则退出码 2（用于门禁期，阻断布局契约被破坏）

建议收紧触发器（把 warn 升级为 fail）：
- 连续 N 次（例如 5 次）运行中 `unknown_tool_kind=0` 且 `name_conflict_tools_vs_src=0`
- 代码库已有明确的 wrapper 模板与 REPO-ONLY 标记约定，新增工具不会频繁触发误报

### 5.2 可选：把门禁搬到本地 pre-commit（更早失败，更低 PR 往返）

如果你希望在本地提交前就阻止“工具布局契约被破坏”，可以把以下命令接入 pre-commit 的 `repo: local` hooks：

完整的 pre-commit 使用流程与常见问题，见 [本地 pre-commit 使用指南](pre_commit.md)。

```yaml
repos:
  - repo: local
    hooks:
      - id: rag-gate-fast
        name: rag-gate --profile fast
        entry: python
        args: [tools\\rag_python.py, tools\\gate.py, --profile, fast, --root, .]
        language: unsupported
        pass_filenames: false
      - id: rag-ruff
        name: check_ruff --format
        entry: python
        args: [tools\\rag_python.py, tools\\check_ruff.py, --root, ., --format]
        language: unsupported
        pass_filenames: true
        types: [tools\\rag_python.py, python]
      - id: rag-mypy
        name: check_mypy --root .
        entry: python
        args: [tools\\rag_python.py, tools\\check_mypy.py, --root, .]
        language: unsupported
        pass_filenames: false
      - id: show-python
        name: show python used bey entry
        language: unsupported
        entry: python
        args: [tools\\rag_python.py, -c, "import sys; print(sys.executable); print(sys.version)"]
        pass_filenames: false
        always_run: true
```

要点：
- pre-commit 要求 hook 在失败时返回非 0 退出码（否则不会阻断提交）。
- 对这种“不依赖文件列表、而是审计仓库状态”的检查，建议 `pass_filenames: false`。
- 若不同设备/环境 Python 路径不同，设置环境变量 `RAG_PYTHON` 指向解释器路径（未设置则回退到 `python`）。

### 5.3 审查规范（Review Spec）门禁

从 2026-01-12 起，gate profile（fast/ci/release）包含 `validate_review_spec`：

- SSOT：`docs/reference/review/review_spec.v1.json`
- 生成产物：`docs/reference/review/REVIEW_SPEC.md`

当 SSOT 变更但未同步刷新生成文档时，该门禁会 FAIL。刷新命令：

```bash
python tools/generate_review_spec_docs.py --root . --write
```
