# `check_docs_conventions.py` 使用说明（docs Markdown 工程约定门禁）


> **适用日期**：2025-12-28  
> **脚本位置建议**：`tools/check_docs_conventions.py`  
> **输出位置**：默认写入 `data_processed/build_reports/docs_conventions_report.json`（可通过配置文件修改）

---

## 1. 目的与适用场景

当你对 `docs/` / `tools/` 等 Markdown 做批处理（例如自动插入目录 TOC），工程上需要一个门禁来保证输出稳定、避免格式漂移影响：

- GitHub 渲染与目录可点击性
- 后续脚本二次处理（例如抽取 YAML 元数据、统一标题、生成站点导航等）

该脚本实现一个最小但明确的约定检查。

---

## 2. 约定规则（默认）

对每个 Markdown 文件：

1) 首个正文标题必须是 **H1 级别**（`# ...`），标题内容不强制与文件名一致。

2) 目录标题后必须紧跟 **两行空行**（便于插入 TOC 并保持可读性）

3) 允许 YAML front matter：
- 若文件以 `---` 开头，视为 front matter，直到下一个 `---` 结束
- 检查从 front matter 结束后的正文开始执行

> 可选：使用 `--fix` 自动在目录标题后补齐缺失的空行。

---

## 3. 快速开始

```bash
# 默认：扫描 docs/ 和 tools/，并写出报告
python tools/check_docs_conventions.py --root .

# 如需自动补齐目录标题后的空行（会就地写回文件）
python tools/check_docs_conventions.py --root . --fix

# 全仓库扫描（可能产生噪声，建议搭配 --ignore）
python tools/check_docs_conventions.py --root . --full-repo

# 使用自定义配置文件（命令行参数可覆盖配置值）
python tools/check_docs_conventions.py --root . --config my_docs_conventions.json
```

---

## 4. 参数详解

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--config` | `.docs_conventions_config.json` | 配置文件路径（JSON，命令行可覆盖其中字段） |
| `--dirs` | `docs tools` | 需要检查的目录（可多值，空格分隔） |
| `--full-repo` | `false` | 扫描整个仓库（覆盖 `--dirs`） |
| `--glob` | `**/*.md` | 匹配模式 |
| `--ignore` | 见下 | fnmatch 语法的忽略列表（对 root 相对的 posix 路径生效） |
| `--out` | `data_processed/build_reports/docs_conventions_report.json` | 输出报告 |
| `--fix` | `false` | 自动补齐标题后的空行 |

默认忽略：`.git/**`, `.venv/**`, `venv/**`, `data_processed/**`, `chroma_db/**`, `third_party/**`, `**/__pycache__/**`, `.ruff_cache/**`, `.mypy_cache/**`, `.pytest_cache/**`, `**/node_modules/**`。

示例：只检查 `docs/` 根下 md：

```bash
python tools/check_docs_conventions.py --root . --dirs docs --glob "*.md"
```

### 配置文件示例（JSON）

默认读取仓库根目录下 `.docs_conventions_config.json`（如不存在则使用内置默认）。命令行参数会覆盖配置文件中的同名字段。

```json
{
  "dirs": ["docs", "tools"],
  "full_repo": false,
  "glob": "**/*.md",
  "ignore": ["docs/archive/**", ".git/**", "data_processed/**"],
  "out": "data_processed/build_reports/docs_conventions_report.json",
  "fix": false
}
```

---

## 5. 输出报告说明

报告包含：

- `overall`：PASS/FAIL
- `counts.files`：检查文件数
- `counts.bad`：违反约定的文件数
- `dirs`：实际扫描的目录列表；`missing_dirs`：缺失的目录
- `ignore`：生效的忽略列表
- `files[]`：每个文件的检查结果：
  - `expected_title`（H1 即可，标题内容自由）
  - `has_front_matter`
  - `issues[]`：问题列表（title 不是 H1 / need two blank lines 等）

---

## 6. 退出码

- `0`：全部通过
- `2`：存在违反约定的文件，或 `docs_dir` 不存在

---

## 7. 常见问题与处理

1) title 不是 H1  
原因：首行非 H1（如直接文本/列表）。  
处理：把目录标题写成 `# ...`。

2) two blank lines 缺失  
原因：目录生成器未插入空行或被手工删改。  
处理：将“插入空行”纳入生成器输出模板，并将本检查作为门禁。
