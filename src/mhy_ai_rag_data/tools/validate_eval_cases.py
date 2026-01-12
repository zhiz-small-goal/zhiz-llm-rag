#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_eval_cases.py

目的：
- 校验 eval_cases.jsonl 的结构与“可执行性”，降低因为手工维护导致的评测噪声
- 可选：对 expected_sources 指向的文件/目录做存在性检查
- 可选：检查 must_include 是否至少出现在某个 expected_source 文件内容中（减少“写了个答案不可能包含的锚点”）

输出：
- <root>/data_processed/build_reports/eval_cases_validation.json

退出码：
- 0：PASS
- 2：FAIL（存在解析/结构/一致性问题）
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except Exception as e:
            out.append({"_parse_error": f"line {idx}: {type(e).__name__}: {e}", "_raw": s})
    return out


def is_probably_dir(s: str) -> bool:
    return s.endswith("/") or s.endswith("\\")


def normalize_rel(s: str) -> str:
    return s.replace("\\", "/").lstrip("./")


DEFAULT_BUCKET = "official"
ALLOWED_BUCKETS = {"official", "oral", "ambiguous"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument(
        "--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)"
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/eval_cases_validation.json",
        help="output report (relative to root)",
    )
    ap.add_argument(
        "--check-sources-exist", action="store_true", help="check that expected_sources path exists under root"
    )
    ap.add_argument(
        "--check-must-include-in-sources",
        action="store_true",
        help="check each must_include appears in at least one expected_source file (only for file paths)",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cases_path = (root / args.cases).resolve()
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "timestamp": now_iso(),
        "root": str(root),
        "cases_path": str(cases_path),
        "overall": "PASS",
        "counts": {"lines": 0, "cases": 0, "errors": 0, "warnings": 0},
        "errors": [],
        "warnings": [],
    }

    if not cases_path.exists():
        report["overall"] = "FAIL"
        report["errors"].append({"code": "cases_missing", "msg": f"cases file not found: {cases_path}"})
        report["counts"]["errors"] += 1
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[validate_cases] overall=FAIL out={out_path}")
        return 2

    cases = read_jsonl(cases_path)
    report["counts"]["lines"] = len(cases)

    seen_ids: Set[str] = set()
    for idx, case in enumerate(cases, start=1):
        if "_parse_error" in case:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "json_parse_error", "msg": case["_parse_error"]})
            report["counts"]["errors"] += 1
            continue

        report["counts"]["cases"] += 1

        # required fields
        for k in ("id", "query", "expected_sources", "must_include"):
            if k not in case:
                report["overall"] = "FAIL"
                report["errors"].append({"line": idx, "code": "missing_field", "field": k})
                report["counts"]["errors"] += 1

        cid = str(case.get("id", "")).strip()
        if not cid:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "empty_id"})
            report["counts"]["errors"] += 1
        elif cid in seen_ids:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "duplicate_id", "id": cid})
            report["counts"]["errors"] += 1
        else:
            seen_ids.add(cid)

        q = str(case.get("query", "")).strip()
        if len(q) < 2:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "bad_query", "query": q})
            report["counts"]["errors"] += 1

        exp = case.get("expected_sources")
        if not isinstance(exp, list) or not exp:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "bad_expected_sources"})
            report["counts"]["errors"] += 1
            exp_list: List[str] = []
        else:
            exp_list = [str(x) for x in exp if str(x).strip()]

        mi = case.get("must_include")
        if not isinstance(mi, list) or not mi:
            report["overall"] = "FAIL"
            report["errors"].append({"line": idx, "code": "bad_must_include"})
            report["counts"]["errors"] += 1
            mi_list: List[str] = []
        else:
            mi_list = [str(x) for x in mi if str(x).strip()]

        # optional fields: bucket/pair_id/concept_id (for oral-vs-official regression)
        raw_bucket = case.get("bucket")
        if raw_bucket is None or str(raw_bucket).strip() == "":
            report["warnings"].append({"line": idx, "code": "missing_bucket_default", "bucket": DEFAULT_BUCKET})
            report["counts"]["warnings"] += 1
            bucket = DEFAULT_BUCKET
        else:
            bucket = str(raw_bucket).strip().lower()
            if bucket not in ALLOWED_BUCKETS:
                report["overall"] = "FAIL"
                report["errors"].append(
                    {"line": idx, "code": "invalid_bucket", "bucket": bucket, "allowed": sorted(list(ALLOWED_BUCKETS))}
                )
                report["counts"]["errors"] += 1
                bucket = "unknown"

        pair_id = case.get("pair_id")
        if bucket in ("oral", "official"):
            if pair_id is None or str(pair_id).strip() == "":
                report["warnings"].append({"line": idx, "code": "missing_pair_id", "bucket": bucket})
                report["counts"]["warnings"] += 1
        if pair_id is not None and str(pair_id).strip() == "":
            report["warnings"].append({"line": idx, "code": "empty_pair_id"})
            report["counts"]["warnings"] += 1

        concept_id = case.get("concept_id")
        if concept_id is not None and str(concept_id).strip() == "":
            report["warnings"].append({"line": idx, "code": "empty_concept_id"})
            report["counts"]["warnings"] += 1

        # must_include quality checks
        if mi_list:
            uniq = []
            for t in mi_list:
                if t not in uniq:
                    uniq.append(t)
            if len(uniq) != len(mi_list):
                report["warnings"].append({"line": idx, "code": "must_include_duplicates", "must_include": mi_list})
                report["counts"]["warnings"] += 1
            for t in uniq:
                if len(t) < 2:
                    report["warnings"].append({"line": idx, "code": "must_include_too_short", "term": t})
                    report["counts"]["warnings"] += 1

        # check expected sources existence
        if args.check_sources_exist and exp_list:
            for s in exp_list:
                rel = normalize_rel(s)
                p = (root / rel).resolve()
                if is_probably_dir(s):
                    if not p.exists() or not p.is_dir():
                        report["overall"] = "FAIL"
                        report["errors"].append({"line": idx, "code": "expected_dir_missing", "path": s})
                        report["counts"]["errors"] += 1
                else:
                    if not p.exists() or not p.is_file():
                        # allow prefix match patterns like "postmortems/" handled above; here only file
                        report["overall"] = "FAIL"
                        report["errors"].append({"line": idx, "code": "expected_file_missing", "path": s})
                        report["counts"]["errors"] += 1

        # check must_include appears in expected sources (file paths only)
        if args.check_must_include_in_sources and exp_list and mi_list:
            # load file contents for file-like sources only (skip dirs/prefixes)
            file_paths = []
            for s in exp_list:
                if is_probably_dir(s):
                    continue
                rel = normalize_rel(s)
                p = (root / rel).resolve()
                if p.exists() and p.is_file():
                    file_paths.append(p)
            if file_paths:
                texts = []
                for fp in file_paths[:5]:  # cap
                    try:
                        texts.append(fp.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass
                merged = "\n".join(texts)
                for t in mi_list:
                    if t and (t not in merged):
                        report["warnings"].append(
                            {
                                "line": idx,
                                "code": "must_include_not_in_expected_sources",
                                "term": t,
                                "sources_checked": [str(p.relative_to(root)) for p in file_paths[:5]],
                            }
                        )
                        report["counts"]["warnings"] += 1

    if report["counts"]["errors"] > 0:
        report["overall"] = "FAIL"

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[validate_cases] overall={report['overall']} out={out_path}")
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
