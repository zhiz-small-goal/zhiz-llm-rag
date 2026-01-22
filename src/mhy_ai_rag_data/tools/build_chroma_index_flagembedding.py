#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_chroma_index_flagembedding.py

目标：
- 继续使用 FlagEmbedding(BGE-M3) 写入 Chroma（PersistentClient）。
- 在“强一致验收（expected_chunks == embeddings_in_collection）”前提下，提供可扩展的同步语义（sync）：
  - sync-mode=none：只 upsert（旧条目不会自动删除；可能导致 count 漂移）
  - sync-mode=delete-stale：对删除/变更文档先删除旧 chunk_id 再全量 upsert（稳定但仍 O(N) embedding）
  - sync-mode=incremental：对删除/变更文档删除旧 chunk_id，只对新增/变更文档 embedding+upsert（长期 O(Δ)）

核心约束（与你项目现有的 check_chroma_build.py 对齐）：
- chunk_id 生成策略：chunk_id = f"{doc_id}:{chunk_index}"（与 build_chroma_index.py 一致）
- chunk_conf/include_media_stub/embed_model 任一变化会触发 schema_hash 变化（建议视为“新索引版本”）

状态文件（manifest/index_state）：
- 默认写入：data_processed/index_state/<collection>/<schema_hash>/index_state.json
- 并写入：data_processed/index_state/<collection>/LATEST 指针

注意：
- 删除操作 collection.delete(ids=...) 属于 destructive；脚本默认仅在能定位到“上一轮该文档的 n_chunks”时删除。
- 若找不到 state 但 collection 已非空，默认执行“重置 collection 后全量构建”（可用参数调整）。
"""

from __future__ import annotations

from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args

import argparse
import time
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "build_chroma_index_flagembedding",
    "kind": "INDEX_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": True,
    "supports_selftest": True,
    "entrypoint": "python tools/build_chroma_index_flagembedding.py",
}


# Chroma metadata values are scalars, but stubs also allow SparseVector; keep Any for compatibility.
MetaValue = Any

WAL_VERSION = 2

DOC_EVENT_DOC_BEGIN = "DOC_BEGIN"
DOC_EVENT_DELETE_OLD_DONE = "DELETE_OLD_DONE"
DOC_EVENT_UPSERT_NEW_DONE = "UPSERT_NEW_DONE"
DOC_EVENT_DOC_COMMITTED = "DOC_COMMITTED"
DOC_EVENT_DOC_DONE = "DOC_DONE"
DOC_EVENT_DELETE_STALE_DONE = "DELETE_STALE_DONE"

DOC_EVENT_TYPES = {
    DOC_EVENT_DOC_BEGIN,
    DOC_EVENT_DELETE_OLD_DONE,
    DOC_EVENT_UPSERT_NEW_DONE,
    DOC_EVENT_DOC_COMMITTED,
    DOC_EVENT_DOC_DONE,
    DOC_EVENT_DELETE_STALE_DONE,
}

DOC_FINAL_SKIP_EVENTS = {DOC_EVENT_DOC_COMMITTED, DOC_EVENT_DOC_DONE, DOC_EVENT_UPSERT_NEW_DONE}
DOC_DELETE_SKIP_EVENTS = {
    DOC_EVENT_DELETE_OLD_DONE,
    DOC_EVENT_UPSERT_NEW_DONE,
    DOC_EVENT_DOC_COMMITTED,
    DOC_EVENT_DOC_DONE,
}
DOC_INITIATED_EVENTS = DOC_DELETE_SKIP_EVENTS | {DOC_EVENT_DOC_BEGIN}


def _merge_doc_event(done: Dict[str, Any], ev: Dict[str, Any], event_type: str) -> None:
    uri = str(ev.get("uri") or "")
    if not uri:
        return
    entry: Dict[str, Any] = dict(done.get(uri) or {})
    entry["doc_id"] = str(ev.get("doc_id") or entry.get("doc_id") or "")
    content_sha = ev.get("content_sha256")
    if content_sha is not None:
        entry["content_sha256"] = str(content_sha)
    old_content_sha = ev.get("old_content_sha256")
    if old_content_sha is not None:
        entry["old_content_sha256"] = str(old_content_sha)
    n_chunks = ev.get("n_chunks")
    if n_chunks is not None:
        try:
            entry["n_chunks"] = int(n_chunks)
        except Exception:
            entry["n_chunks"] = int(entry.get("n_chunks") or 0)
    chunks_total = ev.get("chunks_upserted_total")
    if chunks_total is not None:
        try:
            entry["chunks_upserted_total"] = int(chunks_total)
        except Exception:
            entry["chunks_upserted_total"] = int(entry.get("chunks_upserted_total") or 0)
    source_type = ev.get("source_type")
    if source_type is not None:
        entry["source_type"] = str(source_type)
    updated_at = ev.get("updated_at")
    if updated_at is not None:
        entry["updated_at"] = str(updated_at)
    entry["last_event"] = event_type
    entry["ts"] = str(ev.get("ts") or entry.get("ts") or "")
    done[uri] = entry


def _print_resume_status(
    *,
    stage_file: Path,
    stage: Dict[str, Any],
    collection: str,
    schema_hash: str,
    db_path: Path,
) -> int:
    print("=== RESUME STATUS (stage/WAL) ===")
    print(f"stage_file={stage_file}")
    print(f"db_path={db_path}")
    print(f"collection={collection} schema_hash={schema_hash}")
    if not stage.get("exists"):
        print("[INFO] stage not found; nothing to resume.")
        return 0
    run_id = str(stage.get("run_id") or "")
    wal_version = int(stage.get("wal_version") or 1)
    print(f"run_id={run_id} wal_version={wal_version} finished_ok={stage.get('finished_ok')}")
    print(
        f"done_docs={len(stage.get('done') or {})} committed_batches={stage.get('committed_batches', 0)}"
        f" chunks_upserted_total_last={stage.get('chunks_upserted_total_last', 0)} tail_truncated={bool(stage.get('tail_truncated'))}"
    )
    run_start = stage.get("run_start") or {}
    if run_start:
        print(
            f"run_start: ts={run_start.get('ts')} sync_mode={run_start.get('sync_mode')} "
            f"db_path={run_start.get('db_path')} collection={run_start.get('collection')} schema_hash={run_start.get('schema_hash')}"
        )
    done = stage.get("done") or {}
    sample = list(sorted(done.items()))[:3]
    if sample:
        print("done_sample:")
        for uri, ev in sample:
            print(
                f"  uri={uri} last_event={ev.get('last_event')} sha={ev.get('content_sha256')} "
                f"old_sha={ev.get('old_content_sha256')} n_chunks={ev.get('n_chunks')} chunks_total={ev.get('chunks_upserted_total')}"
            )
    return 0


# -------- shared loader --------


def _load_build_logic() -> Any:
    """Import shared chunking/indexing logic from the installed package.

    Why: repo root/build_chroma_index.py is a compatibility wrapper after the src-layout refactor;
    the authoritative implementation lives in mhy_ai_rag_data.build_chroma_index.
    """
    from mhy_ai_rag_data import build_chroma_index as mod

    return mod


def _chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}:{idx}"


def _batched(seq: List[str], batch_size: int) -> Any:
    for i in range(0, len(seq), batch_size):
        yield seq[i : i + batch_size]


def _safe_bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


# -------- stage checkpoint (resume) --------


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append_jsonl(path: Path, obj: Dict[str, Any], *, fsync: bool = True) -> None:
    """Append one JSON line and optionally fsync for crash-safety."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        if fsync:
            os.fsync(f.fileno())


