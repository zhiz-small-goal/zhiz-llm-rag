#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.verify_report_output_contract

Verify the "globally consistent report output" contract for schema_version=2 reports.

This tool is intended for CI / gate usage. It validates a high-signal subset:

Console (stdout)
- detail ordered by numeric severity_level: low -> high (most severe last)
- summary appears after details
- output ends with exactly one extra blank line (overall endswith "\n\n")
- no more than 2 consecutive blank lines anywhere

Markdown
- summary appears before details
- details ordered by numeric severity_level: high -> low
- loc rendered as clickable markdown link: [loc](loc_uri) when loc_uri exists

Paths
- report.root uses '/' separators
- item loc / loc_uri use '/' separators (no backslashes)
- loc_uri uses vscode://file/<abs_path>:line:col form

Exit codes
- 0: PASS
- 2: FAIL (contract violation)
- 3: ERROR (unhandled exception)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, ensure_report_v2, iso_now
from mhy_ai_rag_data.tools.report_events import iter_items
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output
from mhy_ai_rag_data.tools.report_render import render_console, render_markdown


@dataclass
class Result:
    ok: bool
    errors: List[str]
    warnings: List[str]


_CONSOLE_ITEM_RE = re.compile(r"^- \[[^\]]+\] \(sev=(\d+)\) ")
_MD_ITEM_RE = re.compile(r"^### \[[^\]]+\] \(sev=(\d+)\) ")
_VS_URI_RE = re.compile(r"\bvscode://file/[^\s)]+")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
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
    rep: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_default,
        "root": str(root.resolve().as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "data": {"events_path": str(events_path.resolve().as_posix())},
    }
    out = prepare_report_for_file_output(rep)
    return out if isinstance(out, dict) else None


def _parse_sev_sequence(lines: Iterable[str], pattern: re.Pattern[str]) -> List[int]:
    sevs: List[int] = []
    for ln in lines:
        m = pattern.match(ln)
        if not m:
            continue
        try:
            sevs.append(int(m.group(1)))
        except Exception:
            continue
    return sevs


def _max_consecutive_blank_lines(text: str) -> int:
    streak = 0
    best = 0
    for ln in text.splitlines():
        if ln.strip() == "":
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _non_decreasing(xs: List[int]) -> bool:
    return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))


def _non_increasing(xs: List[int]) -> bool:
    return all(xs[i] >= xs[i + 1] for i in range(len(xs) - 1))


