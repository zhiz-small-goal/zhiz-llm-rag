#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suggest_eval_case.py

目的：
- 在你“对资料内容不熟”的情况下，半自动生成 eval case：
  1) 用当前 Chroma 向量库对 query 做 topK 检索，给出候选 expected_sources（来源路径）
  2) 从 topK 文本片段中提取一组“更可能稳定出现”的 must_include 候选（锚点词）
  3) 输出一个可直接粘贴进 eval_cases.jsonl 的 JSON 对象（也可直接 append）

为什么有用：
- 你不需要预先把整套 docs 背熟，只需要依赖检索命中的“最相关片段”
- must_include 的候选来自片段内真实出现的词/命令/路径，减少凭空猜测

注意：
- must_include 是“最小断言”，应偏向“稳定锚点”（命令、参数名、文件名、关键术语），
  避免纯同义词/泛化动词导致脆弱或误判。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def stable_id_from_query(query: str) -> str:
    h = hashlib.sha1(query.strip().encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"case_{h}"


def pick_meta_source(md: Dict[str, Any], field_priority: List[str]) -> str:
    for k in field_priority:
        v = md.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fallback: any string field that looks like a path
    for k, v in md.items():
        if isinstance(v, str) and ("/" in v or "\\" in v) and len(v) <= 260:
            return v.strip()
    return ""


ASCII_TOKEN_RX = re.compile(r"[A-Za-z0-9_./:\\-]{3,}")
CH_RX = re.compile(r"[\u4e00-\u9fff]+")

# 极简停用词（避免把非常泛的词当锚点；后续可按你项目语料补充）
STOP_PHRASES = {
    "如何", "怎么", "什么", "以及", "一个", "我们", "可以", "进行", "这里", "这个", "因为", "如果", "然后",
    "需要", "建议", "注意", "步骤", "使用", "命令", "方法", "问题", "项目", "目录", "文件", "脚本",
}


def extract_candidates(text: str, max_terms: int = 8) -> List[str]:
    """
    从检索片段提取 must_include 候选：
    - 优先：ASCII token（命令、参数、路径、端点）
    - 再：中文 n-gram（2~4字）频次较高者
    约束：
    - 候选必须真实出现在 text 中
    - 去重、去停用、避免过短
    """
    candidates: List[str] = []

    # 1) ASCII tokens
    ascii_tokens = ASCII_TOKEN_RX.findall(text)
    # 去掉纯数字/过短
    ascii_tokens = [t for t in ascii_tokens if not t.isdigit() and len(t) >= 3]
    # 更偏好含 / - _ . 的 token（更像命令/路径/端点）
    ascii_tokens.sort(key=lambda s: (0 if any(ch in s for ch in "/\\-_.:") else 1, -len(s)))
    for t in ascii_tokens:
        if t not in candidates:
            candidates.append(t)
        if len(candidates) >= max_terms // 2:
            break

    # 2) 中文 n-gram（2~4）
    ch_segments = CH_RX.findall(text)
    grams_count: Dict[str, int] = {}
    for seg in ch_segments:
        seg = seg.strip()
        if len(seg) < 2:
            continue
        # 只取中等长度片段生成 n-gram，避免全文爆炸
        if len(seg) > 200:
            seg = seg[:200]
        for n in (2, 3, 4):
            if len(seg) < n:
                continue
            for i in range(0, len(seg) - n + 1):
                g = seg[i:i+n]
                if g in STOP_PHRASES:
                    continue
                # 避免全是泛词的片段
                if any(sw in g for sw in ("如何", "怎么", "什么")):
                    continue
                grams_count[g] = grams_count.get(g, 0) + 1

    # 频次优先，长度次之
    grams = sorted(grams_count.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    for g, _ in grams:
        if g in STOP_PHRASES:
            continue
        if g not in candidates:
            candidates.append(g)
        if len(candidates) >= max_terms:
            break

    return candidates[:max_terms]


def load_cases_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def append_case(path: Path, case: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--query", required=True, help="user query to build eval case")
    ap.add_argument("--bucket", default="official", choices=["official", "oral", "ambiguous"], help="case bucket: official/oral/ambiguous")
    ap.add_argument("--pair-id", default="", help="bind oral vs official variants (optional, recommended)")
    ap.add_argument("--concept-id", default="", help="concept grouping id (optional)")
    ap.add_argument("--db", default="chroma_db", help="chroma db directory relative to root")
    ap.add_argument("--collection", default="rag_chunks", help="chroma collection name")
    ap.add_argument("--k", type=int, default=5, help="topK for retrieval")
    ap.add_argument("--meta-field", default="source_uri|source|path|file", help="metadata source field priority, separated by |")
    ap.add_argument("--embed-backend", default="auto", choices=["auto", "flagembedding", "sentence-transformers"], help="embedding backend")
    ap.add_argument("--embed-model", default="BAAI/bge-m3", help="embedding model name (should match index)")
    ap.add_argument("--device", default="cpu", help="embedding device: cpu/cuda (backend dependent)")
    ap.add_argument("--max-terms", type=int, default=8, help="max must_include candidates")
    ap.add_argument("--pick-sources", type=int, default=2, help="how many top sources to include into expected_sources")
    ap.add_argument("--tags", default="suggested", help="comma separated tags")
    ap.add_argument("--out", default="", help="write the suggested case json to this path (optional)")
    ap.add_argument("--append-to", default="", help="append suggested case to an existing jsonl file (optional)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db_path = (root / args.db).resolve()
    if not db_path.exists():
        print(f"[suggest] FAIL: chroma db not found: {db_path}")
        return 2

    # 1) embed
    query_vec: Optional[List[float]] = None
    backend = args.embed_backend
    if backend == "auto":
        backend = "flagembedding"
        try:
            import FlagEmbedding  # type: ignore
        except Exception:
            backend = "sentence-transformers"

    if backend == "flagembedding":
        try:
            from FlagEmbedding import FlagModel  # type: ignore
        except Exception as e:
            print(f"[suggest] FAIL: FlagEmbedding not available: {type(e).__name__}: {e}")
            return 2
        model = FlagModel(args.embed_model, query_instruction_for_retrieval=None, use_fp16=("cuda" in args.device.lower()))
        emb = model.encode([args.query])
        query_vec = emb[0].tolist() if hasattr(emb[0], "tolist") else list(emb[0])
    else:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:
            print(f"[suggest] FAIL: sentence_transformers not available: {type(e).__name__}: {e}")
            return 2
        model = SentenceTransformer(args.embed_model, device=args.device)
        emb = model.encode([args.query], normalize_embeddings=True)
        query_vec = emb[0].tolist() if hasattr(emb[0], "tolist") else list(emb[0])

    # 2) query chroma
    try:
        import chromadb  # type: ignore
    except Exception as e:
        print(f"[suggest] FAIL: chromadb not available: {type(e).__name__}: {e}")
        return 2

    client = chromadb.PersistentClient(path=str(db_path))
    try:
        col = client.get_collection(args.collection)
    except Exception as e:
        print(f"[suggest] FAIL: collection not found: {args.collection}  ({type(e).__name__}: {e})")
        return 2

    res = col.query(
        query_embeddings=[query_vec],
        n_results=int(args.k),
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    mds = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    field_priority = [x.strip() for x in args.meta_field.split("|") if x.strip()]
    top_sources: List[str] = []
    top_snippets: List[str] = []

    for i, (doc, md) in enumerate(zip(docs, mds)):
        src = pick_meta_source(md or {}, field_priority)
        if src:
            top_sources.append(src)
        # snippet
        s = str(doc or "")
        s = s.strip()
        if s:
            top_snippets.append(s[:2000])

    # suggested expected_sources: unique, keep first N
    expected_sources = []
    for s in top_sources:
        if s not in expected_sources:
            expected_sources.append(s)
        if len(expected_sources) >= int(args.pick_sources):
            break

    merged_text = "\n".join(top_snippets)
    must_include = extract_candidates(merged_text, max_terms=int(args.max_terms))

    case = {
        "id": stable_id_from_query(args.query),
        "bucket": args.bucket,
        "pair_id": (args.pair_id.strip() or None),
        "concept_id": (args.concept_id.strip() or None),
        "query": args.query,
        "expected_sources": expected_sources if expected_sources else ["<TODO: fill expected_sources>"],
        "must_include": must_include if must_include else ["<TODO: fill must_include>"],
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
        "_suggest_meta": {
            "timestamp": now_iso(),
            "k": int(args.k),
            "collection": args.collection,
            "embed_backend": backend,
            "embed_model": args.embed_model,
            "device": args.device,
            "top_sources": top_sources[: int(args.k)],
            "top_distances": dists[: int(args.k)],
        },
    }

    # output
    print(json.dumps(case, ensure_ascii=False, indent=2))

    if args.out:
        out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[suggest] wrote case json: {out_path}")

    if args.append_to:
        apath = (root / args.append_to).resolve() if not Path(args.append_to).is_absolute() else Path(args.append_to).resolve()
        append_case(apath, case)
        print(f"[suggest] appended to: {apath}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
