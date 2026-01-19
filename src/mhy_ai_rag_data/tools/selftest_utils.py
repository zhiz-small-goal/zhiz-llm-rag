#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.selftest_utils

Shared helpers for `--selftest` across report-output-v2 tools.

Design constraints (from docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md)
- stdout: only the final report console rendering (endswith "\n\n").
- stderr: must include an `out = <path>` token line, followed by a pure path line.
- selftest should be deterministic and not require DB/network/large files.

High-cost tools
- selftest additionally emits:
  - report.events.jsonl (>= 2 JSON object lines)
  - checkpoint.json (atomically written)
  - durability parameter parsing branch touches flush/fsync at least once (default mode=fsync).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from mhy_ai_rag_data.tools.checkpoint_utils import atomic_write_json
from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter


def add_selftest_args(ap: argparse.ArgumentParser) -> None:
    """Attach canonical selftest CLI args."""

    ap.add_argument(
        "--selftest",
        action="store_true",
        help="run a deterministic selftest that only validates output contract",
    )
    ap.add_argument(
        "--artifacts",
        default="data_processed/build_reports/_selftest_artifacts",
        help="base directory for selftest outputs",
    )
    ap.add_argument(
        "--selftest-id",
        default="",
        help="override tool id used for naming the selftest artifact directory",
    )

    # durability knobs (used by high_cost tools in selftest)
    ap.add_argument(
        "--durability-mode",
        default="",
        help="(selftest/high_cost) none|flush|fsync; default is fsync for high_cost selftest",
    )
    ap.add_argument(
        "--fsync-interval-ms",
        type=int,
        default=250,
        help="(selftest/high_cost) fsync throttle interval in ms",
    )


def _selftest_paths(*, artifacts_root: Path, tool_id: str) -> Dict[str, Path]:
    tool_dir = (artifacts_root / tool_id).resolve()
    return {
        "tool_dir": tool_dir,
        "report_json": tool_dir / "report.json",
        "report_md": tool_dir / "report.md",
        "events": tool_dir / "report.events.jsonl",
        "checkpoint": tool_dir / "checkpoint.json",
    }


def _emit_out_tokens(*, report_json: Path) -> None:
    # stderr token for downstream scripts; also emit pure path on next line.
    sys.stderr.write(f"out = {report_json.as_posix()}\n")
    sys.stderr.write(f"{report_json.as_posix()}\n")
    sys.stderr.flush()


def run_selftest(
    *,
    meta: Mapping[str, Any],
    repo_root: Path,
    artifacts_root: Path,
    durability_mode: str,
    fsync_interval_ms: int,
    loc_source: Optional[Path] = None,
) -> int:
    """Execute the canonical selftest and exit code.

    The returned rc follows report.summary.overall_rc.
    """

    tool_id = str(meta.get("id") or "tool")
    high_cost = bool(meta.get("high_cost") or False)

    # high_cost default: touch fsync branch at least once.
    mode = (durability_mode or "").strip().lower()
    if high_cost and not mode:
        mode = "fsync"
    if mode not in {"", "none", "flush", "fsync"}:
        mode = "fsync" if high_cost else "flush"

    paths = _selftest_paths(artifacts_root=artifacts_root, tool_id=tool_id)
    tool_dir = paths["tool_dir"]
    tool_dir.mkdir(parents=True, exist_ok=True)

    items = [
        ensure_item_fields(
            {
                "tool": tool_id,
                "title": "selftest_pass",
                "status_label": "PASS",
                "severity_level": 0,
                "message": "selftest generated a minimal v2 report (PASS/INFO/WARN)",
                "loc": f"{(loc_source or Path('src')).as_posix()}:1:1" if loc_source else "src/:1:1",
            },
            tool_default=tool_id,
        ),
        ensure_item_fields(
            {
                "tool": tool_id,
                "title": "selftest_info",
                "status_label": "INFO",
                "severity_level": 1,
                "message": "info item for ordering + summary buckets",
            },
            tool_default=tool_id,
        ),
        ensure_item_fields(
            {
                "tool": tool_id,
                "title": "selftest_warn",
                "status_label": "WARN",
                "severity_level": 2,
                "message": "warn item for ordering + summary buckets",
            },
            tool_default=tool_id,
        ),
    ]

    # high_cost: emit events + checkpoint (deterministic, tiny)
    if high_cost:
        ew = ItemEventsWriter(
            path=paths["events"],
            durability_mode=mode or "fsync",
            fsync_interval_ms=max(0, int(fsync_interval_ms)),
        ).open(truncate=True)
        try:
            ew.emit_item(items[1])
            ew.emit_item(items[2])
        finally:
            ew.close()

        atomic_write_json(
            paths["checkpoint"],
            {
                "schema_version": 1,
                "tool": tool_id,
                "generated_at": iso_now(),
                "mode": "selftest",
                "durability_mode": mode or "fsync",
                "note": "checkpoint written atomically (tmp then rename)",
            },
        )

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_id,
        "root": str(repo_root.resolve().as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "data": {
            "selftest": True,
            "high_cost": high_cost,
            "durability_mode": mode,
            "artifacts_dir": str(tool_dir.as_posix()),
            "events_path": str(paths["events"].as_posix()) if high_cost else "",
            "checkpoint_path": str(paths["checkpoint"].as_posix()) if high_cost else "",
        },
    }

    # stdout: only the report rendering.
    write_report_bundle(
        report=report,
        report_json=paths["report_json"],
        report_md=paths["report_md"],
        repo_root=repo_root,
        console_title=tool_id,
        emit_console=True,
    )

    _emit_out_tokens(report_json=paths["report_json"])
    return int(report["summary"]["overall_rc"])


def maybe_run_selftest_from_args(
    *,
    args: argparse.Namespace,
    meta: Mapping[str, Any],
    repo_root: Path,
    loc_source: Optional[Path] = None,
) -> Optional[int]:
    """Return rc if selftest ran, otherwise None."""

    if not bool(getattr(args, "selftest", False)):
        return None

    artifacts = Path(str(getattr(args, "artifacts", "data_processed/build_reports/_selftest_artifacts")))
    tid_override = str(getattr(args, "selftest_id", "") or "").strip()

    if tid_override:
        meta = dict(meta)
        meta["id"] = tid_override

    rc = run_selftest(
        meta=meta,
        repo_root=repo_root,
        artifacts_root=artifacts,
        durability_mode=str(getattr(args, "durability_mode", "") or ""),
        fsync_interval_ms=int(getattr(args, "fsync_interval_ms", 250) or 250),
        loc_source=loc_source,
    )
    return rc
