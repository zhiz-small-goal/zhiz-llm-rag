# `view_stage2_reports.py` 使用说明（Stage-2 输出文件一键解读）

> **脚本位置建议**：`tools/view_stage2_reports.py`  
> **适用日期**：2026-01-05

---

## 1) 解决什么问题

- 额外：若 `eval_retrieval_report.json` 包含 `buckets`（分桶指标），会在摘要中一并展示（用于口语 vs 术语回归）。

你按推荐流程依次运行：

1. `suggest_expected_sources.py`（取证 expected_sources）
2. `validate_eval_cases.py`（门禁校验）
3. `run_eval_retrieval.py`（检索回归）
4. `run_eval_rag.py`（端到端回归）

会得到多份 JSON/JSONL 输出。该脚本用于把这些输出文件的关键字段汇总成一份可读摘要，避免你逐个打开 JSON 手动找字段。

---

## 2) 快速开始

在项目根目录：

```bash
python tools/view_stage2_reports.py --root .
```

如果你想把摘要落盘成 Markdown：

```bash
python tools/view_stage2_reports.py --root . --md-out data_processed/build_reports/stage2_summary.md
```

---

## 3) 它会读取哪些文件（默认路径）

- 用例集：`data_processed/eval/eval_cases.jsonl`（必需）
- 门禁报告：`data_processed/build_reports/eval_cases_validation.json`（必需）
- 检索回归：`data_processed/build_reports/eval_retrieval_report.json`（可选）
- 端到端回归：`data_processed/build_reports/eval_rag_report.json`（可选）

如果你在运行评测时改了输出路径，可以用参数覆盖：

```bash
python tools/view_stage2_reports.py --root . --retrieval some/other.json --rag some/other.json
```

可用参数补充说明：
- `--cases`：覆盖 eval_cases.jsonl 路径  
- `--validation`：覆盖 eval_cases_validation.json 路径  
- `--show-fails`：每个报告展示多少条失败样例（默认 5）

---

## 4) 退出码

- 0：成功汇总（即使评测 FAIL 也会输出汇总；评测是否通过看报告的 `overall` 或指标）
- 2：缺少必需文件（用例集或门禁报告缺失）

---

## 5) 你应该如何解读输出

- `eval_cases.jsonl`：看“可解析用例数”与解析错误行数，保证用例集结构稳定。
- `eval_cases_validation.json`：看 `overall/errors/warnings`，errors 必须为 0 才建议进入评测。
- `eval_retrieval_report.json`：看 `hit_rate` 与未命中样例，定位 expected_sources 是否写错或检索退化。
- `eval_rag_report.json`：看 `pass_rate` 与 missing/answer_snippet，定位 must_include 断言或端到端链路问题。
