#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_chunks_from_units.py

修复说明（2025-12-27 hotfix）
----------------------------
你在 Windows 上运行时遇到：
  [FATAL] cannot import chunking logic from build_chroma_index.py: 'NoneType' object has no attribute '__dict__'

根因：
  该脚本用 importlib 加载 build_chroma_index.py，但未把临时模块注册进 sys.modules。
  dataclasses 在处理类型注解时会通过 sys.modules[__module__] 取模块字典，取不到会触发上述异常。

修复：
  在 exec_module() 之前执行：sys.modules[spec.name] = mod

其余逻辑不变（仍然保证 plan 与 build 使用同一套 chunking/should_index 逻辑）。
"""

from __future__ import annotations


import argparse
from pathlib import Path
from typing import Any, Dict

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "plan_chunks_from_units",
    "kind": "INDEX_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/plan_chunks_from_units.py",
}


def _bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dry-run chunk planning from text_units.jsonl (same logic as build_chroma_index.py)"
    )
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--units", default="data_processed/text_units.jsonl", help="Units JSONL path (relative to root)")
    ap.add_argument("--chunk-chars", type=int, default=1200)
    ap.add_argument("--overlap-chars", type=int, default=120)
    ap.add_argument("--min-chunk-chars", type=int, default=200)
    ap.add_argument(
        "--include-media-stub",
        default="false",
        help="Whether to index media stubs (true/false). Must match build step.",
    )
    ap.add_argument("--out", default="data_processed/chunk_plan.json", help="Output json path (relative to root)")
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
    units_path = (root / args.units).resolve()
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not units_path.exists():
        print(f"[FATAL] units not found: {units_path}")
        return 2

    # Import the package build script to guarantee *exact* same logic.
    # NOTE: after src-layout refactor, repo root/build_chroma_index.py is only a wrapper.
    try:
        from mhy_ai_rag_data import build_chroma_index as mod

        ChunkConf = mod.ChunkConf
        iter_units = mod.iter_units
        should_index_unit = mod.should_index_unit
        build_chunks_from_unit = mod.build_chunks_from_unit
    except Exception as e:
        print(f"[FATAL] cannot import chunking logic from mhy_ai_rag_data.build_chroma_index: {e}")
        return 2

    include_media_stub = _bool(args.include_media_stub)
    conf = ChunkConf(max_chars=args.chunk_chars, overlap_chars=args.overlap_chars, min_chars=args.min_chunk_chars)

    planned_chunks = 0
    units_read = 0
    units_indexed = 0
    units_skipped = 0

    # type_breakdown[source_type] = {"indexed": x, "skipped": y, "chunks": z}
    type_breakdown: Dict[str, Dict[str, int]] = {}

    for unit in iter_units(units_path):
        units_read += 1
        st = str(unit.get("source_type", "") or "").lower()
        type_breakdown.setdefault(st, {"indexed": 0, "skipped": 0, "chunks": 0})

        if not should_index_unit(unit, include_media_stub):
            units_skipped += 1
            type_breakdown[st]["skipped"] += 1
            continue

        units_indexed += 1
        type_breakdown[st]["indexed"] += 1

        chunks, _ = build_chunks_from_unit(unit, conf)
        planned_chunks += len(chunks)
        type_breakdown[st]["chunks"] += len(chunks)

    report: Dict[str, Any] = {
        "root": str(root),
        "units_path": str(units_path),
        "planned_chunks": planned_chunks,
        "units_read": units_read,
        "units_indexed": units_indexed,
        "units_skipped": units_skipped,
        "chunk_conf": {
            "chunk_chars": args.chunk_chars,
            "overlap_chars": args.overlap_chars,
            "min_chunk_chars": args.min_chunk_chars,
        },
        "include_media_stub": include_media_stub,
        "type_breakdown": type_breakdown,
    }

    report_v2 = {
        "schema_version": 2,
        "generated_at": report.get("generated_at") or report.get("timestamp") or "",
        "tool": "plan_chunks_from_units",
        "root": str(root.as_posix()),
        "summary": {},
        "items": [
            {
                "tool": "plan_chunks_from_units",
                "title": "chunk_plan",
                "status_label": "PASS",
                "severity_level": 0,
                "message": (
                    f"units_read={units_read} units_indexed={units_indexed} units_skipped={units_skipped} "
                    f"planned_chunks={planned_chunks} include_media_stub={include_media_stub}"
                ),
                "detail": report,
            }
        ],
        "data": report,
    }

    write_report_bundle(
        report=report_v2,
        report_json=out_path,
        repo_root=root,
        console_title="plan_chunks_from_units",
        emit_console=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
