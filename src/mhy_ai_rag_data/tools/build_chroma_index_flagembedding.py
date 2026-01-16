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

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, cast

# Chroma metadata values are scalars, but stubs also allow SparseVector; keep Any for compatibility.
MetaValue = Any

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


# -------- main --------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build/Upsert Chroma index using FlagEmbedding (BGE-M3) with optional sync."
    )
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

    args = ap.parse_args()

    root = Path(args.root).resolve()
    units_path = (root / args.units).resolve()
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
    include_media_stub = bool(args.include_media_stub)

    # 4) state / schema hash
    try:
        from mhy_ai_rag_data.tools import index_state as ist
    except Exception as e:
        print(f"[FATAL] cannot import mhy_ai_rag_data.tools.index_state: {e}")
        return 2

    chunk_conf_dict = {
        "chunk_chars": int(args.chunk_chars),
        "overlap_chars": int(args.overlap_chars),
        "min_chunk_chars": int(args.min_chunk_chars),
    }
    schema_hash = ist.compute_schema_hash(
        embed_model=str(args.embed_model),
        chunk_conf=chunk_conf_dict,
        include_media_stub=include_media_stub,
        id_strategy_version=1,
    )

    state_root = (root / args.state_root).resolve()
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
    prev_state = ist.load_index_state(state_file)
    existing_count = 0
    try:
        existing_count = int(collection.count())
    except Exception:
        existing_count = 0

    if prev_state is None and existing_count > 0:
        # 状态缺失但库非空：无法可靠定位“多余 ids”，默认策略是 reset 后全量重建。
        policy = str(args.on_missing_state)
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
                chunks_deleted += delete_doc_chunks(doc_id, n_chunks)
                docs_deleted += 1
            except Exception:
                return 2

        # delete changed docs old chunks (important to avoid leftover ids when chunk count shrinks)
        for uri in changed_uris:
            prev = prev_docs.get(uri) or {}
            doc_id = str(prev.get("doc_id") or "")
            n_chunks = int(prev.get("n_chunks") or 0)
            try:
                chunks_deleted += delete_doc_chunks(doc_id, n_chunks)
            except Exception:
                return 2

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
        nonlocal ids_buf, docs_buf, metas_buf, embeds_buf
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
        ids_buf, docs_buf, metas_buf, embeds_buf = [], [], [], []

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

    for uri in to_process_uris:
        info = cur_docs.get(uri)
        if not info:
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
        state_obj: Dict[str, Any] = {
            "schema_version": 1,
            "schema_hash": schema_hash,
            "root": str(root),
            "db": str(args.db),
            "collection": str(args.collection),
            "embed_model": str(args.embed_model),
            "chunk_conf": chunk_conf_dict,
            "include_media_stub": include_media_stub,
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "docs": new_docs_state,
            "last_build": {
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
            },
        }
        ist.save_json_atomic(state_file, state_obj)
        ist.write_latest_pointer(state_root, args.collection, schema_hash)

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
        print(f"STATUS: FAIL (sync mismatch; expected_chunks={expected_chunks} got={final_count})")
        print("HINT: if你是首次引入 index_state 或 state 丢失，请用 --on-missing-state reset 让库回到干净态。")
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
