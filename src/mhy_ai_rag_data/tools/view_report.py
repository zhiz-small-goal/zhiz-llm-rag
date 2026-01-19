#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.view_report

View/render a schema_version=2 report (items model) to:
- console (scroll-friendly: least severe first; summary at end; extra trailing blank line)
- markdown (human entrypoint: summary at top; most severe first; clickable loc via loc_uri)

Recovery mode
- --events: render directly from a jsonl item stream (report.events.jsonl)

Contract highlights
- Sorting uses numeric severity_level (no status_label string ordering).
- Stable ordering within the same severity_level by generation order.
- Paths use '/' separators; loc is pure text; loc_uri is vscode://file/<abs_path>:line:col.
"""

from __future__ import annotations


import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, ensure_report_v2, iso_now
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args
from mhy_ai_rag_data.tools.report_events import iter_items
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output
from mhy_ai_rag_data.tools.report_render import render_console, render_markdown


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "view_report",
    "kind": "RENDER_REPORT",
    "contract_version": 2,
    "channels": ["console", "file"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/view_report.py",
}


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _load_report_from_events(*, root: Path, events_path: Path, tool_default: str) -> Optional[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in iter_items(events_path):
        if not isinstance(raw, dict):
            continue
        items.append(ensure_item_fields(raw, tool_default=tool_default))

    if not items:
        return None

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_default,
        "root": str(root.resolve().as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "data": {
            "events_path": str(events_path.resolve().as_posix()),
        },
    }

    # Normalize paths + enrich loc_uri; keep report structure stable.
    result = prepare_report_for_file_output(report)
    return result if isinstance(result, dict) else None


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="View/render report.json or report.events.jsonl (schema_version=2)")
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--report", default="", help="report.json path (relative to root)")
    ap.add_argument("--events", default="", help="item events jsonl (relative to root); used for recovery/rebuild")
    ap.add_argument("--tool-default", default="report", help="tool name used when rebuilding from events")
    ap.add_argument("--md-out", default="", help="optional markdown output path (relative to root)")

    args = ap.parse_args()

    _repo_root = Path(getattr(args, "root", ".")).resolve()
    _loc = Path(__file__).resolve()
    try:
        _loc = _loc.relative_to(_repo_root)
    except Exception:
        pass

    _rc = maybe_run_selftest_from_args(args=args, meta=REPORT_TOOL_META, repo_root=_repo_root, loc_source=_loc)
    if _rc is not None:
        return _rc

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve() if args.report else None
    events_path = (root / args.events).resolve() if args.events else None

    report: Optional[Dict[str, Any]] = None
    source_path: Optional[Path] = None

    if events_path is not None and args.events:
        report = _load_report_from_events(root=root, events_path=events_path, tool_default=str(args.tool_default))
        source_path = events_path

    if report is None and report_path is not None and args.report:
        raw = _load_json(report_path)
        if raw is not None:
            report = ensure_report_v2(raw)
            source_path = report_path

    if report is None or not isinstance(report, dict) or int(report.get("schema_version") or 0) != 2:
        sp = str(source_path) if source_path else "(none)"
        print(f"[view_report] missing or invalid report: {sp}")
        return 2

    report = prepare_report_for_file_output(report)
    if not isinstance(report, dict):
        print("[view_report] normalize failed")
        return 2

    print(render_console(report, title=str(report.get("tool") or "report")), end="")

    if args.md_out:
        out_path = (root / args.md_out).resolve()
        md = render_markdown(
            report, report_path=(source_path or out_path), root=root, title=str(report.get("tool") or "report")
        )
        _atomic_write_text(out_path, md)
        # informational output: keep stdout reserved for the rendered report
        sys.stderr.write(f"[view_report] wrote markdown: {out_path.as_posix()}\n")
        sys.stderr.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
