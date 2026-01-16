import argparse
from typing import Any, List, Optional

from chromadb import PersistentClient
from FlagEmbedding import BGEM3FlagModel


def build_embedder(
    model_name: str = "BAAI/bge-m3", device: str = "cpu", batch_size: int = 32
) -> tuple[BGEM3FlagModel, int]:
    """
    Create a BGEM3FlagModel embedder consistent with the index build step.
    """
    model = BGEM3FlagModel(model_name, use_fp16=True, device=device)
    return model, batch_size


def embed_queries(model: BGEM3FlagModel, queries: List[str], batch_size: int = 32) -> Any:
    """
    Encode queries into dense embeddings using bge-m3.
    """
    outputs = model.encode(queries, batch_size=batch_size)
    dense_vecs = outputs["dense_vecs"]
    return dense_vecs


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Chroma RAG query CLI for manual inspection.")
    parser.add_argument("--db", default="chroma_db", help="Path to Chroma persistent directory")
    parser.add_argument("--collection", default="rag_chunks", help="Collection name")
    parser.add_argument("--q", required=True, help="Query text")
    parser.add_argument("--k", type=int, default=5, help="Number of results to retrieve")
    parser.add_argument("--device", default="cpu", help="Device for embedding model, e.g. cpu / cuda:0")
    parser.add_argument(
        "--embed-model",
        default="BAAI/bge-m3",
        help="Embedding model name; should match the one used in build step",
    )
    parser.add_argument("--embed-batch", type=int, default=32, help="Batch size for embedding")
    parser.add_argument(
        "--where",
        default=None,
        help='Metadata filter, e.g. "source_type=md" or "access=public,pii=no"',
    )
    args = parser.parse_args()

    print(f"db_path={args.db}")
    print(f"collection={args.collection}")
    print(f"query={args.q!r}")
    print(f"k={args.k}")
    print(f"embed_model={args.embed_model}")
    print(f"device={args.device}")

    # 1) Connect to Chroma
    client = PersistentClient(path=args.db)
    try:
        coll = client.get_collection(args.collection)
    except Exception as e:
        print(f"STATUS: FAIL (cannot open collection) - {e}")
        return

    # 2) Build embedder and encode query
    try:
        model, batch_size = build_embedder(args.embed_model, device=args.device, batch_size=args.embed_batch)
    except Exception as e:
        print(f"STATUS: FAIL (cannot init embedding model) - {e}")
        return

    try:
        q_vec = embed_queries(model, [args.q], batch_size=batch_size)[0]
    except Exception as e:
        print(f"STATUS: FAIL (cannot embed query) - {e}")
        return

    # 3) Query Chroma
    where_filter: Optional[dict[str, Any]] = None
    if args.where:
        where_filter = {}
        for kv in str(args.where).split(","):
            kv = kv.strip()
            if not kv or "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            where_filter[k.strip()] = v.strip()

    try:
        results = coll.query(
            query_embeddings=[q_vec],
            n_results=args.k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        print(f"STATUS: FAIL (chroma query failed) - {e}")
        return

    ids_list = results.get("ids")
    docs_list = results.get("documents")
    metas_list = results.get("metadatas")
    dists_list = results.get("distances")

    if not ids_list or not docs_list or not metas_list or not dists_list:
        print("STATUS: INFO (no results)")
        return

    ids = ids_list[0]
    docs = docs_list[0]
    metas = metas_list[0]
    dists = dists_list[0]

    print(f"retrieved={len(ids)}")
    if not ids:
        print("STATUS: INFO (no results)")
        return

    print("\nTop results:")
    for i in range(len(ids)):
        meta = metas[i] or {}
        text = docs[i] or ""
        text_preview = text.replace("\n", " ")
        if len(text_preview) > 200:
            text_preview = text_preview[:200] + "..."
        print(f"[{i + 1}] id={ids[i]}")
        print(f"    distance={dists[i]}")
        print(f"    doc_id={meta.get('doc_id')}")
        print(f"    source_uri={meta.get('source_uri')}")
        print(f"    locator={meta.get('locator')}")
        print(f"    text_preview={text_preview}")


if __name__ == "__main__":
    main()
