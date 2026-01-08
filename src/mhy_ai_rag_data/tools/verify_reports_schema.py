#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_reports_schema.py

用途：对方案2产生的 JSON report 做最小 schema 校验，便于回归/CI gate。
退出码：0=PASS；2=FAIL

用法：
  python tools/verify_reports_schema.py --report data_processed/build_reports/units.json --step units
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

REQ_TOP = ["schema_version", "ts", "step", "status", "inputs", "metrics", "errors"]
ALLOWED_STATUS = {"PASS","FAIL","ERROR","INFO"}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--step", default="", help="Optional expected step name")
    args = ap.parse_args()

    p = Path(args.report)
    if not p.exists():
        print(f"[FAIL] report missing: {p}")
        return 2

    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[FAIL] invalid json: {e}")
        return 2

    missing = [k for k in REQ_TOP if k not in obj]
    if missing:
        print(f"[FAIL] missing keys: {missing}")
        return 2

    if obj.get("status") not in ALLOWED_STATUS:
        print(f"[FAIL] bad status: {obj.get('status')}")
        return 2

    if args.step and obj.get("step") != args.step:
        print(f"[FAIL] step mismatch: expected={args.step} got={obj.get('step')}")
        return 2

    if not isinstance(obj.get("inputs"), dict) or not isinstance(obj.get("metrics"), dict) or not isinstance(obj.get("errors"), list):
        print("[FAIL] inputs/metrics/errors types invalid")
        return 2

    print("[PASS] report schema ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
