---
title: tools/ 目录说明（入口层 / 治理脚本）
version: v1.3
last_updated: 2026-01-12
---

# tools/ 目录说明（入口层 / 治理脚本）

本项目采用 **src-layout**：
- **权威实现（SSOT）**：`src/mhy_ai_rag_data/...`（可被 `python -m ...` 或 console_scripts 调用）
- **兼容入口（wrapper）**：`tools/*.py`（允许运行 `python tools\xxx.py`，但内部转发到 src）
- **仓库内工具（repo-only）**：`tools/*.py` 中的少数脚本，仅用于仓库门禁/修复/审计（不作为可安装库 API）

为避免重构时出现“同名双实现”“导入影子覆盖”“入口语义漂移”，tools/ 下脚本遵循以下约定，并由 `tools/check_tools_layout.py` 进行审计。

## 目录
- [关键入口（先看这里）](#关键入口先看这里)
- [wrapper 自动生成（推荐默认）](#wrapper-自动生成推荐默认)
- [约定（contract）](#约定contract)
- [工具布局审计](#工具布局审计)
- [退出码约定（与门禁一致）](#退出码约定与门禁一致)
- [新增一个工具脚本时怎么选](#新增一个工具脚本时怎么选)

## 关键入口（先看这里）

- 单入口 Gate（Schema + Policy + report）：`tools/gate.py`  / `rag-gate`
  - 使用说明：`tools/gate_README.md`
- JSON Schema 校验：`tools/schema_validate.py` / `rag-schema-validate`
  - 使用说明：`tools/schema_validate_README.md`

## wrapper 自动生成（推荐默认）
为避免 wrapper 模板被手工改坏或复制粘贴导致漂移，本仓库提供统一生成器：
- 生成器：`tools/gen_tools_wrappers.py`（repo-only）
- 配置：`tools/wrapper_gen_config.json`

常用命令：
```cmd
python tools/gen_tools_wrappers.py --check
python tools/gen_tools_wrappers.py --write
```

约束：
- 只有 `tools/wrapper_gen_config.json` 的 `managed_wrappers` 列表中的 wrapper 才是“受管 wrapper”。
- 受管 wrapper 的内容必须与生成器模板一致；不要手工编辑，统一用 `--write` 刷新。
- 需要新增一个 wrapper 时：先在 src 侧实现 `src/mhy_ai_rag_data/tools/<name>.py`，再复制任意一个受管 wrapper 的文件名（或先手工创建占位文件，包含 marker），然后执行 `--write` 刷新并提交。

## 约定（contract）

### 1) 两类脚本
1) **AUTO-GENERATED WRAPPER**
- 角色：兼容入口层。
- 行为：确保 repo root 下可 `python tools\xxx.py` 运行，但会 `runpy.run_module('mhy_ai_rag_data.tools.xxx', run_name='__main__')` 转发到 src。
- 约束：当 src 侧存在同名实现时，tools 侧必须是 wrapper（SSOT 在 src）。

2) **REPO-ONLY TOOL**
- 角色：仓库内治理/审计/修复工具。
- 行为：只保证在仓库环境下可运行（例如 CI Lite 门禁脚本、发布清理脚本）。
- 约束：不要在 src 下创建同名实现；否则会引入双实现歧义。

### 2) marker-first：每个 tools/*.py 必须显式标记
- wrapper 必须包含：`AUTO-GENERATED WRAPPER`
- repo-only 必须包含：`REPO-ONLY TOOL`

未标记会被 `check_tools_layout` 判定为 `unknown`，在严格模式下可直接 FAIL。

## 工具布局审计

- 入口：`python tools\check_tools_layout.py --mode warn|fail [--out <json>]`
- 说明：见 `tools/check_tools_layout_README.md`

建议：
- 迁移期/开发期使用 `--mode warn`（不阻断，但输出问题清单）
- CI/门禁期使用 `--mode fail`（阻断不符合 contract 的改动）


## 退出码约定（与门禁一致）

本目录下用于门禁/回归的脚本，退出码遵循项目统一契约（见 docs/REFERENCE.md 的 "3.1 退出码"）：

- `0`：PASS（或迁移期的 WARN/INFO，不强制失败）
- `2`：FAIL（门禁不通过/强校验失败）
- `3`：ERROR（脚本异常/未捕获异常）

## 新增一个工具脚本时怎么选

1) 你希望“可安装后仍能稳定使用”的命令（未来可能变 console_scripts）：
- 实现：放 `src/mhy_ai_rag_data/tools/<name>.py`
- tools 入口：生成 `tools/<name>.py` wrapper（AUTO-GENERATED WRAPPER）

2) 你只是做仓库治理/审计（仅用于开发/CI）：
- 直接放 `tools/<name>.py`（REPO-ONLY TOOL）
- 尽量采用 `check_*/fix_*` 命名，并在 README 或 docs/howto 中说明何时运行。
