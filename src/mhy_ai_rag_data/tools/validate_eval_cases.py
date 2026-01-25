#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_eval_cases.py

校验 eval_cases.jsonl 的结构与可执行性，并以 schema_version=2 的 items 报告输出。

全局一致输出改造点：
- 控制台（stdout）：detail 轻->重（最严重留在最后），summary 在末尾，整体以 "\n\n" 结尾
- 落盘：report.json + report.md（.md 内定位可点击 VS Code 跳转）

退出码（与 report.summary.overall_rc 对齐）：
- 0：PASS
- 2：FAIL（存在结构/一致性错误）
- 3：ERROR（运行期异常）

说明：
- 本脚本把 errors/warnings 全部转成 item；不再额外输出 stdout 文本，避免污染最终报告渲染。
"""

from __future__ import annotations


import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "validate_eval_cases",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/validate_eval_cases.py",
}


DEFAULT_BUCKET = "official"
ALLOWED_BUCKETS = {"official", "oral", "ambiguous"}


def _normalize_rel(s: str) -> str:
    return (s or "").replace("\\", "/").lstrip("./")


def read_jsonl_with_lineno(path: Path) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            s = (line or "").strip()
            if s:
                out.append((lineno, s))
    return out


def is_probably_dir(s: str) -> bool:
    return str(s).endswith("/") or str(s).endswith("\\")


def main() -> int:
    ap = argparse.ArgumentParser()
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument(
        "--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)"
    )
    ap.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="if cases missing, emit WARN and exit 0 (for gate integration)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/eval_cases_validation.json",
        help="output report json (relative to root)",
    )
    ap.add_argument("--md-out", default="", help="optional report.md path (relative to root); default: <out>.md")
    ap.add_argument(
        "--check-sources-exist", action="store_true", help="check that expected_sources path exists under root"
    )
    ap.add_argument(
        "--check-must-include-in-sources",
        action="store_true",
        help="check each must_include appears in at least one expected_source file (only for file paths)",
    )
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
    cases_path = (root / args.cases).resolve()
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = (root / args.md_out).resolve() if args.md_out else default_md_path_for_json(out_path)

    items: List[Dict[str, Any]] = []
    t0 = time.time()

    def _emit(raw: Dict[str, Any]) -> None:
        items.append(ensure_item_fields(raw, tool_default="validate_eval_cases"))

    def _termination_item(message: str) -> Dict[str, Any]:
        return {
            "tool": "validate_eval_cases",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/validate_eval_cases.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    try:
        if not cases_path.exists():
            if getattr(args, "skip_if_missing", False):
                _emit(
                    {
                        "tool": "validate_eval_cases",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: cases file not found: {cases_path.as_posix()}",
                        "loc": _normalize_rel(str(args.cases)),
                        "detail": {"skip_reason": f"cases file not found: {cases_path.as_posix()}"},
                    }
                )
            else:
                _emit(_termination_item(f"cases file not found: {cases_path.as_posix()}"))
        else:
            lines = read_jsonl_with_lineno(cases_path)

            seen_ids: Set[str] = set()
            for lineno, raw in lines:
                # parse json
                try:
                    obj = json.loads(raw)
                except Exception as e:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": f"line_{lineno}",
                            "status_label": "ERROR",
                            "severity_level": 4,
                            "message": f"json_parse_error: {type(e).__name__}: {e}",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                            "detail": {"raw": raw},
                        }
                    )
                    continue

                if not isinstance(obj, dict):
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": f"line_{lineno}",
                            "status_label": "ERROR",
                            "severity_level": 4,
                            "message": "json_not_object",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                            "detail": {"raw": raw},
                        }
                    )
                    continue

                # required fields
                for k in ("id", "query", "expected_sources", "must_include"):
                    if k not in obj:
                        _emit(
                            {
                                "tool": "validate_eval_cases",
                                "title": str(obj.get("id") or f"line_{lineno}"),
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": f"missing_field: {k}",
                                "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                "detail": {"field": k},
                            }
                        )

                cid = str(obj.get("id", "")).strip()
                if not cid:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": f"line_{lineno}",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "empty_id",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        }
                    )
                elif cid in seen_ids:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": cid,
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "duplicate_id",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        }
                    )
                else:
                    seen_ids.add(cid)

                q = str(obj.get("query", "")).strip()
                if len(q) < 2:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": cid or f"line_{lineno}",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "bad_query",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                            "detail": {"query": q},
                        }
                    )

                exp = obj.get("expected_sources")
                exp_list: List[str] = [str(x) for x in exp] if isinstance(exp, list) else []
                if not exp_list:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": cid or f"line_{lineno}",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "bad_expected_sources",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        }
                    )

                mi = obj.get("must_include")
                mi_list: List[str] = [str(x) for x in mi] if isinstance(mi, list) else []
                if not mi_list:
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": cid or f"line_{lineno}",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": "bad_must_include",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        }
                    )

                # optional bucket validation
                raw_bucket = obj.get("bucket")
                if raw_bucket is None or str(raw_bucket).strip() == "":
                    _emit(
                        {
                            "tool": "validate_eval_cases",
                            "title": cid or f"line_{lineno}",
                            "status_label": "WARN",
                            "severity_level": 2,
                            "message": f"missing_bucket_default: {DEFAULT_BUCKET}",
                            "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        }
                    )
                    bucket = DEFAULT_BUCKET
                else:
                    bucket = str(raw_bucket).strip().lower()
                    if bucket not in ALLOWED_BUCKETS:
                        _emit(
                            {
                                "tool": "validate_eval_cases",
                                "title": cid or f"line_{lineno}",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": f"invalid_bucket: {bucket}",
                                "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                "detail": {"allowed": sorted(list(ALLOWED_BUCKETS))},
                            }
                        )

                pair_id = obj.get("pair_id")
                if bucket in ("oral", "official"):
                    if pair_id is None or str(pair_id).strip() == "":
                        _emit(
                            {
                                "tool": "validate_eval_cases",
                                "title": cid or f"line_{lineno}",
                                "status_label": "WARN",
                                "severity_level": 2,
                                "message": f"missing_pair_id bucket={bucket}",
                                "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                            }
                        )

                # must_include quality checks
                if mi_list:
                    uniq: List[str] = []
                    for t in mi_list:
                        if t not in uniq:
                            uniq.append(t)
                    if len(uniq) != len(mi_list):
                        _emit(
                            {
                                "tool": "validate_eval_cases",
                                "title": cid or f"line_{lineno}",
                                "status_label": "WARN",
                                "severity_level": 2,
                                "message": "must_include_duplicates",
                                "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                "detail": {"must_include": mi_list},
                            }
                        )
                    for t in uniq:
                        if len(str(t)) < 2:
                            _emit(
                                {
                                    "tool": "validate_eval_cases",
                                    "title": cid or f"line_{lineno}",
                                    "status_label": "WARN",
                                    "severity_level": 2,
                                    "message": f"must_include_too_short: {t}",
                                    "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                }
                            )

                # check expected sources existence
                if args.check_sources_exist and exp_list:
                    for s in exp_list:
                        rel = _normalize_rel(str(s))
                        p = (root / rel).resolve()
                        if is_probably_dir(s):
                            if not p.exists() or not p.is_dir():
                                _emit(
                                    {
                                        "tool": "validate_eval_cases",
                                        "title": cid or f"line_{lineno}",
                                        "status_label": "FAIL",
                                        "severity_level": 3,
                                        "message": f"expected_dir_missing: {s}",
                                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                    }
                                )
                        else:
                            if not p.exists() or not p.is_file():
                                _emit(
                                    {
                                        "tool": "validate_eval_cases",
                                        "title": cid or f"line_{lineno}",
                                        "status_label": "FAIL",
                                        "severity_level": 3,
                                        "message": f"expected_file_missing: {s}",
                                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                    }
                                )

                # check must_include appears in expected sources (file paths only)
                if args.check_must_include_in_sources and exp_list and mi_list:
                    file_paths: List[Path] = []
                    for s in exp_list:
                        if is_probably_dir(s):
                            continue
                        rel = _normalize_rel(str(s))
                        p = (root / rel).resolve()
                        if p.exists() and p.is_file():
                            file_paths.append(p)
                    if file_paths:
                        texts: List[str] = []
                        for fp in file_paths[:5]:
                            try:
                                texts.append(fp.read_text(encoding="utf-8", errors="replace"))
                            except Exception:
                                pass
                        merged = "\n".join(texts)
                        for t in mi_list:
                            if t and (str(t) not in merged):
                                _emit(
                                    {
                                        "tool": "validate_eval_cases",
                                        "title": cid or f"line_{lineno}",
                                        "status_label": "WARN",
                                        "severity_level": 2,
                                        "message": f"must_include_not_in_expected_sources: {t}",
                                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                                        "detail": {
                                            "sources_checked": [
                                                str(p.relative_to(root)).replace("\\", "/") for p in file_paths[:5]
                                            ]
                                        },
                                    }
                                )

        summary = compute_summary(items)
        report = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "validate_eval_cases",
            "root": str(root.resolve().as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {
                "cases_path": str(cases_path.resolve().as_posix()),
                "checks": {
                    "check_sources_exist": bool(args.check_sources_exist),
                    "check_must_include_in_sources": bool(args.check_must_include_in_sources),
                },
                "elapsed_ms": int((time.time() - t0) * 1000),
            },
        }

        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=root,
            console_title="validate_eval_cases",
            emit_console=True,
        )
        return int(summary.overall_rc)

    except Exception as e:
        _emit(_termination_item(f"unhandled exception: {type(e).__name__}: {e}"))
        summary = compute_summary(items)
        report = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "validate_eval_cases",
            "root": str(root.resolve().as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {"cases_path": str(cases_path.resolve().as_posix()), "elapsed_ms": int((time.time() - t0) * 1000)},
        }
        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=root,
            console_title="validate_eval_cases",
            emit_console=True,
        )
        return int(summary.overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
