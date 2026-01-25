#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_eval_retrieval_baseline.py

Purpose
- Compare current Stage-2 retrieval evaluation report against a stored baseline
  (created by snapshot_eval_retrieval_baseline.py).
- Designed for gate integration: if evaluation is skipped (missing inputs), the
  comparison step emits WARN and exits 0; if evaluated, a statistically-free
  deterministic regression check is enforced.

Baseline format
- A JSON file with schema_version=1 written by snapshot_eval_retrieval_baseline.py.

"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args


REPORT_SCHEMA_VERSION = 2

# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "compare_eval_retrieval_baseline",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/compare_eval_retrieval_baseline.py",
}


def _normalize_rel(s: str) -> str:
    return (s or "").replace("\\", "/").lstrip("./")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return cast(Dict[str, Any], json.load(f))


def _as_dict(value: Any) -> Dict[str, Any]:
    """Best-effort: only propagate mapping values, otherwise return empty dict."""
    return dict(value) if isinstance(value, Mapping) else {}


def _extract_current_config(report: Mapping[str, Any]) -> Dict[str, Any]:
    data = _as_dict(report.get("data"))
    embed = _as_dict(data.get("embed"))
    retrieval = _as_dict(data.get("retrieval"))
    return {
        "k": int(data.get("k") or 0),
        "collection": str(data.get("collection") or ""),
        "db_path": str(data.get("db_path") or ""),
        "cases_path": str(data.get("cases_path") or ""),
        "embed_backend": str(embed.get("backend") or ""),
        "embed_model": str(embed.get("model") or ""),
        "device": str(embed.get("device") or ""),
        "retrieval_mode": str(retrieval.get("mode") or ""),
        "dense_pool_k": int(retrieval.get("dense_pool_k") or 0),
        "keyword_pool_k": int(retrieval.get("keyword_pool_k") or 0),
        "fusion_method": str(retrieval.get("fusion_method") or ""),
        "rrf_k": int(retrieval.get("rrf_k") or 0),
    }


