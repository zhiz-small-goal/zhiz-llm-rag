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

控制台输出策略（本次改动）：
- 默认只显示一个“总体进度条”（doc 维度），用于感知写入进度；
- 其余 INFO 级过程信息写入日志文件；
- WARNING/ERROR 级信息仍会即时在控制台提示（不吞掉关键告警/失败原因）；
- FlagEmbedding 内部的 tqdm 文本（如 “Inference Embeddings / pre tokenize”）默认抑制，避免污染进度条。

核心约束（与你项目现有的 check_chroma_build.py 对齐）：
- chunk_id 生成策略：chunk_id = f"{doc_id}:{chunk_index}"（与 build_chroma_index.py 一致）
- chunk_conf/include_media_stub/embed_model 任一变化会触发 schema_hash 变化（建议视为“新索引版本”）

状态文件（manifest/index_state）：
- 默认写入：data_processed/index_state/<collection>/<schema_hash>/index_state.json
- 并写入：data_processed/index_state/<collection>/LATEST 指针

注意：
- 删除操作 collection.delete(ids=...) 属于 destructive；脚本默认仅在能定位到“上一轮该文档的 n_chunks”时删除。
- 若找不到 state 但 collection 已非空，默认拒绝继续（fail）；如需重置需显式指定（DESTRUCTIVE）。
"""

from __future__ import annotations

from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args

import argparse
import time
import json
import os
import uuid
import logging
import logging.handlers
import sys
from contextlib import contextmanager, redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, cast

try:
    from tqdm import tqdm
except Exception:  # tqdm not installed
    tqdm = None


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


def _safe_bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


@contextmanager
def _suppress_stderr(enabled: bool) -> Any:
    """Suppress writes to stderr in a scoped region (used to silence third-party tqdm noise)."""
    if not enabled:
        yield
        return
    devnull = None
    try:
        devnull = open(os.devnull, "w", encoding="utf-8", errors="ignore")
        with redirect_stderr(devnull):
            yield
    finally:
        try:
            if devnull:
                devnull.close()
        except Exception:
            pass


class _TqdmConsoleHandler(logging.Handler):
    """Console handler that cooperates with tqdm progress bars (no progress line corruption)."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if tqdm is not None:
            try:
                tqdm.write(msg)
                return
            except Exception:
                pass
        try:
            sys.stderr.write(msg + "\n")
        except Exception:
            pass


def _setup_logging(*, log_path: Path, level: str) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("build_chroma_index_flagembedding")
    logger.setLevel(logging.DEBUG)  # handlers decide effective level
    logger.handlers.clear()
    logger.propagate = False

    lvl = getattr(logging, str(level).upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler: keep more details
    fh = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(lvl)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler: warnings/errors only (to preserve a clean progress line)
    ch = _TqdmConsoleHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("logging initialized: log_file=%s log_level=%s", log_path.as_posix(), str(level).upper())
    return logger


# -------- WAL / resume helpers --------
WAL_VERSION = 1
WAL_FILENAME = "index_state.stage.jsonl"


def _iso_now() -> str:
    # Avoid timezone arithmetic here; ISO string is sufficient for logs.
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


@dataclass
class WalDoc:
    source_uri: str
    doc_id: str
    content_sha256: str
    n_chunks: int
    updated_at: str

    def to_state_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_uri": self.source_uri,
            "source_type": "",
            "content_sha256": self.content_sha256,
            "n_chunks": int(self.n_chunks),
            "updated_at": self.updated_at,
        }


@dataclass
class WalSnapshot:
    run_id: str
    done_docs: Dict[str, WalDoc]
    committed_batches: int
    upsert_rows_committed_total: int
    finished_ok: bool
    truncated_tail_ignored: bool
    last_event: str


