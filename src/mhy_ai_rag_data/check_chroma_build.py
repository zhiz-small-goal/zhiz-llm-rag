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
from typing import Any, Dict, List, Optional

from mhy_ai_rag_data.tools.report_contract import ensure_item_fields, ensure_report_v2, status_label_to_severity_level
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output
from mhy_ai_rag_data.tools.report_render import render_console
from mhy_ai_rag_data.tools.reporting import add_error, build_base, status_to_rc, write_report


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


def _mk_item(*, tool: str, title: str, status_label: str, message: str, detail: Any = None) -> Dict[str, Any]:
    it: Dict[str, Any] = {
        "tool": tool,
        "title": title,
        "status_label": status_label,
        "severity_level": status_label_to_severity_level(status_label),
        "message": message,
    }
    if detail is not None:
        it["detail"] = detail
    return ensure_item_fields(it, tool_default=tool)


def _emit_console_v2(*, report: Dict[str, Any], title: str) -> None:
    v2 = ensure_report_v2(report)
    normalized = prepare_report_for_file_output(v2)
    if not isinstance(normalized, dict):
        raise TypeError("prepare_report_for_file_output must return dict for console output")
    print(render_console(normalized, title=title), end="")


def main(
    db_path: Path,
    collection: str,
    expected_chunks: Optional[int],
    plan: Optional[Dict[str, Any]],
    *,
    plan_path: Optional[Path] = None,
    json_out: Optional[str] = None,
    json_stdout: bool = False,
    console_format: str = "v2",
) -> int:
    legacy_console = str(console_format).strip().lower() == "legacy"
    tool_name = "check"

    report = build_base(
        tool_name,
        inputs={
            "db": str(db_path),
            "collection": collection,
            "plan": str(plan_path) if plan_path else None,
            "expected_chunks_override": expected_chunks,
        },
    )
    sample_rows = []
    items: List[Dict[str, Any]] = []

    def p(*args: Any, **kwargs: Any) -> None:
        if legacy_console:
            print(*args, **kwargs)

    p(f"db_path={db_path}")
    p(f"collection={collection}")

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
        p(f"expected_chunks={expected_chunks} (from {expected_from})")
    else:
        p("expected_chunks=None (no strict check)")
    if plan_conf is not None:
        p(f"plan.include_media_stub={plan_conf.get('include_media_stub')}")
        p(f"plan.chunk_conf={plan_conf.get('chunk_conf')}")
        p(
            f"plan.units_read={plan_conf.get('units_read')} units_indexed={plan_conf.get('units_indexed')} units_skipped={plan_conf.get('units_skipped')}"
        )

    items.append(
        _mk_item(
            tool=tool_name,
            title="inputs",
            status_label="INFO",
            message=f"db={db_path.as_posix()} collection={collection} plan={(plan_path.as_posix() if plan_path else '')}",
            detail=dict(report.get("inputs") or {}),
        )
    )
    if expected_chunks is not None:
        items.append(
            _mk_item(
                tool=tool_name,
                title="expected",
                status_label="INFO",
                message=f"expected_chunks={expected_chunks} expected_from={expected_from or ''}",
                detail={"expected_chunks": expected_chunks, "expected_from": expected_from, "plan_conf": plan_conf},
            )
        )
    else:
        items.append(
            _mk_item(
                tool=tool_name,
                title="expected",
                status_label="INFO",
                message="expected_chunks=None (no strict check)",
                detail={"expected_chunks": None, "expected_from": None, "plan_conf": plan_conf},
            )
        )

    # --- open collection ---
    try:
        from chromadb import PersistentClient
    except Exception as e:
        add_error(report, "import", f"cannot import chromadb: {e}")
        p(f"[FATAL] cannot import chromadb: {e}")
        p('[HINT] install optional deps: pip install -e .[embed]  (or pip install ".[embed]" on bash)')
        items.append(
            _mk_item(
                tool=tool_name,
                title="import chromadb",
                status_label="FAIL",
                message="cannot import chromadb",
                detail={
                    "error": repr(e),
                    "hint": 'pip install -e .[embed]  (or pip install ".[embed]" on bash)',
                },
            )
        )
        report["status"] = "FAIL"
        report["items"] = items
        if not legacy_console and not json_stdout:
            _emit_console_v2(report=report, title="check_chroma_build")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
        return status_to_rc(report["status"])

    client = PersistentClient(path=str(db_path))
    try:
        coll = client.get_collection(collection)
    except Exception as e:
        p(f"STATUS: FAIL (cannot open collection) - {e}")
        report["status"] = "FAIL"
        add_error(report, "CANNOT_OPEN_COLLECTION", "cannot open collection", detail=repr(e))
        items.append(
            _mk_item(
                tool=tool_name,
                title="open collection",
                status_label="FAIL",
                message="cannot open collection",
                detail={"collection": collection, "error": repr(e)},
            )
        )
        report["items"] = items
        if not legacy_console and not json_stdout:
            _emit_console_v2(report=report, title="check_chroma_build")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
        return status_to_rc(report["status"])

    try:
        n = coll.count()
    except Exception as e:
        p(f"STATUS: FAIL (cannot read count) - {e}")
        report["status"] = "FAIL"
        add_error(report, "CANNOT_READ_COUNT", "cannot read collection count", detail=repr(e))
        items.append(
            _mk_item(
                tool=tool_name,
                title="read count",
                status_label="FAIL",
                message="cannot read collection.count()",
                detail={"error": repr(e)},
            )
        )
        report["items"] = items
        if not legacy_console and not json_stdout:
            _emit_console_v2(report=report, title="check_chroma_build")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
        return status_to_rc(report["status"])

    p(f"embeddings_in_collection={n}")
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
            p("STATUS: PASS (count matches expected_chunks)")
            report["status"] = "PASS"
            items.append(
                _mk_item(
                    tool=tool_name,
                    title="count check",
                    status_label="PASS",
                    message=f"count matches expected_chunks ({n})",
                    detail={"expected": expected_chunks, "got": n},
                )
            )
        else:
            p(f"STATUS: FAIL (count mismatch; expected={expected_chunks} got={n})")
            report["status"] = "FAIL"
            add_error(report, "COUNT_MISMATCH", "count mismatch", detail={"expected": expected_chunks, "got": n})
            items.append(
                _mk_item(
                    tool=tool_name,
                    title="count check",
                    status_label="FAIL",
                    message=f"count mismatch (expected={expected_chunks} got={n})",
                    detail={"expected": expected_chunks, "got": n},
                )
            )
            # Still print a minimal hint for debugging.
            if plan_conf is not None:
                tb = plan_conf.get("type_breakdown")
                if isinstance(tb, dict):
                    top = sorted(
                        ((k, v.get("chunks", 0)) for k, v in tb.items() if isinstance(v, dict)),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:8]
                    p(f"plan.type_breakdown.top_chunks={top}")
                    report["metrics"]["plan_type_breakdown_top_chunks"] = top
                    items.append(
                        _mk_item(
                            tool=tool_name,
                            title="plan type_breakdown",
                            status_label="INFO",
                            message=f"top_chunks={top}",
                        )
                    )
            report["items"] = items
            if not legacy_console and not json_stdout:
                _emit_console_v2(report=report, title="check_chroma_build")
            _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
            return status_to_rc(report["status"])
    else:
        p("STATUS: INFO (no strict expected; only reporting count)")
        report["status"] = "INFO"
        items.append(
            _mk_item(
                tool=tool_name,
                title="count check",
                status_label="INFO",
                message=f"embeddings_in_collection={n} (no strict expected)",
                detail={"got": n},
            )
        )

    # --- sample records ---
    if n == 0:
        p("Collection is empty, nothing to sample.")
        items.append(
            _mk_item(
                tool=tool_name,
                title="sample",
                status_label="INFO",
                message="collection is empty, nothing to sample",
            )
        )
        report["items"] = items
        if not legacy_console and not json_stdout:
            _emit_console_v2(report=report, title="check_chroma_build")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
        return status_to_rc(report["status"])

    try:
        sample = coll.get(limit=min(5, n))
    except Exception as e:
        p(f"STATUS: WARN (cannot fetch sample documents) - {e}")
        add_error(report, "CANNOT_FETCH_SAMPLE", "cannot fetch sample documents", detail=repr(e))
        items.append(
            _mk_item(
                tool=tool_name,
                title="sample",
                status_label="WARN",
                message="cannot fetch sample documents",
                detail={"error": repr(e)},
            )
        )
        report["items"] = items
        if not legacy_console and not json_stdout:
            _emit_console_v2(report=report, title="check_chroma_build")
        _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)
        return status_to_rc(report["status"])

    ids = sample.get("ids", []) or []
    docs = sample.get("documents", []) or []
    metas = sample.get("metadatas", []) or []

    p("\nSample records:")
    m = min(len(ids), len(docs), len(metas))
    for i in range(m):
        meta = metas[i] or {}
        p(f"- id={ids[i]}")
        p(f"  doc_id={meta.get('doc_id')}")
        p(f"  source_uri={meta.get('source_uri')}")
        p(f"  source_type={meta.get('source_type')}")
        p(f"  locator={meta.get('locator')}")
        p(f"  text_preview={_safe_preview(docs[i])}")
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
        items.append(
            _mk_item(
                tool=tool_name,
                title=f"sample[{i}]",
                status_label="INFO",
                message=f"id={ids[i]} source_type={meta.get('source_type')} source_uri={meta.get('source_uri')}",
                detail=sample_rows[-1],
            )
        )

    report["sample"] = sample_rows
    report["items"] = items
    if not legacy_console and not json_stdout:
        _emit_console_v2(report=report, title="check_chroma_build")
    _emit_report(report, json_out=json_out, json_stdout=json_stdout, emit_wrote_line=legacy_console)

    return status_to_rc(report["status"])


