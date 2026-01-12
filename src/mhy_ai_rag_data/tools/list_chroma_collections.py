#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""list_chroma_collections.py

目的
----
列出指定 Chroma persistent DB 下所有 collection，并检查目标 collection 是否存在。
这是在模型机上验证“向量库同步成功”的第一步。

用法
----
python list_chroma_collections.py --db chroma_db --expect rag_chunks

退出码
------
0：成功（并且若指定 --expect，则存在）
2：失败（打不开 DB 或 expect 不存在）
"""

from __future__ import annotations

import argparse
from pathlib import Path

from chromadb import PersistentClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="chroma_db", help="Chroma persistent directory")
    ap.add_argument("--expect", default=None, help="Expected collection name")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    print(f"db_path={db}")

    try:
        client = PersistentClient(path=str(db))
        cols = client.list_collections()
    except Exception as e:
        print(f"STATUS: FAIL (cannot open db) - {e}")
        return 2

    names = [c.name for c in cols]
    if not names:
        print("(no collections)")
    else:
        print("collections:")
        for n in names:
            print(f"- name={n!r}")

    if args.expect:
        if args.expect in names:
            print(f"STATUS: OK (found collection {args.expect!r})")
            return 0
        print(f"STATUS: FAIL (missing expected collection {args.expect!r})")
        return 2

    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
