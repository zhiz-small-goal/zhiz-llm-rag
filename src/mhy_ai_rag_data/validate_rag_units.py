#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_rag_units.py

One-file validator for:
  - inventory.csv
  - data_processed/text_units.jsonl

Checks:
  1) JSONL parseability + required fields + non-empty text
  2) Alignment: every inventory source_uri has a unit; each uri maps to a single doc_id
  3) Markdown refs sanity: md units contain asset_refs/doc_refs; targets exist on disk; locator quality

Usage:
  python validate_rag_units.py
  python validate_rag_units.py --root . --inventory inventory.csv --units data_processed/text_units.jsonl

JSON report contract (v1):
  - Exit code: 0=PASS, 2=FAIL, 3=ERROR
  - If --json-out is provided: only write that path (no extra default *report_ts.json)

Notes:
  - The script prints a human-readable summary to stdout.
  - If --json-out/--json-stdout is provided, it also emits a machine-readable JSON report.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mhy_ai_rag_data.tools.reporting import build_base, add_error, status_to_rc, write_report


REQ_FIELDS = {
    "doc_id",
    "source_uri",
    "source_type",
    "locator",
    "text",
    "content_sha256",
    "updated_at",
    "note",
}


@dataclass
class Stats:
    total_units: int = 0
    bad_json: int = 0
    missing_fields: int = 0
    empty_text: int = 0
    dup_unit_uris: int = 0
    inv_rows: int = 0
    missing_units_for_inventory: int = 0
    multi_docid_uris: int = 0

    md_units: int = 0
    md_missing_refs_fields: int = 0
    md_asset_refs: int = 0
    md_doc_refs: int = 0
    md_broken_asset_targets: int = 0
    md_broken_doc_targets: int = 0
    md_unknown_locator_refs: int = 0

    image_units: int = 0
    video_units: int = 0
    other_units: int = 0


