#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_chroma_build.py

目的
----
对已构建的 Chroma collection 做“可追溯”的后置验收，避免仅靠手填 expected_chunks 引发误报。

验收口径（优先级）
------------------
1) 若提供 --plan（chunk_plan.json），则以计划报告中的 planned_chunks 作为唯一 expected。
2) 否则若提供 --expected-chunks > 0，则以 expected-chunks 作为 expected（覆盖值；低可信）。
3) 否则仅报告 count / 抽样，不做强校验。

退出码
------
0：PASS 或 INFO
2：FAIL（强校验不通过 / collection 不可读）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from mhy_ai_rag_data.tools.reporting import build_base, add_error, status_to_rc, write_report


def _extract_plan_obj(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # v1 shape (legacy): {"planned_chunks": int, ...}
    if isinstance(obj.get("planned_chunks"), int):
        return obj

    # v2 report-bundle shape (current): {"schema_version": 2, ..., "data": {...planned_chunks...}}
    data = obj.get("data")
    if isinstance(data, dict) and isinstance(data.get("planned_chunks"), int):
        return data

    # Defensive fallback: some tools may embed the payload under items[].detail.
    items = obj.get("items")
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            detail = it.get("detail")
            if isinstance(detail, dict) and isinstance(detail.get("planned_chunks"), int):
                return detail

    return None


def _load_plan(plan_path: Path) -> Dict[str, Any]:
    obj = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("plan is not a json object")
    plan = _extract_plan_obj(obj)
    if plan is None:
        raise ValueError("plan missing planned_chunks (supported: planned_chunks or data.planned_chunks)")
    return plan


def _safe_preview(s: str, n: int = 160) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else (s[:n] + "...")


def main(
    db_path: Path,
    collection: str,
    expected_chunks: Optional[int],
    plan: Optional[Dict[str, Any]],
    *,
    plan_path: Optional[Path] = None,
    json_out: Optional[str] = None,
    json_stdout: bool = False,
) -> int:
    report = build_base(
        "check",
        inputs={
            "db": str(db_path),
            "collection": collection,
            "plan": str(plan_path) if plan_path else None,
            "expected_chunks_override": expected_chunks,
        },
    )
    sample_rows = []
    print(f"db_path={db_path}")
    print(f"collection={collection}")

    # --- expected policy ---
    expected_from = None
    plan_conf = None
    if plan is not None:
        planned = plan.get("planned_chunks")
        if planned is None:
            raise ValueError("plan missing planned_chunks")
        expected_chunks = int(planned)
        expected_from = f"plan:{plan_path}" if plan_path else "plan:chunk_plan.json"
        plan_conf = {
            "include_media_stub": plan.get("include_media_stub"),
            "chunk_conf": plan.get("chunk_conf"),
            "units_read": plan.get("units_read"),
            "units_indexed": plan.get("units_indexed"),
            "units_skipped": plan.get("units_skipped"),
            "type_breakdown": plan.get("type_breakdown"),
        }
    elif expected_chunks is not None:
        expected_from = "override:--expected-chunks"

    if expected_chunks is not None:
        print(f"expected_chunks={expected_chunks} (from {expected_from})")
    else:
        print("expected_chunks=None (no strict check)")
    if plan_conf is not None:
        print(f"plan.include_media_stub={plan_conf.get('include_media_stub')}")
        print(f"plan.chunk_conf={plan_conf.get('chunk_conf')}")
        print(
            f"plan.units_read={plan_conf.get('units_read')} units_indexed={plan_conf.get('units_indexed')} units_skipped={plan_conf.get('units_skipped')}"
        )

    # --- open collection ---
    try:
        from chromadb import PersistentClient
    except Exception as e:
        add_error(report, "import", f"cannot import chromadb: {e}")
        print(f"[FATAL] cannot import chromadb: {e}")
        print('[HINT] install optional deps: pip install -e .[embed]  (or pip install ".[embed]" on bash)')
        report["status"] = "FAIL"
        return status_to_rc(report["status"])

    client = PersistentClient(path=str(db_path))
    try:
        coll = client.get_collection(collection)
    except Exception as e:
        print(f"STATUS: FAIL (cannot open collection) - {e}")
        report["status"] = "FAIL"
        add_error(report, "CANNOT_OPEN_COLLECTION", "cannot open collection", detail=repr(e))
        _emit_report(report, json_out=json_out, json_stdout=json_stdout)
        return status_to_rc(report["status"])

    try:
        n = coll.count()
    except Exception as e:
        print(f"STATUS: FAIL (cannot read count) - {e}")
        report["status"] = "FAIL"
        add_error(report, "CANNOT_READ_COUNT", "cannot read collection count", detail=repr(e))
        _emit_report(report, json_out=json_out, json_stdout=json_stdout)
        return status_to_rc(report["status"])

    print(f"embeddings_in_collection={n}")
    report["metrics"].update(
        {
            "expected_chunks": expected_chunks,
            "expected_from": expected_from,
            "embeddings_in_collection": n,
            "plan_conf": plan_conf,
        }
    )

    # --- strict check (if expected provided) ---
    if expected_chunks is not None:
        if n == expected_chunks:
            print("STATUS: PASS (count matches expected_chunks)")
            report["status"] = "PASS"
        else:
            print(f"STATUS: FAIL (count mismatch; expected={expected_chunks} got={n})")
            report["status"] = "FAIL"
            add_error(report, "COUNT_MISMATCH", "count mismatch", detail={"expected": expected_chunks, "got": n})
            # Still print a minimal hint for debugging.
            if plan_conf is not None:
                tb = plan_conf.get("type_breakdown")
                if isinstance(tb, dict):
                    top = sorted(
                        ((k, v.get("chunks", 0)) for k, v in tb.items() if isinstance(v, dict)),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:8]
                    print(f"plan.type_breakdown.top_chunks={top}")
                    report["metrics"]["plan_type_breakdown_top_chunks"] = top
            _emit_report(report, json_out=json_out, json_stdout=json_stdout)
            return status_to_rc(report["status"])
    else:
        print("STATUS: INFO (no strict expected; only reporting count)")
        report["status"] = "INFO"

    # --- sample records ---
    if n == 0:
        print("Collection is empty, nothing to sample.")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout)
        return status_to_rc(report["status"])

    try:
        sample = coll.get(limit=min(5, n))
    except Exception as e:
        print(f"STATUS: WARN (cannot fetch sample documents) - {e}")
        add_error(report, "CANNOT_FETCH_SAMPLE", "cannot fetch sample documents", detail=repr(e))
        _emit_report(report, json_out=json_out, json_stdout=json_stdout)
        return status_to_rc(report["status"])

    ids = sample.get("ids", []) or []
    docs = sample.get("documents", []) or []
    metas = sample.get("metadatas", []) or []

    print("\nSample records:")
    m = min(len(ids), len(docs), len(metas))
    for i in range(m):
        meta = metas[i] or {}
        print(f"- id={ids[i]}")
        print(f"  doc_id={meta.get('doc_id')}")
        print(f"  source_uri={meta.get('source_uri')}")
        print(f"  source_type={meta.get('source_type')}")
        print(f"  locator={meta.get('locator')}")
        print(f"  text_preview={_safe_preview(docs[i])}")
        sample_rows.append(
            {
                "id": ids[i],
                "doc_id": meta.get("doc_id"),
                "source_uri": meta.get("source_uri"),
                "source_type": meta.get("source_type"),
                "locator": meta.get("locator"),
                "text_preview": _safe_preview(docs[i]),
            }
        )

    report["sample"] = sample_rows
    _emit_report(report, json_out=json_out, json_stdout=json_stdout)

    return status_to_rc(report["status"])


