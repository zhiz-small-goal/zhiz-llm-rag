#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.checkpoint_utils

Minimal checkpoint helpers for "high_cost" tools.

Contract goals
- checkpoint is a single JSON object written atomically (tmp then rename).
- file must be valid JSON even if the process is interrupted between updates.
- newline normalized to '\n' for diff/CI stability.

This module intentionally has no third-party deps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    """Atomically write JSON to `path`.

    Implementation
    - write to sibling temporary file (same directory)
    - fsync is not forced here; callers that require stronger durability should
      fsync at a higher level (e.g., events writer durability_mode=fsync).
    """

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp.write_text(data, encoding="utf-8", newline="\n")
    tmp.replace(path)


def read_json(path: Path) -> Dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
