#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.reporting

目标：
- 为本项目的“步骤验收脚本”提供统一的 JSON report 契约与写入行为。
- 关键规则：**当用户提供 --json-out 时，只写该路径，不再额外写默认时间戳报告文件。**

约定退出码（建议各脚本遵循）：
- 0：PASS
- 2：FAIL（检查不通过 / 前置条件不满足）
- 3：ERROR（脚本异常）

report 基础结构建议：
{
  "schema_version": 1,
  "step": "llm_probe|units|check|...",
  "ts": 1730000000,
  "status": "PASS|FAIL|ERROR|INFO",
  "inputs": {...},
  "metrics": {...},
  "errors": [...]
}
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output


SCHEMA_VERSION = 1


def now_ts() -> int:
    return int(time.time())


def build_base(step: str, *, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "step": step,
        "ts": now_ts(),
        "status": "INFO",
        "inputs": inputs or {},
        "metrics": {},
        "errors": [],
    }


def add_error(report: Dict[str, Any], code: str, message: str, *, detail: Any = None) -> None:
    err = {"code": code, "message": message}
    if detail is not None:
        err["detail"] = detail
    report.setdefault("errors", []).append(err)


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def write_report(report: Dict[str, Any], *, json_out: Optional[str], default_name: str) -> Path:
    """写入 report。

    行为规则：
    - 若 json_out 非空：仅写 json_out（遵循“只产出一份”规则）。
    - 否则：写到当前工作目录的 default_name。

    返回：实际写入的路径（Path）。
    """
    if json_out:
        out_path = Path(json_out)
        ensure_parent_dir(out_path)
    else:
        out_path = Path(default_name)

    payload = prepare_report_for_file_output(report)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return out_path


def status_to_rc(status: str) -> int:
    s = (status or "").upper()
    if s == "PASS":
        return 0
    if s in ("FAIL",):
        return 2
    if s in ("ERROR",):
        return 3
    # INFO / WARN 等：不强制失败
    return 0
