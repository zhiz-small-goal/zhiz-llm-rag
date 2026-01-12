#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_eval_retrieval.py

目的：
- 对用例集做“检索侧”回归：是否能在 topK 命中期望来源文档
- 产出可审计报告：每个 case 的命中情况、召回指标（hit@k）

依赖：
- 必需：chromadb
- 可选：FlagEmbedding 或 sentence_transformers（二选一，用于把 query 编码成向量）
  - 优先：FlagEmbedding（若你们已使用 bge-m3/FlagEmbedding 体系）
  - 备选：sentence_transformers

输出：
- <root>/data_processed/build_reports/eval_retrieval_report.json

用法：
  python tools/run_eval_retrieval.py --root . --db chroma_db --collection rag_chunks --k 5 --embed-model BAAI/bge-m3
  python tools/run_eval_retrieval.py --root . --embed-backend flagembedding
  python tools/run_eval_retrieval.py --root . --embed-backend sentence-transformers

注意：
- 需要你在构建索引时使用同一 embedding 模型族，否则向量空间不一致会导致召回退化。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Mapping, Sequence

import platform

from mhy_ai_rag_data.tools.report_stream import StreamWriter, default_run_id

REPORT_SCHEMA_VERSION = "2"
DEFAULT_BUCKET = "official"
ALLOWED_BUCKETS = {"official", "oral", "ambiguous"}

def normalize_bucket(v: Any, warnings: List[Dict[str, Any]], *, case_id: str, line_hint: Optional[int] = None) -> str:
    """
    Normalize bucket for eval cases.
    - missing/empty -> DEFAULT_BUCKET
    - invalid -> "unknown" and emit warning (validator should catch in CI)
    """
    if v is None:
        warnings.append({"code": "missing_bucket_default", "case_id": case_id, "bucket": DEFAULT_BUCKET, "line": line_hint})
        return DEFAULT_BUCKET
    s = str(v).strip().lower()
    if not s:
        warnings.append({"code": "missing_bucket_default", "case_id": case_id, "bucket": DEFAULT_BUCKET, "line": line_hint})
        return DEFAULT_BUCKET
    if s in ALLOWED_BUCKETS:
        return s
    warnings.append({"code": "invalid_bucket_unknown", "case_id": case_id, "bucket": s, "allowed": sorted(list(ALLOWED_BUCKETS)), "line": line_hint})
    return "unknown"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_embedder(backend: str, model_name: str, device: str) -> Any:
    backend = backend.lower().strip()
    if backend in ("auto", "flagembedding"):
        try:
            from FlagEmbedding import FlagModel
            return ("flagembedding", FlagModel(model_name, device=device))
        except Exception:
            if backend == "flagembedding":
                raise
    if backend in ("auto", "sentence-transformers", "sentence_transformers"):
        try:
            from sentence_transformers import SentenceTransformer
            return ("sentence-transformers", SentenceTransformer(model_name, device=device))
        except Exception:
            raise
    raise RuntimeError(f"Unsupported embed backend: {backend}")


def embed_query(embedder: Any, backend: str, text: str) -> List[float]:
    if backend == "flagembedding":
        vec = embedder.encode(text)
        return vec.tolist() if hasattr(vec, "tolist") else list(vec)
    if backend == "sentence-transformers":
        vec = embedder.encode([text], normalize_embeddings=False)[0]
        return vec.tolist() if hasattr(vec, "tolist") else list(vec)
    raise RuntimeError(f"Unknown backend: {backend}")


