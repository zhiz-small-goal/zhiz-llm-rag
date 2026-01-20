# tools/ README ↔ 入口脚本映射索引（Reference）

本页用于定位 `tools/` 目录下各工具 README 与其对应的入口脚本/模块实现的映射关系，供后续 **README↔源码对齐校验**、**自动区块生成**、**门禁/CI** 使用。

## 机器可读索引

- `docs/reference/readme_code_sync_index.yaml`

字段约定（概要）：

- `path`：README 相对路径
- `tool_id`：稳定工具标识（默认取 README 文件名的 `<tool_id>_README.md` 前缀）
- `impl.module`：实现模块（优先指向 `src/mhy_ai_rag_data/tools/<tool_id>.py`）
- `impl.wrapper`：wrapper 脚本（若存在，通常为 `tools/<tool_id>.py`）
- `entrypoints`：建议的运行入口（脚本 / `-m` 模块）
- `contracts.output`：输出契约分类（`report-output-v2` / `legacy` / `none`）
- `generation.options`：参数表生成策略（`static-ast` / `help-snapshot`）

## 变更规则

- 当工具新增/改名/迁移入口时：
  1. 先更新对应 README 的 frontmatter（`tool_id` / `impl.*` / `entrypoints` 等）；
  2. 再更新 `readme_code_sync_index.yaml`（由 Step3/Step4 的脚本逐步接管生成）。

