#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_reports_schema.py

用途：对“报告基础结构（schema_version=2，item 模型）”做 schema 校验。
退出码：0=PASS；2=FAIL；3=ERROR

用法：
  # 仅做最小结构校验（v2）
  python tools/verify_reports_schema.py --report data_processed/build_reports/gate_report.json

  # 校验期望 tool（兼容参数名：--step）
  python tools/verify_reports_schema.py --report data_processed/build_reports/units.json --step units

  # 使用 JSON Schema（更严格）
  python tools/verify_reports_schema.py --report data_processed/build_reports/gate_report.json --schema schemas/gate_report_v2.schema.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQ_TOP_V2 = ["schema_version", "generated_at", "tool", "root", "summary", "items"]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify report schema (v2 minimal or JSON Schema).")
    ap.add_argument("--report", required=True, help="JSON report path")
    ap.add_argument("--step", default="", help="Optional expected tool name (legacy flag name)")
    ap.add_argument("--schema", default="", help="Optional JSON Schema path for jsonschema validation")
    args = ap.parse_args()

    p = Path(args.report)
    if not p.exists():
        print(f"[FAIL] report missing: {p}")
        return 2

    try:
        obj = _load_json(p)
    except Exception as e:
        print(f"[FAIL] invalid json: {e}")
        return 2

    if args.schema:
        try:
            import jsonschema
        except Exception as e:
            print("[ERROR] jsonschema not installed; cannot use --schema")
            print("        underlying:", repr(e))
            return 3

        try:
            schema = _load_json(Path(args.schema))
            jsonschema.validate(instance=obj, schema=schema)
        except jsonschema.ValidationError as e:
            loc = "/".join([str(x) for x in e.path]) if e.path else ""
            print("[FAIL] jsonschema validation failed")
            if loc:
                print("  at:", loc)
            print("  message:", e.message)
            return 2
        except Exception as e:
            print(f"[ERROR] jsonschema error: {e}")
            return 3

    if not isinstance(obj, dict):
        print("[FAIL] report must be a JSON object")
        return 2

    missing = [k for k in REQ_TOP_V2 if k not in obj]
    if missing:
        print(f"[FAIL] missing keys: {missing}")
        return 2

    try:
        sv = int(obj.get("schema_version") or 0)
    except Exception:
        sv = 0
    if sv != 2:
        print(f"[FAIL] schema_version must be 2 (got={obj.get('schema_version')})")
        return 2

    if args.step and str(obj.get("tool") or "") != args.step:
        print(f"[FAIL] tool mismatch: expected={args.step} got={obj.get('tool')}")
        return 2

    if not isinstance(obj.get("summary"), dict):
        print("[FAIL] summary must be an object")
        return 2
    summ = obj["summary"]
    for k in ("overall_status_label", "overall_rc", "max_severity_level", "counts", "total_items"):
        if k not in summ:
            print(f"[FAIL] summary missing key: {k}")
            return 2
    if not isinstance(summ.get("counts"), dict):
        print("[FAIL] summary.counts must be an object")
        return 2

    if not isinstance(obj.get("items"), list):
        print("[FAIL] items must be an array")
        return 2
    items = obj["items"]
    for i, it in enumerate(items[:50]):
        if not isinstance(it, dict):
            print(f"[FAIL] items[{i}] must be an object")
            return 2
        for k in ("tool", "title", "status_label", "severity_level", "message"):
            if k not in it:
                print(f"[FAIL] items[{i}] missing key: {k}")
                return 2
        # severity must be int-like
        sev_raw = it.get("severity_level")
        if sev_raw is None:
            print(f"[FAIL] items[{i}].severity_level must be int")
            return 2
        try:
            int(sev_raw)
        except Exception:
            print(f"[FAIL] items[{i}].severity_level must be int")
            return 2

    print("[PASS] report schema ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
