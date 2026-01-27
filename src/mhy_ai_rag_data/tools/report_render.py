#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_render

Generic renderer for schema_version=2 reports (items model).

Console contract (stdout):
- detail: severity_level low -> high (most severe last)
- summary printed at the end
- extra trailing blank line (overall ends with "\n\n")
- stable ordering within the same severity_level by generation order

Markdown contract (.md as human entrypoint):
- summary at top
- details ordered severity_level high -> low
- location rendered as clickable Markdown links: [loc](loc_uri)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mhy_ai_rag_data.tools.report_contract import compute_summary
from mhy_ai_rag_data.tools.vscode_links import normalize_abs_path_posix, to_vscode_file_uri_from_path


def _stable_sorted_items(report: Dict[str, Any], *, reverse: bool) -> List[Tuple[int, int, Dict[str, Any]]]:
    """Return (severity_level, generation_index, item) sorted stably."""

    raw = report.get("items") or []
    out: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, it in enumerate(raw):
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
    sevs = sorted(sev_map.keys(), reverse=(order == "desc"))
    lines: List[str] = []
    for sev in sevs:
        lab_counts = sev_map.get(sev) or {}
        total = sum(int(v) for v in lab_counts.values())
        parts = [f"{k}={lab_counts[k]}" for k in sorted(lab_counts.keys())]
        detail = (" " + " ".join(parts)) if parts else ""
        lines.append(f"- sev={sev}: {total}{detail}")
    return lines


def _md_link(text: str, uri: str) -> str:
    if not uri:
        return text
    return f"[{text}]({uri})"


def render_console(report: Dict[str, Any], *, title: str = "report") -> str:
    """Render report to a scroll-friendly console string.

    The returned string ends with "\n\n".
    """

    root = str(report.get("root") or "")
    gen = str(report.get("generated_at") or "")
    summ = report.get("summary") or {}

    items_raw = report.get("items") or []
    items: List[Dict[str, Any]] = [it for it in items_raw if isinstance(it, dict)]

    lines: List[str] = []
    lines.append(f"# {title}")
    if root:
        lines.append(f"root: {root}")
    lines.append("")

    lines.append("## details (most severe last)")

    sorted_items = _stable_sorted_items(report, reverse=False)
    prev_sev: Optional[int] = None
    first = True

    for sev, _idx, it in sorted_items:
        # spacing contract:
        # - 1 empty line between items
        # - 2 empty lines between severity groups
        if not first:
            lines.append("")
            if prev_sev is not None and sev != prev_sev:
                lines.append("")
        first = False
        prev_sev = sev

        title_s = str(it.get("title") or "")
        status = str(it.get("status_label") or "INFO")
        msg = str(it.get("message") or "")

        lines.append(f"- [{status}] (sev={sev}) {title_s}")
        if msg:
            lines.append(f"  - {msg}")

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
                lines.append(f"    - {loc_i}" + (f" ({uri_i})" if uri_i else ""))

    lines.append("")
    lines.append("## summary")

    overall = str(summ.get("overall_status_label") or "")
    overall_rc = summ.get("overall_rc")
    max_sev = summ.get("max_severity_level")
    total_items = summ.get("total_items")

    lines.append(f"overall: {overall} rc={overall_rc} max_sev={max_sev} total_items={total_items}")

    # counts_by_severity (low->high)
    sev_map = _counts_by_severity(items)
    lines.append("counts_by_severity (low->high):")
    lines.extend(_sev_bucket_lines(sev_map, order="asc"))
    lines.append("")

    metrics = summ.get("metrics") if isinstance(summ, dict) else None
    if isinstance(metrics, dict) and metrics:
        lines.append("metrics:")
        for k in sorted(metrics.keys()):
            lines.append(f"- {k}: {metrics[k]}")
        lines.append("")

    # generated_at metadata (after summary)
    if gen:
        lines.append(f"generated_at: {gen}")

    # must end with an extra blank line for prompt separation ("\n\n")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_markdown(
    report: Dict[str, Any],
    *,
    report_path: Path,
    root: Path,
    title: str = "Report",
) -> str:
    """Render report to markdown.

    - Summary at top
    - Details: most severe first
    - loc rendered as [loc](loc_uri)
    """

    items_raw = report.get("items") or []
    items: List[Dict[str, Any]] = [it for it in items_raw if isinstance(it, dict)]

    summ = report.get("summary")
    if not isinstance(summ, dict):
        summ = compute_summary(items).to_dict()

    lines: List[str] = []
    lines.append("---")
    lines.append(f"title: {title}")
    lines.append("schema_version: 2")
    lines.append(f"generated_at: {report.get('generated_at')}")
    lines.append("---")
    lines.append("")

    lines.append(f"# {title}")
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

    # clickable report path
    rp_abs = report_path.resolve()
    rp_uri = to_vscode_file_uri_from_path(rp_abs)
    lines.append(f"- report_source: {_md_link(normalize_abs_path_posix(rp_abs.as_posix()), rp_uri)}")

    sev_map = _counts_by_severity(items)
    lines.append("- counts_by_severity (high->low):")
    for line in _sev_bucket_lines(sev_map, order="desc"):
        lines.append(f"  {line}")

    metrics = summ.get("metrics") if isinstance(summ, dict) else None
    if isinstance(metrics, dict) and metrics:
        lines.append("- metrics:")
        for k in sorted(metrics.keys()):
            lines.append(f"  - {k}: {metrics[k]}")

    lines.append("")

    # details: most severe first
    lines.append("## Details (most severe first)")
    lines.append("")

    sorted_items = _stable_sorted_items(report, reverse=True)
    for sev, _idx, it in sorted_items:
        title_s = str(it.get("title") or "")
        status = str(it.get("status_label") or "INFO")
        msg = str(it.get("message") or "")

        lines.append(f"### [{status}] (sev={sev}) {title_s}")
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

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
