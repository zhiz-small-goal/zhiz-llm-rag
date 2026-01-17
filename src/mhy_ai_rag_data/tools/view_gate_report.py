#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.view_gate_report

Render a schema_version=2 gate report (items model) to:
- console (scroll-friendly: least severe first; summary at end; extra trailing blank line)
- markdown (human entrypoint: summary at top; most severe first; clickable loc via loc_uri)

Recovery mode
- --events: render directly from a jsonl item stream (report.events.jsonl) to rebuild markdown/console

Contract highlights
- Sorting uses numeric `severity_level` (no status_label string ordering).
- Stable ordering: within the same severity_level, preserve generation order.
- Markdown paths and VS Code links use '/' separators; loc stays pure text, loc_uri is vscode://file/... absolute.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_events import iter_items
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output
from mhy_ai_rag_data.tools.vscode_links import normalize_abs_path_posix, to_vscode_file_uri_from_path


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _load_report_from_events(*, root: Path, events_path: Path) -> Optional[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in iter_items(events_path):
        if not isinstance(raw, dict):
            continue
        items.append(ensure_item_fields(raw, tool_default="rag-gate"))

    if not items:
        return None

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": "rag-gate",
        "root": str(root.resolve().as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "data": {
            "events_path": str(events_path.resolve().as_posix()),
        },
    }

    # Normalize paths + enrich loc_uri for markdown; keep report structure stable.
    return prepare_report_for_file_output(report)


def _stable_sorted_items(report: Dict[str, Any], *, reverse: bool) -> List[Tuple[int, int, Dict[str, Any]]]:
    """Return items decorated with (severity_level, generation_index, item) sorted stably.

    Contract:
    - Primary key: numeric severity_level.
    - Stability: within the same severity_level, preserve generation order (idx asc).

    reverse=False  => low->high (console)
    reverse=True   => high->low (markdown)
    """

    items = report.get("items") or []
    out: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        sev = it.get("severity_level")
        try:
            sev_i = int(sev) if sev is not None else 1
        except (ValueError, TypeError):
            sev_i = 1
        out.append((sev_i, idx, it))

    if reverse:
        out.sort(key=lambda t: (-t[0], t[1]))
    else:
        out.sort(key=lambda t: (t[0], t[1]))
    return out


def _counts_by_severity(items: List[Dict[str, Any]]) -> Dict[int, Dict[str, int]]:
    """Return sev -> {STATUS_LABEL -> count}."""

    out: Dict[int, Dict[str, int]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            sev = int(it.get("severity_level", 1))
        except Exception:
            sev = 1
        lab = str(it.get("status_label") or "INFO").upper()
        out.setdefault(sev, {})[lab] = out.setdefault(sev, {}).get(lab, 0) + 1
    return out


def _sev_bucket_lines(sev_map: Dict[int, Dict[str, int]], *, order: str) -> List[str]:
    """Format severity buckets.

    order: asc|desc
    """

    sevs = sorted(sev_map.keys(), reverse=(order == "desc"))
    lines: List[str] = []
    for sev in sevs:
        lab_counts = sev_map.get(sev) or {}
        total = sum(int(v) for v in lab_counts.values())
        # show stable label order within bucket: by label name
        parts = [f"{k}={lab_counts[k]}" for k in sorted(lab_counts.keys())]
        detail = (" " + " ".join(parts)) if parts else ""
        lines.append(f"- sev={sev}: {total}{detail}")
    return lines


def _render_console(report: Dict[str, Any]) -> str:
    root = str(report.get("root") or "")
    gen = str(report.get("generated_at") or "")
    summ = report.get("summary") or {}

    items_raw = report.get("items") or []
    items: List[Dict[str, Any]] = [it for it in items_raw if isinstance(it, dict)]

    lines: List[str] = []
    lines.append("# gate report")
    lines.append(f"root: {root}")
    lines.append(f"generated_at: {gen}")
    lines.append("")

    lines.append("## details (most severe last)")

    sorted_items = _stable_sorted_items(report, reverse=False)
    prev_sev: Optional[int] = None
    first = True
    for sev, _idx, it in sorted_items:
        if not first:
            # spacing contract:
            # - 1 empty line between items
            # - 2 empty lines between severity groups
            lines.append("")
            if prev_sev is not None and sev != prev_sev:
                lines.append("")
        first = False
        prev_sev = sev

        title = str(it.get("title") or "")
        status = str(it.get("status_label") or "INFO")
        msg = str(it.get("message") or "")

        lines.append(f"- [{status}] (sev={sev}) {title}")
        if msg:
            lines.append(f"  - {msg}")

        # loc (pure text) or list[str]
        loc = it.get("loc")
        loc_uri = it.get("loc_uri")
        if isinstance(loc, str) and loc.strip():
            if isinstance(loc_uri, str) and loc_uri.strip():
                lines.append(f"  - loc: {loc} ({loc_uri})")
            else:
                lines.append(f"  - loc: {loc}")
        elif isinstance(loc, list) and loc:
            lines.append("  - loc:")
            for i, loc_i in enumerate(loc[:5]):
                if not isinstance(loc_i, str) or not loc_i.strip():
                    continue
                uri_i = ""
                if isinstance(loc_uri, list) and i < len(loc_uri) and isinstance(loc_uri[i], str):
                    uri_i = loc_uri[i]
                if uri_i:
                    lines.append(f"    - {loc_i} ({uri_i})")
                else:
                    lines.append(f"    - {loc_i}")

        # common gate detail: log path
        det = it.get("detail")
        if isinstance(det, dict):
            lp = det.get("log_path")
            if isinstance(lp, str) and lp.strip():
                lines.append(f"  - log: {lp}")

    # summary at the end
    lines.append("")
    lines.append("## summary")

    overall = str(summ.get("overall_status_label") or "")
    overall_rc = summ.get("overall_rc")
    max_sev = summ.get("max_severity_level")
    total_items = summ.get("total_items")

    lines.append(f"overall: {overall} rc={overall_rc} max_sev={max_sev} total_items={total_items}")

    sev_map = _counts_by_severity(items)
    lines.append("counts_by_severity (low->high):")
    lines.extend(_sev_bucket_lines(sev_map, order="asc"))

    # must end with an extra blank line for prompt separation ("\n\n")
    lines.append("")
    return "\n".join(lines) + "\n"


def _md_link(text: str, uri: str) -> str:
    if not uri:
        return text
    return f"[{text}]({uri})"


def _render_markdown(report: Dict[str, Any], *, report_path: Path, root: Path) -> str:
    summ = report.get("summary") or {}
    items_raw = report.get("items") or []
    items: List[Dict[str, Any]] = [it for it in items_raw if isinstance(it, dict)]

    lines: List[str] = []
    lines.append("---")
    lines.append("title: gate_report.md (derived)")
    lines.append("version: v1")
    lines.append(f"generated_at: {report.get('generated_at')}")
    lines.append("---")
    lines.append("")
    lines.append("# Gate report")
    lines.append("")

    # summary must be at top
    lines.append("## Summary")
    lines.append("")

    overall = str(summ.get("overall_status_label") or "")
    overall_rc = summ.get("overall_rc")
    max_sev = summ.get("max_severity_level")
    total_items = summ.get("total_items")

    lines.append(f"- overall: **{overall}** (rc={overall_rc})")
    lines.append(f"- max_severity_level: {max_sev}")
    lines.append(f"- total_items: {total_items}")

    # clickable paths
    rp_abs = report_path.resolve()
    rp_uri = to_vscode_file_uri_from_path(rp_abs)
    lines.append(f"- report_source: {_md_link(normalize_abs_path_posix(str(rp_abs.as_posix())), rp_uri)}")

    # severity-sorted counts for markdown (high->low)
    sev_map = _counts_by_severity(items)
    lines.append("- counts_by_severity (high->low):")
    for line in _sev_bucket_lines(sev_map, order="desc"):
        lines.append(f"  {line}")

    # show gate_logs_dir if present
    data = report.get("data")
    if isinstance(data, dict):
        gld = data.get("gate_logs_dir")
        if isinstance(gld, str) and gld.strip():
            gld_abs = Path(gld)
            try:
                if not gld_abs.is_absolute():
                    gld_abs = (root / gld_abs).resolve()
            except Exception:
                pass
            gld_uri = to_vscode_file_uri_from_path(gld_abs)
            lines.append(f"- gate_logs_dir: {_md_link(normalize_abs_path_posix(str(gld_abs.as_posix())), gld_uri)}")

    # optional: events_path (recovery)
    if isinstance(data, dict) and data.get("events_path"):
        ev_abs = Path(str(data.get("events_path"))).resolve()
        ev_uri = to_vscode_file_uri_from_path(ev_abs)
        lines.append(f"- report_events: {_md_link(normalize_abs_path_posix(str(ev_abs.as_posix())), ev_uri)}")

    lines.append("")

    # details: most severe first
    lines.append("## Details (most severe first)")
    lines.append("")

    sorted_items = _stable_sorted_items(report, reverse=True)
    for sev, _idx, it in sorted_items:
        title = str(it.get("title") or "")
        status = str(it.get("status_label") or "INFO")
        msg = str(it.get("message") or "")

        lines.append(f"### [{status}] (sev={sev}) {title}")
        lines.append("")
        if msg:
            lines.append(msg)
            lines.append("")

        loc = it.get("loc")
        loc_uri = it.get("loc_uri")
        if isinstance(loc, str) and loc.strip():
            uri = loc_uri if isinstance(loc_uri, str) else ""
            lines.append(f"- loc: {_md_link(loc, uri)}")
        elif isinstance(loc, list) and loc:
            lines.append("- loc:")
            for i, loc_i in enumerate(loc[:10]):
                if not isinstance(loc_i, str) or not loc_i.strip():
                    continue
                uri_i = ""
                if isinstance(loc_uri, list) and i < len(loc_uri) and isinstance(loc_uri[i], str):
                    uri_i = loc_uri[i]
                lines.append(f"  - {_md_link(loc_i, uri_i)}")

        det = it.get("detail")
        if isinstance(det, dict):
            lp = det.get("log_path")
            if isinstance(lp, str) and lp.strip():
                lp_abs = Path(lp)
                try:
                    if not lp_abs.is_absolute():
                        lp_abs = (root / lp_abs).resolve()
                except Exception:
                    pass
                lp_uri = to_vscode_file_uri_from_path(lp_abs)
                lines.append(f"- log: {_md_link(normalize_abs_path_posix(str(lp_abs.as_posix())), lp_uri)}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="View/render gate_report.json or gate_report.events.jsonl")
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument(
        "--report",
        default="data_processed/build_reports/gate_report.json",
        help="gate_report.json path (relative to root)",
    )
    ap.add_argument(
        "--events",
        default="",
        help="optional: item events jsonl to render (relative to root); used for recovery/rebuild",
    )
    ap.add_argument("--md-out", default="", help="optional markdown output path (relative to root)")

    args = ap.parse_args()

    root = Path(args.root).resolve()

    report_path = (root / args.report).resolve() if args.report else None
    events_path = (root / args.events).resolve() if args.events else None

    report: Optional[Dict[str, Any]] = None
    source_path: Optional[Path] = None

    if events_path is not None:
        report = _load_report_from_events(root=root, events_path=events_path)
        source_path = events_path

    if report is None and report_path is not None:
        report = _load_json(report_path)
        source_path = report_path

    if report is None or not isinstance(report, dict) or report.get("schema_version") != 2:
        sp = str(source_path) if source_path else "(none)"
        print(f"[gate_report] missing or invalid report: {sp}")
        return 2

    # Normalize paths/order/loc/loc_uri for consistent rendering
    report = prepare_report_for_file_output(report)

    # console output
    print(_render_console(report), end="")

    # markdown optional
    if args.md_out:
        out_path = (root / args.md_out).resolve()
        md = _render_markdown(report, report_path=(source_path or out_path), root=root)
        _atomic_write_text(out_path, md)
        print(f"[gate_report] wrote markdown: {out_path.as_posix()}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