def _emit_report(report: Dict[str, Any], *, json_out: Optional[str], json_stdout: bool) -> None:
    """Only emit a JSON report when requested (avoid creating default files unexpectedly)."""
    if json_out:
        out_path = write_report(report, json_out=json_out, default_name=f"check_report_{report.get('ts', 0)}.json")
        print(f"Wrote report: {out_path}")
    if json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    # If neither json_out nor json_stdout is provided, do nothing.


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Check a built Chroma collection with plan-driven expected_chunks.")
    ap.add_argument("--db", default="chroma_db", help="Path to Chroma persistent directory")
    ap.add_argument("--collection", default="rag_chunks", help="Collection name")
    ap.add_argument(
        "--plan",
        default=None,
        help="Path to chunk_plan.json (generated by tools/plan_chunks_from_units.py). If provided, overrides expected.",
    )
    ap.add_argument(
        "--expected-chunks",
        type=int,
        default=0,
        help="Legacy override expected chunks; set to 0 to disable. Ignored if --plan is provided.",
    )
    ap.add_argument("--json-out", default=None, help="JSON 报告输出路径（提供则写入该文件）")
    ap.add_argument("--json-stdout", action="store_true", help="将 JSON 报告打印到 stdout（不落盘）")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    plan_obj = None
    plan_path = None
    if args.plan:
        plan_path = Path(args.plan).resolve()
        if not plan_path.exists():
            print(f"[FATAL] plan not found: {plan_path}")
            # report as FAIL if requested
            rep = build_base(
                "check",
                inputs={"db": str(Path(args.db).resolve()), "collection": args.collection, "plan": str(plan_path)},
            )
            rep["status"] = "FAIL"
            add_error(rep, "PLAN_NOT_FOUND", "plan not found", detail=str(plan_path))
            if args.json_out:
                out_path = write_report(
                    rep, json_out=args.json_out, default_name=f"check_report_{rep.get('ts', 0)}.json"
                )
                print(f"Wrote report: {out_path}")
            if args.json_stdout:
                print(json.dumps(rep, ensure_ascii=False, indent=2))
            raise SystemExit(status_to_rc(rep["status"]))
        try:
            plan_obj = _load_plan(plan_path)
        except Exception as e:
            print(f"[FATAL] cannot load plan: {e}")
            rep = build_base(
                "check",
                inputs={"db": str(Path(args.db).resolve()), "collection": args.collection, "plan": str(plan_path)},
            )
            rep["status"] = "FAIL"
            add_error(rep, "PLAN_LOAD_FAIL", "cannot load plan", detail=repr(e))
            if args.json_out:
                out_path = write_report(
                    rep, json_out=args.json_out, default_name=f"check_report_{rep.get('ts', 0)}.json"
                )
                print(f"Wrote report: {out_path}")
            if args.json_stdout:
                print(json.dumps(rep, ensure_ascii=False, indent=2))
            raise SystemExit(status_to_rc(rep["status"]))

    expected = None if args.expected_chunks <= 0 else int(args.expected_chunks)
    raise SystemExit(
        main(
            db_path=db,
            collection=args.collection,
            expected_chunks=expected,
            plan=plan_obj,
            plan_path=plan_path,
            json_out=args.json_out,
            json_stdout=args.json_stdout,
        )
    )
