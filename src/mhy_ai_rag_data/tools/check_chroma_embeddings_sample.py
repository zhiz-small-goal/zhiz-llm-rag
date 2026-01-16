#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_chroma_embeddings_sample.py

目的
----
对 Chroma collection 抽样读取 embeddings，并做快速一致性检查：
- 维度是否一致
- 向量 L2 范数分布（用于判断是否做了归一化）
- 是否存在 NaN/Inf

注意
----
Chroma 默认 query 不返回 embeddings；本脚本使用 coll.get(include=["embeddings"]) 抽样读取。
数据集很大时请把 --limit 设小。

用法
----
python check_chroma_embeddings_sample.py --db chroma_db --collection rag_chunks --limit 50
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from chromadb import PersistentClient


def _norm2(v):
    s = 0.0
    for x in v:
        fx = float(x)
        if math.isnan(fx) or math.isinf(fx):
            return float("nan")
        s += fx * fx
    return math.sqrt(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="chroma_db")
    ap.add_argument("--collection", default="rag_chunks")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    client = PersistentClient(path=str(db_path))
    try:
        coll = client.get_collection(args.collection)
    except Exception as e:
        print(f"STATUS: FAIL (cannot open collection) - {e}")
        return 2

    try:
        res = coll.get(limit=args.limit, include=["embeddings", "metadatas"])
    except Exception as e:
        print(f"STATUS: FAIL (cannot get embeddings) - {e}")
        return 2

    embs = res.get("embeddings")
    if embs is None:
        embs = []
    if len(embs) == 0:
        print("STATUS: WARN (no embeddings returned; collection empty or backend disabled embeddings)")
        return 0

    dims = [len(e) for e in embs if e is not None]
    if not dims:
        print("STATUS: WARN (embeddings are None)")
        return 0

    dim_set = sorted(set(dims))
    norms = [_norm2(e) for e in embs if e is not None]
    norms_clean = [n for n in norms if not math.isnan(n)]

    print(f"db_path={db_path}")
    print(f"collection={args.collection}")
    print(f"sampled={len(embs)}")
    print(f"dims_set={dim_set}")
    if norms_clean:
        print(f"norm2_min={min(norms_clean):.6f}")
        print(f"norm2_max={max(norms_clean):.6f}")
        print(f"norm2_mean={(sum(norms_clean) / len(norms_clean)):.6f}")

    if len(dim_set) != 1:
        print("STATUS: WARN (embedding dimension not consistent)")
    else:
        print("STATUS: OK (dimension consistent)")

    # heuristic: if normalized for cosine, norm should be close to 1
    if norms_clean:
        near1 = sum(1 for n in norms_clean if abs(n - 1.0) < 1e-2)
        print(f"near_unit_norm={near1}/{len(norms_clean)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