def _extract_current_metrics(report: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    data = _as_dict(report.get("data"))
    metrics = _as_dict(data.get("metrics"))
    buckets = _as_dict(data.get("buckets"))
    return metrics, buckets


def _as_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument(
        "--report",
        default="data_processed/build_reports/eval_retrieval_report.json",
        help="current eval report json (relative to root)",
    )
    ap.add_argument(
        "--baseline",
        default="data_processed/baselines/eval_retrieval_baseline.json",
        help="baseline snapshot json (relative to root)",
    )
    ap.add_argument(
        "--allowed-drop",
        type=float,
        default=0.0,
        help="allowed decrease in hit_rate (e.g. 0.01 allows 1% absolute drop)",
    )
    ap.add_argument(
        "--bucket-allowed-drop",
        type=float,
        default=0.0,
        help="allowed decrease for per-bucket hit_rate (absolute)",
    )
    ap.add_argument(
        "--strict-config",
        action="store_true",
        help="require config match (k/model/mode/etc). If not set, only checks k/mode.",
    )
    ap.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="if report missing, emit WARN and exit 0 (for gate integration)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/eval_retrieval_baseline_compare_report.json",
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
    baseline_path = (root / args.baseline).resolve()
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = (root / args.md_out).resolve() if args.md_out else default_md_path_for_json(out_path)

    items: List[Dict[str, Any]] = []
    t0 = time.time()

    def _emit(raw: Dict[str, Any]) -> None:
        items.append(ensure_item_fields(raw, tool_default="compare_eval_retrieval_baseline"))

    def _termination_item(message: str) -> Dict[str, Any]:
        return {
            "tool": "compare_eval_retrieval_baseline",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/compare_eval_retrieval_baseline.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    baseline_obj: Optional[Dict[str, Any]] = None
    current_report: Optional[Dict[str, Any]] = None
    skip_reason: Optional[str] = None

    try:
        if not report_path.exists():
            if args.skip_if_missing:
                skip_reason = f"report not found: {report_path.as_posix()}"
                _emit(
                    {
                        "tool": "compare_eval_retrieval_baseline",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skip_reason}",
                        "loc": _normalize_rel(str(args.report)),
                        "detail": {"skip_reason": skip_reason},
                    }
                )
            else:
                _emit(_termination_item(f"report not found: {report_path.as_posix()}"))
        else:
            current_report = _read_json(report_path)
            data = _as_dict(current_report.get("data"))
            run_meta = _as_dict(data.get("run_meta"))
            if bool(run_meta.get("skipped")):
                skip_reason = str(run_meta.get("skip_reason") or "report skipped")
                _emit(
                    {
                        "tool": "compare_eval_retrieval_baseline",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skip_reason}",
                        "loc": _normalize_rel(str(args.report)),
                        "detail": {"skip_reason": skip_reason},
                    }
                )
            else:
                # baseline must exist if report is evaluated
                if not baseline_path.exists():
                    msg = f"baseline not found: {baseline_path.as_posix()} (run snapshot_eval_retrieval_baseline)"
                    _emit(
                        {
                            "tool": "compare_eval_retrieval_baseline",
                            "title": "baseline_missing",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": msg,
                            "loc": _normalize_rel(str(args.baseline)),
                            "detail": {"hint": "python tools/snapshot_eval_retrieval_baseline.py"},
                        }
                    )
                else:
                    baseline_obj = _read_json(baseline_path)
                    base = _as_dict(baseline_obj.get("baseline"))
                    base_cfg = _as_dict(base.get("config"))
                    base_metrics = _as_dict(base.get("metrics"))
                    base_buckets = _as_dict(base.get("buckets"))

                    cur_cfg = _extract_current_config(current_report)
                    cur_metrics, cur_buckets = _extract_current_metrics(current_report)

                    # Config checks
                    cfg_mismatch: Dict[str, Dict[str, Any]] = {}
                    always_keys = ["k", "retrieval_mode"]
                    strict_keys = [
                        "collection",
                        "embed_backend",
                        "embed_model",
                        "device",
                        "dense_pool_k",
                        "keyword_pool_k",
                        "fusion_method",
                        "rrf_k",
                    ]
                    keys = list(always_keys) + (strict_keys if args.strict_config else [])
                    for k in keys:
                        if str(base_cfg.get(k)) != str(cur_cfg.get(k)):
                            cfg_mismatch[k] = {"baseline": base_cfg.get(k), "current": cur_cfg.get(k)}

                    if cfg_mismatch:
                        _emit(
                            {
                                "tool": "compare_eval_retrieval_baseline",
                                "title": "config_mismatch",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": "baseline config mismatch (likely version/config drift)",
                                "loc": _normalize_rel(str(args.baseline)),
                                "detail": cfg_mismatch,
                            }
                        )
                    else:
                        # Overall metric
                        base_hr = _as_float(base_metrics.get("hit_rate"))
                        cur_hr = _as_float(cur_metrics.get("hit_rate"))
                        delta = cur_hr - base_hr
                        allowed = float(args.allowed_drop)
                        if delta < -allowed:
                            _emit(
                                {
                                    "tool": "compare_eval_retrieval_baseline",
                                    "title": "hit_rate_regression",
                                    "status_label": "FAIL",
                                    "severity_level": 3,
                                    "message": f"hit_rate regressed: {cur_hr:.6f} vs {base_hr:.6f} (delta={delta:.6f} < -{allowed:.6f})",
                                    "loc": _normalize_rel(str(args.report)),
                                    "detail": {
                                        "baseline": base_hr,
                                        "current": cur_hr,
                                        "delta": delta,
                                        "allowed_drop": allowed,
                                    },
                                }
                            )
                        else:
                            _emit(
                                {
                                    "tool": "compare_eval_retrieval_baseline",
                                    "title": "hit_rate",
                                    "status_label": "PASS",
                                    "severity_level": 0,
                                    "message": f"hit_rate OK: {cur_hr:.6f} vs {base_hr:.6f} (delta={delta:.6f})",
                                    "loc": _normalize_rel(str(args.report)),
                                    "detail": {
                                        "baseline": base_hr,
                                        "current": cur_hr,
                                        "delta": delta,
                                        "allowed_drop": allowed,
                                    },
                                }
                            )

                        # Optional: dense hit rate informational
                        base_dense = _as_float(base_metrics.get("hit_rate_dense"))
                        cur_dense = _as_float(cur_metrics.get("hit_rate_dense"))
                        _emit(
                            {
                                "tool": "compare_eval_retrieval_baseline",
                                "title": "hit_rate_dense",
                                "status_label": "INFO",
                                "severity_level": 1,
                                "message": f"dense hit_rate: {cur_dense:.6f} vs {base_dense:.6f} (delta={cur_dense - base_dense:.6f})",
                                "loc": _normalize_rel(str(args.report)),
                                "detail": {
                                    "baseline": base_dense,
                                    "current": cur_dense,
                                    "delta": cur_dense - base_dense,
                                },
                            }
                        )

                        # Per-bucket checks
                        b_allowed = float(args.bucket_allowed_drop)
                        for bucket in sorted(set(list(base_buckets.keys()) + list(cur_buckets.keys()))):
                            b0 = _as_dict(base_buckets.get(bucket))
                            b1 = _as_dict(cur_buckets.get(bucket))
                            b0_hr = _as_float(b0.get("hit_rate"))
                            b1_hr = _as_float(b1.get("hit_rate"))
                            b_delta = b1_hr - b0_hr
                            if b_delta < -b_allowed:
                                _emit(
                                    {
                                        "tool": "compare_eval_retrieval_baseline",
                                        "title": f"bucket_regression:{bucket}",
                                        "status_label": "FAIL",
                                        "severity_level": 3,
                                        "message": f"bucket {bucket} regressed: {b1_hr:.6f} vs {b0_hr:.6f} (delta={b_delta:.6f} < -{b_allowed:.6f})",
                                        "loc": _normalize_rel(str(args.report)),
                                        "detail": {
                                            "bucket": bucket,
                                            "baseline": b0_hr,
                                            "current": b1_hr,
                                            "delta": b_delta,
                                            "allowed_drop": b_allowed,
                                        },
                                    }
                                )
                            else:
                                _emit(
                                    {
                                        "tool": "compare_eval_retrieval_baseline",
                                        "title": f"bucket:{bucket}",
                                        "status_label": "PASS",
                                        "severity_level": 0,
                                        "message": f"bucket {bucket} OK: {b1_hr:.6f} vs {b0_hr:.6f} (delta={b_delta:.6f})",
                                        "loc": _normalize_rel(str(args.report)),
                                        "detail": {
                                            "bucket": bucket,
                                            "baseline": b0_hr,
                                            "current": b1_hr,
                                            "delta": b_delta,
                                            "allowed_drop": b_allowed,
                                        },
                                    }
                                )

    except Exception as e:
        _emit(_termination_item(f"unhandled exception: {type(e).__name__}: {e}"))

    summary = compute_summary(items)

    report: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": iso_now(),
        "tool": "compare_eval_retrieval_baseline",
        "root": str(root.resolve().as_posix()),
        "summary": summary.to_dict(),
        "items": items,
        "data": {
            "report_path": str(report_path.as_posix()),
            "baseline_path": str(baseline_path.as_posix()),
            "allowed_drop": float(args.allowed_drop),
            "bucket_allowed_drop": float(args.bucket_allowed_drop),
            "strict_config": bool(args.strict_config),
            "run_meta": {
                "tool": "compare_eval_retrieval_baseline",
                "tool_impl": "src/mhy_ai_rag_data/tools/compare_eval_retrieval_baseline.py",
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "argv": sys.argv,
                "skipped": bool(skip_reason),
                "skip_reason": skip_reason,
            },
        },
    }

    write_report_bundle(
        report=report,
        report_json=out_path,
        report_md=md_path,
        repo_root=root,
        console_title="compare_eval_retrieval_baseline",
        emit_console=True,
    )

    return int(summary.overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
