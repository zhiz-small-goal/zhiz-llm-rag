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
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter
from mhy_ai_rag_data.tools.runtime_feedback import Progress

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--db", default="chroma_db", help="chroma db dir (relative to root)")
    ap.add_argument("--collection", default="rag_chunks", help="collection name")
    ap.add_argument(
        "--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)"
    )
    ap.add_argument("--k", type=int, default=5, help="topK for retrieval")
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
    ap.add_argument(
        "--durability-mode",
        default="flush",
        choices=["none", "flush", "fsync"],
        help="events durability: none|flush|fsync (fsync is throttled by --fsync-interval-ms)",
    )
    ap.add_argument(
        "--fsync-interval-ms",
        type=int,
        default=1000,
        help="fsync throttle interval in ms when durability_mode=fsync",
    )
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
    t0 = time.time()

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
                "run_meta": {
                    "tool": "run_eval_retrieval",
                    "tool_impl": "src/mhy_ai_rag_data/tools/run_eval_retrieval.py",
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                    "argv": sys.argv,
                },
                "metrics": {
                    "cases_total": int(total_valid_cases),
                    "evaluated_cases": int(evaluated_cases),
                    "hit_cases": int(hit_cases),
                    "hit_rate": (float(hit_cases) / float(evaluated_cases)) if evaluated_cases else 0.0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                },
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
            _emit_item(_termination_item(message=f"cases not found: {cases_path.as_posix()}"))
            return _finalize_and_write()

        if not db_path.exists():
            _emit_item(_termination_item(message=f"db not found: {db_path.as_posix()}"))
            return _finalize_and_write()

        try:
            import chromadb
        except Exception as e:
            _emit_item(_termination_item(message=f"chromadb import failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        try:
            progress.update(stage="load_cases")
            raw_lines = read_jsonl_with_lineno(cases_path)
        except Exception as e:
            _emit_item(_termination_item(message=f"read cases failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        # init embedder
        try:
            progress.update(stage="init_embedder")
            backend, embedder = load_embedder(args.embed_backend, args.embed_model, args.device)
        except Exception as e:
            _emit_item(_termination_item(message=f"embedder init failed: {type(e).__name__}: {e}", exc=e))
            return _finalize_and_write()

        client = chromadb.PersistentClient(path=str(db_path))
        col = client.get_collection(args.collection)

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

        hit_cases = 0
        evaluated_cases = 0

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

            evaluated_cases += 1
            try:
                qvec = embed_query(embedder, backend, q)
                query_embeddings: List[Sequence[float]] = [qvec]
                res = col.query(
                    query_embeddings=query_embeddings, n_results=int(args.k), include=["metadatas", "distances"]
                )
                metadatas = (res.get("metadatas") or [[]])[0]
                distances = (res.get("distances") or [[]])[0]
            except Exception as e:
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

            got_sources: List[Dict[str, Any]] = []
            for i, m in enumerate(metadatas or []):
                m = m or {}
                src = extract_source(m, str(args.meta_field))
                got_sources.append(
                    {"rank": i + 1, "source": str(src), "distance": distances[i] if i < len(distances) else None}
                )

            def _is_hit() -> bool:
                # hit rule: any expected substring matches any got source
                for e in expected:
                    for g in got_sources:
                        if e and g.get("source") and (e in str(g.get("source"))):
                            return True
                # allow prefix match for expected dir like "docs/"
                for e in expected:
                    if e.endswith("/"):
                        for g in got_sources:
                            if str(g.get("source") or "").replace("\\", "/").startswith(e):
                                return True
                return False

            hit_val: Optional[bool] = _is_hit() if expected else None
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
                "topk": got_sources,
                "debug": {
                    "retrieval_mode": "dense_only",
                    "dense_topk": got_sources,
                    "keyword_topk": [],
                    "fusion_topk": [],
                    "expansion_trace": None,
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
                    "message": f"hit_at_k={hit_val} bucket={bucket} k={int(args.k)}",
                    "loc": f"{_normalize_rel(args.cases)}:{lineno}:1",
                    "duration_ms": int((time.time() - case_t0) * 1000),
                    "detail": one_case,
                }
            )

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
