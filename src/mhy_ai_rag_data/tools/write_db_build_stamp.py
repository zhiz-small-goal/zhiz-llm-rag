#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_db_build_stamp.py

目标
----
为 Chroma 持久化库写入一个“构建戳（build stamp）”文件，用于：
- 在 rag-status 中提供**稳定**的“DB 是否新于 plan/check”等依赖判定；
- 避免 Windows/SQLite 在仅查询（read）场景下也刷新 DB 目录/文件 mtime，导致 check.json 被误判为 STALE。

设计要点
--------
- 构建戳文件仅应在“写库”行为成功完成后更新（build/upsert/sync），而不应在 query/eval/retriever 等只读行为中变化。
- stamp 文件放在 state_root（默认 data_processed/index_state）下，便于与增量同步状态同域管理。

默认输出
--------
<state_root>/db_build_stamp.json

"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mhy_ai_rag_data.tools import index_state as index_state_mod


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _sha256_file(p: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _read_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001
        return None, f"json_parse_error: {type(e).__name__}: {e}"


def _infer_planned_chunks(plan_obj: Any) -> Optional[int]:
    # 支持历史/不同脚本可能产出的几种形态。
    if isinstance(plan_obj, dict):
        if isinstance(plan_obj.get("planned_chunks"), int):
            return int(plan_obj["planned_chunks"])
        if isinstance(plan_obj.get("n_chunks"), int):
            return int(plan_obj["n_chunks"])
        chunks = plan_obj.get("chunks")
        if isinstance(chunks, list):
            return len(chunks)
        planned = plan_obj.get("planned")
        if isinstance(planned, list):
            return len(planned)
        return None
    if isinstance(plan_obj, list):
        return len(plan_obj)
    return None


def _maybe_get_collection_count(db: Path, collection: str) -> Tuple[Optional[int], Optional[str]]:
    try:
        import chromadb  # type: ignore
    except Exception as e:  # noqa: BLE001
        return None, f"chromadb_import_failed: {type(e).__name__}: {e}"

    try:
        client = chromadb.PersistentClient(path=str(db))
        col = client.get_collection(collection)
        return int(col.count()), None
    except Exception as e:  # noqa: BLE001
        return None, f"chroma_count_failed: {type(e).__name__}: {e}"


def write_db_build_stamp(
    *,
    root: Path,
    db: Path,
    collection: str,
    state_root: Path,
    plan_path: Optional[Path] = None,
    collection_count: Optional[int] = None,
    writer: str = "manual",
    out_path: Optional[Path] = None,
) -> Path:
    """Write a stable build-stamp json file.

    - 若 collection_count 未提供，将尝试连接 Chroma 读取 count（可失败，失败时写入 None + error）。
    - 若 plan_path 提供且存在，将写入其 sha256 与 planned_chunks，便于离线审计。
    """

    root = root.resolve()
    db = db.resolve()
    state_root = state_root.resolve()

    if out_path is None:
        out_path = state_root / "db_build_stamp.json"
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    schema_hash: Optional[str] = None
    try:
        schema_hash = index_state_mod.read_latest_pointer(state_root, collection)
    except Exception:  # noqa: BLE001
        schema_hash = None

    plan_info: Dict[str, Any] = {"path": None, "sha256": None, "planned_chunks": None, "read_error": None}
    if plan_path is not None:
        plan_path = plan_path.resolve()
        plan_info["path"] = str(plan_path)
        if plan_path.exists() and plan_path.is_file():
            try:
                plan_info["sha256"] = _sha256_file(plan_path)
            except Exception as e:  # noqa: BLE001
                plan_info["read_error"] = f"plan_hash_failed: {type(e).__name__}: {e}"
            obj, err = _read_json(plan_path)
            if err:
                plan_info["read_error"] = err
            else:
                plan_info["planned_chunks"] = _infer_planned_chunks(obj)
        else:
            plan_info["read_error"] = "plan_not_found"

    count_err: Optional[str] = None
    if collection_count is None:
        if db.exists():
            collection_count, count_err = _maybe_get_collection_count(db, collection)
        else:
            count_err = "db_not_found"

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at": _now_iso(),
        "writer": writer,
        "root": str(root),
        "db": str(db),
        "collection": collection,
        "schema_hash": schema_hash,
        "collection_count": collection_count,
        "count_error": count_err,
        "plan": plan_info,
        "note": "Updated only by successful write-to-db operations (build/upsert/sync) or explicit manual stamp.",
    }

    index_state_mod.atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Write a stable DB build-stamp for rag-status freshness.")
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--db", default="chroma_db", help="Chroma persistent dir")
    ap.add_argument("--collection", default="rag_chunks", help="Chroma collection")
    ap.add_argument("--state-root", default="data_processed/index_state", help="index_state root (default: data_processed/index_state)")
    ap.add_argument("--plan", default="data_processed/chunk_plan.json", help="plan path (optional; default points to standard location)")
    ap.add_argument("--writer", default="manual", help="writer tag (e.g., build_chroma_index_flagembedding)")
    ap.add_argument("--count", type=int, default=None, help="optional: override collection_count (skip opening chroma)")
    ap.add_argument("--out", default=None, help="output path (default: <state_root>/db_build_stamp.json)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db).resolve()
    state_root = (root / args.state_root).resolve() if not Path(args.state_root).is_absolute() else Path(args.state_root).resolve()

    plan_path: Optional[Path] = None
    if args.plan:
        plan_path = (root / args.plan).resolve() if not Path(args.plan).is_absolute() else Path(args.plan).resolve()

    out_path: Optional[Path] = None
    if args.out:
        out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()

    p = write_db_build_stamp(
        root=root,
        db=db,
        collection=str(args.collection),
        state_root=state_root,
        plan_path=plan_path,
        collection_count=args.count,
        writer=str(args.writer),
        out_path=out_path,
    )
    print(f"Wrote db build stamp: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
