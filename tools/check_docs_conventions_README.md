# `check_docs_conventions.py` 使用说明（docs Markdown 工程约定门禁）

> **适用日期**：2025-12-28  
> **脚本位置建议**：`tools/check_docs_conventions.py`  
> **输出位置**：默认写入 `data_processed/build_reports/docs_conventions_report.json`

---

## 1. 目的与适用场景

当你对 `docs/` 下 Markdown 做批处理（例如自动插入目录 TOC），工程上需要一个门禁来保证输出稳定、避免格式漂移影响：

- GitHub 渲染与目录可点击性
- 后续脚本二次处理（例如抽取 YAML 元数据、统一标题、生成站点导航等）

该脚本实现一个最小但明确的约定检查。

---

## 2. 约定规则（默认）

对每个 Markdown 文件：

1) 首个正文标题必须为：

- `# {文件名}目录：`  
  其中 `{文件名}` 为不带扩展名的文件名（`Path.stem`）

2) 目录标题后必须紧跟 **两行空行**（便于插入 TOC 并保持可读性）

3) 允许 YAML front matter：
- 若文件以 `---` 开头，视为 front matter，直到下一个 `---` 结束
- 检查从 front matter 结束后的正文开始执行

---

## 3. 快速开始

```bash
python tools/check_docs_conventions.py --root . --docs-dir docs
```

---

## 4. 参数详解

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--docs-dir` | `docs` | 要检查的目录（相对 root） |
| `--glob` | `**/*.md` | 匹配模式 |
| `--out` | `data_processed/build_reports/docs_conventions_report.json` | 输出报告 |

示例：只检查 `docs/` 根下 md：

```bash
python tools/check_docs_conventions.py --root . --docs-dir docs --glob "*.md"
```

---

## 5. 输出报告说明

报告包含：

- `overall`：PASS/FAIL
- `counts.files`：检查文件数
- `counts.bad`：违反约定的文件数
- `files[]`：每个文件的检查结果：
  - `expected_title`
  - `has_front_matter`
  - `issues[]`：问题列表（title mismatch / need two blank lines 等）

---

## 6. 退出码

- `0`：全部通过
- `2`：存在违反约定的文件，或 `docs_dir` 不存在

---

## 7. 常见问题与处理

1) title mismatch  
原因：自动 TOC 工具没按约定写标题，或文件名与标题不一致。  
处理：统一用脚本生成标题，避免手工编辑导致漂移。

2) two blank lines 缺失  
原因：目录生成器未插入空行或被手工删改。  
处理：将“插入空行”纳入生成器输出模板，并将本检查作为门禁。
