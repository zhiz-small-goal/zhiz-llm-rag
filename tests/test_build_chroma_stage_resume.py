from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from mhy_ai_rag_data.tools.build_chroma_index_flagembedding import read_wal


def _write_event(path: Path, obj: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def test_read_wal_marks_tail_truncated_and_tracks_committed_docs(tmp_path: Path) -> None:
    stage_file = tmp_path / "index_state.stage.jsonl"
    run_id = "run-1"
    base = {"run_id": run_id, "collection": "c1", "schema_hash": "abc", "db_path": "/db", "wal_version": 1}
    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:00Z",
            "seq": 1,
            "event": "RUN_START",
            **base,
        },
    )
    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:01Z",
            "seq": 2,
            "event": "DOC_COMMITTED",
            "source_uri": "u1",
            "doc_id": "d1",
            "content_sha256": "sha-new",
            "n_chunks": 2,
            "updated_at": "2026-01-22T00:00:01Z",
            **base,
        },
    )
    # truncated line
    with open(stage_file, "a", encoding="utf-8") as f:
        f.write("{\n")

    wal = read_wal(stage_file, collection="c1", schema_hash="abc", db_path_posix="/db")
    assert wal is not None
    assert wal.run_id == run_id
    assert wal.truncated_tail_ignored is True
    assert wal.finished_ok is False
    assert wal.last_event == "DOC_COMMITTED"
    assert wal.committed_batches == 0
    assert wal.upsert_rows_committed_total == 0
    assert "u1" in wal.done_docs
    assert wal.done_docs["u1"].doc_id == "d1"
    assert wal.done_docs["u1"].content_sha256 == "sha-new"
    assert wal.done_docs["u1"].n_chunks == 2


def test_read_wal_tracks_batches_and_finish(tmp_path: Path) -> None:
    stage_file = tmp_path / "index_state.stage.jsonl"
    run_id = "run-status"
    base = {"run_id": run_id, "collection": "c1", "schema_hash": "abc", "db_path": "/db", "wal_version": 1}
    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:00Z",
            "seq": 1,
            "event": "RUN_START",
            "sync_mode": "incremental",
            **base,
        },
    )
    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:02Z",
            "seq": 2,
            "event": "UPSERT_BATCH_COMMITTED",
            "batch_size": 2,
            "upsert_rows_committed_total": 2,
            **base,
        },
    )
    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:03Z",
            "seq": 3,
            "event": "DOC_DONE",
            "source_uri": "u2",
            "doc_id": "d2",
            "content_sha256": "sha-2",
            "n_chunks": 2,
            "updated_at": "2026-01-22T00:00:03Z",
            **base,
        },
    )

    _write_event(
        stage_file,
        {
            "ts": "2026-01-22T00:00:04Z",
            "seq": 4,
            "event": "RUN_FINISH",
            "ok": True,
            **base,
        },
    )

    wal = read_wal(stage_file, collection="c1", schema_hash="abc", db_path_posix="/db")
    assert wal is not None
    assert wal.run_id == run_id
    assert wal.finished_ok is True
    assert wal.last_event == "RUN_FINISH"
    assert wal.committed_batches == 1
    assert wal.upsert_rows_committed_total == 2
    assert "u2" in wal.done_docs
    assert wal.done_docs["u2"].doc_id == "d2"