def _load_stage(path: Path) -> Dict[str, Any]:
    """Load stage checkpoint.

    Format: JSONL events. We only consider the latest RUN_START segment.
    """
    out: Dict[str, Any] = {
        "exists": False,
        "run_start": None,
        "run_id": None,
        "finished_ok": None,
        "done": {},  # uri -> {content_sha256, doc_id, n_chunks, updated_at}
        "wal_version": 1,
        "committed_batches": 0,
        "chunks_upserted_total_last": 0,
        "tail_truncated": False,
    }
    if not path.exists():
        return out
    out["exists"] = True
    cur_run_id: Optional[str] = None
    cur_start: Optional[Dict[str, Any]] = None
    done: Dict[str, Any] = {}
    finished_ok: Optional[bool] = None
    wal_version = 1
    committed_batches = 0
    chunks_total = 0
    tail_truncated = False

    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    # tolerate partial/corrupt tail; resume will fall back to fewer done entries
                    tail_truncated = True
                    continue
                t = str(ev.get("t") or "")
                if t == "RUN_START":
                    cur_run_id = str(ev.get("run_id") or "")
                    cur_start = dict(ev)
                    done = {}
                    finished_ok = None
                    committed_batches = 0
                    chunks_total = 0
                    wal_version = int(ev.get("wal_version") or wal_version or 1)
                    continue
                if not cur_run_id:
                    continue
                if str(ev.get("run_id") or "") != cur_run_id:
                    continue
                if t == "UPSERT_BATCH_COMMITTED":
                    committed_batches += 1
                    chunks_total = int(ev.get("chunks_upserted_total") or chunks_total)
                    continue
                if t in DOC_EVENT_TYPES:
                    _merge_doc_event(done, ev, t)
                    continue
                if t == "RUN_FINISH":
                    finished_ok = bool(ev.get("ok"))
                    continue
    except Exception:
        # If stage can't be read, treat as non-existent to avoid unsafe skips.
        return {
            "exists": False,
            "run_start": None,
            "run_id": None,
            "finished_ok": None,
            "done": {},
        }

    out["run_start"] = cur_start
    out["run_id"] = cur_run_id
    out["finished_ok"] = finished_ok
    out["done"] = done
    out["wal_version"] = wal_version
    out["committed_batches"] = committed_batches
    out["chunks_upserted_total_last"] = chunks_total
    out["tail_truncated"] = tail_truncated
    return out


def _stage_matches_run(
    stage_start: Optional[Dict[str, Any]], *, db_path: Path, collection: str, schema_hash: str
) -> bool:
    if not stage_start:
        return False
    if str(stage_start.get("schema_hash") or "") != str(schema_hash):
        return False
    if str(stage_start.get("collection") or "") != str(collection):
        return False
    if str(stage_start.get("db_path") or "") != str(db_path.as_posix()):
        return False
    return True


# -------- main --------


