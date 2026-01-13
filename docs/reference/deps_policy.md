---
title: 依赖策略（Dependency Policy）
version: v1.0
last_updated: 2026-01-13
---

# 依赖策略（Dependency Policy）


## 目录
- [依赖策略总览](#deps-policy-overview)
- [默认安装范围](#default-install-scope)
- [可选安装与 extras](#extras)
- [ci extras 约束](#ci-extras)
- [dev extras 约束](#dev-extras)
- [embed extras 约束](#embed-extras)
- [为何 pyproject.toml 采用 ASCII-only](#why-ascii-only)
- [如何新增或调整依赖](#how-to-change-deps)

---

## deps-policy-overview
本项目把依赖分为两类：**默认安装（轻量、可用、可回归）** 与 **可选 extras（按需启用的重依赖）**。

- 默认安装目标：让 `pip install -e .` 在常见开发机与 CI 上快速可用，覆盖 Stage-1 主线（inventory → units → validate → plan）。
- 可选 extras 目标：把 Stage-2（embedding / chroma / 检索闭环）等重依赖隔离出来，只有在你明确需要时才安装，避免把不确定性引入 PR/CI 主线。

---

## default-install-scope
默认安装（`pip install -e .`）应当只包含 Stage-1 所需的轻量依赖，典型包括：

- 数据处理/校验：pydantic、pandas、numpy
- 进度与日志：tqdm、rich
- 文本/配置：PyYAML、markdown-it-py 等

默认安装不应隐式引入 embedding/chroma 相关包，以免出现：
- wheel 覆盖滞后导致源码编译
- 平台/编译器差异导致安装失败
- CI 运行时依赖爆炸造成回归不稳定

---

## extras
项目通过 `pyproject.toml -> [project.optional-dependencies]` 提供 extras。推荐的使用方式：

- `.[ci]`：PR/CI 门禁与最小测试集
- `.[dev]`：本地开发工具（可选）
- `.[embed]`：Stage-2 embedding/chroma/retrieval loop（重依赖，按需开启）

---

## ci-extras
`ci` extras 的目标是“稳定且最小”，约束如下：

1) 只放 **门禁与最小测试** 必需包（例如 pytest）。
2) 不放任何 embedding/chroma/模型下载相关依赖。
3) 若某个检查脚本需要重依赖才能运行，应当拆分为：
   - PR/CI 主线：跳过或替代为轻量 smoke check
   - 单独 workflow / 手动 job：在 `.[embed]` 环境下执行

---

## dev-extras
`dev` extras 允许引入本地效率工具，但仍建议保持可控：

- 允许：ruff、mypy、pytest-cov、pre-commit 等
- 不建议：把 Stage-2 重依赖放入 dev（避免“本地装了所以感觉没问题，但 CI 会炸”）

若你个人还有一两个临时工具，优先放入 `dev` extras（可审计、可复现），而不是靠迁移虚拟环境。

---

## embed-extras
`embed` extras 只用于 Stage-2（embedding/chroma/retrieval loop），属于重依赖区：

- 仅在确实需要构建/检索 Chroma 或跑检索闭环时安装。
- 对 Python 版本建议采用 **fail-fast** 策略：在较新的解释器上明确阻止安装，避免进入回溯解析或源码编译链路（本仓库当前使用 python_version marker 实现）。

---

## why-ascii-only
本仓库对 `pyproject.toml` 采用 ASCII-only 的原因不是“规范要求”，而是工程约束：

- 复制粘贴很容易引入全角标点、智能引号、不可见空格等字符；
- 这些字符会导致跨编辑器/跨系统的解析行为变得不确定；
- `pyproject.toml` 是“安装入口契约”，一旦解析失败会在最早阶段中止，成本最高。

因此：中文解释放在 `docs/`，`pyproject.toml` 只保留 ASCII 指针与机器可解析配置。

---

## how-to-change-deps
新增/调整依赖的建议流程：

1) 判断依赖归属：Stage-1（默认）还是 Stage-2（embed extras）还是工具链（ci/dev）。
2) 修改 `pyproject.toml` 对应列表，并在本地重建 venv 验证：
   - `python -m venv .venv_ci`
   - `pip install -e ".[ci]"`
3) 若你是从旧环境迁移来的包，优先把它写回 `dev` extras，而不是复制旧 venv 的 site-packages。
4) 更新 `docs/howto/ci_pr_gates.md`，确保主线命令与门禁一致。
