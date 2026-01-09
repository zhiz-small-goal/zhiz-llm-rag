## README.md 目录
- [Mhy_AI_RAG_data](#mhy_ai_rag_data)
  - [文档导航（从这里开始）](#文档导航从这里开始)
  - [Golden Path（PR/CI Lite 快速回归）](#golden-pathprci-lite-快速回归)
  - [安装矩阵（依赖分层）](#安装矩阵依赖分层)
  - [支持和沟通](#支持与沟通support)
  - [旧版 README（已归档）](#旧版-readme已归档)


# zhiz-llm-rag

> 目标：构建可审计、可回归的 RAG 数据管线（inventory → units → validate → plan → embedding/chroma），并以门禁化方式降低重构回归成本。


## 文档导航（从这里开始）
- 📚 [`docs/INDEX.md`](docs/INDEX.md)

## Golden Path（PR/CI Lite 快速回归）
> 不下载大模型、不建 Chroma；用于重构后快速确认“入口点/契约/最小集成”均未回归。

```cmd
python -m venv .venv_ci
.\.venv_ci\Scripts\activate
python -m pip install -U pip
pip install -e ".[ci]"

python tools\check_tools_layout.py --mode fail
python tools\check_cli_entrypoints.py
python tools\check_md_refs_contract.py
pytest -q
```

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


## 旧版 README（已归档）
- 归档位置：[`docs/archive/README_LEGACY_FULL.md`](docs/archive/README_LEGACY_FULL.md)
- 说明：旧版包含大量操作细节，易与运行手册重复；现按 Diátaxis 分类收敛到 docs/ 下。
