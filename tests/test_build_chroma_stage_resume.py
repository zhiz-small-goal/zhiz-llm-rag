from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from mhy_ai_rag_data.tools.build_chroma_index_flagembedding import (
    DOC_EVENT_DOC_COMMITTED,
    DOC_EVENT_DOC_DONE,
    DOC_EVENT_UPSERT_NEW_DONE,
    _load_stage,
    _print_resume_status,
)


def _write_event(path: Path, obj: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def test_load_stage_marks_tail_truncated_and_merges_doc_events(tmp_path: Path) -> None:
    stage_file = tmp_path / "index_state.stage.jsonl"
    run_id = "run-1"
    _write_event(
        stage_file,
        {
            "t": "RUN_START",
            "run_id": run_id,
            "ts": "2026-01-22T00:00:00Z",
            "wal_version": 2,
            "schema_hash": "abc",
            "collection": "c1",
            "db_path": "/db",
        },
    )
    _write_event(
        stage_file,
        {
            "t": DOC_EVENT_DOC_COMMITTED,
            "run_id": run_id,
            "ts": "2026-01-22T00:00:01Z",
            "uri": "u1",
            "doc_id": "d1",
            "content_sha256": "sha-new",
            "old_content_sha256": "sha-old",
            "n_chunks": 2,
            "chunks_upserted_total": 2,
        },
    )
    # truncated line
    with open(stage_file, "a", encoding="utf-8") as f:
        f.write("{\n")

    stage = _load_stage(stage_file)
    assert stage["tail_truncated"] is True
    assert stage["wal_version"] == 2
    assert stage["committed_batches"] == 0
    done = stage["done"]
    assert "u1" in done
    assert done["u1"]["last_event"] == DOC_EVENT_DOC_COMMITTED
    assert done["u1"]["content_sha256"] == "sha-new"
    assert done["u1"]["old_content_sha256"] == "sha-old"


def test_resume_status_prints_summary(capsys: Any, tmp_path: Path) -> None:
    stage_file = tmp_path / "index_state.stage.jsonl"
    run_id = "run-status"
    _write_event(
        stage_file,
        {
            "t": "RUN_START",
            "run_id": run_id,
            "ts": "2026-01-22T00:00:00Z",
            "wal_version": 2,
            "schema_hash": "abc",
            "collection": "c1",
            "db_path": "/db",
            "sync_mode": "incremental",
        },
    )
    _write_event(
        stage_file,
        {
            "t": "UPSERT_BATCH_COMMITTED",
            "run_id": run_id,
            "ts": "2026-01-22T00:00:02Z",
            "batch_size": 2,
            "chunks_upserted_total": 2,
        },
    )
    _write_event(
        stage_file,
        {
            "t": DOC_EVENT_UPSERT_NEW_DONE,
            "run_id": run_id,
            "ts": "2026-01-22T00:00:03Z",
            "uri": "u2",
            "doc_id": "d2",
            "content_sha256": "sha-2",
            "old_content_sha256": "sha-old2",
            "n_chunks": 2,
            "chunks_upserted_total": 2,
            "source_type": "md",
        },
    )
    _write_event(
        stage_file,
        {
            "t": DOC_EVENT_DOC_DONE,
            "run_id": run_id,
            "ts": "2026-01-22T00:00:04Z",
            "uri": "u2",
            "doc_id": "d2",
            "content_sha256": "sha-2",
            "n_chunks": 2,
            "chunks_upserted_total": 2,
        },
    )

    stage = _load_stage(stage_file)
    rc = _print_resume_status(
        stage_file=stage_file, stage=stage, collection="c1", schema_hash="abc", db_path=Path("/db")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "done_docs=1" in out
    assert "committed_batches=1" in out
    assert "chunks_upserted_total_last=2" in out
    assert "run_start: ts=2026-01-22T00:00:00Z" in out
    assert "uri=u2" in out
