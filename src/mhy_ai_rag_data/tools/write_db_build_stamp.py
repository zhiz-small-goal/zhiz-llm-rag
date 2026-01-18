#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.write_db_build_stamp

写入“DB build stamp”到 state_root/db_build_stamp.json。

目的
- 为 rag-status 提供**稳定 freshness basis**：仅在“写库成功”后更新，避免读取/评测触碰 DB 目录 mtime 导致误 STALE。
- 该文件属于“状态元数据”，但同样遵循**统一报告契约（schema_version=2）**：
  - 顶层具备 schema_version/generated_at/tool/root/summary/items
  - 允许扩展字段（例如 db/collection/schema_hash/plan 等），用于机器侧读取

路径
- 默认：<root>/data_processed/index_state/db_build_stamp.json

生成时机（建议）
- build/upsert/sync 成功后自动写入（build_chroma_index.py 已集成）。
- 也允许手动补写（旧库/迁移时）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output

# Optional: import Chroma only when used


def _sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return h.hexdigest()


def _read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj, None
        return None, "json_root_not_object"
    except Exception as e:  # noqa: BLE001
        return None, f"json_parse_error: {e!r}"


def _iso_local() -> str:
    # Keep legacy-friendly local timestamp for human reading.
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _sanitize_no_backslash(obj: Any) -> Any:
    """Ensure item fields contain no backslashes.

    verify_report_output_contract() will recursively scan item string fields and fail on '\\'.
    For state-metadata reports, we sanitize any human-facing strings placed under `items`.
    """

    if isinstance(obj, str):
        return obj.replace("\\", "/")
    if isinstance(obj, dict):
        return {k: _sanitize_no_backslash(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_no_backslash(v) for v in obj]
    return obj


def _try_collection_count(*, db: Path, collection: str) -> Tuple[Optional[int], Optional[str]]:
    try:
        import chromadb

        Settings = chromadb.config.Settings
        client = chromadb.PersistentClient(path=str(db), settings=Settings(anonymized_telemetry=False))
        col = client.get_collection(name=str(collection))
        return int(col.count()), None
    except Exception as e:  # noqa: BLE001
        # keep message compact; paths may appear -> sanitize later if emitted to items
        return None, f"{type(e).__name__}: {e}"


def write_db_build_stamp(
    *,
    root: Path,
    db: Path,
    collection: str,
    state_root: Path,
    plan_path: Optional[Path],
    collection_count: Optional[int],
    writer: str,
    out_path: Optional[Path] = None,
    schema_hash: Optional[str] = None,
) -> Path:
    """Write db_build_stamp.json.

    Contract (file output): schema_version=2 report.

    Notes
    - `collection_count` can be provided by caller to avoid re-opening Chroma.
    - If not provided, this function will try to read count (best-effort).
    """

    root = root.resolve()
    db = db.resolve()
    state_root = state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)

    if out_path is None:
        out_path = state_root / "db_build_stamp.json"
    out_path = out_path.resolve()

    # plan snapshot (best-effort)
    plan_info: Dict[str, Any] = {
        "path": None,
        "sha256": None,
        "planned_chunks": None,
        "read_error": None,
    }
    if plan_path is not None:
        pp = plan_path.resolve()
        plan_info["path"] = str(pp)
        if pp.exists():
            obj, err = _read_json(pp)
            if err:
                plan_info["read_error"] = err
            else:
                try:
                    raw = pp.read_text(encoding="utf-8")
                    plan_info["sha256"] = _sha256_text(raw)
                except Exception as e:  # noqa: BLE001
                    plan_info["read_error"] = f"sha256_failed: {type(e).__name__}: {e}"
                if obj is not None and isinstance(obj.get("planned_chunks"), int):
                    plan_info["planned_chunks"] = int(obj["planned_chunks"])
        else:
            plan_info["read_error"] = "plan_missing"

    # count snapshot (best-effort)
    count_err: Optional[str] = None
    if collection_count is None:
        collection_count, count_err = _try_collection_count(db=db, collection=collection)

    # 1) legacy-like state payload (kept as top-level fields for consumers)
    payload: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": "db_build_stamp",
        "root": str(root.as_posix()),
        # legacy-ish fields
        "updated_at": _iso_local(),
        "writer": str(writer),
        "db": str(db.as_posix()),
        "collection": str(collection),
        "schema_hash": schema_hash,
        "collection_count": collection_count,
        "count_error": count_err,
        "plan": plan_info,
        "note": "Updated only by successful write-to-db operations (build/upsert/sync) or explicit manual stamp.",
    }

    # 2) report items (no backslashes allowed anywhere under each item)
    items: list[Dict[str, Any]] = []

    items.append(
        ensure_item_fields(
            _sanitize_no_backslash(
                {
                    "tool": "db_build_stamp",
                    "key": "stamp_written",
                    "title": "db_build_stamp written",
                    "status_label": "PASS",
                    "severity_level": 0,
                    "message": f"wrote {out_path.as_posix()} (collection={collection})",
                    "detail": {
                        "out_path": out_path.as_posix(),
                        "db": db.as_posix(),
                        "collection": str(collection),
                        "schema_hash": schema_hash,
                        "collection_count": collection_count,
                        "writer": str(writer),
                    },
                }
            ),
            tool_default="db_build_stamp",
        )
    )

    if count_err:
        items.append(
            ensure_item_fields(
                _sanitize_no_backslash(
                    {
                        "tool": "db_build_stamp",
                        "key": "collection_count_unavailable",
                        "title": "collection_count unavailable",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": str(count_err),
                        "detail": {"db": db.as_posix(), "collection": str(collection)},
                    }
                ),
                tool_default="db_build_stamp",
            )
        )

    if plan_info.get("read_error"):
        items.append(
            ensure_item_fields(
                _sanitize_no_backslash(
                    {
                        "tool": "db_build_stamp",
                        "key": "plan_read_issue",
                        "title": "plan read issue",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": str(plan_info.get("read_error")),
                        "detail": {"plan_path": str(plan_info.get("path") or "")},
                    }
                ),
                tool_default="db_build_stamp",
            )
        )

    payload["items"] = items
    payload["summary"] = compute_summary(items).to_dict()

    # Keep an explicit "data" block for future evolvability.
    payload.setdefault("data", {})
    if isinstance(payload["data"], dict):
        payload["data"].setdefault(
            "state",
            {
                "db": str(db.as_posix()),
                "collection": str(collection),
                "schema_hash": schema_hash,
                "collection_count": collection_count,
                "count_error": count_err,
                "plan": plan_info,
                "writer": str(writer),
                "updated_at": payload.get("updated_at"),
            },
        )

    final_obj = prepare_report_for_file_output(payload)
    if not isinstance(final_obj, dict):
        raise RuntimeError("prepare_report_for_file_output did not return dict")

    # atomic-ish write
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(final_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)

    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Write db_build_stamp.json (state metadata, schema_version=2 report)")
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="chroma_db")
    ap.add_argument("--collection", default="rag_chunks")
    ap.add_argument("--state-root", default="data_processed/index_state")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--writer", default="manual")
    ap.add_argument("--schema-hash", default=None)
    ap.add_argument("--out", default=None, help="output path (default: <state_root>/db_build_stamp.json)")
    ap.add_argument(
        "--collection-count",
        default=None,
        help="optional: provide collection.count snapshot to avoid opening Chroma (int)",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db).resolve()
    state_root = (root / args.state_root).resolve()
    plan_path = None
    if args.plan:
        plan_path = (root / args.plan).resolve() if not Path(args.plan).is_absolute() else Path(args.plan).resolve()

    out_path = None
    if args.out:
        out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()

    cc = None
    if args.collection_count is not None:
        try:
            cc = int(args.collection_count)
        except Exception:
            cc = None

    p = write_db_build_stamp(
        root=root,
        db=db,
        collection=str(args.collection),
        state_root=state_root,
        plan_path=plan_path,
        collection_count=cc,
        writer=str(args.writer),
        out_path=out_path,
        schema_hash=str(args.schema_hash) if args.schema_hash else None,
    )

    print(f"[OK] wrote: {p}")
    return 0


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt")
        return 3
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] unhandled exception: {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(_entry())
