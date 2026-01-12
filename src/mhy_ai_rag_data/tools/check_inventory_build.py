#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_inventory_build.py

目的：
- 为 inventory.csv 提供“可审计快照（snapshot）”与“前后差异对比（diff）”。
- 解决场景：输入集合漂移（新增/删除/内容变更/ID 变更）导致下游 units/plan/build/check 发生变化。

用法（在仓库根目录）：
  # 1) 生成快照
  python tools/check_inventory_build.py --snapshot-out data_processed/build_reports/inventory_snapshot.json

  # 2) 对比当前 inventory 与历史快照
  python tools/check_inventory_build.py --compare-snapshot data_processed/build_reports/inventory_snapshot.json \
    --diff-out data_processed/build_reports/inventory_diff.json

  # 3) 严格模式（存在差异即非 0，适合 CI/门禁）
  python tools/check_inventory_build.py --compare-snapshot data_processed/build_reports/inventory_snapshot.json --strict

退出码：
  0: PASS（无差异）或仅生成 snapshot
  2: FAIL（存在差异且 --strict）或输入/解析错误
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from mhy_ai_rag_data.project_paths import find_project_root


SNAPSHOT_SCHEMA = "inventory_snapshot_v1"
DIFF_SCHEMA = "inventory_diff_v1"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _safe_int(x: str | None, default: int = 0) -> int:
    try:
        return int(str(x or "").strip())
    except Exception:
        return default


@dataclass(frozen=True)
class InvRow:
    doc_id: str
    source_uri: str
    filename: str
    source_type: str
    content_sha256: str
    size_bytes: int
    updated_at: str
    note: str

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "InvRow":
        return InvRow(
            doc_id=(d.get("doc_id") or "").strip(),
            source_uri=(d.get("source_uri") or "").strip(),
            filename=(d.get("filename") or "").strip(),
            source_type=(d.get("source_type") or "").strip(),
            content_sha256=(d.get("content_sha256") or "").strip(),
            size_bytes=_safe_int(d.get("size_bytes"), 0),
            updated_at=(d.get("updated_at") or "").strip(),
            note=(d.get("note") or "").strip(),
        )

    def key(self) -> str:
        return self.source_uri


