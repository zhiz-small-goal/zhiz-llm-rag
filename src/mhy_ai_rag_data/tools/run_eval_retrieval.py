#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_eval_retrieval.py

检索侧回归：对用例集评估 topK 是否命中期望来源文档。

全局一致输出改造（schema_version=2 / items 模型）：
- 控制台（stdout）：detail 轻->重（最严重留在最后），summary 在末尾，整体以 "\n\n" 结尾
- 落盘：同时生成 report.json + report.md（.md 内定位可点击 VS Code 跳转）
- 高耗时可恢复：运行中 append 写 items-only 的 report.events.jsonl（每条 flush；可选 fsync 节流）
- 运行时反馈：progress 输出到 stderr（auto|on|off；TTY 且非 CI 才启用）

用法（项目根目录）：
  python -m mhy_ai_rag_data.tools.run_eval_retrieval --root . --db chroma_db --collection rag_chunks --k 5

说明：
- 本脚本会把每个 case 生成 1 条 item；validator warnings 也会转成 items。
- severity_level 为数值（越大越严重）；同 severity 内保持产生顺序稳定。
"""

from __future__ import annotations


import argparse
import json
import math
import re
from collections import Counter
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter
from mhy_ai_rag_data.tools.runtime_feedback import Progress


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "run_eval_retrieval",
    "kind": "EVAL_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": True,
    "supports_selftest": True,
    "entrypoint": "python tools/run_eval_retrieval.py",
}


REPORT_SCHEMA_VERSION = 2
DEFAULT_BUCKET = "official"
ALLOWED_BUCKETS = {"official", "oral", "ambiguous"}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _normalize_rel(s: str) -> str:
    return (s or "").replace("\\", "/").lstrip("./")


def _events_path_for_out_json(out_json: Path) -> Path:
    if out_json.suffix.lower() == ".json":
        return out_json.with_suffix(".events.jsonl")
    return Path(str(out_json) + ".events.jsonl")


def normalize_bucket(v: Any, warnings: List[Dict[str, Any]], *, case_id: str, line_hint: Optional[int] = None) -> str:
    """Normalize bucket for eval cases.

    - missing/empty -> DEFAULT_BUCKET
    - invalid -> "unknown" and emit warning (validator should catch in CI)
    """

    if v is None:
        warnings.append(
            {"code": "missing_bucket_default", "case_id": case_id, "bucket": DEFAULT_BUCKET, "line": line_hint}
        )
        return DEFAULT_BUCKET
    s = str(v).strip().lower()
    if not s:
        warnings.append(
            {"code": "missing_bucket_default", "case_id": case_id, "bucket": DEFAULT_BUCKET, "line": line_hint}
        )
        return DEFAULT_BUCKET
    if s in ALLOWED_BUCKETS:
        return s
    warnings.append(
        {
            "code": "invalid_bucket_unknown",
            "case_id": case_id,
            "bucket": s,
            "allowed": sorted(list(ALLOWED_BUCKETS)),
            "line": line_hint,
        }
    )
    return "unknown"


def read_jsonl_with_lineno(path: Path) -> List[Tuple[int, Dict[str, Any]]]:
    out: List[Tuple[int, Dict[str, Any]]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            s = (line or "").strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    out.append((lineno, obj))
                else:
                    out.append((lineno, {"_parse_error": "json_not_object", "_raw": s}))
            except Exception as e:
                out.append((lineno, {"_parse_error": f"{type(e).__name__}: {e}", "_raw": s}))
    return out


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
        from sentence_transformers import SentenceTransformer

        return ("sentence-transformers", SentenceTransformer(model_name, device=device))
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
    """从 metadata 提取来源字段。

    meta_field 支持 "source|path|file" 的优先级表达：用 '|' 分隔多个候选字段。
    """

    for key in [k.strip() for k in (meta_field or "").split("|") if k.strip()]:
        if key in meta and meta[key]:
            return str(meta[key])
    return ""


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", re.UNICODE)


def _tokenize(s: str) -> List[str]:
    s = (s or "").lower()
    return _TOKEN_RE.findall(s)


class _KeywordIndex:
    # Minimal BM25-style index over Chroma documents, restricted to the query vocabulary.

    def __init__(
        self,
        *,
        doc_ids: List[str],
        doc_sources: List[str],
        doc_tfs: List[Dict[str, int]],
        doc_lens: List[int],
        avgdl: float,
        df: Dict[str, int],
        n_docs: int,
    ) -> None:
        self.doc_ids = doc_ids
        self.doc_sources = doc_sources
        self.doc_tfs = doc_tfs
        self.doc_lens = doc_lens
        self.avgdl = float(avgdl)
        self.df = df
        self.n_docs = int(n_docs)


def _build_keyword_index(
    *,
    doc_ids: List[str],
    doc_texts: List[str],
    doc_metas: List[Mapping[str, Any]],
    query_vocab: set[str],
    meta_field: str,
) -> _KeywordIndex:
    # Restrict tf/df to tokens that appear in any query, to reduce memory.
    df: Dict[str, int] = {t: 0 for t in query_vocab}
    doc_tfs: List[Dict[str, int]] = []
    doc_lens: List[int] = []
    doc_sources: List[str] = []

    total_len = 0
    n_docs = len(doc_texts)

    for i in range(n_docs):
        txt = doc_texts[i] or ""
        toks = _tokenize(txt)
        dl = len(toks)
        total_len += dl
        doc_lens.append(dl)

        tf: Dict[str, int] = {}
        for t in toks:
            if t in query_vocab:
                tf[t] = tf.get(t, 0) + 1
        doc_tfs.append(tf)

        for t in tf.keys():
            df[t] = df.get(t, 0) + 1

        meta = doc_metas[i] if i < len(doc_metas) else {}
        doc_sources.append(extract_source(meta or {}, meta_field))

    avgdl = (float(total_len) / float(n_docs)) if n_docs else 0.0
    return _KeywordIndex(
        doc_ids=doc_ids,
        doc_sources=doc_sources,
        doc_tfs=doc_tfs,
        doc_lens=doc_lens,
        avgdl=avgdl,
        df=df,
        n_docs=n_docs,
    )


def _load_chroma_docs(
    col: Any,
    *,
    include_documents: bool,
    batch_size: int = 512,
) -> Tuple[List[str], List[str], List[Mapping[str, Any]]]:
    """Load all docs from a Chroma collection.

    Why: keyword retrieval needs documents; Chroma `get()` is usually paginated.

    Returns: (ids, documents, metadatas)
    - If documents are not stored in the collection, documents may be an empty list.
    """

    include: List[str] = ["metadatas"]
    if include_documents:
        include.append("documents")

    # Best effort paging (API differs across chromadb versions).
    try:
        n = int(col.count())
    except Exception:
        n = -1

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Mapping[str, Any]] = []

    def _extend(res: Mapping[str, Any]) -> None:
        _ids = res.get("ids") or []
        _docs = res.get("documents") or []
        _metas = res.get("metadatas") or []

        # Some versions may return nested lists.
        if _ids and isinstance(_ids, list) and _ids and isinstance(_ids[0], list):
            _ids = _ids[0]
        if _docs and isinstance(_docs, list) and _docs and isinstance(_docs[0], list):
            _docs = _docs[0]
        if _metas and isinstance(_metas, list) and _metas and isinstance(_metas[0], list):
            _metas = _metas[0]

        ids.extend([str(x) for x in (_ids or [])])
        docs.extend([str(x or "") for x in (_docs or [])])
        metas.extend([x if isinstance(x, dict) else {} for x in (_metas or [])])

    # Fast path: try single get() call.
    try:
        res0 = col.get(include=include)
        if isinstance(res0, dict) and res0.get("ids"):
            _extend(res0)
            # If it looks like a full dump, accept.
            if n <= 0 or len(ids) >= n or (n > 0 and len(ids) == n):
                return ids, docs, metas
    except Exception:
        pass

    if n <= 0:
        return ids, docs, metas

    # Paged path.
    ids.clear()
    docs.clear()
    metas.clear()
    offset = 0
    while offset < n:
        lim = min(int(batch_size), n - offset)
        try:
            res = col.get(include=include, limit=lim, offset=offset)
        except TypeError:
            # Older API might not support offset/limit.
            res = col.get(include=include)
        if not isinstance(res, dict) or not res.get("ids"):
            break
        _extend(res)
        offset += lim

    return ids, docs, metas


def _bm25_score(
    *,
    q_tokens: List[str],
    tf: Mapping[str, int],
    dl: int,
    avgdl: float,
    df: Mapping[str, int],
    n_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not q_tokens or not n_docs or avgdl <= 0:
        return 0.0

    score = 0.0
    # Use unique tokens only for scoring.
    for t in set(q_tokens):
        f = int(tf.get(t, 0))
        if f <= 0:
            continue
        dfi = int(df.get(t, 0))
        # BM25 idf (with +1 to keep non-negative)
        idf = math.log(((n_docs - dfi + 0.5) / (dfi + 0.5)) + 1.0)
        denom = f + k1 * (1.0 - b + b * (float(dl) / float(avgdl)))
        score += idf * ((f * (k1 + 1.0)) / (denom if denom else 1.0))
    return float(score)


def _keyword_search(
    *,
    idx: _KeywordIndex,
    query: str,
    topk: int,
) -> List[Dict[str, Any]]:
    toks = _tokenize(query)
    scored: List[Tuple[float, int]] = []
    for i in range(idx.n_docs):
        s = _bm25_score(
            q_tokens=toks,
            tf=idx.doc_tfs[i],
            dl=idx.doc_lens[i],
            avgdl=idx.avgdl,
            df=idx.df,
            n_docs=idx.n_docs,
        )
        if s > 0.0:
            scored.append((s, i))
    # Stable: score desc, then doc ordinal asc.
    scored.sort(key=lambda x: (-x[0], x[1]))

    out: List[Dict[str, Any]] = []
    for rank, (s, i) in enumerate(scored[: max(0, int(topk))], start=1):
        out.append(
            {
                "rank": rank,
                "id": str(idx.doc_ids[i]),
                "source": str(idx.doc_sources[i]),
                "keyword_score": float(s),
            }
        )
    return out


def _rrf_fuse(
    *,
    dense: List[Dict[str, Any]],
    keyword: List[Dict[str, Any]],
    topk: int,
    rrf_k: int = 60,
) -> List[Dict[str, Any]]:
    # Reciprocal Rank Fusion.
    scores: Dict[str, float] = {}
    dense_rank: Dict[str, int] = {}
    keyword_rank: Dict[str, int] = {}

    for it in dense:
        cid = str(it.get("id") or "")
        if not cid:
            continue
        r = int(it.get("rank") or 0) or (len(dense_rank) + 1)
        dense_rank[cid] = r
        scores[cid] = scores.get(cid, 0.0) + (1.0 / float(rrf_k + r))

    for it in keyword:
        cid = str(it.get("id") or "")
        if not cid:
            continue
        r = int(it.get("rank") or 0) or (len(keyword_rank) + 1)
        keyword_rank[cid] = r
        scores[cid] = scores.get(cid, 0.0) + (1.0 / float(rrf_k + r))

    # Materialize candidates.
    dense_by_id = {str(it.get("id")): it for it in dense if it.get("id")}
    keyword_by_id = {str(it.get("id")): it for it in keyword if it.get("id")}

    fused: List[Dict[str, Any]] = []
    for cid, sc in scores.items():
        base: Dict[str, Any] = {"id": cid, "fusion_score": float(sc)}
        if cid in dense_by_id:
            base["distance"] = dense_by_id[cid].get("distance")
            base["source"] = dense_by_id[cid].get("source")
        if cid in keyword_by_id:
            base["keyword_score"] = keyword_by_id[cid].get("keyword_score")
            if not base.get("source"):
                base["source"] = keyword_by_id[cid].get("source")
        base["dense_rank"] = dense_rank.get(cid)
        base["keyword_rank"] = keyword_rank.get(cid)
        fused.append(base)

    # Stable: fusion_score desc, then best rank asc, then id.
    def _best_rank(x: Dict[str, Any]) -> int:
        dr = x.get("dense_rank")
        kr = x.get("keyword_rank")
        ranks = [r for r in [dr, kr] if isinstance(r, int) and r > 0]
        return min(ranks) if ranks else 10**9

    fused.sort(key=lambda x: (-float(x.get("fusion_score") or 0.0), _best_rank(x), str(x.get("id") or "")))
    out: List[Dict[str, Any]] = []
    for r, it in enumerate(fused[: max(0, int(topk))], start=1):
        it2 = dict(it)
        it2["rank"] = r
        out.append(it2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    add_selftest_args(ap)
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--db", default="chroma_db", help="chroma db dir (relative to root)")
    ap.add_argument("--collection", default="rag_chunks", help="collection name")
    ap.add_argument(
        "--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)"
    )
    ap.add_argument("--k", type=int, default=5, help="topK for retrieval")
    ap.add_argument(
        "--retrieval-mode",
        default="hybrid",
        choices=["dense", "hybrid"],
        help="retrieval strategy: dense|hybrid (dense + keyword via RRF)",
    )
    ap.add_argument(
        "--dense-topk",
        type=int,
        default=0,
        help="dense candidate pool for fusion; 0 means use --k",
    )
    ap.add_argument(
        "--keyword-topk",
        type=int,
        default=0,
        help="keyword candidate pool for fusion; 0 means use --k",
    )
    ap.add_argument(
        "--fusion-method",
        default="rrf",
        choices=["rrf"],
        help="fusion method for hybrid retrieval (currently: rrf)",
    )
    ap.add_argument("--rrf-k", type=int, default=60, help="RRF k parameter (rank bias)")
    ap.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="if inputs/deps missing, emit WARN and exit 0 (for gate integration)",
    )

    ap.add_argument(
        "--meta-field",
        default="source_uri|source|path|file",
        help="metadata field(s) for source path (use | to separate)",
    )
    ap.add_argument("--embed-backend", default="auto", help="auto|flagembedding|sentence-transformers")
    ap.add_argument("--embed-model", default="BAAI/bge-m3", help="embed model name")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/eval_retrieval_report.json",
        help="output json (relative to root)",
    )
    ap.add_argument("--md-out", default="", help="optional report.md path (relative to root); default: <out>.md")
    ap.add_argument(
        "--events-out",
        default="auto",
        help="item events output (jsonl): auto|off|<path> (relative to root). Used for recovery/rebuild.",
    )
    # durability knobs are provided by add_selftest_args:
    #   --durability-mode none|flush|fsync
    #   --fsync-interval-ms <int>
    ap.add_argument(
        "--progress",
        default="auto",
        choices=["auto", "on", "off"],
        help="runtime progress feedback to stderr: auto|on|off",
    )
    ap.add_argument(
        "--progress-min-interval-ms",
        type=int,
        default=200,
        help="min progress update interval in ms (throttling)",
    )
    args = ap.parse_args()

    _repo_root = Path(getattr(args, "root", ".")).resolve()
    _loc = Path(__file__).resolve()
    try:
        _loc = _loc.relative_to(_repo_root)
    except Exception:
        pass

    _rc = maybe_run_selftest_from_args(args=args, meta=REPORT_TOOL_META, repo_root=_repo_root, loc_source=_loc)
    if _rc is not None:
        return _rc

    root = Path(args.root).resolve()
    cases_path = (root / args.cases).resolve()
    db_path = (root / args.db).resolve()
    out_path = (root / args.out).resolve()
    _ensure_dir(out_path.parent)
    md_path = (root / args.md_out).resolve() if args.md_out else default_md_path_for_json(out_path)

    # runtime feedback (stderr only)
    progress = Progress(total=None, mode=args.progress, min_interval_ms=int(args.progress_min_interval_ms)).start()
    progress.update(stage="init")

    # events stream (items only; for recovery)
    events_writer: Optional[ItemEventsWriter] = None
    events_path: Optional[Path] = None
    events_mode = str(args.events_out or "auto").strip().lower()
    if events_mode not in ("", "off", "none", "false", "0"):
        if events_mode == "auto":
            events_path = _events_path_for_out_json(out_path)
        else:
            events_path = (root / str(args.events_out)).resolve()
        _ensure_dir(events_path.parent)
        events_writer = ItemEventsWriter(
            path=events_path,
            durability_mode=str(args.durability_mode),
            fsync_interval_ms=int(args.fsync_interval_ms),
        ).open(truncate=True)

    items: List[Dict[str, Any]] = []
    per_case: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    # metrics snapshot (populated during evaluation; written to report.data)
    total_valid_cases = 0
    evaluated_cases = 0
    hit_cases = 0
    hit_cases_dense = 0
    t0 = time.time()
    skipped_reason: Optional[str] = None

    # derived retrieval params (used in report.data)
    dense_pool_k = int(args.dense_topk) if int(args.dense_topk) > 0 else int(args.k)
    keyword_pool_k = int(args.keyword_topk) if int(args.keyword_topk) > 0 else int(args.k)
    kw_index_info: Dict[str, Any] = {"enabled": False}
    bucket_metrics: Dict[str, Any] = {}
    query_error_cases = 0

    def _emit_item(raw: Dict[str, Any]) -> None:
        it = ensure_item_fields(raw, tool_default="run_eval_retrieval")
        items.append(it)
        if events_writer is not None:
            events_writer.emit_item(it)

    def _termination_item(*, message: str, exc: Optional[BaseException] = None) -> Dict[str, Any]:
        tb = traceback.format_exc() if exc is not None else ""
        return {
            "tool": "run_eval_retrieval",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/run_eval_retrieval.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
            "detail": {
                "exception": f"{type(exc).__name__}: {exc}" if exc is not None else "",
                "traceback": tb,
            },
        }

    def _finalize_and_write() -> int:
        summary = compute_summary(items)
        report: Dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": iso_now(),
            "tool": "run_eval_retrieval",
            "root": str(root.resolve().as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {
                "db_path": str(db_path.resolve().as_posix()),
                "collection": str(args.collection),
                "k": int(args.k),
                "cases_path": str(cases_path.resolve().as_posix()),
                "embed": {
                    "backend": str(args.embed_backend),
                    "model": str(args.embed_model),
                    "device": str(args.device),
                },
                "retrieval": {
                    "mode": str(args.retrieval_mode),
                    "dense_pool_k": int(dense_pool_k),
                    "keyword_pool_k": int(keyword_pool_k),
                    "fusion_method": str(args.fusion_method),
                    "rrf_k": int(args.rrf_k),
                    "keyword_index": kw_index_info,
                },
                "run_meta": {
                    "tool": "run_eval_retrieval",
                    "tool_impl": "src/mhy_ai_rag_data/tools/run_eval_retrieval.py",
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                    "argv": sys.argv,
                    "skipped": bool(skipped_reason),
                    "skip_reason": skipped_reason,
                },
                "metrics": {
                    "cases_total": int(total_valid_cases),
                    "evaluated_cases": int(evaluated_cases),
                    "query_error_cases": int(query_error_cases),
                    "hit_cases": int(hit_cases),
                    "hit_rate": (float(hit_cases) / float(evaluated_cases)) if evaluated_cases else 0.0,
                    "hit_cases_dense": int(hit_cases_dense),
                    "hit_rate_dense": (float(hit_cases_dense) / float(evaluated_cases)) if evaluated_cases else 0.0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                },
                "buckets": bucket_metrics,
                "warnings": warnings,
                "cases": per_case,
            },
        }
        if events_path is not None:
            report["data"]["events_path"] = str(events_path.resolve().as_posix())

        # Ensure progress line is cleaned before final stdout report.
        progress.close()
        if events_writer is not None:
            events_writer.close()

        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=root,
            console_title="eval_retrieval",
            emit_console=True,
        )
        return int(summary.overall_rc)

    try:
        if not cases_path.exists():
            if args.skip_if_missing:
                skipped_reason = f"cases not found: {cases_path.as_posix()}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": _normalize_rel(args.cases),
                        "detail": {"skip_reason": skipped_reason},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"cases not found: {cases_path.as_posix()}"))
            return _finalize_and_write()

        if not db_path.exists():
            if args.skip_if_missing:
                skipped_reason = f"db not found: {db_path.as_posix()}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": str(db_path.as_posix()),
                        "detail": {"skip_reason": skipped_reason},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"db not found: {db_path.as_posix()}"))
            return _finalize_and_write()

        try:
            import chromadb
        except Exception as e:
            if args.skip_if_missing:
                skipped_reason = f"chromadb import failed: {type(e).__name__}: {e}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": "python:import",
                        "detail": {"skip_reason": skipped_reason},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"chromadb import failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        try:
            progress.update(stage="load_cases")
            raw_lines = read_jsonl_with_lineno(cases_path)
        except Exception as e:
            if args.skip_if_missing:
                skipped_reason = f"read cases failed: {type(e).__name__}: {e}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": str(cases_path.as_posix()),
                        "detail": {"skip_reason": skipped_reason},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"read cases failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        # init embedder
        try:
            progress.update(stage="init_embedder")
            backend, embedder = load_embedder(args.embed_backend, args.embed_model, args.device)
        except Exception as e:
            if args.skip_if_missing:
                skipped_reason = f"embedder init failed: {type(e).__name__}: {e}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": "embedder:init",
                        "detail": {"skip_reason": skipped_reason},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"embedder init failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        try:
            client = chromadb.PersistentClient(path=str(db_path))
            col = client.get_collection(args.collection)
        except Exception as e:
            if args.skip_if_missing:
                skipped_reason = f"open collection failed: {type(e).__name__}: {e}"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "stage2_prereq",
                        "status_label": "WARN",
                        "severity_level": 2,
                        "message": f"SKIP: {skipped_reason}",
                        "loc": str(db_path.as_posix()),
                        "detail": {"skip_reason": skipped_reason, "collection": str(args.collection)},
                    }
                )
                return _finalize_and_write()
            _emit_item(_termination_item(message=f"open collection failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        # Emit items for parse errors / non-object JSON, and keep valid dict cases for evaluation.
        valid_cases: List[Tuple[int, Dict[str, Any]]] = []
        for lineno, obj in raw_lines:
            if not isinstance(obj, dict):
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": f"line_{lineno}",
                        "status_label": "ERROR",
                        "severity_level": 4,
                        "message": "json_not_object",
                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        "detail": {"line": lineno, "raw": obj},
                    }
                )
                continue
            if "_parse_error" in obj:
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": f"line_{lineno}",
                        "status_label": "ERROR",
                        "severity_level": 4,
                        "message": f"json_parse_error: {obj.get('_parse_error')}",
                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        "detail": dict(obj),
                    }
                )
                continue
            valid_cases.append((lineno, obj))

        total_valid_cases = len(valid_cases)
        progress.total = total_valid_cases if valid_cases else None

        # Candidate pool sizes for dense + keyword retrieval.
        dense_pool_k = int(args.dense_topk) if int(args.dense_topk) > 0 else int(args.k)
        keyword_pool_k = int(args.keyword_topk) if int(args.keyword_topk) > 0 else int(args.k)

        # Build a lightweight keyword index (BM25-ish) over stored Chroma documents.
        # NOTE: this requires the collection to store `documents`.
        kw_idx: Optional[_KeywordIndex] = None
        kw_index_info = {"enabled": False, "n_docs": 0, "avgdl": 0.0, "query_vocab": 0}
        if str(args.retrieval_mode) == "hybrid":
            progress.update(stage="build_keyword_index")
            query_vocab: set[str] = set()
            for _ln, cc in valid_cases:
                qv = str(cc.get("query") or "").strip()
                for t in _tokenize(qv):
                    if t:
                        query_vocab.add(t)
            kw_index_info["query_vocab"] = len(query_vocab)

            doc_ids, doc_texts, doc_metas = _load_chroma_docs(col, include_documents=True)
            kw_index_info["n_docs"] = len(doc_texts)

            if not doc_texts:
                # Hybrid requires documents. Treat this as a data contract issue.
                msg = "hybrid retrieval requires Chroma documents (collection has no documents)"
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": "keyword_index_missing_documents",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": msg,
                        "loc": str(db_path.as_posix()),
                        "detail": {
                            "collection": str(args.collection),
                            "hint": "rebuild index with documents stored (include=documents)",
                        },
                    }
                )
                return _finalize_and_write()

            kw_idx = _build_keyword_index(
                doc_ids=doc_ids,
                doc_texts=doc_texts,
                doc_metas=doc_metas,
                query_vocab=query_vocab,
                meta_field=str(args.meta_field),
            )
            kw_index_info.update({"enabled": True, "avgdl": float(kw_idx.avgdl)})

        for idx, (lineno, c) in enumerate(valid_cases, start=1):
            progress.update(current=idx, stage="eval")

            cid = str(c.get("id", "")).strip() or f"line_{lineno}"
            q = str(c.get("query", "")).strip()
            case_t0 = time.time()

            bucket = normalize_bucket(c.get("bucket"), warnings, case_id=cid, line_hint=lineno)
            pair_id = c.get("pair_id")
            concept_id = c.get("concept_id")
            must_include = c.get("must_include", []) or []
            expected = c.get("expected_sources", []) or []
            expected = [str(x) for x in expected]

            if not q:
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": cid,
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "missing query",
                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        "duration_ms": int((time.time() - case_t0) * 1000),
                        "detail": {"line": lineno, "case": dict(c)},
                    }
                )
                continue
            try:
                qvec = embed_query(embedder, backend, q)
                query_embeddings: List[Sequence[float]] = [qvec]
                res = col.query(
                    query_embeddings=query_embeddings,
                    n_results=int(dense_pool_k),
                    include=["metadatas", "distances"],
                )
                ids = (res.get("ids") or [[]])[0]
                metadatas = (res.get("metadatas") or [[]])[0]
                distances = (res.get("distances") or [[]])[0]
            except Exception as e:
                query_error_cases += 1
                _emit_item(
                    {
                        "tool": "run_eval_retrieval",
                        "title": cid,
                        "status_label": "ERROR",
                        "severity_level": 4,
                        "message": f"query failed: {type(e).__name__}: {e}",
                        "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                        "duration_ms": int((time.time() - case_t0) * 1000),
                        "detail": {"line": lineno, "case": dict(c), "traceback": traceback.format_exc()},
                    }
                )
                continue

            evaluated_cases += 1

            dense_topk: List[Dict[str, Any]] = []
            for i, m in enumerate(metadatas or []):
                m = m or {}
                src = extract_source(m, str(args.meta_field))
                dense_topk.append(
                    {
                        "rank": i + 1,
                        "id": str(ids[i]) if i < len(ids) else "",
                        "source": str(src),
                        "distance": distances[i] if i < len(distances) else None,
                    }
                )

            keyword_topk: List[Dict[str, Any]] = []
            if str(args.retrieval_mode) == "hybrid" and kw_idx is not None:
                keyword_topk = _keyword_search(idx=kw_idx, query=q, topk=int(keyword_pool_k))

            if str(args.retrieval_mode) == "hybrid":
                topk_hits = _rrf_fuse(
                    dense=dense_topk,
                    keyword=keyword_topk,
                    topk=int(args.k),
                    rrf_k=int(args.rrf_k),
                )
            else:
                topk_hits = dense_topk[: int(args.k)]

            def _is_hit(got: List[Dict[str, Any]]) -> bool:
                # hit rule: any expected substring matches any got source
                for e in expected:
                    for g in got:
                        if e and g.get("source") and (e in str(g.get("source"))):
                            return True
                # allow prefix match for expected dir like "docs/"
                for e in expected:
                    if e.endswith("/"):
                        for g in got:
                            if str(g.get("source") or "").replace("\\", "/").startswith(e):
                                return True
                return False

            hit_dense: Optional[bool] = _is_hit(dense_topk[: int(args.k)]) if expected else None
            hit_val: Optional[bool] = _is_hit(topk_hits) if expected else None
            if hit_dense is True:
                hit_cases_dense += 1
            if hit_val is True:
                hit_cases += 1

            one_case = {
                "id": cid,
                "bucket": bucket,
                "pair_id": pair_id,
                "concept_id": concept_id,
                "query": q,
                "expected_sources": expected,
                "must_include": must_include,
                "hit_at_k": hit_val,
                "topk": topk_hits,
                "debug": {
                    "retrieval_mode": str(args.retrieval_mode),
                    "dense_topk": dense_topk[: int(args.k)],
                    "keyword_topk": keyword_topk[: int(args.k)],
                    "fusion_topk": topk_hits if str(args.retrieval_mode) == "hybrid" else [],
                    "expansion_trace": None,
                    "fusion_method": str(args.fusion_method),
                    "rrf_k": int(args.rrf_k),
                    "hit_at_k_dense": hit_dense,
                },
            }
            per_case.append(one_case)

            if hit_val is True:
                status_label = "PASS"
                severity_level = 0
            elif hit_val is False:
                status_label = "FAIL"
                severity_level = 3
            else:
                status_label = "INFO"
                severity_level = 1

            _emit_item(
                {
                    "tool": "run_eval_retrieval",
                    "title": cid,
                    "status_label": status_label,
                    "severity_level": severity_level,
                    "message": f"hit_at_k={hit_val} bucket={bucket} k={int(args.k)} mode={str(args.retrieval_mode)}",
                    "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                    "duration_ms": int((time.time() - case_t0) * 1000),
                    "detail": one_case,
                }
            )

        # Aggregate bucket metrics (evaluated cases only; query errors are excluded from denominators).
        b_total: Counter[str] = Counter()
        b_hit: Counter[str] = Counter()
        b_hit_dense: Counter[str] = Counter()
        for cc in per_case:
            b = str(cc.get("bucket") or "unknown")
            b_total[b] += 1
            if cc.get("hit_at_k") is True:
                b_hit[b] += 1
            try:
                if (cc.get("debug") or {}).get("hit_at_k_dense") is True:
                    b_hit_dense[b] += 1
            except Exception:
                pass

        bucket_metrics = {}
        for b in sorted(b_total.keys()):
            denom = int(b_total[b])
            bucket_metrics[b] = {
                "evaluated_cases": denom,
                "hit_cases": int(b_hit[b]),
                "hit_rate": (float(b_hit[b]) / float(denom)) if denom else 0.0,
                "hit_cases_dense": int(b_hit_dense[b]),
                "hit_rate_dense": (float(b_hit_dense[b]) / float(denom)) if denom else 0.0,
            }

        # Warnings -> items
        for w in warnings:
            line_hint = w.get("line")
            loc = (
                f"{_normalize_rel(args.cases)}:{int(line_hint)}:1"
                if isinstance(line_hint, int)
                else _normalize_rel(args.cases)
            )
            _emit_item(
                {
                    "tool": "run_eval_retrieval",
                    "title": f"{w.get('code', 'warning')}:{w.get('case_id', '')}",
                    "status_label": "WARN",
                    "severity_level": 2,
                    "message": str(w.get("code") or "warning"),
                    "loc": loc,
                    "detail": dict(w),
                }
            )

        return _finalize_and_write()

    except KeyboardInterrupt as e:
        _emit_item(_termination_item(message="KeyboardInterrupt", exc=e))
        return _finalize_and_write()
    except Exception as e:
        _emit_item(_termination_item(message=f"unhandled exception: {type(e).__name__}: {e}", exc=e))
        return _finalize_and_write()


if __name__ == "__main__":
    raise SystemExit(main())
