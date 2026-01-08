#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_chroma_coverage_vs_units.py

目的
----
用于“中断恢复/是否需要重跑”的快速判断：

- 以 build_chroma_index.py 的 chunking/ID 口径（doc_id:chunk_index）为准，
  从 data_processed/text_units.jsonl 重新计算**期望 chunk IDs**。
- 去 Chroma collection 批量查询这些 IDs 是否存在，输出：
  expected / present / missing / coverage%

说明
----
本项目 build 使用 upsert 且 chunk_id 可复现，因此：
- 重新运行 build 不会产生重复记录（同 ID 覆盖写入），但会重复计算 embedding。
- 该脚本可帮助你在“杀进程/断电后”判断缺口比例，再决定是否重跑。

用法
----
python tools/check_chroma_coverage_vs_units.py \
  --root . \
  --units data_processed/text_units.jsonl \
  --db chroma_db \
  --collection rag_chunks \
  --include-media-stub true \
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 \
  --batch 200

退出码
------
0：成功输出覆盖率
2：失败（输入缺失/collection 不可读）
"""

from __future__ import annotations

import argparse
from pathlib import Path



def _bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Check coverage of Chroma records vs units-derived expected chunk IDs.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--units", default="data_processed/text_units.jsonl")
    ap.add_argument("--db", default="chroma_db")
    ap.add_argument("--collection", default="rag_chunks")
    ap.add_argument("--include-media-stub", default="true")
    ap.add_argument("--chunk-chars", type=int, default=1200)
    ap.add_argument("--overlap-chars", type=int, default=120)
    ap.add_argument("--min-chunk-chars", type=int, default=200)
    ap.add_argument("--batch", type=int, default=200)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    units_path = (root / args.units).resolve()
    if not units_path.exists():
        print(f"[FATAL] units not found: {units_path}")
        return 2

    try:
        from mhy_ai_rag_data import build_chroma_index as mod
        ChunkConf = mod.ChunkConf
        iter_units = mod.iter_units
        should_index_unit = mod.should_index_unit
        build_chunks_from_unit = mod.build_chunks_from_unit
    except Exception as e:
        print(f"[FATAL] cannot import from mhy_ai_rag_data.build_chroma_index: {e}")
        return 2

    include_media_stub = _bool(args.include_media_stub)
    conf = ChunkConf(max_chars=args.chunk_chars, overlap_chars=args.overlap_chars, min_chars=args.min_chunk_chars)

    # 1) compute expected ids
    expected_ids: list[str] = []
    for unit in iter_units(units_path):
        if not should_index_unit(unit, include_media_stub):
            continue
        chunks, base_md = build_chunks_from_unit(unit, conf)
        if not chunks:
            continue
        doc_id = str(base_md.get("doc_id"))
        for i in range(len(chunks)):
            expected_ids.append(f"{doc_id}:{i}")

    expected = len(expected_ids)
    print(f"expected_chunks={expected}")
    print(f"include_media_stub={include_media_stub}")
    print(f"chunk_conf=chunk_chars:{args.chunk_chars} overlap_chars:{args.overlap_chars} min_chunk_chars:{args.min_chunk_chars}")

    # 2) query chroma for presence
    from chromadb import PersistentClient
    client = PersistentClient(path=str((root / args.db).resolve()))
    try:
        coll = client.get_collection(args.collection)
    except Exception as e:
        print(f"[FATAL] cannot open collection: {e}")
        return 2

    present = 0
    missing = 0
    batch = max(1, int(args.batch))
    for i in range(0, expected, batch):
        ids = expected_ids[i : i + batch]
        try:
            got = coll.get(ids=ids, include=[])
        except Exception as e:
            print(f"[FATAL] collection.get failed at batch {i//batch}: {e}")
            return 2
        got_ids = set(got.get("ids") or [])
        present += len(got_ids)
        missing += (len(ids) - len(got_ids))

    cov = (present / expected * 100.0) if expected > 0 else 100.0
    print(f"present={present}")
    print(f"missing={missing}")
    print(f"coverage_percent={cov:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