def _collect_string_fields(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _collect_string_fields(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _collect_string_fields(v)


def _check_paths(report: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errs: List[str] = []
    warns: List[str] = []

    root = report.get("root")
    if isinstance(root, str):
        if "\\" in root:
            errs.append(f"report.root contains backslash: {root}")
    else:
        errs.append("report.root missing or not a string")

    for s in _collect_string_fields(report.get("items") or []):
        if "\\" in s:
            errs.append(f"item field contains backslash: {s}")

    # loc_uri form check (best-effort)
    for it in report.get("items") or []:
        if not isinstance(it, dict):
            continue
        uri = it.get("loc_uri")
        if isinstance(uri, str) and uri.strip():
            if not uri.startswith("vscode://file/"):
                errs.append(f"loc_uri must start with vscode://file/: {uri}")
            if "\\" in uri:
                errs.append(f"loc_uri contains backslash: {uri}")
            if not re.search(r":\d+:\d+$", uri):
                errs.append(f"loc_uri must end with :line:col: {uri}")
        elif isinstance(uri, list):
            for u in uri:
                if not isinstance(u, str) or not u.strip():
                    continue
                if not u.startswith("vscode://file/"):
                    errs.append(f"loc_uri must start with vscode://file/: {u}")
                if "\\" in u:
                    errs.append(f"loc_uri contains backslash: {u}")
                if not re.search(r":\d+:\d+$", u):
                    errs.append(f"loc_uri must end with :line:col: {u}")

    return errs, warns


def verify(*, report: Dict[str, Any], report_path: Path, repo_root: Path, strict: bool) -> Result:
    errors: List[str] = []
    warnings: List[str] = []

    # schema
    if int(report.get("schema_version") or 0) != 2:
        errors.append(f"schema_version must be 2 (got {report.get('schema_version')})")

    # item severity_level must be numeric
    for i, it in enumerate(report.get("items") or []):
        if not isinstance(it, dict):
            errors.append(f"item[{i}] must be dict")
            continue
        if "severity_level" not in it:
            errors.append(f"item[{i}] missing severity_level")
            continue
        severity_level = it.get("severity_level")
        if severity_level is None:
            errors.append(f"item[{i}] severity_level is not int-like: {severity_level}")
            continue
        try:
            int(severity_level)
        except Exception:
            errors.append(f"item[{i}] severity_level is not int-like: {it.get('severity_level')}")

    # render
    console = render_console(report, title=str(report.get("tool") or "report"))
    md = render_markdown(report, report_path=report_path, root=repo_root, title=str(report.get("tool") or "report"))

    # console tail must be exactly \n\n
    if not console.endswith("\n\n"):
        errors.append("console output must end with \\n\\n")
    if console.endswith("\n\n\n"):
        errors.append("console output must not end with more than one blank line")

    # console blank-line cap
    max_blank = _max_consecutive_blank_lines(console)
    if max_blank > 2:
        errors.append(f"console output has >2 consecutive blank lines (max={max_blank})")

    # console ordering + summary position
    if "## details" not in console.lower():
        errors.append("console output missing details section")
    if "## summary" not in console.lower():
        errors.append("console output missing summary section")
    else:
        pos_details = console.lower().find("## details")
        pos_summary = console.lower().find("## summary")
        if pos_details >= 0 and pos_summary >= 0 and pos_summary < pos_details:
            errors.append("console summary must appear after details")

    sevs_console = _parse_sev_sequence(console.splitlines(), _CONSOLE_ITEM_RE)
    if sevs_console and not _non_decreasing(sevs_console):
        errors.append(f"console detail severity must be low->high: {sevs_console}")

    # markdown section order
    if "## Summary" not in md:
        errors.append("markdown missing '## Summary'")
    if "## Details" not in md:
        errors.append("markdown missing '## Details'")
    else:
        if md.find("## Summary") > md.find("## Details"):
            errors.append("markdown summary must appear before details")

    sevs_md = _parse_sev_sequence(md.splitlines(), _MD_ITEM_RE)
    if sevs_md and not _non_increasing(sevs_md):
        errors.append(f"markdown detail severity must be high->low: {sevs_md}")

    # markdown clickable links for expected loc_uris
    expected_uris: List[str] = []
    for it in report.get("items") or []:
        if not isinstance(it, dict):
            continue
        uri = it.get("loc_uri")
        if isinstance(uri, str) and uri.strip():
            expected_uris.append(uri)
        elif isinstance(uri, list):
            expected_uris.extend([u for u in uri if isinstance(u, str) and u.strip()])

    for uri in expected_uris[:50]:
        if uri not in md:
            errors.append(f"markdown missing expected loc_uri link: {uri}")

    # at least one vscode link if any loc_uri exists
    if expected_uris and not _VS_URI_RE.search(md):
        errors.append("markdown should contain vscode://file links")

    # path normalization
    e2, w2 = _check_paths(report)
    errors.extend(e2)
    warnings.extend(w2)

    if strict and warnings:
        errors.extend([f"[strict] {w}" for w in warnings])
        warnings = []

    return Result(ok=(not errors), errors=errors, warnings=warnings)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify report output contract (schema_version=2)")
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument("--report", default="", help="report.json path (relative to root)")
    ap.add_argument("--events", default="", help="events jsonl path (relative to root)")
    ap.add_argument("--tool-default", default="report", help="tool name used when rebuilding from events")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    repo_root = Path(args.root).resolve()
    report_path: Optional[Path] = (repo_root / args.report).resolve() if args.report else None
    events_path: Optional[Path] = (repo_root / args.events).resolve() if args.events else None

    report: Optional[Dict[str, Any]] = None
    source_path: Optional[Path] = None

    if events_path is not None and args.events:
        report = _load_report_from_events(root=repo_root, events_path=events_path, tool_default=str(args.tool_default))
        source_path = events_path

    if report is None and report_path is not None and args.report:
        raw = _read_json(report_path)
        if raw is not None:
            report = ensure_report_v2(raw)
            source_path = report_path

    if report is None:
        print("[FAIL] missing or invalid input (provide --report or --events)")
        return 2

    report = prepare_report_for_file_output(report)
    if not isinstance(report, dict):
        print("[ERROR] prepare_report_for_file_output failed")
        return 3

    rp = source_path or (report_path or repo_root / "(report)")
    res = verify(report=report, report_path=rp, repo_root=repo_root, strict=bool(args.strict))

    if res.ok:
        print("[PASS] report output contract satisfied")
        if res.warnings:
            for w in res.warnings:
                print("[WARN]", w)
        return 0

    print("[FAIL] report output contract violated")
    for e in res.errors:
        print("  -", e)
    if res.warnings:
        for w in res.warnings:
            print("[WARN]", w)
    return 2


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt", file=sys.stderr)
        return 3
    except SystemExit:
        raise
    except Exception:
        print("[ERROR] unhandled exception", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(_entry())
