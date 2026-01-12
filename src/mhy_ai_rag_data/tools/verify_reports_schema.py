#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_reports_schema.py

用途：对“build_report 基础结构”做 schema 校验（可选：使用 JSON Schema / jsonschema）。
退出码：0=PASS；2=FAIL；3=ERROR

用法：
  # 仅做最小结构校验
  python tools/verify_reports_schema.py --report data_processed/build_reports/units.json --step units

  # 使用 JSON Schema（更严格）
  python tools/verify_reports_schema.py --report data_processed/build_reports/units.json --schema schemas/build_report_v1.schema.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQ_TOP = ["schema_version", "step", "ts", "status", "inputs", "metrics", "errors"]
ALLOWED_STATUS = {"PASS", "FAIL", "ERROR", "INFO", "WARN"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify build report schema (minimal or JSON Schema).")
    ap.add_argument("--report", required=True, help="JSON report path")
    ap.add_argument("--step", default="", help="Optional expected step name")
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

    missing = [k for k in REQ_TOP if k not in obj]
    if missing:
        print(f"[FAIL] missing keys: {missing}")
        return 2

    if args.step and obj.get("step") != args.step:
        print(f"[FAIL] step mismatch: expected={args.step} got={obj.get('step')}")
        return 2

    if obj.get("status") not in ALLOWED_STATUS:
        print(f"[FAIL] invalid status: {obj.get('status')} (allowed={sorted(ALLOWED_STATUS)})")
        return 2

    if (
        not isinstance(obj.get("inputs"), dict)
        or not isinstance(obj.get("metrics"), dict)
        or not isinstance(obj.get("errors"), list)
    ):
        print("[FAIL] inputs/metrics/errors types invalid")
        return 2

    print("[PASS] report schema ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