def _safe_json_loads(line: str) -> Dict[str, Any] | None:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def read_wal(
    wal_path: Path,
    *,
    collection: str,
    schema_hash: str,
    db_path_posix: str,
) -> WalSnapshot | None:
    """Read WAL and return snapshot for the latest matching run.

    The WAL may contain multiple runs (append-only). We treat the latest RUN_START/RUN_RESUME
    as the active run. If the active run has RUN_FINISH(ok=true), it is considered finished.

    Tail truncation tolerance: if the last line is partially written, stop reading and mark
    truncated_tail_ignored.
    """
    if not wal_path.exists():
        return None

    active_run_id = ""
    done_docs: Dict[str, WalDoc] = {}
    committed_batches = 0
    upsert_rows_committed_total = 0
    finished_ok = False
    truncated_tail_ignored = False
    last_event = ""

    for raw in wal_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = _safe_json_loads(line)
        if obj is None:
            truncated_tail_ignored = True
            break

        if str(obj.get("collection") or "") != str(collection):
            continue
        if str(obj.get("schema_hash") or "") != str(schema_hash):
            continue
        if str(obj.get("db_path") or "") not in {"", str(db_path_posix)}:
            # Allow empty db_path for backward/partial events.
            continue

        ev = str(obj.get("event") or "")
        rid = str(obj.get("run_id") or "")

        if ev in {"RUN_START", "RUN_RESUME"}:
            active_run_id = rid
            done_docs = {}
            committed_batches = 0
            upsert_rows_committed_total = 0
            finished_ok = False
            truncated_tail_ignored = False
            last_event = ev
            continue

        if not active_run_id or rid != active_run_id:
            continue

        last_event = ev

        if ev in {"DOC_COMMITTED", "DOC_DONE"}:
            uri = str(obj.get("source_uri") or "")
            if not uri:
                continue
            done_docs[uri] = WalDoc(
                source_uri=uri,
                doc_id=str(obj.get("doc_id") or ""),
                content_sha256=str(obj.get("content_sha256") or ""),
                n_chunks=int(obj.get("n_chunks") or 0),
                updated_at=str(obj.get("updated_at") or ""),
            )
        elif ev == "UPSERT_BATCH_COMMITTED":
            committed_batches += 1
            upsert_rows_committed_total = int(obj.get("upsert_rows_committed_total") or upsert_rows_committed_total)
        elif ev == "RUN_FINISH":
            finished_ok = bool(obj.get("ok"))

    if not active_run_id:
        return None

    return WalSnapshot(
        run_id=active_run_id,
        done_docs=done_docs,
        committed_batches=committed_batches,
        upsert_rows_committed_total=upsert_rows_committed_total,
        finished_ok=finished_ok,
        truncated_tail_ignored=truncated_tail_ignored,
        last_event=last_event,
    )


class WalWriter:
    def __init__(
        self,
        *,
        wal_path: Path,
        collection: str,
        schema_hash: str,
        db_path_posix: str,
        run_id: str,
        fsync_mode: str,
        fsync_interval: int,
    ) -> None:
        self.wal_path = wal_path
        self.collection = str(collection)
        self.schema_hash = str(schema_hash)
        self.db_path_posix = str(db_path_posix)
        self.run_id = str(run_id)
        self.fsync_mode = str(fsync_mode)
        self.fsync_interval = int(max(1, fsync_interval))
        self._seq = 0
        self._since_fsync = 0

        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.wal_path.open("a", encoding="utf-8")

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass

    def _maybe_fsync(self) -> None:
        if self.fsync_mode == "off":
            return
        if self.fsync_mode == "doc":
            # handled explicitly by caller
            return
        self._since_fsync += 1
        if self.fsync_mode == "interval" and self._since_fsync >= self.fsync_interval:
            try:
                self._fp.flush()
                os.fsync(self._fp.fileno())
            except Exception:
                pass
            self._since_fsync = 0

    def fsync_now(self) -> None:
        try:
            self._fp.flush()
            os.fsync(self._fp.fileno())
        except Exception:
            pass
        self._since_fsync = 0

    def write_event(self, event: str, payload: Dict[str, Any] | None = None) -> None:
        self._seq += 1
        obj: Dict[str, Any] = {
            "wal_version": WAL_VERSION,
            "ts": _iso_now(),
            "seq": self._seq,
            "event": str(event),
            "run_id": self.run_id,
            "collection": self.collection,
            "schema_hash": self.schema_hash,
            "db_path": self.db_path_posix,
        }
        if payload:
            obj.update(payload)
        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        try:
            self._fp.write(line + "\n")
            self._fp.flush()
        except Exception:
            return

        self._maybe_fsync()


