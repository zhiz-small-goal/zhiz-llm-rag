
"""Chroma 检索封装。

提供 retrieve(question, k) -> SourceChunk 列表，
供 RAG 上层直接调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Any

from mhy_ai_rag_data.rag_config import CHROMA_DB_PATH, CHROMA_COLLECTION, RAG_TOP_K
from mhy_ai_rag_data.embeddings_bge_m3 import embed_query

_CLIENT: Any = None
_COLLECTION = None


@dataclass
class SourceChunk:
    sid: str
    doc_id: str | None
    source_uri: str | None
    locator: str | None
    text: str


def _get_collection():
    global _CLIENT, _COLLECTION
    if _COLLECTION is None:
        from chromadb import PersistentClient
        _CLIENT = PersistentClient(path=CHROMA_DB_PATH)
        _COLLECTION = _CLIENT.get_collection(CHROMA_COLLECTION)
    return _COLLECTION


def retrieve(question: str, k: int | None = None, where: Optional[Dict[str, str]] = None) -> List[SourceChunk]:
    """对自然语言 question 进行检索，返回 SourceChunk 列表。

    参数：
      - k: 返回 top-k 条数（None 则取配置 RAG_TOP_K）
      - where: 可选 Chroma metadata 过滤（where dict），例如 {"source_type":"md"}

    说明：where 仅用于隔离变量做回归/诊断；若你在上层做更复杂的过滤/重排，建议在 RAG 层实现策略。
    """
    if k is None:
        k = RAG_TOP_K

    coll = _get_collection()
    q_vec = embed_query(question)
    results = coll.query(query_embeddings=[q_vec], n_results=k, where=where)

    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    chunks: List[SourceChunk] = []
    for idx, cid in enumerate(ids):
        meta = metas[idx] or {}
        text = docs[idx] or ""
        chunks.append(
            SourceChunk(
                sid=f"S{idx+1}",
                doc_id=meta.get("doc_id"),
                source_uri=meta.get("source_uri"),
                locator=meta.get("locator"),
                text=text,
            )
        )
    return chunks


if __name__ == "__main__":
    import argparse
    import textwrap as _tw

    parser = argparse.ArgumentParser(description="简单 CLI：检索并打印前 k 条结果。")
    parser.add_argument("--q", required=True, help="查询问题文本")
    parser.add_argument("--k", type=int, default=None, help="返回结果条数，默认取配置中的 RAG_TOP_K")
    parser.add_argument("--where", default=None, help='Metadata filter, e.g. "source_type=md" or "access=public,pii=no"')
    args = parser.parse_args()

    where = None
    if args.where:
        s = (args.where or "").strip()
        # 兼容两种写法：
        # 1) JSON dict: {"source_type":"md"}
        # 2) kv 列表: source_type=md,access=public
        if s.startswith("{"):
            import json as _json

            try:
                obj = _json.loads(s)
                if isinstance(obj, dict):
                    where = {str(k): str(v) for k, v in obj.items()}
            except Exception:
                where = None
        else:
            d = {}
            for kv in s.split(","):
                kv = kv.strip()
                if not kv or "=" not in kv:
                    continue
                k, v = kv.split("=", 1)
                d[k.strip()] = v.strip()
            where = d or None

    print(f"query={args.q!r}")
    print(f"k={args.k or RAG_TOP_K}")
    print(f"where={where!r}")

    chunks = retrieve(args.q, args.k, where=where)
    print(f"retrieved={len(chunks)}\n")

    for ch in chunks:
        preview = ch.text.replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "..."
        print(f"{ch.sid}: doc_id={ch.doc_id} source_uri={ch.source_uri} locator={ch.locator}")
        print(_tw.indent(preview, prefix="    "))
        print()
