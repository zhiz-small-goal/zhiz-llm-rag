# `init_eval_cases.py` 使用说明（Stage-2：初始化评测用例集 JSONL）


> **适用日期**：2025-12-28  
> **脚本位置建议**：`tools/init_eval_cases.py`  
> **输出位置**：默认写入 `data_processed/eval/eval_cases.jsonl`

---

## 1. 目的与适用场景

Stage-2 的核心是“可度量的回归”。该脚本用于创建评测用例集（JSONL），使你可以：

- 对每次改动后的检索/生成结果做一致的回归检查
- 用结构化报告定位“哪些问题退化/改善”
- 让用例集可版本化（git diff 审阅新增/修改/删除的用例）

---

## 2. 用例格式（每行一个 JSON）

字段定义（建议最小集）：

- `id`：用例唯一标识（稳定，不随 query 文案小改动而改变）
- `query`：用户问题
- `expected_sources`：期望命中的文档路径片段（用于检索侧 hit@k）
- `must_include`：生成答案必须包含的关键词/短语（用于端到端最小断言）
- `tags`：标签（可选）

示例：

```json
{"id":"tutorial_save_import_export","query":"存档导入与导出怎么做？","expected_sources":["data_raw/教程/05_1.4存档导入与导出.md"],"must_include":["导入","导出"],"tags":["tutorial","baseline"]}
```

---

## 3. 快速开始

```bash
python tools/init_eval_cases.py --root .
```

默认会创建（或覆盖策略由参数控制）：

- `data_processed/eval/eval_cases.jsonl`

---

## 4. 参数详解

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 项目根目录 |
| `--out` | `data_processed/eval/eval_cases.jsonl` | 输出路径（相对 root） |
| `--force` | false | 覆盖重建（谨慎） |

覆盖重建：

```bash
python tools/init_eval_cases.py --root . --force
```

---

## 5. 退出码与常见错误

- `0`：写入成功
- `2`：输出已存在且未指定 `--force`

---

## 6. 工程化建议（如何让用例集有效）

- 初期建议 20～50 条，覆盖：
  - 高频“流程类”问题
  - 易混淆问题（相似概念区分）
  - 边界问题（上下文不足）
  - 你最在意的教程/排障类问题
- `expected_sources` 建议尽量指向具体文件；目录前缀可作为过渡，但会降低判定信号强度。
- `must_include` 只做最小断言；后续可升级为结构化输出或引用校验。