def load_inventory_csv(path: Path) -> List[InvRow]:
    if not path.exists():
        raise FileNotFoundError(f"missing inventory.csv: {path}")
    rows: List[InvRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("inventory.csv missing header")
        for i, d in enumerate(reader, start=2):
            try:
                r = InvRow.from_dict(d)
            except Exception as e:
                raise ValueError(f"inventory.csv parse error at line {i}: {type(e).__name__}: {e}")
            if not r.source_uri:
                # defensive: skip empty rows
                continue
            rows.append(r)
    rows.sort(key=lambda x: x.source_uri)
    return rows


def build_summary(rows: List[InvRow]) -> Dict[str, Any]:
    type_counts: Dict[str, int] = {}
    total_size = 0
    for r in rows:
        type_counts[r.source_type] = type_counts.get(r.source_type, 0) + 1
        total_size += int(r.size_bytes)
    return {
        "rows": len(rows),
        "total_size_bytes": total_size,
        "source_type_counts": dict(sorted(type_counts.items(), key=lambda kv: kv[0])),
    }


def inventory_digest(rows: List[InvRow]) -> str:
    # stable digest for quick comparisons
    parts: List[str] = []
    for r in rows:
        parts.append(
            "|".join(
                [
                    r.source_uri,
                    r.content_sha256,
                    str(r.size_bytes),
                    r.updated_at,
                    r.doc_id,
                ]
            )
        )
    return sha256_text("\n".join(parts))


def write_snapshot(out_path: Path, inventory_path: Path, rows: List[InvRow]) -> None:
    payload: Dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "ts": now_iso(),
        "inventory_path": inventory_path.as_posix(),
        "summary": build_summary(rows),
        "inventory_digest_sha256": inventory_digest(rows),
        "items": [
            {
                "doc_id": r.doc_id,
                "source_uri": r.source_uri,
                "filename": r.filename,
                "source_type": r.source_type,
                "content_sha256": r.content_sha256,
                "size_bytes": r.size_bytes,
                "updated_at": r.updated_at,
                "note": r.note,
            }
            for r in rows
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_snapshot(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing snapshot: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot json must be object")
    if data.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError(f"unsupported snapshot schema: {data.get('schema')}")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("snapshot.items must be list")
    return data


def index_items(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for it in items:
        su = str(it.get("source_uri") or "").strip()
        if su:
            out[su] = it
    return out


def diff_inventory(
    current: List[InvRow],
    snapshot_items: List[Dict[str, Any]],
    *,
    compare_updated_at: bool,
) -> Dict[str, Any]:
    cur_map: Dict[str, InvRow] = {r.source_uri: r for r in current}
    snap_map = index_items(snapshot_items)

    cur_keys = set(cur_map.keys())
    snap_keys = set(snap_map.keys())
    added = sorted(list(cur_keys - snap_keys))
    removed = sorted(list(snap_keys - cur_keys))

    changed_content: List[Dict[str, Any]] = []
    changed_meta: List[Dict[str, Any]] = []
    doc_id_changed: List[Dict[str, Any]] = []

    common = sorted(list(cur_keys & snap_keys))
    for k in common:
        cur = cur_map[k]
        snap = snap_map.get(k, {})

        snap_doc_id = str(snap.get("doc_id") or "")
        snap_sha = str(snap.get("content_sha256") or "")
        snap_size = _safe_int(str(snap.get("size_bytes") or "0"), 0)
        snap_upd = str(snap.get("updated_at") or "")

        # content drift: sha/size (updated_at optional)
        content_diff: List[Dict[str, Any]] = []
        if cur.content_sha256 != snap_sha:
            content_diff.append({"field": "content_sha256", "a": snap_sha, "b": cur.content_sha256})
        if int(cur.size_bytes) != int(snap_size):
            content_diff.append({"field": "size_bytes", "a": snap_size, "b": cur.size_bytes})
        if compare_updated_at and (cur.updated_at != snap_upd):
            content_diff.append({"field": "updated_at", "a": snap_upd, "b": cur.updated_at})
        if content_diff:
            changed_content.append({"source_uri": k, "diff": content_diff})

        # doc_id drift (even if content same)
        if cur.doc_id and snap_doc_id and (cur.doc_id != snap_doc_id):
            doc_id_changed.append({"source_uri": k, "a": snap_doc_id, "b": cur.doc_id})

        # meta drift
        meta_diff: List[Dict[str, Any]] = []
        for field in ["filename", "source_type", "note"]:
            av = str(snap.get(field) or "")
            bv = getattr(cur, field)
            if av != bv:
                meta_diff.append({"field": field, "a": av, "b": bv})
        if meta_diff:
            changed_meta.append({"source_uri": k, "diff": meta_diff})

    return {
        "added": added,
        "removed": removed,
        "changed_content": changed_content,
        "changed_meta": changed_meta,
        "doc_id_changed": doc_id_changed,
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="project root (default: auto-detect from CWD)")
    ap.add_argument("--inventory", default="inventory.csv", help="inventory.csv path (relative to root by default)")
    ap.add_argument("--snapshot-out", default="", help="write snapshot json to this path")
    ap.add_argument("--compare-snapshot", default="", help="compare current inventory.csv against a snapshot json")
    ap.add_argument("--diff-out", default="", help="write diff json to this path (optional)")
    ap.add_argument("--compare-updated-at", action="store_true", help="treat updated_at changes as content drift")
    ap.add_argument("--strict", action="store_true", help="exit non-zero when diff exists")
    ap.add_argument("--max-details", type=int, default=200, help="cap details lists in diff report")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    root = find_project_root(args.root)
    inv_path = Path(args.inventory)
    if not inv_path.is_absolute():
        inv_path = (root / inv_path)
    inv_path = inv_path.resolve(strict=False)

    try:
        rows = load_inventory_csv(inv_path)
    except Exception as e:
        print(f"[check_inventory] FAIL: {type(e).__name__}: {e}")
        return 2

    # snapshot
    if args.snapshot_out:
        outp = Path(args.snapshot_out)
        if not outp.is_absolute():
            outp = (root / outp)
        outp = outp.resolve(strict=False)
        write_snapshot(outp, inv_path.relative_to(root), rows)
        print(f"[check_inventory] snapshot_out={outp} rows={len(rows)}")
        # if only snapshot requested, continue (allow compare in same run)

    # compare
    if args.compare_snapshot:
        snap_path = Path(args.compare_snapshot)
        if not snap_path.is_absolute():
            snap_path = (root / snap_path)
        snap_path = snap_path.resolve(strict=False)
        try:
            snap = load_snapshot(snap_path)
        except Exception as e:
            print(f"[check_inventory] FAIL: {type(e).__name__}: {e}")
            return 2

        diffs = diff_inventory(rows, snap.get("items") or [], compare_updated_at=bool(args.compare_updated_at))
        has_diff = bool(
            diffs["added"]
            or diffs["removed"]
            or diffs["changed_content"]
            or diffs["changed_meta"]
            or diffs["doc_id_changed"]
        )

        # trim
        md = max(0, int(args.max_details))
        def _trim_list(x: list[Any]) -> tuple[list[Any], int]:
            if len(x) <= md:
                return x, 0
            return x[:md], len(x) - md

        added_list, added_more = _trim_list(diffs["added"])
        removed_list, removed_more = _trim_list(diffs["removed"])
        cc_list, cc_more = _trim_list(diffs["changed_content"])
        cm_list, cm_more = _trim_list(diffs["changed_meta"])
        id_list, id_more = _trim_list(diffs["doc_id_changed"])

        report: Dict[str, Any] = {
            "schema": DIFF_SCHEMA,
            "ts": now_iso(),
            "root": root.as_posix(),
            "inventory_path": inv_path.relative_to(root).as_posix() if root in inv_path.parents else inv_path.as_posix(),
            "snapshot_path": snap_path.relative_to(root).as_posix() if root in snap_path.parents else snap_path.as_posix(),
            "summary": {
                "current": build_summary(rows),
                "snapshot_rows": int((snap.get("summary") or {}).get("rows") or 0),
                "has_diff": has_diff,
                "counts": {
                    "added": len(diffs["added"]),
                    "removed": len(diffs["removed"]),
                    "changed_content": len(diffs["changed_content"]),
                    "changed_meta": len(diffs["changed_meta"]),
                    "doc_id_changed": len(diffs["doc_id_changed"]),
                },
                "truncated": {
                    "added_more": added_more,
                    "removed_more": removed_more,
                    "changed_content_more": cc_more,
                    "changed_meta_more": cm_more,
                    "doc_id_changed_more": id_more,
                },
            },
            "details": {
                "added": added_list,
                "removed": removed_list,
                "changed_content": cc_list,
                "changed_meta": cm_list,
                "doc_id_changed": id_list,
            },
        }

        if args.diff_out:
            diff_out = Path(args.diff_out)
            if not diff_out.is_absolute():
                diff_out = (root / diff_out)
            diff_out = diff_out.resolve(strict=False)
        else:
            diff_out = inv_path.parent / f"inventory_diff_{int(time.time())}.json"

        _write_json(diff_out, report)
        print(f"[check_inventory] compare={'FAIL' if has_diff else 'PASS'} out={diff_out}")

        if has_diff and args.strict:
            return 2
        return 0

    # no compare => pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