def _emit_report(
    report: Dict[str, Any],
    *,
    json_out: Optional[str],
    json_stdout: bool,
    emit_wrote_line: bool,
) -> None:
    """Only emit a JSON report when requested (avoid creating default files unexpectedly)."""
    normalized: Dict[str, Any] | None = None
    if json_out:
        out_path = write_report(report, json_out=json_out, default_name=f"check_report_{report.get('ts', 0)}.json")
        if emit_wrote_line:
            print(f"Wrote report: {out_path}")
    if json_stdout:
        normalized_any = prepare_report_for_file_output(ensure_report_v2(report))
        if isinstance(normalized_any, dict):
            normalized = normalized_any
        print(json.dumps(normalized or report, ensure_ascii=False, indent=2))
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
    ap.add_argument(
        "--console-format",
        default="v2",
        choices=["v2", "legacy"],
        help="Console output format: v2=render schema_version=2 report; legacy=previous line-based output.",
    )
    ap.add_argument("--json-out", default=None, help="JSON 报告输出路径（提供则写入该文件）")
    ap.add_argument("--json-stdout", action="store_true", help="将 JSON 报告打印到 stdout（不落盘）")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    plan_obj = None
    plan_path = None
    if args.plan:
        plan_path = Path(args.plan).resolve()
        legacy_console = str(getattr(args, "console_format", "v2")).strip().lower() == "legacy"
        if not plan_path.exists():
            if legacy_console:
                print(f"[FATAL] plan not found: {plan_path}")
            # report as FAIL if requested
            rep = build_base(
                "check",
                inputs={"db": str(Path(args.db).resolve()), "collection": args.collection, "plan": str(plan_path)},
            )
            rep["status"] = "FAIL"
            add_error(rep, "PLAN_NOT_FOUND", "plan not found", detail=str(plan_path))
            rep["items"] = [
                _mk_item(
                    tool="check",
                    title="plan",
                    status_label="FAIL",
                    message="plan not found",
                    detail={"plan": plan_path.as_posix()},
                )
            ]
            if not legacy_console and not bool(getattr(args, "json_stdout", False)):
                _emit_console_v2(report=rep, title="check_chroma_build")
            _emit_report(
                rep,
                json_out=str(getattr(args, "json_out", "") or "") or None,
                json_stdout=bool(getattr(args, "json_stdout", False)),
                emit_wrote_line=legacy_console,
            )
            raise SystemExit(status_to_rc(rep["status"]))
        try:
            plan_obj = _load_plan(plan_path)
        except Exception as e:
            if legacy_console:
                print(f"[FATAL] cannot load plan: {e}")
            rep = build_base(
                "check",
                inputs={"db": str(Path(args.db).resolve()), "collection": args.collection, "plan": str(plan_path)},
            )
            rep["status"] = "FAIL"
            add_error(rep, "PLAN_LOAD_FAIL", "cannot load plan", detail=repr(e))
            rep["items"] = [
                _mk_item(
                    tool="check",
                    title="plan",
                    status_label="FAIL",
                    message="cannot load plan",
                    detail={"plan": plan_path.as_posix(), "error": repr(e)},
                )
            ]
            if not legacy_console and not bool(getattr(args, "json_stdout", False)):
                _emit_console_v2(report=rep, title="check_chroma_build")
            _emit_report(
                rep,
                json_out=str(getattr(args, "json_out", "") or "") or None,
                json_stdout=bool(getattr(args, "json_stdout", False)),
                emit_wrote_line=legacy_console,
            )
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
            console_format=str(getattr(args, "console_format", "v2")),
        )
    )
