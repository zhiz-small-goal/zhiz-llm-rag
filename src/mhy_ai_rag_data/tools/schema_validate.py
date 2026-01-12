#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.schema_validate

Validate a JSON instance against a JSON Schema (Draft 2020-12).

Exit codes:
- 0: PASS
- 2: FAIL (validation failed)
- 3: ERROR (runtime/setup error)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate JSON instance against JSON Schema.")
    ap.add_argument("--schema", required=True, help="Schema path (json)")
    ap.add_argument("--instance", required=True, help="Instance path (json)")
    args = ap.parse_args()

    schema_path = Path(args.schema)
    inst_path = Path(args.instance)

    try:
        import jsonschema
    except Exception as e:  # pragma: no cover
        print("[ERROR] jsonschema is not installed. Install with: pip install -e '.[ci]'")
        print("        underlying:", repr(e))
        return 3

    try:
        schema = _load_json(schema_path)
        inst = _load_json(inst_path)
    except Exception as e:
        print(f"[ERROR] failed to load json: {e}")
        return 3

    try:
        jsonschema.validate(instance=inst, schema=schema)
    except jsonschema.ValidationError as e:
        loc = "/".join([str(x) for x in e.path]) if e.path else ""
        print("[FAIL] schema validation failed")
        print("  instance:", str(inst_path))
        print("  schema:  ", str(schema_path))
        if loc:
            print("  at:      ", loc)
        print("  message: ", e.message)
        return 2
    except Exception as e:
        print(f"[ERROR] schema validation error: {e}")
        return 3

    print("[PASS] schema validation ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
