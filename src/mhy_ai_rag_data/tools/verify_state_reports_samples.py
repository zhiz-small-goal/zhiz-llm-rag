#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_state_reports_samples.py

目的：
- 为 index_state / db_build_stamp 这类“状态元数据报告”提供一个固定样例的契约自检。
- 不依赖 Chroma 或外部服务；仅验证 report-output-v2 的结构与渲染约束。

退出码：
- 0 PASS
- 2 FAIL
- 3 ERROR

用法（CMD）：
  python tools/verify_state_reports_samples.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from mhy_ai_rag_data.project_paths import find_project_root
from mhy_ai_rag_data.tools import index_state
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output
from mhy_ai_rag_data.tools.verify_report_output_contract import verify


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sample_db_build_stamp_v2(*, root: Path) -> Dict[str, Any]:
    tool_name = "write_db_build_stamp"
    items = [
        ensure_item_fields(
            {
                "tool": tool_name,
                "key": "sample_stamp",
                "title": "db_build_stamp sample",
                "status_label": "PASS",
                "severity_level": 0,
                "message": "sample db_build_stamp report (contract check)",
                "detail": {"collection": "rag_chunks", "collection_count": 3},
            },
            tool_default=tool_name,
        )
    ]

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_name,
        "root": str(root.resolve().as_posix()),
        "summary": compute_summary(items).to_dict(),
        "items": items,
        "db": "data_processed/chroma_db",
        "collection": "rag_chunks",
        "collection_count": 3,
        "writer": "sample",
        "state_root": "data_processed/index_state",
    }

    out = prepare_report_for_file_output(report)
    if not isinstance(out, dict):
        raise RuntimeError("prepare_report_for_file_output did not return dict")
    return out


def main() -> int:
    try:
        root = find_project_root().resolve()

        out_dir = root / "data_processed" / "build_reports" / "_selftest_state_reports"

        # 1) legacy v1-like index_state -> normalized v2
        legacy_v1: Dict[str, Any] = {
            "schema_hash": "deadbeef" * 8,
            "updated_at": "2026-01-01T00:00:00Z",
            "docs": {
                "file://sample.txt": {
                    "doc_id": "doc_1",
                    "source_uri": "file://sample.txt",
                    "source_type": "file",
                    "content_sha256": "0" * 64,
                    "n_chunks": 2,
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            },
        }

        normalized_v2 = index_state.ensure_index_state_report_v2(
            legacy_v1,
            root=root,
            state_file=out_dir / "index_state_v1_legacy.json",
        )
        normalized_v2 = prepare_report_for_file_output(normalized_v2)
        if not isinstance(normalized_v2, dict):
            raise RuntimeError("prepare_report_for_file_output did not return dict")

        p1 = out_dir / "index_state_from_v1.sample.json"
        _write_json(p1, normalized_v2)

        r1 = verify(report=normalized_v2, report_path=p1, repo_root=root, strict=True)
        if r1.errors:
            print("[FAIL] index_state normalized-from-v1 sample failed")
            for e in r1.errors:
                print("  -", e)
            return 2

        # 2) v2 index_state written by SSOT writer
        docs = {
            "file://sample2.txt": {
                "doc_id": "doc_2",
                "source_uri": "file://sample2.txt",
                "source_type": "file",
                "content_sha256": "1" * 64,
                "n_chunks": 1,
                "updated_at": "2026-01-02T00:00:00Z",
            }
        }

        last_build = {
            "sync_mode": "sample",
            "units_total": 1,
            "units_indexed": 1,
            "units_skipped": 0,
            "docs_current": 1,
            "docs_processed": 1,
            "docs_deleted": 0,
            "chunks_deleted": 0,
            "chunks_upserted": 1,
            "expected_chunks": 1,
            "collection_count": 1,
            "build_seconds": 0.1,
        }

        p2 = index_state.write_index_state_report(
            root=root,
            state_root=out_dir / "state_root",
            collection="rag_chunks",
            schema_hash="cafebabe" * 8,
            db=out_dir / "chroma_db",
            embed_model="sample-model",
            chunk_conf={"chunk_chars": 256, "overlap": 32, "min_chunk_chars": 64},
            include_media_stub=False,
            docs=docs,
            last_build=last_build,
            items=[
                {
                    "tool": "index_state",
                    "key": "sample_state",
                    "title": "index_state sample",
                    "status_label": "PASS",
                    "severity_level": 0,
                    "message": "sample index_state report (contract check)",
                    "detail": {"docs": 1, "expected_chunks": 1},
                }
            ],
        )

        v2_written = json.loads(p2.read_text(encoding="utf-8"))
        if not isinstance(v2_written, dict):
            raise RuntimeError("index_state written report is not object")

        r2 = verify(report=v2_written, report_path=p2, repo_root=root, strict=True)
        if r2.errors:
            print("[FAIL] index_state v2-written sample failed")
            for e in r2.errors:
                print("  -", e)
            return 2

        # 3) db_build_stamp v2 sample
        stamp = _sample_db_build_stamp_v2(root=root)
        p3 = out_dir / "db_build_stamp.sample.json"
        _write_json(p3, stamp)

        r3 = verify(report=stamp, report_path=p3, repo_root=root, strict=True)
        if r3.errors:
            print("[FAIL] db_build_stamp sample failed")
            for e in r3.errors:
                print("  -", e)
            return 2

        print("[PASS] state report samples ok")
        print(f"[PASS] wrote samples under: {out_dir.as_posix()}")
        return 0

    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
