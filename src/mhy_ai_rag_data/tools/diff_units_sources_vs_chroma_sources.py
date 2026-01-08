#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff_units_sources_vs_chroma_sources.py

目的
----
对比：text_units.jsonl 的 source_uri 集合 vs Chroma collection 中 metadata 的 source_uri 集合。

典型用途
--------
1) 解释“为什么库里 unique_source_uri 比 units 少很多”：通常是构建阶段按 source_type 过滤导致。
2) 当你引入 --include-media-stub 或 OCR/ASR 后，确认媒体是否按预期进入库。

用法
----
python diff_units_sources_vs_chroma_sources.py \
  --root . \
  --units data_processed/text_units.jsonl \
  --db chroma_db \
  --collection rag_chunks \
  --max-sample 20

退出码
------
0：成功
2：失败（文件/库无法读取）
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from chromadb import PersistentClient


def _ext(p: str) -> str:
    try:
        return Path(p).suffix.lower() or "(no_ext)"
    except Exception:
        return "(bad_path)"


def load_units_sources(units_path: Path) -> set[str]:
    s: set[str] = set()
    with units_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            uri = str(obj.get("source_uri", "") or "").strip()
            if uri:
                s.add(uri)
    return s


def load_chroma_sources(db_path: Path, collection: str) -> set[str]:
    client = PersistentClient(path=str(db_path))
    coll = client.get_collection(collection)

    # Chroma 的 get(limit=...) 不保证能一次性拿完；
    # 这里用 offset 分页拉取 metadata，直到取完。
    sources: set[str] = set()
    offset = 0
    page = 2000
    while True:
        res = coll.get(limit=page, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        if not metas:
            break
        for md in metas:
            if not md:
                continue
            uri = str(md.get("source_uri", "") or "").strip()
            if uri:
                sources.add(uri)
        offset += len(metas)
        if len(metas) < page:
            break
    return sources


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff unique source_uri between units and Chroma collection")
    ap.add_argument("--root", default=".")
    ap.add_argument("--units", default="data_processed/text_units.jsonl")
    ap.add_argument("--db", default="chroma_db")
    ap.add_argument("--collection", default="rag_chunks")
    ap.add_argument("--max-sample", type=int, default=20)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    units_path = (root / args.units).resolve()
    db_path = (root / args.db).resolve()

    if not units_path.exists():
        print(f"[FATAL] units not found: {units_path}")
        return 2
    if not db_path.exists():
        print(f"[FATAL] chroma db not found: {db_path}")
        return 2

    try:
        units_sources = load_units_sources(units_path)
    except Exception as e:
        print(f"[FATAL] failed to read units: {e}")
        return 2

    try:
        chroma_sources = load_chroma_sources(db_path, args.collection)
    except Exception as e:
        print(f"[FATAL] failed to read chroma collection: {e}")
        return 2

    skipped = sorted(units_sources - chroma_sources)
    added = sorted(chroma_sources - units_sources)

    print(f"units_unique_sources={len(units_sources)}")
    print(f"chroma_unique_sources={len(chroma_sources)}")
    print(f"skipped_sources(units_only)={len(skipped)}")
    print(f"added_sources(chroma_only)={len(added)}")

    if skipped:
        c = Counter(_ext(x) for x in skipped)
        print("\nSkipped extensions (top 15):")
        for k, v in c.most_common(15):
            print(f"  {k}: {v}")
        print("\nSkipped sample:")
        for x in skipped[: args.max_sample]:
            print(f"  {x}")

    if added:
        print("\nAdded sample (chroma_only):")
        for x in added[: args.max_sample]:
            print(f"  {x}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
