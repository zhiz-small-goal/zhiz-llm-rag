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