def main() -> int:
    # Two-pass parse: make `--selftest` work without requiring a subcommand.
    pre = argparse.ArgumentParser(add_help=False)
    add_selftest_args(pre)
    pre.add_argument("--root", default=".", help="Project root")
    pre_args, _ = pre.parse_known_args()

    _repo_root = Path(getattr(pre_args, "root", ".")).resolve()
    _loc = Path(__file__).resolve()
    try:
        _loc = _loc.relative_to(_repo_root)
    except Exception:
        pass

    _rc = maybe_run_selftest_from_args(args=pre_args, meta=REPORT_TOOL_META, repo_root=_repo_root, loc_source=_loc)
    if _rc is not None:
        return _rc

    ap = argparse.ArgumentParser(
        description="Build/Upsert Chroma index using FlagEmbedding (BGE-M3) with optional sync."
    )
    add_selftest_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build/upsert collection")
    b.add_argument("--root", default=".", help="Project root")
    b.add_argument("--units", default="data_processed/text_units.jsonl")
    b.add_argument("--db", default="chroma_db")
    b.add_argument("--collection", default="rag_chunks")
    b.add_argument(
        "--plan", default=None, help="Optional: chunk_plan.json path used only for db_build_stamp traceability."
    )

    b.add_argument("--embed-model", default="BAAI/bge-m3")
    b.add_argument("--device", default="cpu")
    b.add_argument("--embed-batch", type=int, default=32)
    b.add_argument("--upsert-batch", type=int, default=256)

    b.add_argument("--chunk-chars", type=int, default=1200)
    b.add_argument("--overlap-chars", type=int, default=120)
    b.add_argument("--min-chunk-chars", type=int, default=200)
    b.add_argument("--include-media-stub", action="store_true", help="index media stubs too")
    b.add_argument("--hnsw-space", default="cosine", help="cosine/l2/ip (stored in collection metadata)")

    # sync / state
    b.add_argument(
        "--sync-mode",
        default="incremental",
        choices=["none", "delete-stale", "incremental"],
        help="Sync semantics: none/upsert-only; delete-stale=delete old per-doc then full upsert; incremental=delete old per-doc and only embed changed docs.",
    )
    b.add_argument(
        "--state-root",
        default="data_processed/index_state",
        help="Directory to store index_state/manifest (relative to root).",
    )
    b.add_argument(
        "--on-missing-state",
        default="reset",
        choices=["reset", "fail", "full-upsert"],
        help="If state missing but collection is non-empty: reset collection / fail / proceed with full upsert (may keep stale).",
    )
    b.add_argument(
        "--schema-change",
        default="reset",
        choices=["reset", "fail"],
        help="If schema_hash differs from LATEST pointer: reset collection (recommended) or fail.",
    )
    b.add_argument("--delete-batch", type=int, default=5000, help="Batch size for collection.delete(ids=...).")
    b.add_argument(
        "--strict-sync", default="true", help="true/false: fail if collection.count != expected_chunks after build."
    )
    b.add_argument("--write-state", default="true", help="true/false: write index_state.json after successful build.")
    b.add_argument(
        "--resume",
        default="auto",
        choices=["auto", "on", "off"],
        help="Resume semantics for interrupted builds: auto=use stage if present and also write stage for future resume; on=force stage+resume; off=disable stage/resume.",
    )
    b.add_argument(
        "--stage-fsync",
        default="doc",
        help="off/doc/interval (legacy true/false) fsync strategy when writing the stage/WAL file.",
    )
    b.add_argument(
        "--stage-fsync-interval",
        type=int,
        default=10,
        help="When --stage-fsync=interval, fsync every N events (>=1) to balance safety/IO.",
    )
    b.add_argument(
        "--resume-status",
        action="store_true",
        help="Print resume/WAL status for this collection/schema and exit without running build.",
    )

    args = ap.parse_args()

    root = Path(args.root).resolve()
    units_path = (root / args.units).resolve()
    include_media_stub = bool(args.include_media_stub)

    # 0.5) state invariants (available to --resume-status)
    chunk_conf_dict = {
        "chunk_chars": int(args.chunk_chars),
        "overlap_chars": int(args.overlap_chars),
        "min_chunk_chars": int(args.min_chunk_chars),
    }

    try:
        from mhy_ai_rag_data.tools import index_state as ist
    except Exception as e:
        print(f"[FATAL] cannot import mhy_ai_rag_data.tools.index_state: {e}")
        return 2

    schema_hash = ist.compute_schema_hash(
        embed_model=str(args.embed_model),
        chunk_conf=chunk_conf_dict,
        include_media_stub=include_media_stub,
        id_strategy_version=1,
    )

    state_root = (root / args.state_root).resolve()
    state_file = ist.state_file_for(state_root, args.collection, schema_hash)
    stage_file = state_file.parent / "index_state.stage.jsonl"
    db_path = (root / args.db).resolve()

    if getattr(args, "resume_status", False):
        stage = _load_stage(stage_file)
        return _print_resume_status(
            stage_file=stage_file,
            stage=stage,
            collection=str(args.collection),
            schema_hash=schema_hash,
            db_path=db_path,
        )

    if not units_path.exists():
        print(f"[FATAL] units not found: {units_path}")
        return 2

    # 1) load shared logic (same as build_chroma_index.py)
    try:
        mod = _load_build_logic()
        ChunkConf = mod.ChunkConf
        iter_units = mod.iter_units
        should_index_unit = mod.should_index_unit
        build_chunks_from_unit = mod.build_chunks_from_unit
        normalize_dense = getattr(mod, "normalize_dense", None)
    except Exception as e:
        print(f"[FATAL] cannot import chunking logic: {e}")
        return 2

    # 2) load embedding model
    try:
        from FlagEmbedding import BGEM3FlagModel
    except Exception as e:
        print(
            '[FATAL] FlagEmbedding not installed. Install: pip install -e .[embed]  (or pip install ".[embed]" on bash)'
        )
        print(str(e))
        return 2

    model = None
    try:
        # Newer versions may support device kw; keep best-effort.
        model = BGEM3FlagModel(args.embed_model, use_fp16=True, device=str(args.device))
    except TypeError:
        model = BGEM3FlagModel(args.embed_model, use_fp16=True)
        print(
            f"[WARN] BGEM3FlagModel() 不支持 device=，已回退为默认 device；你指定的 --device={args.device} 可能未生效。"
        )

    def _require_chromadb() -> Any:
        """Import chromadb only when needed."""
        try:
            import chromadb

            return chromadb
        except ImportError as e:
            print("Failed to import chromadb. Please install chromadb: pip install chromadb")
            raise ImportError("chromadb not installed. Install: pip install chromadb") from e

    # 3) init chroma
    try:
        chromadb_mod = _require_chromadb()
        chromadb = chromadb_mod
        Settings = chromadb_mod.config.Settings
    except Exception as e:
        print('[FATAL] chromadb not installed. Install: pip install -e .[embed]  (or pip install ".[embed]" on bash)')
        print(str(e))
        return 2

    db_path = (root / args.db).resolve()
    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path), settings=Settings(anonymized_telemetry=False))

    # collection
    col_meta = {"hnsw:space": str(args.hnsw_space)}
    try:
        collection = client.get_or_create_collection(name=args.collection, metadata=col_meta)
    except TypeError:
        collection = client.get_or_create_collection(name=args.collection)

    conf = ChunkConf(max_chars=args.chunk_chars, overlap_chars=args.overlap_chars, min_chars=args.min_chunk_chars)

    # 4) state / schema hash
    latest = ist.read_latest_pointer(state_root, args.collection)
    if latest and latest != schema_hash:
        msg = f"[SCHEMA] LATEST={latest} != current={schema_hash} (embed_model/chunk_conf/include_media_stub changed)"
        if args.schema_change == "fail":
            print("[FATAL] " + msg)
            return 2
        print("[WARN] " + msg)
        print("[WARN] schema-change=reset -> will reset collection and create a new state version")
        # Reset collection: easiest to guarantee correctness
        try:
            client.delete_collection(name=args.collection)
        except Exception as e:
            # If delete_collection is unavailable or fails, fall back to drop-and-recreate via db dir is NOT safe here.
            print(f"[FATAL] failed to delete_collection(name={args.collection}): {e}")
            return 2
        try:
            collection = client.get_or_create_collection(name=args.collection, metadata=col_meta)
        except TypeError:
            collection = client.get_or_create_collection(name=args.collection)
        latest = None  # treat as fresh

    state_file = ist.state_file_for(state_root, args.collection, schema_hash)
    prev_state = ist.load_index_state(state_file, root=root)
    existing_count = 0
    try:
        existing_count = int(collection.count())
    except Exception:
        existing_count = 0

    # 4.5) stage checkpoint (resume interrupted builds)
    resume_mode = str(getattr(args, "resume", "auto")).strip().lower()
    stage_enabled = resume_mode != "off"
    stage_file = state_file.parent / "index_state.stage.jsonl"
    run_id: Optional[str] = None
    stage_done: Dict[str, Any] = {}
    stage_event_seq = 0
    committed_batches_this_run = 0

    raw_fsync = str(getattr(args, "stage_fsync", "doc")).strip().lower()
    if raw_fsync in {"true", "doc"}:
        stage_fsync_mode = "doc"
    elif raw_fsync in {"false", "off"}:
        stage_fsync_mode = "off"
    elif raw_fsync == "interval":
        stage_fsync_mode = "interval"
    else:
        stage_fsync_mode = "doc"
    stage_fsync_interval = max(1, int(getattr(args, "stage_fsync_interval", 10)))

    def _stage_append_event(
        event_type: str, payload: Optional[Dict[str, Any]] = None, *, force_fsync: bool = False
    ) -> None:
        nonlocal stage_event_seq
        if not (stage_enabled and run_id):
            return
        stage_event_seq += 1
        event = {"t": event_type, "run_id": run_id, "ts": _utc_now_iso()}
        if payload:
            event.update(payload)
        do_fsync = False
        if stage_fsync_mode == "doc":
            do_fsync = True
        elif stage_fsync_mode == "interval":
            do_fsync = stage_event_seq % stage_fsync_interval == 0
        do_fsync = do_fsync or force_fsync
        _append_jsonl(stage_file, event, fsync=do_fsync)

    stage = (
        _load_stage(stage_file)
        if stage_enabled
        else {
            "exists": False,
            "run_start": None,
            "run_id": None,
            "finished_ok": None,
            "done": {},
            "wal_version": 1,
            "committed_batches": 0,
            "chunks_upserted_total_last": 0,
            "tail_truncated": False,
        }
    )

    stage_wal_version = int(stage.get("wal_version") or 1)
    resume_active = False
    if stage_enabled and stage.get("exists"):
        # If a previous run finished OK but stage cleanup was interrupted, clean it up.
        if stage.get("finished_ok") is True:
            try:
                stage_file.unlink(missing_ok=True)
            except TypeError:
                try:
                    if stage_file.exists():
                        stage_file.unlink()
                except Exception:
                    pass
            stage = {
                "exists": False,
                "run_start": None,
                "run_id": None,
                "finished_ok": None,
                "done": {},
                "wal_version": 1,
                "committed_batches": 0,
                "chunks_upserted_total_last": 0,
                "tail_truncated": False,
            }

    incompatible_wal = stage_enabled and stage.get("exists") and stage_wal_version > WAL_VERSION

    if stage_enabled and stage.get("exists") and not incompatible_wal:
        # Only resume when stage matches the same db/collection/schema and collection has data.
        if (
            _stage_matches_run(
                cast(Optional[Dict[str, Any]], stage.get("run_start")),
                db_path=db_path,
                collection=str(args.collection),
                schema_hash=schema_hash,
            )
            and existing_count > 0
        ):
            resume_active = True
            run_id = str(stage.get("run_id") or "") or None
            stage_done = cast(Dict[str, Any], stage.get("done") or {})
            print(
                f"[RESUME] detected stage checkpoint: file={stage_file.as_posix()} done_docs={len(stage_done)} collection_count={existing_count}"
            )
            if run_id:
                _stage_append_event(
                    "RUN_RESUME",
                    {
                        "db_path": db_path.as_posix(),
                        "collection": str(args.collection),
                        "schema_hash": schema_hash,
                        "wal_version": stage_wal_version,
                    },
                    force_fsync=True,
                )
        else:
            stage_done = {}
    elif incompatible_wal:
        print(f"[WARN] stage wal_version={stage_wal_version} > current={WAL_VERSION}; resume disabled for this run.")

    if stage_enabled and not resume_active:
        run_id = str(uuid.uuid4())
        _stage_append_event(
            "RUN_START",
            {
                "db_path": db_path.as_posix(),
                "collection": str(args.collection),
                "schema_hash": schema_hash,
                "sync_mode": str(args.sync_mode),
                "wal_version": WAL_VERSION,
            },
            force_fsync=True,
        )

    if stage_enabled:
        print(
            "[STAGE]"
            f" resume_active={resume_active}"
            f" wal_version={stage.get('wal_version', 1)}"
            f" run_id={run_id}"
            f" done_docs={len(stage_done)}"
            f" committed_batches={stage.get('committed_batches', 0)}"
            f" chunks_upserted_total_last={stage.get('chunks_upserted_total_last', 0)}"
            f" tail_truncated_ignored={bool(stage.get('tail_truncated'))}"
            f" stage_fsync_mode={stage_fsync_mode}"
            + (f" interval={stage_fsync_interval}" if stage_fsync_mode == "interval" else "")
        )

    # If state missing but collection non-empty, allow resume to proceed even when on-missing-state=reset.
    allow_missing_state_resume = bool(stage_enabled and resume_active and len(stage_done) > 0)

    if prev_state is None and existing_count > 0:
        # 状态缺失但库非空：无法可靠定位“多余 ids”，默认策略是 reset 后全量重建。
        policy = str(args.on_missing_state)
        if allow_missing_state_resume:
            print(
                "[WARN] index_state missing but stage checkpoint detected; override on-missing-state policy to full-upsert to continue resume"
            )
            policy = "full-upsert"
        print(f"[WARN] index_state missing but collection.count={existing_count}. policy={policy}")
        if policy == "fail":
            print("[FATAL] missing index_state + non-empty collection; refuse to proceed")
            return 2
        if policy == "reset":
            try:
                client.delete_collection(name=args.collection)
            except Exception as e:
                print(f"[FATAL] failed to delete_collection(name={args.collection}) on missing-state reset: {e}")
                return 2
            try:
                collection = client.get_or_create_collection(name=args.collection, metadata=col_meta)
            except TypeError:
                collection = client.get_or_create_collection(name=args.collection)
            existing_count = 0
        # full-upsert: proceed without reset (may keep stale)

    # 5) read current units (doc-level)
    cur_docs: Dict[str, Dict[str, Any]] = {}
    total_units = 0
    indexed_units = 0
    skipped_units = 0

    for unit in iter_units(units_path):
        total_units += 1
        if not should_index_unit(unit, include_media_stub=include_media_stub):
            skipped_units += 1
            continue

        indexed_units += 1
        source_uri = str(unit.get("source_uri") or "")
        if not source_uri:
            continue
        cur_docs[source_uri] = {
            "doc_id": str(unit.get("doc_id") or ""),
            "source_uri": source_uri,
            "source_type": str(unit.get("source_type") or ""),
            "content_sha256": str(unit.get("content_sha256") or ""),
            "updated_at": str(unit.get("updated_at") or ""),
            "unit": unit,  # keep reference for building
        }

    # 6) decide delta (based on prev_state manifest)
    prev_docs: Dict[str, Any] = {}
    if isinstance(prev_state, dict):
        prev_docs = dict(prev_state.get("docs", {}) or {})

    prev_uris = set(prev_docs.keys())
    cur_uris = set(cur_docs.keys())

    deleted_uris = sorted(prev_uris - cur_uris)
    added_uris = sorted(cur_uris - prev_uris)

    changed_uris: List[str] = []
    unchanged_uris: List[str] = []
    for uri in sorted(prev_uris & cur_uris):
        prev = prev_docs.get(uri) or {}
        if str(prev.get("content_sha256", "")) != str(cur_docs[uri].get("content_sha256", "")):
            changed_uris.append(uri)
        else:
            unchanged_uris.append(uri)

    sync_mode = str(args.sync_mode)
    if sync_mode == "none":
        # legacy: treat everything as "changed" to force full upsert (no delete)
        to_process_uris = sorted(cur_uris)
        do_delete = False
    elif sync_mode == "delete-stale":
        # stable sync: delete old for deleted + changed, then full upsert all current
        to_process_uris = sorted(cur_uris)
        do_delete = True
    else:
        # incremental: delete old for deleted + changed, embed only added+changed
        to_process_uris = sorted(set(added_uris) | set(changed_uris))
        do_delete = True

    # expected chunks (for strict check)
    expected_chunks = 0
    # for unchanged docs (incremental), expected comes from previous n_chunks
    if sync_mode == "incremental" and prev_state is not None:
        for uri in unchanged_uris:
            expected_chunks += int((prev_docs.get(uri) or {}).get("n_chunks", 0))

    # 7) delete stale per-doc chunks (no global ids enumeration)
    chunks_deleted = 0
    docs_deleted = 0

    def delete_doc_chunks(doc_id: str, n_chunks: int) -> int:
        if not doc_id or n_chunks <= 0:
            return 0
        ids: List[str] = [_chunk_id(doc_id, i) for i in range(int(n_chunks))]
        deleted = 0
        for batch in _batched(ids, int(args.delete_batch)):
            try:
                collection.delete(ids=batch)
            except Exception as e:
                print(f"[FATAL] collection.delete failed (doc_id={doc_id}, batch={len(batch)}): {e}")
                raise
            deleted += len(batch)
        return deleted

    if do_delete and prev_state is not None:
        # delete removed docs
        for uri in deleted_uris:
            prev = prev_docs.get(uri) or {}
            doc_id = str(prev.get("doc_id") or "")
            n_chunks = int(prev.get("n_chunks") or 0)
            try:
                deleted = delete_doc_chunks(doc_id, n_chunks)
                chunks_deleted += deleted
                docs_deleted += 1
            except Exception:
                return 2
            if stage_enabled and run_id:
                _stage_append_event(
                    DOC_EVENT_DELETE_STALE_DONE,
                    {
                        "uri": uri,
                        "doc_id": doc_id,
                        "old_content_sha256": str(prev.get("content_sha256") or ""),
                        "old_n_chunks": n_chunks,
                        "deleted_chunks": deleted,
                    },
                )

        # delete changed docs old chunks (important to avoid leftover ids when chunk count shrinks)
        for uri in changed_uris:
            prev = prev_docs.get(uri) or {}
            doc_id = str(prev.get("doc_id") or "")
            prev_n_chunks = int(prev.get("n_chunks") or 0)
            prev_sha = str(prev.get("content_sha256") or "")
            stage_doc = stage_done.get(uri) or {}
            stage_event = str(stage_doc.get("last_event") or "")
            delete_done = stage_event in DOC_DELETE_SKIP_EVENTS and stage_doc.get("old_content_sha256") == prev_sha
            cur_info = cur_docs.get(uri) or {}
            if delete_done:
                continue
            if stage_event not in DOC_INITIATED_EVENTS:
                _stage_append_event(
                    DOC_EVENT_DOC_BEGIN,
                    {
                        "uri": uri,
                        "doc_id": doc_id,
                        "content_sha256": str(cur_info.get("content_sha256") or ""),
                        "old_content_sha256": prev_sha,
                        "old_n_chunks": prev_n_chunks,
                        "source_type": str(cur_info.get("source_type") or ""),
                        "updated_at": str(cur_info.get("updated_at") or ""),
                    },
                )
            try:
                deleted = delete_doc_chunks(doc_id, prev_n_chunks)
                chunks_deleted += deleted
            except Exception:
                return 2
            if stage_enabled and run_id:
                _stage_append_event(
                    DOC_EVENT_DELETE_OLD_DONE,
                    {
                        "uri": uri,
                        "doc_id": doc_id,
                        "old_content_sha256": prev_sha,
                        "old_n_chunks": prev_n_chunks,
                        "deleted_chunks": deleted,
                        "source_type": str(cur_info.get("source_type") or ""),
                        "updated_at": str(cur_info.get("updated_at") or ""),
                    },
                )

    # 8) embed + upsert (for selected docs)
    ids_buf: List[str] = []
    docs_buf: List[str] = []
    metas_buf: List[Dict[str, MetaValue]] = []
    embeds_buf: List[List[float]] = []

    def l2_normalize(embs: Any) -> Any:
        import math

        out = []
        for v in embs:
            n = math.sqrt(sum((x * x for x in v))) or 1.0
            out.append([float(x) / n for x in v])
        return out

    def flush() -> None:
        nonlocal ids_buf, docs_buf, metas_buf, embeds_buf, committed_batches_this_run
        if not ids_buf:
            return
        vecs = embeds_buf
        if normalize_dense:
            vecs = normalize_dense(vecs)
        else:
            vecs = l2_normalize(vecs)

        # upsert
        metas_for_upsert = cast(List[Mapping[str, MetaValue]], metas_buf)
        collection.upsert(
            ids=ids_buf,
            documents=docs_buf,
            metadatas=metas_for_upsert,
            embeddings=vecs,
        )
        batch_size = len(ids_buf)
        ids_buf, docs_buf, metas_buf, embeds_buf = [], [], [], []

        if stage_enabled and run_id:
            _stage_append_event(
                "UPSERT_BATCH_COMMITTED",
                {
                    "batch_size": batch_size,
                    "chunks_upserted_total": chunks_upserted,
                },
            )
            committed_batches_this_run += 1

    t0 = time.perf_counter()

    # prepare new docs state mapping
    new_docs_state: Dict[str, Dict[str, Any]] = {}

    # first: carry over unchanged docs state (incremental mode)
    if sync_mode == "incremental" and prev_state is not None:
        for uri in unchanged_uris:
            prev = prev_docs.get(uri) or {}
            if prev:
                new_docs_state[uri] = dict(prev)

    chunks_upserted = 0
    docs_processed = 0
    docs_resumed_skipped = 0
    docs_checkpointed = 0

    for uri in to_process_uris:
        info = cur_docs.get(uri)
        if not info:
            continue

        stage_doc = stage_done.get(uri) or {}
        stage_event = str(stage_doc.get("last_event") or "")
        stage_sha = str(stage_doc.get("content_sha256") or "")
        cur_sha = str(info.get("content_sha256") or "")
        # Resume: skip docs already checkpointed as DONE for the same content_sha256.
        if (
            stage_enabled
            and resume_active
            and run_id
            and stage_doc
            and stage_event in DOC_FINAL_SKIP_EVENTS
            and stage_sha
            and cur_sha
            and stage_sha == cur_sha
        ):
            n_chunks = int(stage_doc.get("n_chunks") or 0)
            expected_chunks += n_chunks
            new_docs_state[uri] = {
                "doc_id": str(stage_doc.get("doc_id") or info.get("doc_id") or ""),
                "source_uri": uri,
                "source_type": str(info.get("source_type") or stage_doc.get("source_type") or ""),
                "content_sha256": cur_sha,
                "n_chunks": int(n_chunks),
                "updated_at": str(info.get("updated_at") or stage_doc.get("updated_at") or ""),
            }
            docs_processed += 1
            docs_resumed_skipped += 1
            if docs_resumed_skipped <= 3 or (docs_resumed_skipped % 200 == 0):
                print(f"[RESUME] skip done doc: uri={uri} n_chunks={n_chunks}")
            continue

        unit = info["unit"]
        chunk_texts, base_md = build_chunks_from_unit(unit, conf)
        # NOTE: build_chunks_from_unit may return [] for some corner cases; treat as 0 chunks.
        doc_id = str(base_md.get("doc_id") or info.get("doc_id") or "")
        n_chunks = len(chunk_texts or [])
        expected_chunks += n_chunks

        # update state for this doc
        new_docs_state[uri] = {
            "doc_id": doc_id,
            "source_uri": uri,
            "source_type": str(info.get("source_type") or ""),
            "content_sha256": str(info.get("content_sha256") or ""),
            "n_chunks": int(n_chunks),
            "updated_at": str(info.get("updated_at") or ""),
        }

        if not chunk_texts:
            # No chunks: still treat the doc as processed and checkpoint it for resume.
            if stage_enabled and run_id:
                payload = {
                    "uri": uri,
                    "doc_id": doc_id,
                    "content_sha256": str(info.get("content_sha256") or ""),
                    "n_chunks": 0,
                    "chunks_upserted_total": chunks_upserted,
                    "source_type": str(info.get("source_type") or ""),
                    "updated_at": str(info.get("updated_at") or ""),
                }
                _stage_append_event(DOC_EVENT_DOC_COMMITTED, payload)
                _stage_append_event(DOC_EVENT_DOC_DONE, payload)
                docs_checkpointed += 1
            docs_processed += 1
            continue

        # Embed chunk_texts in batches
        for i in range(0, len(chunk_texts), args.embed_batch):
            batch_texts = chunk_texts[i : i + args.embed_batch]

            # embeddings
            try:
                out = model.encode(
                    batch_texts,
                    batch_size=len(batch_texts),
                    max_length=8192,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )
                dense = out["dense_vecs"]
            except Exception as e:
                print(f"[FATAL] embedding failed for doc={uri}: {e}")
                return 2

            for j, ct in enumerate(batch_texts):
                idx = i + j
                cid = _chunk_id(doc_id, idx)
                md = dict(base_md)
                md["chunk_index"] = idx
                md["chunk_chars"] = len(ct)
                # keep stable source_uri for downstream debug
                md["source_uri"] = uri

                ids_buf.append(cid)
                docs_buf.append(ct)
                metas_buf.append(md)

                vec = dense[j]
                embeds_buf.append([float(x) for x in vec])

                chunks_upserted += 1
                if len(ids_buf) >= args.upsert_batch:
                    flush()

        # Ensure this doc's chunks have been upserted before checkpointing.
        if stage_enabled and run_id:
            flush()
            payload = {
                "uri": uri,
                "doc_id": doc_id,
                "content_sha256": str(info.get("content_sha256") or ""),
                "n_chunks": int(n_chunks),
                "chunks_upserted_total": chunks_upserted,
                "source_type": str(info.get("source_type") or ""),
                "updated_at": str(info.get("updated_at") or ""),
            }
            _stage_append_event(DOC_EVENT_UPSERT_NEW_DONE, payload)
            _stage_append_event(DOC_EVENT_DOC_COMMITTED, payload)
            _stage_append_event(DOC_EVENT_DOC_DONE, payload)
            docs_checkpointed += 1

        docs_processed += 1

    flush()

    dt = time.perf_counter() - t0

    # 9) strict sync check (optional)
    strict_sync = _safe_bool(args.strict_sync)
    final_count = None
    try:
        final_count = int(collection.count())
    except Exception:
        final_count = None

    ok = True
    if strict_sync and final_count is not None:
        if final_count != expected_chunks:
            ok = False

    # 10) write state (only on success)
    write_state = _safe_bool(args.write_state)
    if ok and write_state:
        # NOTE: index_state 作为状态元数据，也纳入 schema_version=2 report output 契约（写入侧 SSOT 在 index_state.py）。
        tool_name = "index_state"

        raw_items: list[dict[str, Any]] = []
        raw_items.append(
            {
                "tool": tool_name,
                "key": "state_written",
                "title": "index_state written",
                "status_label": "PASS",
                "severity_level": 0,
                "message": f"wrote {state_file.as_posix()} (collection={args.collection} schema_hash={schema_hash})",
                "detail": {
                    "state_file": state_file.as_posix(),
                    "collection": str(args.collection),
                    "schema_hash": schema_hash,
                    "sync_mode": sync_mode,
                    "docs_current": len(cur_docs),
                    "docs_processed": docs_processed,
                    "expected_chunks": expected_chunks,
                    "collection_count": final_count,
                    "build_seconds": round(float(dt), 3),
                },
            }
        )

        if final_count is None:
            raw_items.append(
                {
                    "tool": tool_name,
                    "key": "collection_count_unavailable",
                    "title": "collection.count unavailable",
                    "status_label": "WARN",
                    "severity_level": 2,
                    "message": "collection.count() unavailable (count is None)",
                    "detail": {"db_path": db_path.as_posix(), "collection": str(args.collection)},
                }
            )

        last_build = {
            "sync_mode": sync_mode,
            "units_total": total_units,
            "units_indexed": indexed_units,
            "units_skipped": skipped_units,
            "docs_current": len(cur_docs),
            "docs_processed": docs_processed,
            "docs_deleted": docs_deleted,
            "chunks_deleted": chunks_deleted,
            "chunks_upserted": chunks_upserted,
            "expected_chunks": expected_chunks,
            "collection_count": final_count,
            "build_seconds": round(float(dt), 3),
        }

        ist.write_index_state_report(
            root=root,
            state_root=state_root,
            collection=str(args.collection),
            schema_hash=schema_hash,
            db=db_path,
            embed_model=str(args.embed_model),
            chunk_conf=chunk_conf_dict,
            include_media_stub=include_media_stub,
            docs=new_docs_state,
            last_build=last_build,
            items=raw_items,
        )

    # 11) summary
    print("=== BUILD SUMMARY (FlagEmbedding) ===")
    print(f"db_path={db_path}")
    print(f"collection={args.collection}")
    print(f"embed_model={args.embed_model} device={args.device}")
    print(f"sync_mode={sync_mode} strict_sync={strict_sync} write_state={write_state}")
    print(f"schema_hash={schema_hash}")
    if latest:
        print(f"latest_schema={latest}")
    print(f"state_file={state_file}")
    print(f"units_total={total_units} units_indexed={indexed_units} units_skipped={skipped_units}")
    print(
        f"docs_current={len(cur_docs)} added={len(added_uris)} changed={len(changed_uris)} deleted={len(deleted_uris)} unchanged={len(unchanged_uris)}"
    )
    print(f"docs_processed={docs_processed} chunks_upserted={chunks_upserted} chunks_deleted={chunks_deleted}")
    print(f"expected_chunks={expected_chunks} collection_count={final_count}")
    print(f"include_media_stub={include_media_stub}")
    print(f"chunk_conf={chunk_conf_dict}")
    print(f"elapsed_sec={round(float(dt), 3)}")

    if strict_sync and final_count is not None and final_count != expected_chunks:
        delta = int(expected_chunks) - int(final_count)
        print(f"STATUS: FAIL (sync mismatch; expected_chunks={expected_chunks} got={final_count} delta={delta})")
        print("HINT: if你是首次引入 index_state 或 state 丢失，请用 --on-missing-state reset 让库回到干净态。")
        if stage_enabled and run_id:
            _stage_append_event(
                "RUN_FINISH",
                {
                    "ok": False,
                    "collection_count": final_count,
                    "expected_chunks": expected_chunks,
                    "docs_processed": docs_processed,
                    "docs_resumed_skipped": docs_resumed_skipped,
                    "docs_checkpointed": docs_checkpointed,
                    "reason": "strict_sync_mismatch",
                    "delta": delta,
                    "committed_batches": committed_batches_this_run,
                    "chunks_upserted_total": chunks_upserted,
                    "sync_mode": sync_mode,
                    "wal_version": WAL_VERSION,
                },
                force_fsync=True,
            )
        return 2

    # 12) write DB build stamp (stable freshness basis for rag-status)
    try:
        from mhy_ai_rag_data.tools.write_db_build_stamp import write_db_build_stamp

        plan_for_stamp = None
        if args.plan:
            plan_arg = str(args.plan)
            plan_for_stamp = (
                (root / plan_arg).resolve() if not Path(plan_arg).is_absolute() else Path(plan_arg).resolve()
            )

        stamp_out = write_db_build_stamp(
            root=root,
            db=db_path,
            collection=str(args.collection),
            state_root=state_root,
            plan_path=plan_for_stamp,
            collection_count=final_count,
            writer="build_chroma_index_flagembedding",
        )
        print(f"[OK] wrote db_build_stamp: {stamp_out}")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] failed to write db_build_stamp.json: {type(e).__name__}: {e}")

    # finalize stage checkpoint (if enabled)
    if stage_enabled and run_id:
        _stage_append_event(
            "RUN_FINISH",
            {
                "ok": True,
                "collection_count": final_count,
                "expected_chunks": expected_chunks,
                "docs_processed": docs_processed,
                "docs_resumed_skipped": docs_resumed_skipped,
                "docs_checkpointed": docs_checkpointed,
                "reason": "ok",
                "committed_batches": committed_batches_this_run,
                "chunks_upserted_total": chunks_upserted,
                "sync_mode": sync_mode,
                "wal_version": WAL_VERSION,
            },
            force_fsync=True,
        )
        # Best-effort cleanup: stage is only needed for interrupted runs.
        try:
            stage_file.unlink(missing_ok=True)
        except TypeError:
            try:
                if stage_file.exists():
                    stage_file.unlink()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