def _load_inventory(inv_path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with inv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _iter_units(units_path: Path):
    with units_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            yield i, line


def _is_local_target(uri: str) -> bool:
    s = (uri or "").strip()
    if not s:
        return False
    # targets in our units should already be normalized; still guard.
    return not s.startswith(("http://", "https://", "mailto:", "data:"))


def _collect(root: Path, inv_path: Path, units_path: Path, max_samples: int) -> Tuple[Stats, List[str], List[str]]:
    """Return: (stats, fatal_errors, sample_issues)."""
    st = Stats()
    fatal: List[str] = []
    issues: List[str] = []

    if not inv_path.exists():
        fatal.append(f"inventory not found: {inv_path}")
    if not units_path.exists():
        fatal.append(f"units not found: {units_path}")
    if fatal:
        return st, fatal, issues

    inv_rows = _load_inventory(inv_path)
    st.inv_rows = len(inv_rows)
    inv_uris = [((r.get("source_uri") or "").strip()) for r in inv_rows if (r.get("source_uri") or "").strip()]

    unit_by_uri: Dict[str, List[Dict[str, Any]]] = {}
    docid_by_uri: Dict[str, set] = {}

    # ---- 1) JSONL structural checks ----
    for line_no, line in _iter_units(units_path):
        st.total_units += 1
        try:
            obj = json.loads(line)
        except Exception as e:
            st.bad_json += 1
            if len(issues) < max_samples:
                issues.append(f"[JSON_ERROR] line={line_no} err={e}")
            continue

        miss = REQ_FIELDS - set(obj.keys())
        if miss:
            st.missing_fields += 1
            if len(issues) < max_samples:
                issues.append(
                    f"[MISSING_FIELDS] line={line_no} missing={sorted(miss)} source_uri={obj.get('source_uri')}"
                )
            continue

        uri = str(obj.get("source_uri", "")).strip()
        if not uri:
            st.missing_fields += 1
            if len(issues) < max_samples:
                issues.append(f"[MISSING_SOURCE_URI] line={line_no}")
            continue

        unit_by_uri.setdefault(uri, []).append(obj)
        docid_by_uri.setdefault(uri, set()).add(str(obj.get("doc_id", "")).strip())

        text = obj.get("text", "")
        if not isinstance(text, str) or len(text) == 0:
            st.empty_text += 1
            if len(issues) < max_samples:
                issues.append(f"[EMPTY_TEXT] line={line_no} source_uri={uri}")

        src_type = str(obj.get("source_type", "")).strip().lower()
        if src_type == "md":
            st.md_units += 1
            if "asset_refs" not in obj or "doc_refs" not in obj:
                st.md_missing_refs_fields += 1
                if len(issues) < max_samples:
                    issues.append(f"[MD_MISSING_REFS_FIELDS] line={line_no} source_uri={uri}")

            asset_refs = obj.get("asset_refs") or []
            doc_refs = obj.get("doc_refs") or []
            if isinstance(asset_refs, list):
                st.md_asset_refs += len(asset_refs)
            if isinstance(doc_refs, list):
                st.md_doc_refs += len(doc_refs)

            # ---- 3) refs sanity ----
            for ref in asset_refs if isinstance(asset_refs, list) else []:
                tgt = (ref.get("target_uri") if isinstance(ref, dict) else "") or ""
                if not _is_local_target(tgt):
                    continue
                p = (root / tgt).resolve()
                if not p.exists():
                    st.md_broken_asset_targets += 1
                    if len(issues) < max_samples:
                        issues.append(f"[BROKEN_ASSET_REF] md={uri} target_uri={tgt}")
                loc = (ref.get("from_locator") if isinstance(ref, dict) else "") or ""
                if "unknown" in str(loc):
                    st.md_unknown_locator_refs += 1

            for ref in doc_refs if isinstance(doc_refs, list) else []:
                tgt = (ref.get("target_uri") if isinstance(ref, dict) else "") or ""
                if not _is_local_target(tgt):
                    continue
                p = (root / tgt).resolve()
                if not p.exists():
                    st.md_broken_doc_targets += 1
                    if len(issues) < max_samples:
                        issues.append(f"[BROKEN_DOC_REF] md={uri} target_uri={tgt}")
                loc = (ref.get("from_locator") if isinstance(ref, dict) else "") or ""
                if "unknown" in str(loc):
                    st.md_unknown_locator_refs += 1

        elif src_type == "image":
            st.image_units += 1
        elif src_type == "video":
            st.video_units += 1
        else:
            st.other_units += 1

    # duplicates by uri
    for uri, objs in unit_by_uri.items():
        if len(objs) > 1:
            st.dup_unit_uris += len(objs) - 1

    # ---- 2) Alignment checks ----
    missing_units = [u for u in inv_uris if u not in unit_by_uri]
    st.missing_units_for_inventory = len(missing_units)
    if missing_units and len(issues) < max_samples:
        issues.append(f"[MISSING_UNITS] count={len(missing_units)} sample={missing_units[:5]}")

    multi_docid_uris = [u for u, ids in docid_by_uri.items() if len(ids) != 1]
    st.multi_docid_uris = len(multi_docid_uris)
    if multi_docid_uris and len(issues) < max_samples:
        issues.append(f"[MULTI_DOCID_FOR_URI] count={len(multi_docid_uris)} sample={multi_docid_uris[:5]}")

    return st, fatal, issues


def _is_fail(st: Stats) -> bool:
    return (
        st.bad_json > 0
        or st.missing_fields > 0
        or st.empty_text > 0
        or st.missing_units_for_inventory > 0
        or st.multi_docid_uris > 0
        or st.md_missing_refs_fields > 0
        or st.md_broken_asset_targets > 0
        or st.md_broken_doc_targets > 0
    )


def _print_summary(
    root: Path, inv_path: Path, units_path: Path, st: Stats, issues: List[str], max_samples: int, *, fatal: List[str]
) -> None:
    if fatal:
        print("=== RAG ARTIFACTS VALIDATION SUMMARY ===")
        print(f"Root: {root}")
        print(f"Inventory: {inv_path}")
        print(f"Units: {units_path}")
        print("\n=== RESULT ===")
        print("FAIL (fatal precondition)")
        for x in fatal:
            print(f"[FATAL] {x}")
        return

    print("=== RAG ARTIFACTS VALIDATION SUMMARY ===")
    print(f"Root: {root}")
    print(f"Inventory: {inv_path} (rows={st.inv_rows})")
    print(f"Units: {units_path} (units={st.total_units})")
    print("")
    print("1) Structure")
    print(f"  bad_json={st.bad_json}")
    print(f"  missing_fields={st.missing_fields}")
    print(f"  empty_text={st.empty_text}")
    print("")
    print("2) Alignment")
    print(f"  missing_units_for_inventory={st.missing_units_for_inventory}")
    print(f"  dup_unit_uris(extra_records)={st.dup_unit_uris}")
    print(f"  multi_docid_uris={st.multi_docid_uris}")
    print("")
    print("3) Markdown refs")
    print(f"  md_units={st.md_units}")
    print(f"  md_missing_refs_fields={st.md_missing_refs_fields}")
    print(f"  md_asset_refs_total={st.md_asset_refs}")
    print(f"  md_doc_refs_total={st.md_doc_refs}")
    print(f"  md_broken_asset_targets={st.md_broken_asset_targets}")
    print(f"  md_broken_doc_targets={st.md_broken_doc_targets}")
    print(f"  md_unknown_locator_refs={st.md_unknown_locator_refs}")
    print("")
    print("4) By type")
    print(f"  image_units={st.image_units} video_units={st.video_units} other_units={st.other_units}")

    if issues:
        print("\n=== SAMPLE ISSUES (up to {}): ===".format(max_samples))
        for e in issues[:max_samples]:
            print(e)

    print("\n=== RESULT ===")
    if _is_fail(st):
        print("FAIL (fix the issues above before proceeding to chunking/embedding).")
    else:
        print("PASS (safe to proceed to chunking -> embedding -> vector store ingestion).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate inventory.csv and text_units.jsonl for RAG ingestion readiness.")
    ap.add_argument("--root", type=str, default=".", help="Project root directory (default: current dir).")
    ap.add_argument("--inventory", type=str, default="inventory.csv", help="Path to inventory.csv relative to root.")
    ap.add_argument(
        "--units",
        type=str,
        default="data_processed/text_units.jsonl",
        help="Path to text_units.jsonl relative to root.",
    )
    ap.add_argument("--max-samples", type=int, default=10, help="Max number of sample issues to print.")

    # JSON report (optional)
    ap.add_argument("--json-out", default=None, help="JSON 报告输出路径（提供则只写这一份）")
    ap.add_argument("--json-stdout", action="store_true", help="将 JSON 报告输出到 stdout（不落盘）")

    args = ap.parse_args()

    root = Path(args.root).resolve()
    inv_path = (root / args.inventory).resolve()
    units_path = (root / args.units).resolve()

    report = build_base(
        "units",
        inputs={
            "root": str(root),
            "inventory": str(inv_path),
            "units": str(units_path),
            "max_samples": int(args.max_samples),
        },
    )

    try:
        st, fatal, issues = _collect(root, inv_path, units_path, args.max_samples)

        # console output
        _print_summary(root, inv_path, units_path, st, issues, args.max_samples, fatal=fatal)

        # report metrics
        report["metrics"] = {
            "structure": {
                "bad_json": st.bad_json,
                "missing_fields": st.missing_fields,
                "empty_text": st.empty_text,
                "total_units": st.total_units,
            },
            "alignment": {
                "inventory_rows": st.inv_rows,
                "missing_units_for_inventory": st.missing_units_for_inventory,
                "dup_unit_uris_extra_records": st.dup_unit_uris,
                "multi_docid_uris": st.multi_docid_uris,
            },
            "markdown_refs": {
                "md_units": st.md_units,
                "md_missing_refs_fields": st.md_missing_refs_fields,
                "md_asset_refs_total": st.md_asset_refs,
                "md_doc_refs_total": st.md_doc_refs,
                "md_broken_asset_targets": st.md_broken_asset_targets,
                "md_broken_doc_targets": st.md_broken_doc_targets,
                "md_unknown_locator_refs": st.md_unknown_locator_refs,
            },
            "by_type": {
                "image_units": st.image_units,
                "video_units": st.video_units,
                "other_units": st.other_units,
            },
        }
        if fatal:
            report["status"] = "FAIL"
            for x in fatal:
                add_error(report, "FATAL", x)
        else:
            report["status"] = "FAIL" if _is_fail(st) else "PASS"

        if issues:
            # keep the issues list compact
            report["issues_sample"] = issues[: args.max_samples]

        # write/print JSON report only when requested
        if args.json_out:
            out_path = write_report(report, json_out=args.json_out, default_name="units_report.json")
            print(f"Wrote report: {out_path}")
        if args.json_stdout:
            print(json.dumps(report, ensure_ascii=False, indent=2))

        raise SystemExit(status_to_rc(report["status"]))

    except SystemExit:
        raise
    except Exception as e:
        report["status"] = "ERROR"
        add_error(report, "EXCEPTION", "validate_rag_units crashed", detail=repr(e))
        if args.json_out:
            out_path = write_report(report, json_out=args.json_out, default_name="units_report.json")
            print(f"Wrote report: {out_path}")
        if args.json_stdout:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(status_to_rc(report["status"]))


if __name__ == "__main__":
    main()
