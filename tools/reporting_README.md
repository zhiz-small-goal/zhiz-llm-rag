---
title: reporting.py 使用说明（报告生成工具模块）
version: v1.0
last_updated: 2026-01-16
tool_id: reporting

impl:
  module: mhy_ai_rag_data.tools.reporting
  wrapper: tools/reporting.py

entrypoints:
  - python tools/reporting.py
  - python -m mhy_ai_rag_data.tools.reporting
entrypoints_note: "兼容/调试入口：用于 README↔源码对齐与开发自检；不保证提供稳定 CLI（运行通常等同导入）。"

contracts:
  output: none

generation:
  options: help-snapshot
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: other
---
# reporting.py 使用说明


> 目标：为本项目步骤验收脚本提供统一的 JSON report 契约与写入行为，遵循"当提供 --json-out 时，只写该路径，不再额外写默认时间戳报告文件"规则。

## 目的

本模块是工具库模块（非命令行工具），提供统一的报告生成函数，确保：

<!-- ENTRYPOINTS-NONCLI-NOTE -->
## 运行入口（entrypoints）说明（非稳定 CLI）

本 README 顶部与“自动生成参考”里列出的 `entrypoints`，主要用途是 **兼容入口/调试入口**：用于在 repo 根目录下通过 wrapper 触发模块导入、以及让 `check_readme_code_sync` 能识别 README 里的示例命令块并做一致性校验。它不表示该模块对外提供“可长期依赖的命令行接口”。

- **行为边界**：运行 `python tools/reporting.py` 或 `python -m mhy_ai_rag_data.tools.reporting` 的主要效果是“导入模块并完成定义加载”，通常不会生成报告文件；传入参数也不会被消费（除非未来明确加入 CLI）。
- **正确使用方式**：请把它当作库模块，在 Python 里 `import` 后调用下方 API；需要运行验收/门禁/评测等动作时，优先使用项目内的具体 CLI 工具（例如 `tools/gate.py`、`tools/run_ci_gates.cmd`、`tools/run_eval_rag.py` 等）。


- **统一 schema**：所有报告遵循 schema_version=1
- **一致退出码**：PASS=0, FAIL=2, ERROR=3
- **单一产物**：提供 `--json-out` 时只写该文件

## 主要 API

### 1) build_base
```python
from mhy_ai_rag_data.tools.reporting import build_base

report = build_base("llm_probe", inputs={"base_url": "http://localhost:8000/v1"})
# 返回：
# {
#   "schema_version": 1,
#   "step": "llm_probe",
#   "ts": 1737000000,
#   "status": "INFO",
#   "inputs": {...},
#   "metrics": {},
#   "errors": []
# }
```

### 2) add_error
```python
from mhy_ai_rag_data.tools.reporting import add_error

add_error(report, "NO_POST_200", "No POST probe returned HTTP 200")
```

### 3) write_report
```python
from mhy_ai_rag_data.tools.reporting import write_report

path = write_report(report, json_out=args.json_out, default_name="report.json")
Print(f"Wrote: {path}")
```

### 4) status_to_rc
```python
from mhy_ai_rag_data.tools.reporting import status_to_rc

rc = status_to_rc(report["status"])  # PASS=0, FAIL=2, ERROR=3
return rc
```

## 报告结构约定

```json
{
  "schema_version": 1,
  "step": "step_name",
  "ts": 1737000000,
  "status": "PASS|FAIL|ERROR|INFO",
  "inputs": {},
  "metrics": {},
  "errors": [
    {"code": "ERROR_CODE", "message": "...", "detail": {}}
  ]
}
```

## 退出码映射

| Status | 退出码 | 说明 |
|---|---:|---|
| PASS | 0 | 成功 |
| FAIL | 2 | 失败（门禁不通过） |
| ERROR | 3 | 错误（脚本异常） |
| INFO/WARN | 0 | 不强制失败 |

---

**注意**：本模块是**工具库模块**，通常被其他工具导入使用，不直接作为命令行工具运行。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `reporting`
> entrypoints: `python tools/reporting.py`, `python -m mhy_ai_rag_data.tools.reporting`

<!-- AUTO:BEGIN options -->
_(no long flags detected by help-snapshot)_
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
