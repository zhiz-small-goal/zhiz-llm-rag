## README.md 目录
- [Mhy_AI_RAG_data](#mhy_ai_rag_data)
  - [文档导航（从这里开始）](#文档导航从这里开始)
  - [Golden Path（PR/CI Lite 快速回归）](#golden-pathprci-lite-快速回归)
  - [安装矩阵（依赖分层）](#安装矩阵依赖分层)
  - [旧版 README（已归档）](#旧版-readme已归档)


# Mhy_AI_RAG_data

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

python tools\check_cli_entrypoints.py
python tools\check_md_refs_contract.py
pytest -q
```

## 安装矩阵（依赖分层）
- Stage-1（默认轻量）：`pip install -e .`
- PR/CI Lite（测试与门禁）：`pip install -e ".[ci]"`
- Stage-2（embedding/chroma）：`pip install -e ".[embed]"`
- 合并：`pip install -e ".[ci,embed]"`

## 旧版 README（已归档）
- 归档位置：[`docs/archive/README_LEGACY_FULL.md`](docs/archive/README_LEGACY_FULL.md)
- 说明：旧版包含大量操作细节，易与运行手册重复；现按 Diátaxis 分类收敛到 docs/ 下。
