## README.md 目录
- [zhiz-llm-rag](#zhiz-llm-rag)
- [文档导航（从这里开始）](#文档导航从这里开始)
- [Golden Path（PR/CI Lite 快速回归）](#golden-pathprci-lite-快速回归)
- [安装矩阵（依赖分层）](#安装矩阵依赖分层)
- [支持和沟通](#支持与沟通support)
- [项目治理与开源文件](#项目治理与开源文件)
- [旧版 README（已归档）](#旧版-readme已归档)


# zhiz-llm-rag

> 目标：构建可审计、可回归的 RAG 数据管线（inventory → units → validate → plan → embedding/chroma），并以门禁化方式降低重构回归成本。


## 文档导航（从这里开始）
- 📚 [文档导航（Diátaxis）](docs/INDEX.md)
- [tools 目录说明（入口层 / 治理脚本）](tools/README.md)
- [审查规范（Review Spec）](docs/reference/review/README.md)
- [审查流程（How-to）](docs/howto/review_workflow.md)

## Golden Path（PR/CI Lite 快速回归）
> 不下载大模型、不建 Chroma；用于重构后快速确认“入口点/契约/最小集成”均未回归。

```cmd
python -m venv .venv_ci
.\.venv_ci\Scripts\activate
python -m pip install -U pip
pip install -e ".[ci]"

REM 推荐：单入口 gate runner（产出 gate_report.json + gate_logs/）
python tools\gate.py --profile ci --root .

REM 你也可以手动逐条跑（不推荐；更易漂移）
python tools\check_tools_layout.py --mode fail
python tools\check_cli_entrypoints.py
python tools\check_md_refs_contract.py
pytest -q
```

更多门禁说明：见 `docs/howto/ci_pr_gates.md`。

## 安装矩阵（依赖分层）
- Stage-1（默认轻量）：`pip install -e .`
- PR/CI Lite（测试与门禁）：`pip install -e ".[ci]"`
- Stage-2（embedding/chroma）：`pip install -e ".[embed]"`
- 合并：`pip install -e ".[ci,embed]"`

**默认的安装器安装到是 torch-only cpu, 想使用 GPU 需要先安装支持的 torch, 详见[OPERATION_GUIDE.md-环境与安装依赖-如需GPU](docs/howto/OPERATION_GUIDE.md#step-0环境与依赖安装core-vs-embed避免在-python-313-及以上误装-stage-2)

## 支持与沟通（Support）

> 当前阶段：欢迎 **Bug 报告** 与 **问题讨论**；为保证独立迭代节奏与回归质量，暂不接受代码贡献（Pull Request 可能会被直接关闭或不做处理）。

- 🐛 Bug 报告：请使用 Issue 表单提交（推荐）  
  https://github.com/zhiz-small-goal/zhiz-llm-rag/issues/new/choose

- 💬 问答 / 讨论 / 使用交流：请使用 Discussions（Q&A / Discussion）  
  https://github.com/zhiz-small-goal/zhiz-llm-rag/discussions

- ✨ 建议与改进方向：请优先发到 Discussions，并尽量补充你的使用场景、期望行为与复现信息（有助于我评估优先级与可行性）。

### 关于 Pull Request（暂不接收）
目前仓库以维护者独立开发为主，暂不接收外部 PR/代码提交。  
如果你已经准备了补丁或实现思路，建议先在 Discussions 发起讨论（附：动机、方案、影响面、验证方式），我会在合适的阶段再决定是否开放贡献入口并更新本段说明。

## 项目治理与开源文件

- `LICENSE`：开源授权条款
- `CHANGELOG.md`：对外可感知的重要变更记录
- `CITATION.cff`：引用信息（GitHub Cite this repository）
- `CODE_OF_CONDUCT.md`：行为准则与举报渠道
- `CONTRIBUTING.md`：贡献说明与准入条件
- `SECURITY.md`：安全漏洞报告与支持范围
- `SUPPORT.md`：支持与沟通渠道
- `.editorconfig`：基础格式约定（减少无意义 diff）


## 旧版 README（已归档）
- 归档位置：[`docs/archive/README_LEGACY_FULL.md`](docs/archive/README_LEGACY_FULL.md)
- 说明：旧版包含大量操作细节，易与运行手册重复；现按 Diátaxis 分类收敛到 docs/ 下。