def extract_source(meta: Mapping[str, Any], meta_field: str) -> str:
    """
    从 metadata 提取来源字段。不同管道可能叫 source/path/file 等。
    - meta_field 支持 "source|path|file" 的优先级表达：用 '|' 分隔多个候选字段
    """
    for key in [k.strip() for k in meta_field.split("|") if k.strip()]:
        if key in meta and meta[key]:
            return str(meta[key])
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--db", default="chroma_db", help="chroma db dir (relative to root)")
    ap.add_argument("--collection", default="rag_chunks", help="collection name")
    ap.add_argument("--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)")
    ap.add_argument("--k", type=int, default=5, help="topK for retrieval")
    ap.add_argument("--meta-field", default="source_uri|source|path|file", help="metadata field(s) for source path (use | to separate)")
    ap.add_argument("--embed-backend", default="auto", help="auto|flagembedding|sentence-transformers")
    ap.add_argument("--embed-model", default="BAAI/bge-m3", help="embed model name")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument("--out", default="data_processed/build_reports/eval_retrieval_report.json", help="output json (relative to root)")
    # stream events (optional, for real-time observability)
    ap.add_argument("--stream-out", default="", help="optional stream events output (relative to root), e.g. data_processed/build_reports/eval_retrieval_report.events.jsonl")
    ap.add_argument("--stream-format", default="jsonl", choices=["jsonl", "json-seq"], help="stream format: jsonl (default) or json-seq (RFC 7464)")
    ap.add_argument("--progress-every-seconds", type=float, default=10.0, help="print progress summary every N seconds; 0 to disable")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cases_path = (root / args.cases).resolve()
    db_path = (root / args.db).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    run_id = default_run_id("eval_retrieval")
    stream_writer = None
    stream_path = (root / args.stream_out).resolve() if args.stream_out else None
    if stream_path:
        ensure_dir(stream_path.parent)
        stream_writer = StreamWriter(stream_path, fmt=args.stream_format).open()
        stream_writer.emit({
            "record_type": "meta",
            "run_id": run_id,
            "tool": "run_eval_retrieval",
            "tool_impl": "src/mhy_ai_rag_data/tools/run_eval_retrieval.py",
            "argv": sys.argv,
            "root": str(root),
            "db_path": str(db_path),
            "collection": args.collection,
            "k": args.k,
            "embed": {"backend": args.embed_backend, "model": args.embed_model, "device": args.device},
        })

    if not cases_path.exists():
        print(f"[eval_retrieval] FAIL: cases not found: {cases_path}")
        return 2
    if not db_path.exists():
        print(f"[eval_retrieval] FAIL: db not found: {db_path}")
        return 2

    try:
        import chromadb
    except Exception as e:
        print(f"[eval_retrieval] FAIL: chromadb import failed: {type(e).__name__}: {e}")
        return 2

    # embedder
    try:
        backend, embedder = load_embedder(args.embed_backend, args.embed_model, args.device)
    except Exception as e:
        print(f"[eval_retrieval] FAIL: embedder init failed: {type(e).__name__}: {e}")
        return 2

    client = chromadb.PersistentClient(path=str(db_path))
    col = client.get_collection(args.collection)

    cases = read_jsonl(cases_path)
    per_case: List[Dict[str, Any]] = []
    hit_count = 0
    warnings: List[Dict[str, Any]] = []
    bucket_stats: Dict[str, Dict[str, Any]] = {}

    t0 = time.time()
    last_progress = t0
    total_cases = len(cases)

    for idx, c in enumerate(cases, start=1):
        cid = str(c.get("id", "")).strip()
        q = str(c.get("query", "")).strip()
        bucket = normalize_bucket(c.get("bucket"), warnings, case_id=cid)
        pair_id = c.get("pair_id")
        concept_id = c.get("concept_id")
        case_t0 = time.time()
        must_include = c.get("must_include", []) or []
        expected = c.get("expected_sources", []) or []
        expected = [str(x) for x in expected]

        qvec = embed_query(embedder, backend, q)
        query_embeddings: List[Sequence[float]] = [qvec]
        res = col.query(query_embeddings=query_embeddings, n_results=args.k, include=["metadatas", "distances"])
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]

        got_sources: List[Dict[str, Any]] = []
        for i, m in enumerate(metadatas):
            m = m or {}
            src = extract_source(m, args.meta_field)
            got_sources.append({"rank": i + 1, "source": src, "distance": distances[i] if i < len(distances) else None})

        # hit rule: any expected substring matches any got source
        def is_hit() -> bool:
            for e in expected:
                for g in got_sources:
                    if e and g["source"] and (e in g["source"]):
                        return True
            # If expected_sources provided as dirs like "docs/" allow prefix match:
            for e in expected:
                if e.endswith("/"):
                    for g in got_sources:
                        if g["source"].replace("\\", "/").startswith(e):
                            return True
            return False

        hit = is_hit() if expected else None
        if hit is True:
            hit_count += 1

        # per-bucket metrics
        bs = bucket_stats.setdefault(bucket, {"cases": 0, "hit_cases": 0})
        bs["cases"] += 1
        if hit is True:
            bs["hit_cases"] += 1

        per_case.append({
            "id": cid,
            "bucket": bucket,
            "pair_id": pair_id,
            "concept_id": concept_id,
            "query": q,
            "expected_sources": expected,
            "must_include": must_include,
            "hit_at_k": hit,
            "topk": got_sources,
            "debug": {
                "retrieval_mode": "dense_only",
                "dense_topk": got_sources,
                "keyword_topk": [],
                "fusion_topk": [],
                "expansion_trace": None,
            },
        })

        if stream_writer is not None:
            stream_writer.emit({
                "record_type": "case",
                "run_id": run_id,
                "case_index": idx,
                "cases_total": total_cases,
                "case_id": cid,
                "bucket": bucket,
                "pair_id": pair_id,
                "concept_id": concept_id,
                "query": q,
                "expected_sources": expected,
                "hit_at_k": hit,
                "topk": got_sources,
                "elapsed_ms": int((time.time() - case_t0) * 1000),
            })

        if args.progress_every_seconds > 0 and (time.time() - last_progress) >= args.progress_every_seconds:
            elapsed = time.time() - t0
            hr = (hit_count / idx) if idx else 0.0
            stream_tag = str(stream_path) if stream_path else "-"
            print(f"[eval_retrieval] PROGRESS cases_done={idx}/{total_cases} hit_cases={hit_count} hit_rate={hr:.3f} elapsed_s={elapsed:.1f} stream={stream_tag}")
            last_progress = time.time()

    total = len(per_case)
    hit_rate = (hit_count / total) if total else 0.0

    # finalize bucket metrics
    buckets_out: Dict[str, Any] = {}
    for b, st in bucket_stats.items():
        cases_b = int(st.get("cases", 0))
        hit_b = int(st.get("hit_cases", 0))
        buckets_out[b] = {
            "cases": cases_b,
            "hit_cases": hit_b,
            "hit_rate": (hit_b / cases_b) if cases_b else 0.0,
        }

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "timestamp": now_iso(),
        "root": str(root),
        "db_path": str(db_path),
        "collection": args.collection,
        "k": args.k,
        "embed": {"backend": backend, "model": args.embed_model, "device": args.device},
        "run_meta": {
            "tool": "run_eval_retrieval",
            "tool_impl": "src/mhy_ai_rag_data/tools/run_eval_retrieval.py",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "argv": sys.argv,
        },
        "metrics": {"cases": total, "hit_cases": hit_count, "hit_rate": hit_rate},
        "buckets": buckets_out,
        "warnings": warnings,
        "cases": per_case,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if stream_writer is not None:
        stream_writer.emit({
            "record_type": "summary",
            "run_id": run_id,
            "metrics": {"cases": total, "hit_cases": hit_count, "hit_rate": hit_rate},
            "elapsed_ms": int((time.time() - t0) * 1000),
            "final_report": str(out_path),
        })
        stream_writer.close()

    print(f"[eval_retrieval] OK  hit_rate={hit_rate:.3f}  out={out_path}  hit_rate={hit_rate:.3f}  out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
