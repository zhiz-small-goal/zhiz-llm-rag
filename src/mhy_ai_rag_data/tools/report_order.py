#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_order

目标
----
为“落盘报告（JSON）”提供统一的**人类可读顺序**：

1) 报告顶部优先出现“汇总块”（如 summary/metrics/counts/totals）。
2) 明细列表（如 results/cases/items）在落盘时优先把 FAIL/ERROR 放前、PASS 放后。

说明
----
- 该模块只做**序列化顺序**调整：不改变字段语义；JSON 仍是合法对象。
- 仅用于“写文件”的 report（控制台输出的排序策略在另一个需求中处理）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


# --- ordering knobs (file output) ---

# 认为是“汇总块”的 key：放到最前面（若存在）
SUMMARY_KEYS: Tuple[str, ...] = (
    "summary",
    "metrics",
    "buckets",
    "counts",
    "totals",
)

# 常见明细列表 key：这些 key 下的 list（若元素可判定 PASS/FAIL/ERROR）会被排序
DETAIL_LIST_KEYS: Tuple[str, ...] = (
    "results",
    "cases",
    "items",
    "checks",
)


STATUS_RANK_FILE: Dict[str, int] = {
    # 最严重放最前
    "ERROR": 0,
    "ERR": 0,
    "EXCEPTION": 0,
    "FAIL": 1,
    "FAILED": 1,
    "MISS": 1,
    "STALE": 1,
    "WARN": 2,
    "WARNING": 2,
    "SKIP": 3,
    "SKIPPED": 3,
    "PASS": 4,
    "OK": 4,
    "INFO": 5,
}


def _norm_status(s: Any) -> str:
    return str(s or "").strip().upper()


def _rank_from_status(d: Mapping[str, Any]) -> Optional[int]:
    if "status" in d:
        return STATUS_RANK_FILE.get(_norm_status(d.get("status")))
    return None


def _rank_from_common_bools(d: Mapping[str, Any]) -> Optional[int]:
    """Heuristics for case-like entries.

    - eval_rag: passed / error / error_detail / llm_call_ok
    - eval_retrieval: hit_at_k
    """
    if "passed" in d:
        # error first
        if d.get("error") or d.get("error_detail") or (d.get("llm_call_ok") is False):
            return STATUS_RANK_FILE["ERROR"]
        if d.get("passed") is False:
            return STATUS_RANK_FILE["FAIL"]
        if d.get("passed") is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    if "hit_at_k" in d:
        v = d.get("hit_at_k")
        if v is False:
            return STATUS_RANK_FILE["FAIL"]
        if v is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    if "ok" in d:
        v = d.get("ok")
        if v is False:
            return STATUS_RANK_FILE["FAIL"]
        if v is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    return None


def _rank_item(d: Mapping[str, Any]) -> Optional[int]:
    r = _rank_from_status(d)
    if r is not None:
        return r
    return _rank_from_common_bools(d)


def _should_sort_list(xs: List[Any]) -> bool:
    if not xs:
        return False
    # only attempt when most elements are dict-like
    ds = [x for x in xs if isinstance(x, Mapping)]
    if not ds:
        return False
    ranked = [d for d in ds if _rank_item(d) is not None]
    # allow partial lists but require strong signal
    return len(ranked) >= max(3, int(0.6 * len(ds)))


def _sort_list_for_file(xs: List[Any]) -> List[Any]:
    if not _should_sort_list(xs):
        return xs

    # stable sort: keep original order for same rank / unranked
    decorated: List[Tuple[int, int, Any]] = []
    for i, x in enumerate(xs):
        if isinstance(x, Mapping):
            r = _rank_item(x)
        else:
            r = None
        decorated.append(((r if r is not None else 999), i, x))
    decorated.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in decorated]


def _reorder_dict_keys_for_file(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict whose key order is tuned for human reading in file."""
    out: Dict[str, Any] = {}

    # 1) summary-like blocks first
    for k in SUMMARY_KEYS:
        if k in d:
            out[k] = d[k]

    # 2) top-level status/errors early if present
    for k in ("status", "overall_status", "errors"):
        if k in d and k not in out:
            out[k] = d[k]

    # 3) rest preserve original insertion order
    for k, v in d.items():
        if k in out:
            continue
        out[k] = v
    return out


def _rank_mapping_value(v: Any) -> Optional[int]:
    """Rank a mapping entry by severity (lower is more severe).

    This is used for dicts that behave like a set of check items, e.g.
    {"check_a": {"status": "FAIL"}, "check_b": {"status": "PASS"}}.
    """
    if not isinstance(v, Mapping):
        return None

    # 1) explicit status fields
    for key in ("status", "overall", "overall_status"):
        s = v.get(key)
        if isinstance(s, str):
            return STATUS_RANK_FILE.get(s.upper(), 500)

    # 2) boolean ok / passed / hit_at_k
    b = _rank_from_common_bools(v)
    if b is not None:
        return b
    return None


def _should_sort_mapping(d: Dict[str, Any]) -> bool:
    if len(d) < 3:
        return False
    ranked = [1 for v in d.values() if _rank_mapping_value(v) is not None]
    return len(ranked) >= max(2, int(0.6 * len(d)))


def _sort_mapping_by_value_severity(d: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder mapping entries by severity when it looks like a check-map."""
    if not _should_sort_mapping(d):
        return d

    decorated: List[Tuple[int, int, str, Any]] = []
    for i, (k, v) in enumerate(d.items()):
        r = _rank_mapping_value(v)
        decorated.append(((r if r is not None else 999), i, k, v))
    decorated.sort(key=lambda t: (t[0], t[1]))

    out: Dict[str, Any] = {}
    for _, _, k, v in decorated:
        out[k] = v
    return out


def prepare_report_for_file_output(obj: Any) -> Any:
    """Normalize an object for file report output.

    - Reorder dict keys (summary-like first)
    - Sort known detail lists when items are rankable
    - Recurse into nested dict/list
    """
    if isinstance(obj, list):
        xs = [_prepare_any(x) for x in obj]
        return _sort_list_for_file(xs)
    if isinstance(obj, dict):
        # recurse first, then reorder/sort
        d2: Dict[str, Any] = {}
        for k, v in obj.items():
            d2[k] = _prepare_any(v)

        # sort common detail lists by severity
        for lk in DETAIL_LIST_KEYS:
            if lk in d2 and isinstance(d2[lk], list):
                d2[lk] = _sort_list_for_file(d2[lk])

        # For dicts that behave like a set of checks, order by value severity.
        d3 = _sort_mapping_by_value_severity(d2)

        return _reorder_dict_keys_for_file(d3)
    return obj


def _prepare_any(x: Any) -> Any:
    return prepare_report_for_file_output(x)


def write_json_report(path: Path, report: Any) -> None:
    """Write a JSON report to file with normalized ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = prepare_report_for_file_output(report)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
