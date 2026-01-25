#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snapshot_eval_retrieval_baseline.py

Purpose
- Materialize a stable baseline snapshot from the Stage-2 retrieval evaluation report
  (produced by tools/run_eval_retrieval.py).
- The snapshot is later consumed by compare_eval_retrieval_baseline.py to implement
  a reproducible "eval -> gate -> baseline regression" loop.

Exit codes (aligned with report.summary.overall_rc):
- 0: PASS
- 2: FAIL (missing inputs / invalid report / report skipped)
- 3: ERROR (runtime exception)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args


REPORT_SCHEMA_VERSION = 2

# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "snapshot_eval_retrieval_baseline",
    "kind": "STATE_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/snapshot_eval_retrieval_baseline.py",
}


def _normalize_rel(s: str) -> str:
    return (s or "").replace("\\", "/").lstrip("./")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _extract_metrics_and_buckets(data: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # Prefer explicit fields if present; fall back to recompute from cases.
    metrics = dict(data.get("metrics") or {})
    buckets = dict(data.get("buckets") or {})

    if metrics and buckets:
        return metrics, buckets

    cases = data.get("cases") or []
    if not isinstance(cases, list):
        return metrics, buckets

    # Recompute from per-case only.
    bucket_total: Dict[str, int] = {}
    bucket_hit: Dict[str, int] = {}
    bucket_hit_dense: Dict[str, int] = {}

    evaluated = 0
    hit = 0
    hit_dense = 0

    for c in cases:
        if not isinstance(c, dict):
            continue
        b = str(c.get("bucket") or "unknown")
        bucket_total[b] = bucket_total.get(b, 0) + 1
        evaluated += 1

        if c.get("hit_at_k") is True:
            hit += 1
            bucket_hit[b] = bucket_hit.get(b, 0) + 1

        try:
            if (c.get("debug") or {}).get("hit_at_k_dense") is True:
                hit_dense += 1
                bucket_hit_dense[b] = bucket_hit_dense.get(b, 0) + 1
        except Exception:
            pass

    buckets = {}
    for b in sorted(bucket_total.keys()):
        denom = int(bucket_total[b])
        buckets[b] = {
            "evaluated_cases": denom,
            "hit_cases": int(bucket_hit.get(b, 0)),
            "hit_rate": float(bucket_hit.get(b, 0)) / float(denom) if denom else 0.0,
            "hit_cases_dense": int(bucket_hit_dense.get(b, 0)),
            "hit_rate_dense": float(bucket_hit_dense.get(b, 0)) / float(denom) if denom else 0.0,
        }

    if not metrics:
        metrics = {
            "evaluated_cases": int(evaluated),
            "hit_cases": int(hit),
            "hit_rate": float(hit) / float(evaluated) if evaluated else 0.0,
            "hit_cases_dense": int(hit_dense),
            "hit_rate_dense": float(hit_dense) / float(evaluated) if evaluated else 0.0,
        }

    return metrics, buckets


def main() -> int:
    ap = argparse.ArgumentParser()
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument(
        "--report",
        default="data_processed/build_reports/eval_retrieval_report.json",
        help="stage2 eval report json (relative to root)",
    )
    ap.add_argument(
        "--baseline-out",
        default="data_processed/baselines/eval_retrieval_baseline.json",
        help="baseline snapshot json output (relative to root)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/eval_retrieval_baseline_snapshot_report.json",
        help="output report json (relative to root)",
    )
    ap.add_argument("--md-out", default="", help="optional report.md path (relative to root); default: <out>.md")
    args = ap.parse_args()

    repo_root = Path(getattr(args, "root", ".")).resolve()
    loc = Path(__file__).resolve()
    try:
        loc = loc.relative_to(repo_root)
    except Exception:
        pass

    rc = maybe_run_selftest_from_args(args=args, meta=REPORT_TOOL_META, repo_root=repo_root, loc_source=loc)
    if rc is not None:
        return rc

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve()
    baseline_path = (root / args.baseline_out).resolve()
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = (root / args.md_out).resolve() if args.md_out else default_md_path_for_json(out_path)

    items: List[Dict[str, Any]] = []
    t0 = time.time()

    def _emit(raw: Dict[str, Any]) -> None:
        items.append(ensure_item_fields(raw, tool_default="snapshot_eval_retrieval_baseline"))

    def _term(message: str) -> Dict[str, Any]:
        return {
            "tool": "snapshot_eval_retrieval_baseline",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/snapshot_eval_retrieval_baseline.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    snapshot: Dict[str, Any] = {}

    try:
        if not report_path.exists():
            _emit(
                {
                    "tool": "snapshot_eval_retrieval_baseline",
                    "title": "missing_report",
                    "status_label": "FAIL",
                    "severity_level": 3,
                    "message": f"missing report: {report_path.as_posix()}",
                    "loc": _normalize_rel(str(args.report)),
                }
            )
        else:
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(rep, dict) or int(rep.get("schema_version") or 0) != REPORT_SCHEMA_VERSION:
                _emit(
                    {
                        "tool": "snapshot_eval_retrieval_baseline",
                        "title": "invalid_report_schema",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "expected build_report schema_version=2",
                        "loc": _normalize_rel(str(args.report)),
                        "detail": {"schema_version": rep.get("schema_version") if isinstance(rep, dict) else None},
                    }
                )
            else:
                data = rep.get("data") or {}
                run_meta = data.get("run_meta") or {}
                if bool(run_meta.get("skipped")):
                    _emit(
                        {
                            "tool": "snapshot_eval_retrieval_baseline",
                            "title": "report_skipped",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"report skipped; cannot snapshot baseline: {run_meta.get('skip_reason')}",
                            "loc": _normalize_rel(str(args.report)),
                            "detail": {"run_meta": dict(run_meta)},
                        }
                    )
                else:
                    metrics, buckets = _extract_metrics_and_buckets(data)
                    retrieval = dict(data.get("retrieval") or {})
                    embed = dict(data.get("embed") or {})

                    snapshot = {
                        "schema_version": 1,
                        "generated_at": iso_now(),
                        "tool": "snapshot_eval_retrieval_baseline",
                        "baseline": {
                            "config": {
                                "k": int(data.get("k") or 0),
                                "collection": str(data.get("collection") or ""),
                                "db_path": str(data.get("db_path") or ""),
                                "cases_path": str(data.get("cases_path") or ""),
                                "embed": embed,
                                "retrieval": retrieval,
                            },
                            "metrics": metrics,
                            "buckets": buckets,
                        },
                        "source_report": {
                            "path": str(report_path.as_posix()),
                            "sha256": _sha256_file(report_path),
                            "generated_at": str(rep.get("generated_at") or ""),
                            "tool": str(rep.get("tool") or ""),
                        },
                        "env": {
                            "python": sys.version.split()[0],
                            "platform": platform.platform(),
                        },
                    }

                    baseline_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

                    _emit(
                        {
                            "tool": "snapshot_eval_retrieval_baseline",
                            "title": "baseline_written",
                            "status_label": "PASS",
                            "severity_level": 0,
                            "message": f"baseline written: {baseline_path.as_posix()}",
                            "loc": _normalize_rel(str(args.baseline_out)),
                            "detail": {
                                "hit_rate": metrics.get("hit_rate"),
                                "hit_rate_dense": metrics.get("hit_rate_dense"),
                                "buckets": buckets,
                            },
                        }
                    )

    except Exception as e:
        _emit(_term(f"unhandled exception: {type(e).__name__}: {e}"))

    summary = compute_summary(items)
    report_v2: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": iso_now(),
        "tool": "snapshot_eval_retrieval_baseline",
        "root": str(root.resolve().as_posix()),
        "summary": summary.to_dict(),
        "items": items,
        "data": {
            "report_path": str(report_path.as_posix()),
            "baseline_out": str(baseline_path.as_posix()),
            "snapshot": snapshot,
        },
    }

    write_report_bundle(
        report=report_v2,
        report_json=out_path,
        report_md=md_path,
        repo_root=root,
        console_title="snapshot_eval_retrieval_baseline",
        emit_console=True,
    )

    return int(summary.overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
