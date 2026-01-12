#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a human-readable summary from gate_report.json."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


def clip(text: str, limit: int = 120) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument(
        "--report",
        default="data_processed/build_reports/gate_report.json",
        help="gate_report.json path (relative to root)",
    )
    ap.add_argument("--md-out", default="", help="optional markdown output path")
    ap.add_argument("--max-findings", type=int, default=8, help="max findings per step to show")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve()

    report = read_json(report_path)
    if report is None:
        print(f"[gate_report] FAIL: missing or invalid report: {report_path}")
        return 2

    summary = report.get("summary") or {}
    counts = summary.get("counts") or {}
    results = report.get("results") or []
    warnings = report.get("warnings") or []

    lines: List[str] = []
    lines.append("# Gate report summary\n\n")
    lines.append(f"- generated_at: `{report.get('generated_at', '')}`\n")
    lines.append(f"- root: `{report.get('root', '')}`\n")
    lines.append(f"- profile: `{report.get('profile', '')}`\n")
    lines.append(f"- report_path: `{report_path}`\n")
    lines.append(
        f"- status: `{summary.get('overall_status', '')}` (rc={summary.get('overall_rc', '')})\n"
    )
    lines.append(
        f"- counts: pass={counts.get('pass')} fail={counts.get('fail')} "
        f"error={counts.get('error')} skip={counts.get('skip')} total={counts.get('total')}\n\n"
    )

    lines.append("## Results\n")
    if not results:
        lines.append("- no results\n")
    else:
        lines.append("| step_id | status | rc | elapsed_ms | log_path |\n")
        lines.append("| --- | --- | ---: | ---: | --- |\n")
        for r in results:
            lines.append(
                "| {id} | {status} | {rc} | {elapsed} | {log} |\n".format(
                    id=r.get("id", ""),
                    status=r.get("status", ""),
                    rc=r.get("rc", ""),
                    elapsed=r.get("elapsed_ms", ""),
                    log=r.get("log_path", ""),
                )
            )

    notes = [r for r in results if r.get("note")]
    if notes:
        lines.append("\n## Notes\n")
        for r in notes:
            lines.append(f"- {r.get('id', '')}: {clip(str(r.get('note', '')))}\n")

    if warnings:
        lines.append("\n## Warnings\n")
        for w in warnings:
            code = w.get("code", "")
            msg = w.get("message", "")
            detail = w.get("detail", None)
            if detail is None:
                lines.append(f"- {code}: {clip(str(msg))}\n")
            else:
                detail_text = json.dumps(detail, ensure_ascii=False)
                lines.append(f"- {code}: {clip(str(msg))} detail={clip(detail_text)}\n")

    findings_steps = [r for r in results if r.get("findings")]
    if findings_steps:
        lines.append("\n## Findings\n")
        for r in findings_steps:
            step_id = r.get("id", "")
            status = r.get("status", "")
            findings = r.get("findings") or []
            lines.append(f"### {step_id} (status={status})\n")
            lines.append(f"- count: {len(findings)}\n")
            if findings:
                lines.append("- items:\n")
                for f in findings[: args.max_findings]:
                    loc = ",".join(as_list(f.get("loc")))
                    fix = ",".join(as_list(f.get("fix")))
                    line = (
                        f"  - id={f.get('id','')} severity={f.get('severity','')} "
                        f"category={f.get('category','')} status={f.get('status','')} "
                        f"loc={clip(loc, 80)} fix={clip(fix, 80)} owner={f.get('owner','')}\n"
                    )
                    lines.append(line)
                if len(findings) > args.max_findings:
                    lines.append("  - ... (truncated)\n")

    lines.append(f"\n- generated_by: view_gate_report ({now_iso()})\n")

    md = "".join(lines)
    print(md)

    if args.md_out:
        out_path = Path(args.md_out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"\n[gate_report] wrote markdown: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