class WriterLock:
    """Best-effort single-writer lock.

    Uses an atomic create (O_EXCL) on Windows/Linux.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self, *, run_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.path), flags)
        except FileExistsError:
            raise RuntimeError(f"writer lock exists: {self.path.as_posix()}")
        self._fd = fd
        try:
            os.write(fd, f"run_id={run_id}\n".encode("utf-8"))
        except Exception:
            pass

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception:
            pass


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

    # console / logging / progress
    b.add_argument(
        "--progress",
        default="true",
        help="true/false: show a single overall progress bar in console.",
    )
    b.add_argument(
        "--suppress-embed-progress",
        default="true",
        help="true/false: suppress FlagEmbedding internal tqdm output (Inference Embeddings / pre tokenize).",
    )
    b.add_argument(
        "--log-file",
        default="",
        help="Log file path. Default: <state_dir>/build.log . Relative paths are resolved from --root.",
    )
    b.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level for file log: DEBUG/INFO/WARNING/ERROR.",
    )

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
        default="fail",
        choices=["reset", "fail", "full-upsert"],
        help="If state missing but collection is non-empty: reset collection (DESTRUCTIVE: delete+recreate) / fail / proceed with full upsert (may keep stale).",
    )
    b.add_argument(
        "--schema-change",
        default="fail",
        choices=["reset", "fail"],
        help="If schema_hash differs from LATEST pointer: reset collection (DESTRUCTIVE: delete+recreate) or fail.",
    )
    b.add_argument("--delete-batch", type=int, default=5000, help="Batch size for collection.delete(ids=...).")
    b.add_argument(
        "--strict-sync", default="true", help="true/false: fail if collection.count != expected_chunks after build."
    )
    b.add_argument("--write-state", default="true", help="true/false: write index_state.json after successful build.")

    # resume / WAL (progress)
    b.add_argument(
        "--wal", default="on", choices=["on", "off"], help="Write progress WAL (index_state.stage.jsonl) during build."
    )
    b.add_argument(
        "--resume",
        default="auto",
        choices=["auto", "off", "force"],
        help="Resume behavior when WAL exists: auto/off/force.",
    )
    b.add_argument("--resume-status", action="store_true", help="Inspect state/WAL and exit (read-only).")
    b.add_argument(
        "--wal-fsync", default="off", choices=["off", "doc", "interval"], help="WAL fsync policy: off/doc/interval."
    )
    b.add_argument(
        "--wal-fsync-interval", type=int, default=200, help="When wal-fsync=interval, fsync every N WAL events."
    )
    b.add_argument("--keep-wal", action="store_true", help="Do not delete WAL on success.")
    b.add_argument(
        "--writer-lock", default="true", help="true/false: create an exclusive writer lock in the state dir."
    )

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

    # 2) load embedding model (lazy; skip for --resume-status)
    model: Any | None = None

    def _load_flagembedding_model() -> Any:
        nonlocal model
        if model is not None:
            return model

        try:
            from FlagEmbedding import BGEM3FlagModel
        except Exception as e:
            print(
                '[FATAL] FlagEmbedding not installed. Install: pip install -e .[embed]  (or pip install ".[embed]" on bash)'
            )
            print(str(e))
            raise

        try:
            # Newer versions may support device kw; keep best-effort.
            model = BGEM3FlagModel(args.embed_model, use_fp16=True, device=str(args.device))
        except TypeError:
            model = BGEM3FlagModel(args.embed_model, use_fp16=True)
            print(
                f"[WARN] BGEM3FlagModel() 不支持 device=，已回退为默认 device；你指定的 --device={args.device} 可能未生效。"
            )

        return model

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
        print("[DESTRUCTIVE] schema-change=reset will DELETE and RECREATE the collection.")
        print("[DESTRUCTIVE] target: db_path=%s collection=%s" % (db_path.as_posix(), str(args.collection)))
        print(
            "[DESTRUCTIVE] to avoid this, use --schema-change fail and choose a new --collection (versioned) or new --db."
        )
        # Reset collection: easiest to guarantee correctness
        try:
            client.delete_collection(name=args.collection)
        except Exception as e:
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

    # WAL / resume (progress)
    state_dir = ist.state_dir_for(state_root, str(args.collection), str(schema_hash))
    wal_path = state_dir / WAL_FILENAME
    wal_on = str(args.wal).strip().lower() == "on"
    resume_mode = str(args.resume).strip().lower()
    db_path_posix = db_path.as_posix()

    # logging init: now we have state_dir
    log_file_arg = str(getattr(args, "log_file", "") or "").strip()
    if not log_file_arg:
        log_path = state_dir / "build.log"
    else:
        p = Path(log_file_arg)
        log_path = (root / p).resolve() if not p.is_absolute() else p.resolve()
    logger = _setup_logging(log_path=log_path, level=str(getattr(args, "log_level", "INFO")))

    logger.info(
        "start: db=%s collection=%s schema_hash=%s sync_mode=%s",
        db_path.as_posix(),
        str(args.collection),
        schema_hash,
        str(args.sync_mode),
    )
    logger.info(
        "progress=%s suppress_embed_progress=%s",
        str(getattr(args, "progress", "true")),
        str(getattr(args, "suppress_embed_progress", "true")),
    )

    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"

    wal_snapshot: WalSnapshot | None = None
    if resume_mode != "off":
        try:
            wal_snapshot = read_wal(
                wal_path,
                collection=str(args.collection),
                schema_hash=str(schema_hash),
                db_path_posix=db_path_posix,
            )
        except Exception as e:
            logger.warning("failed to read WAL: %s (%s: %s)", wal_path.as_posix(), type(e).__name__, str(e))
            wal_snapshot = None

    resume_active = bool(wal_snapshot is not None and not wal_snapshot.finished_ok)
    if resume_mode == "force" and not resume_active:
        print(f"[FATAL] resume=force but no resumable WAL: {wal_path}")
        return 2

    wal_done_docs: Dict[str, WalDoc] = dict(wal_snapshot.done_docs) if resume_active and wal_snapshot else {}

    wal_stats: Dict[str, int] = {
        "committed_batches": int(wal_snapshot.committed_batches) if resume_active and wal_snapshot else 0,
        "upsert_rows_committed_total": int(wal_snapshot.upsert_rows_committed_total)
        if resume_active and wal_snapshot
        else 0,
    }

    # Backward-compatible aliases (do NOT use as mutation targets in nested functions)

    wal_committed_batches = wal_stats["committed_batches"]

    upsert_rows_committed_total = wal_stats["upsert_rows_committed_total"]

    if bool(getattr(args, "resume_status", False)):
        print("=== RESUME STATUS ===")
        print(f"db_path={db_path_posix}")
        print(f"collection={args.collection}")
        print(f"schema_hash={schema_hash}")
        print(f"collection_count={existing_count}")
        print(f"state_file={state_file} state_present={state_file.exists()}")
        print(f"wal_path={wal_path} wal_present={wal_path.exists()} wal_on={wal_on}")
        if wal_snapshot:
            print(
                f"wal_run_id={wal_snapshot.run_id} wal_finished_ok={wal_snapshot.finished_ok} wal_last_event={wal_snapshot.last_event} wal_truncated_tail_ignored={wal_snapshot.truncated_tail_ignored}"
            )
            print(
                f"wal_docs_committed={len(wal_snapshot.done_docs)} wal_committed_batches={wal_snapshot.committed_batches} wal_upsert_rows_committed_total={wal_snapshot.upsert_rows_committed_total}"
            )
        else:
            print("wal_snapshot=None")
        print(f"resume_mode={resume_mode} resume_active={resume_active}")
        return 0

    # Writer lock (best-effort; local single-writer assumption)
    writer_lock: WriterLock | None = None
    if wal_on and _safe_bool(str(args.writer_lock)):
        try:
            writer_lock = WriterLock(state_dir / "writer.lock")
            writer_lock.acquire(run_id=run_id)
        except Exception as e:
            print(f"[FATAL] {e}")
            return 2

    # WAL writer
    wal_writer: WalWriter | None = None
    if wal_on:
        # If not resuming, rotate existing WAL to avoid mixing multiple runs.
        if wal_path.exists() and not resume_active:
            try:
                rotated = wal_path.with_suffix(wal_path.suffix + f".prev-{int(time.time())}")
                os.replace(str(wal_path), str(rotated))
                logger.warning("existing WAL rotated: %s", rotated.as_posix())
            except Exception:
                pass

        wal_writer = WalWriter(
            wal_path=wal_path,
            collection=str(args.collection),
            schema_hash=str(schema_hash),
            db_path_posix=db_path_posix,
            run_id=run_id,
            fsync_mode=str(args.wal_fsync),
            fsync_interval=int(args.wal_fsync_interval),
        )
        wal_writer.write_event(
            "RUN_RESUME" if resume_active else "RUN_START",
            {
                "sync_mode": str(args.sync_mode),
                "strict_sync": bool(_safe_bool(args.strict_sync)),
                "write_state": bool(_safe_bool(args.write_state)),
            },
        )
        if str(args.wal_fsync) == "doc":
            wal_writer.fsync_now()

    if prev_state is None and existing_count > 0:
        # 状态缺失但库非空：无法可靠定位“多余 ids”。
        # 若 WAL 可恢复：优先续跑（跳过 reset），避免重复写入。
        policy = str(args.on_missing_state)
        logger.warning("index_state missing but collection.count=%s. policy=%s", str(existing_count), policy)
        if resume_active:
            logger.warning(
                "WAL indicates resumable progress; ignore on-missing-state=%s and continue with resume.", policy
            )
        else:
            if policy == "fail":
                print("[FATAL] missing index_state + non-empty collection; refuse to proceed")
                if wal_writer:
                    wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "missing_state"})
                if writer_lock:
                    writer_lock.release()
                return 2
            if policy == "reset":
                print("[DESTRUCTIVE] on-missing-state=reset will DELETE and RECREATE the collection.")
                print("[DESTRUCTIVE] target: db_path=%s collection=%s" % (db_path.as_posix(), str(args.collection)))
                print(
                    "[DESTRUCTIVE] to avoid this, use --on-missing-state fail (recommended) or rebuild into a new --collection."
                )
                try:
                    client.delete_collection(name=args.collection)
                except Exception as e:
                    print(f"[FATAL] failed to delete_collection(name={args.collection}) on missing-state reset: {e}")
                    if wal_writer:
                        wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "missing_state_reset_failed"})
                    if writer_lock:
                        writer_lock.release()
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
        to_process_uris = sorted(cur_uris)
        do_delete = False
    elif sync_mode == "delete-stale":
        to_process_uris = sorted(cur_uris)
        do_delete = True
    else:
        to_process_uris = sorted(set(added_uris) | set(changed_uris))
        do_delete = True

    # expected chunks (for strict check)
    expected_chunks = 0
    if sync_mode == "incremental" and prev_state is not None:
        for uri in unchanged_uris:
            expected_chunks += int((prev_docs.get(uri) or {}).get("n_chunks", 0))

    logger.info(
        "delta: docs_current=%s added=%s changed=%s deleted=%s unchanged=%s to_process=%s do_delete=%s",
        len(cur_docs),
        len(added_uris),
        len(changed_uris),
        len(deleted_uris),
        len(unchanged_uris),
        len(to_process_uris),
        do_delete,
    )

    # Overall progress bar (single)
    progress_enabled = _safe_bool(str(getattr(args, "progress", "true"))) and (tqdm is not None)
    pbar = None
    if progress_enabled:
        pbar = tqdm(total=len(to_process_uris), desc="Chroma Write", unit="doc", dynamic_ncols=True)
        # If resuming, we still advance per-doc when we actually skip/process them; no fake initial offset.

    def _pbar_postfix() -> Dict[str, Any]:
        return {
            "docs": f"{docs_processed}/{len(to_process_uris)}",
            "chunks": int(chunks_upserted),
            "upserted": int(upsert_rows_committed_total),
            "batches": int(wal_committed_batches),
        }

    # 7) delete stale chunks (no global ids enumeration)
    chunks_deleted_removed = 0
    docs_deleted_removed = 0
    chunks_deleted_changed_tail = 0
    docs_changed_tail_deleted = 0

    def delete_doc_chunks_range(doc_id: str, start: int, end_exclusive: int) -> int:
        if not doc_id:
            return 0
        start_i = int(max(0, start))
        end_i = int(max(0, end_exclusive))
        if end_i <= start_i:
            return 0

        deleted = 0
        batch: list[str] = []
        for i in range(start_i, end_i):
            batch.append(_chunk_id(doc_id, i))
            if len(batch) >= int(args.delete_batch):
                try:
                    collection.delete(ids=batch)
                except Exception as e:
                    if pbar is not None:
                        pbar.close()
                    print(f"[FATAL] collection.delete failed (doc_id={doc_id}, batch={len(batch)}): {e}")
                    raise
                deleted += len(batch)
                batch = []

        if batch:
            try:
                collection.delete(ids=batch)
            except Exception as e:
                if pbar is not None:
                    pbar.close()
                print(f"[FATAL] collection.delete failed (doc_id={doc_id}, batch={len(batch)}): {e}")
                raise
            deleted += len(batch)

        return deleted

    def delete_doc_chunks(doc_id: str, n_chunks: int) -> int:
        return delete_doc_chunks_range(doc_id, 0, int(n_chunks))

    # For changed docs, we need previous doc_id/n_chunks to delete the stale tail after upsert.
    changed_prev: Dict[str, Dict[str, Any]] = {}

    if do_delete and prev_state is not None:
        for uri in deleted_uris:
            prev = prev_docs.get(uri) or {}
            doc_id = str(prev.get("doc_id") or "")
            n_chunks = int(prev.get("n_chunks") or 0)
            try:
                chunks_deleted_removed += delete_doc_chunks(doc_id, n_chunks)
                docs_deleted_removed += 1
            except Exception:
                if wal_writer:
                    wal_writer.write_event(
                        "RUN_FINISH", {"ok": False, "reason": "delete_removed_failed", "source_uri": uri}
                    )
                if writer_lock:
                    writer_lock.release()
                if pbar is not None:
                    pbar.close()
                return 2

        for uri in changed_uris:
            prev = prev_docs.get(uri) or {}
            changed_prev[uri] = {"doc_id": str(prev.get("doc_id") or ""), "n_chunks": int(prev.get("n_chunks") or 0)}

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
        if not ids_buf:
            return

        vecs = embeds_buf
        if normalize_dense:
            vecs = normalize_dense(vecs)
        else:
            vecs = l2_normalize(vecs)

        metas_for_upsert = cast(List[Mapping[str, MetaValue]], metas_buf)
        try:
            collection.upsert(ids=ids_buf, documents=docs_buf, metadatas=metas_for_upsert, embeddings=vecs)
        except Exception as e:
            logger.error("collection.upsert failed (batch=%s): %s", len(ids_buf), str(e))
            raise

        batch_size = int(len(ids_buf))
        wal_stats["upsert_rows_committed_total"] += batch_size
        wal_stats["committed_batches"] += 1

        if wal_writer:
            wal_writer.write_event(
                "UPSERT_BATCH_COMMITTED",
                {
                    "batch_size": batch_size,
                    "upsert_rows_committed_total": wal_stats["upsert_rows_committed_total"],
                    "committed_batches": wal_stats["committed_batches"],
                },
            )

        ids_buf.clear()
        docs_buf.clear()
        metas_buf.clear()
        embeds_buf.clear()

    t0 = time.perf_counter()

    new_docs_state: Dict[str, Dict[str, Any]] = {}

    if sync_mode == "incremental" and prev_state is not None:
        for uri in unchanged_uris:
            prev = prev_docs.get(uri) or {}
            if prev:
                new_docs_state[uri] = dict(prev)

    chunks_upserted = 0
    docs_processed = 0
    docs_skipped_resume = 0

    suppress_embed_progress = _safe_bool(str(getattr(args, "suppress_embed_progress", "true")))

    for uri in to_process_uris:
        info = cur_docs.get(uri)
        if not info:
            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(_pbar_postfix())
            continue

        if ids_buf:
            try:
                flush()
            except Exception:
                if wal_writer:
                    wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "upsert_failed"})
                if writer_lock:
                    writer_lock.release()
                if pbar is not None:
                    pbar.close()
                return 2

        cur_sha = str(info.get("content_sha256") or "")

        wal_doc = wal_done_docs.get(uri) if resume_active else None
        if wal_doc and str(wal_doc.content_sha256) == cur_sha:
            n_chunks = int(wal_doc.n_chunks)
            expected_chunks += n_chunks
            new_docs_state[uri] = {
                "doc_id": str(wal_doc.doc_id or info.get("doc_id") or ""),
                "source_uri": uri,
                "source_type": str(info.get("source_type") or ""),
                "content_sha256": cur_sha,
                "n_chunks": n_chunks,
                "updated_at": str(info.get("updated_at") or wal_doc.updated_at or ""),
            }
            docs_processed += 1
            docs_skipped_resume += 1
            if wal_writer:
                wal_writer.write_event(
                    "DOC_SKIPPED",
                    {
                        "source_uri": uri,
                        "doc_id": str(wal_doc.doc_id or ""),
                        "content_sha256": cur_sha,
                        "n_chunks": n_chunks,
                        "reason": "resume_done",
                    },
                )
                if str(args.wal_fsync) == "doc":
                    wal_writer.fsync_now()

            if uri in changed_prev:
                prev_doc_id = str((changed_prev.get(uri) or {}).get("doc_id") or "")
                prev_n = int((changed_prev.get(uri) or {}).get("n_chunks") or 0)
                new_doc_id = str(wal_doc.doc_id or prev_doc_id)
                new_n = n_chunks
                try:
                    if prev_doc_id and prev_n > 0:
                        if prev_doc_id != new_doc_id:
                            deleted_tail = delete_doc_chunks(prev_doc_id, prev_n)
                        elif prev_n > new_n:
                            deleted_tail = delete_doc_chunks_range(prev_doc_id, new_n, prev_n)
                        else:
                            deleted_tail = 0
                        if deleted_tail:
                            chunks_deleted_changed_tail += int(deleted_tail)
                            docs_changed_tail_deleted += 1
                except Exception as e:
                    logger.error("delete changed-tail failed (source_uri=%s): %s", uri, str(e))
                    if wal_writer:
                        wal_writer.write_event(
                            "RUN_FINISH", {"ok": False, "reason": "delete_changed_tail_failed", "source_uri": uri}
                        )
                    if writer_lock:
                        writer_lock.release()
                    if pbar is not None:
                        pbar.close()
                    return 2

            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(_pbar_postfix())
            continue

        unit = info["unit"]

        if wal_writer:
            wal_writer.write_event(
                "DOC_BEGIN", {"source_uri": uri, "doc_id": str(info.get("doc_id") or ""), "content_sha256": cur_sha}
            )

        chunk_texts, base_md = build_chunks_from_unit(unit, conf)
        doc_id = str(base_md.get("doc_id") or info.get("doc_id") or "")
        n_chunks = len(chunk_texts or [])
        expected_chunks += n_chunks

        new_docs_state[uri] = {
            "doc_id": doc_id,
            "source_uri": uri,
            "source_type": str(info.get("source_type") or ""),
            "content_sha256": cur_sha,
            "n_chunks": int(n_chunks),
            "updated_at": str(info.get("updated_at") or ""),
        }

        if not chunk_texts:
            wal_done_docs[uri] = WalDoc(
                source_uri=uri,
                doc_id=doc_id,
                content_sha256=cur_sha,
                n_chunks=0,
                updated_at=str(info.get("updated_at") or ""),
            )
            if wal_writer:
                wal_writer.write_event(
                    "DOC_COMMITTED",
                    {
                        "source_uri": uri,
                        "doc_id": doc_id,
                        "content_sha256": cur_sha,
                        "n_chunks": 0,
                        "updated_at": str(info.get("updated_at") or ""),
                    },
                )
                if str(args.wal_fsync) == "doc":
                    wal_writer.fsync_now()

            if uri in changed_prev:
                prev_doc_id = str((changed_prev.get(uri) or {}).get("doc_id") or "")
                prev_n = int((changed_prev.get(uri) or {}).get("n_chunks") or 0)
                try:
                    if prev_doc_id and prev_n > 0:
                        if prev_doc_id != doc_id:
                            deleted_tail = delete_doc_chunks(prev_doc_id, prev_n)
                        else:
                            deleted_tail = delete_doc_chunks_range(prev_doc_id, 0, prev_n)
                        if deleted_tail:
                            chunks_deleted_changed_tail += int(deleted_tail)
                            docs_changed_tail_deleted += 1
                except Exception as e:
                    logger.error("delete changed-tail failed (source_uri=%s): %s", uri, str(e))
                    if wal_writer:
                        wal_writer.write_event(
                            "RUN_FINISH", {"ok": False, "reason": "delete_changed_tail_failed", "source_uri": uri}
                        )
                    if writer_lock:
                        writer_lock.release()
                    if pbar is not None:
                        pbar.close()
                    return 2

            docs_processed += 1
            if pbar is not None:
                pbar.update(1)
                pbar.set_postfix(_pbar_postfix())
            continue

        # Load model only when we are about to embed.
        try:
            model = _load_flagembedding_model()
        except Exception:
            if wal_writer:
                wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "embed_model_load_failed"})
            if writer_lock:
                writer_lock.release()
            if pbar is not None:
                pbar.close()
            return 2

        # Embed chunk_texts in batches
        for i in range(0, len(chunk_texts), int(args.embed_batch)):
            batch_texts = chunk_texts[i : i + int(args.embed_batch)]

            try:
                with _suppress_stderr(suppress_embed_progress):
                    # Prefer an explicit "no progress bar" kw; fall back if current FlagEmbedding version rejects it.
                    try:
                        out = model.encode(
                            batch_texts,
                            batch_size=len(batch_texts),
                            max_length=8192,
                            return_dense=True,
                            return_sparse=False,
                            return_colbert_vecs=False,
                            show_progress_bar=False,
                        )
                    except TypeError:
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
                logger.error("embedding failed for doc=%s: %s", uri, str(e))
                if wal_writer:
                    wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "embed_failed", "source_uri": uri})
                if writer_lock:
                    writer_lock.release()
                if pbar is not None:
                    pbar.close()
                return 2

            for j, ct in enumerate(batch_texts):
                idx = i + j
                cid = _chunk_id(doc_id, idx)
                md = dict(base_md)
                md["chunk_index"] = idx
                md["chunk_chars"] = len(ct)
                md["source_uri"] = uri

                ids_buf.append(cid)
                docs_buf.append(ct)
                metas_buf.append(md)
                embeds_buf.append([float(x) for x in dense[j]])

                chunks_upserted += 1
                if len(ids_buf) >= int(args.upsert_batch):
                    try:
                        flush()
                    except Exception:
                        if wal_writer:
                            wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "upsert_failed"})
                        if writer_lock:
                            writer_lock.release()
                        if pbar is not None:
                            pbar.close()
                        return 2

        try:
            flush()
        except Exception:
            if wal_writer:
                wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "upsert_failed"})
            if writer_lock:
                writer_lock.release()
            if pbar is not None:
                pbar.close()
            return 2

        wal_done_docs[uri] = WalDoc(
            source_uri=uri,
            doc_id=doc_id,
            content_sha256=cur_sha,
            n_chunks=int(n_chunks),
            updated_at=str(info.get("updated_at") or ""),
        )

        if wal_writer:
            wal_writer.write_event(
                "DOC_COMMITTED",
                {
                    "source_uri": uri,
                    "doc_id": doc_id,
                    "content_sha256": cur_sha,
                    "n_chunks": int(n_chunks),
                    "updated_at": str(info.get("updated_at") or ""),
                },
            )
            if str(args.wal_fsync) == "doc":
                wal_writer.fsync_now()

        if uri in changed_prev:
            prev_doc_id = str((changed_prev.get(uri) or {}).get("doc_id") or "")
            prev_n = int((changed_prev.get(uri) or {}).get("n_chunks") or 0)
            try:
                if prev_doc_id and prev_n > 0:
                    if prev_doc_id != doc_id:
                        deleted_tail = delete_doc_chunks(prev_doc_id, prev_n)
                    elif prev_n > int(n_chunks):
                        deleted_tail = delete_doc_chunks_range(prev_doc_id, int(n_chunks), prev_n)
                    else:
                        deleted_tail = 0
                    if deleted_tail:
                        chunks_deleted_changed_tail += int(deleted_tail)
                        docs_changed_tail_deleted += 1
            except Exception as e:
                logger.error("delete changed-tail failed (source_uri=%s): %s", uri, str(e))
                if wal_writer:
                    wal_writer.write_event(
                        "RUN_FINISH", {"ok": False, "reason": "delete_changed_tail_failed", "source_uri": uri}
                    )
                if writer_lock:
                    writer_lock.release()
                if pbar is not None:
                    pbar.close()
                return 2

        docs_processed += 1
        if pbar is not None:
            pbar.update(1)
            pbar.set_postfix(_pbar_postfix())

    if ids_buf:
        try:
            flush()
        except Exception:
            if wal_writer:
                wal_writer.write_event("RUN_FINISH", {"ok": False, "reason": "upsert_failed"})
            if writer_lock:
                writer_lock.release()
            if pbar is not None:
                pbar.close()
            return 2

    dt = time.perf_counter() - t0

    if pbar is not None:
        pbar.close()

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
            "docs_deleted": int(docs_deleted_removed),
            "chunks_deleted": int(chunks_deleted_removed + chunks_deleted_changed_tail),
            "docs_deleted_removed": int(docs_deleted_removed),
            "docs_changed_tail_deleted": int(docs_changed_tail_deleted),
            "chunks_deleted_removed": int(chunks_deleted_removed),
            "chunks_deleted_changed_tail": int(chunks_deleted_changed_tail),
            "chunks_upserted": chunks_upserted,
            "expected_chunks": expected_chunks,
            "collection_count": final_count,
            "build_seconds": round(float(dt), 3),
            "resume_active": bool(resume_active),
            "docs_skipped_resume": int(docs_skipped_resume),
            "wal_path": wal_path.as_posix(),
            "wal_committed_batches": int(wal_committed_batches),
            "wal_upsert_rows_committed_total": int(upsert_rows_committed_total),
            "log_file": log_path.as_posix(),
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

    # 11) summary (kept on console as key info)
    print("=== BUILD SUMMARY (FlagEmbedding) ===")
    print(f"db_path={db_path}")
    print(f"collection={args.collection}")
    print(f"embed_model={args.embed_model} device={args.device}")
    print(f"sync_mode={sync_mode} strict_sync={strict_sync} write_state={write_state}")
    print(f"schema_hash={schema_hash}")
    if latest:
        print(f"latest_schema={latest}")
    print(f"state_file={state_file}")
    print(f"log_file={log_path}")
    print(f"units_total={total_units} units_indexed={indexed_units} units_skipped={skipped_units}")
    print(
        f"docs_current={len(cur_docs)} added={len(added_uris)} changed={len(changed_uris)} deleted={len(deleted_uris)} unchanged={len(unchanged_uris)}"
    )
    print(
        f"docs_processed={docs_processed} docs_skipped_resume={docs_skipped_resume} chunks_upserted={chunks_upserted}"
    )
    print(
        f"chunks_deleted_removed={chunks_deleted_removed} chunks_deleted_changed_tail={chunks_deleted_changed_tail} chunks_deleted_total={chunks_deleted_removed + chunks_deleted_changed_tail}"
    )
    print(f"expected_chunks={expected_chunks} collection_count={final_count}")
    print(f"include_media_stub={include_media_stub}")
    print(f"chunk_conf={chunk_conf_dict}")
    print(f"elapsed_sec={round(float(dt), 3)}")

    if strict_sync and final_count is not None and final_count != expected_chunks:
        print(f"STATUS: FAIL (sync mismatch; expected_chunks={expected_chunks} got={final_count})")
        print(
            "HINT: 该失败表示 collection.count() 与 expected_chunks 不一致。若 state 缺失且库非空，可用 --on-missing-state reset 重建；若使用 resume/WAL，确认 schema_hash 一致且 WAL 未混入不同 collection/db；若 sync_mode=none 且库已有旧数据，会导致 count 更大。"
        )

        if wal_writer:
            wal_writer.write_event(
                "RUN_FINISH",
                {
                    "ok": False,
                    "reason": "strict_mismatch",
                    "expected_chunks": int(expected_chunks),
                    "collection_count": int(final_count),
                    "docs_processed": int(docs_processed),
                    "docs_skipped_resume": int(docs_skipped_resume),
                    "upsert_rows_committed_total": int(wal_stats["upsert_rows_committed_total"]),
                },
            )
            try:
                wal_writer.close()
            except Exception:
                pass

        if writer_lock:
            writer_lock.release()

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
        logger.warning("failed to write db_build_stamp.json: %s: %s", type(e).__name__, str(e))
        print(f"[WARN] failed to write db_build_stamp.json: {type(e).__name__}: {e}")

    # WAL finalization / cleanup
    if wal_writer:
        wal_writer.write_event(
            "RUN_FINISH",
            {
                "ok": bool(ok),
                "reason": "ok" if ok else "failed",
                "docs_processed": int(docs_processed),
                "docs_skipped_resume": int(docs_skipped_resume),
                "chunks_upserted": int(chunks_upserted),
                "upsert_rows_committed_total": int(wal_stats["upsert_rows_committed_total"]),
                "committed_batches": int(wal_stats["committed_batches"]),
                "expected_chunks": int(expected_chunks),
                "collection_count": final_count,
            },
        )
        try:
            wal_writer.close()
        except Exception:
            pass

        if bool(ok) and bool(write_state) and (not bool(args.keep_wal)):
            try:
                if wal_path.exists():
                    os.remove(wal_path)
            except Exception:
                pass

    if writer_lock:
        try:
            writer_lock.release()
        except Exception:
            pass

    logger.info(
        "finish: ok=%s docs_processed=%s expected_chunks=%s collection_count=%s",
        bool(ok),
        docs_processed,
        expected_chunks,
        final_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
