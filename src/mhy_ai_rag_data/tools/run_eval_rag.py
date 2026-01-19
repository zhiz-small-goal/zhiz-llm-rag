#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_eval_rag.py

目的：
- 在“检索 + 拼接上下文 + 调用 LLM”的路径上做轻量回归
- 用 must_include（关键词/短语）作为最小断言，避免完全主观评判

依赖：
- 必需：chromadb, requests
- 可选：FlagEmbedding 或 sentence_transformers（用于 query embedding）

输出（默认）：
- <root>/data_processed/build_reports/eval_rag_report.json
- <root>/data_processed/build_reports/eval_rag_report.md
- <root>/data_processed/build_reports/eval_rag_report.events.jsonl  (用于中断恢复/重建)

用法：
  python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --k 5 --embed-model BAAI/bge-m3

说明：
- 控制台输出（stdout）为最终报告（detail 从轻到重，summary 在末尾，整体以 \n\n 结束）。
- 运行时进度（stderr）不写入 items/events。
"""

from __future__ import annotations


import argparse
import importlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, iso_now
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter
from mhy_ai_rag_data.tools.runtime_feedback import Progress


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "run_eval_rag",
    "kind": "EVAL_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": True,
    "supports_selftest": False,
    "entrypoint": "python tools/run_eval_rag.py",
}


def safe_truncate(s: Any, n: int) -> str:
    """Best-effort truncate for debug/error payloads."""

    if n <= 0:
        return ""
    t = str(s or "")
    if len(t) <= n:
        return t
    return t[: max(0, n - 1)] + "…"


# 兼容两种运行方式：python -m tools.run_eval_rag 以及 python tools/run_eval_rag.py
try:
    _llm_http_client = importlib.import_module("mhy_ai_rag_data.tools.llm_http_client")
except Exception:  # noqa: BLE001
    _llm_http_client = importlib.import_module("llm_http_client")
chat_completions = _llm_http_client.chat_completions
resolve_model_id = _llm_http_client.resolve_model_id
LLMHTTPError = _llm_http_client.LLMHTTPError


def read_jsonl_cases(path: Path) -> List[Tuple[int, Dict[str, Any]]]:
    """Load jsonl as (line_no, dict). Skips blank lines."""

    out: List[Tuple[int, Dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            s = (raw or "").strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                out.append((line_no, obj))
    return out


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _events_path_for_out_json(out_json: Path) -> Path:
    base = out_json
    if base.suffix:
        base = base.with_suffix("")
    return Path(str(base) + ".events.jsonl")


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
    for key in [k.strip() for k in meta_field.split("|") if k.strip()]:
        if key in meta and meta[key]:
            return str(meta[key])
    return ""


def build_context(docs: List[str], sources: List[str], max_chars: int) -> str:
    """
    将 topK 文档拼接为上下文，并附带来源标识，便于答案可追溯。
    简单做法：按 rank 依次拼接，超过 max_chars 截断。
    """
    parts = []
    used = 0
    for i, (d, s) in enumerate(zip(docs, sources), start=1):
        header = f"[{i}] source={s}\n"
        block = header + (d or "") + "\n\n"
        if used + len(block) > max_chars:
            remain = max(0, max_chars - used)
            if remain > len(header) + 20:
                parts.append(block[:remain])
            break
        parts.append(block)
        used += len(block)
    return "".join(parts).strip()


def must_include_ok(answer: str, must_include: List[str]) -> Tuple[bool, List[str]]:
    missing = []
    for kw in must_include:
        if not kw:
            continue
        if kw not in answer:
            missing.append(kw)
    return (len(missing) == 0), missing


def call_chat(
    base_url: str,
    connect_timeout: float,
    read_timeout: float,
    trust_env_mode: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    result = chat_completions(
        base_url,
        payload,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        trust_env_mode=trust_env_mode,
    )
    # Runtime type check to satisfy mypy strict mode
    if not isinstance(result, dict):
        raise TypeError(f"Expected dict from chat_completions, got {type(result).__name__}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate RAG pipeline and emit schema_version=2 report bundle")
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
    ap.add_argument("--base-url", default="http://localhost:8000/v1", help="OpenAI-compatible base url")
    ap.add_argument("--connect-timeout", type=float, default=10.0, help="HTTP connect timeout seconds")
    ap.add_argument("--timeout", type=float, default=300.0, help="HTTP read timeout seconds (legacy name: --timeout)")
    ap.add_argument(
        "--trust-env",
        default="auto",
        choices=["auto", "true", "false"],
        help="trust env proxies: auto(loopback->false), true, false",
    )
    ap.add_argument(
        "--llm-model", default="auto", help="LLM model id to send; default auto: GET /models and prefer *instruct/*chat"
    )
    ap.add_argument("--context-max-chars", type=int, default=12000, help="max context chars to send to LLM")
    ap.add_argument("--max-tokens", type=int, default=256, help="max_tokens for answer")
    ap.add_argument("--temperature", type=float, default=0.0, help="temperature for answer")
    ap.add_argument(
        "--out", default="data_processed/build_reports/eval_rag_report.json", help="output json (relative to root)"
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
    ap.add_argument(
        "--print-case-errors",
        action="store_true",
        help="print a one-line error per failed case to stderr (for live debugging)",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cases_path = (root / args.cases).resolve()
    db_path = (root / args.db).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

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
        events_writer = ItemEventsWriter(
            path=events_path,
            durability_mode=str(args.durability_mode),
            fsync_interval_ms=int(args.fsync_interval_ms),
        ).open(truncate=True)

    items: List[Dict[str, Any]] = []
    per_case: List[Dict[str, Any]] = []
    pass_count = 0
    t0 = time.time()

    def _emit_item(it: Dict[str, Any]) -> None:
        # Ensure required fields exist (explicit severity_level; no string ordering).
        it.setdefault("tool", "run_eval_rag")
        it.setdefault("title", "")
        it.setdefault("status_label", "INFO")
        it.setdefault("severity_level", 1)
        it.setdefault("message", "")
        if events_writer is not None:
            events_writer.emit_item(it)

    def _termination_item(*, message: str, exc: Optional[BaseException] = None) -> Dict[str, Any]:
        tb = ""
        if exc is not None:
            tb = traceback.format_exc()
        return {
            "tool": "run_eval_rag",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/run_eval_rag.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
            "detail": {
                "exception": f"{type(exc).__name__}: {exc}" if exc is not None else "",
                "traceback": safe_truncate(tb, 8000) if tb else "",
            },
        }

    def _finalize_and_write() -> int:
        summary = compute_summary(items)
        report: Dict[str, Any] = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "run_eval_rag",
            "root": str(root.resolve().as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {
                "db_path": str(db_path.resolve().as_posix()),
                "collection": str(args.collection),
                "k": int(args.k),
                "cases_path": str(cases_path.resolve().as_posix()),
                "metrics": {
                    "cases": len(per_case),
                    "passed_cases": int(pass_count),
                    "pass_rate": (float(pass_count) / float(len(per_case))) if per_case else 0.0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                },
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
            console_title="eval_rag",
            emit_console=True,
        )
        return int(summary.overall_rc)

    try:
        if not cases_path.exists():
            it = _termination_item(message=f"cases not found: {cases_path.as_posix()}")
            items.append(it)
            _emit_item(it)
            return _finalize_and_write()

        if not db_path.exists():
            it = _termination_item(message=f"db not found: {db_path.as_posix()}")
            items.append(it)
            _emit_item(it)
            return _finalize_and_write()

        try:
            import chromadb
        except Exception as e:
            it = _termination_item(message=f"chromadb import failed: {type(e).__name__}: {e}", exc=e)
            items.append(it)
            _emit_item(it)
            return _finalize_and_write()

        try:
            import requests  # noqa: F401
        except Exception as e:
            it = _termination_item(message=f"requests import failed: {type(e).__name__}: {e}", exc=e)
            items.append(it)
            _emit_item(it)
            return _finalize_and_write()

        try:
            progress.update(stage="load_cases")
            cases = read_jsonl_cases(cases_path)
            total_cases = len(cases)
            progress.total = total_cases

            progress.update(current=0, stage="init_embedder")
            backend, embedder = load_embedder(args.embed_backend, args.embed_model, args.device)

            # Resolve model id (avoid placeholder like 'gpt-3.5-turbo' when server exposes real ids)
            progress.update(current=0, stage="resolve_model")
            resolved_model, _model_resolve = resolve_model_id(
                args.base_url,
                args.llm_model,
                connect_timeout=args.connect_timeout,
                read_timeout=args.timeout,
                trust_env_mode=args.trust_env,
                fallback_model="gpt-3.5-turbo",
            )
        except Exception as e:
            it = _termination_item(message=f"init failed: {type(e).__name__}: {e}", exc=e)
            items.append(it)
            _emit_item(it)
            return _finalize_and_write()

        client = chromadb.PersistentClient(path=str(db_path))
        col = client.get_collection(args.collection)

        progress.update(current=0, stage="run")

        for i, (line_no, c) in enumerate(cases, start=1):
            cid = c.get("id", "")
            q = c.get("query", "")
            must_inc = c.get("must_include", []) or []
            must_inc = [str(x) for x in must_inc]

            case_t0 = time.time()

            qvec = embed_query(embedder, backend, q)
            query_embeddings: List[Sequence[float]] = [qvec]
            res = col.query(
                query_embeddings=query_embeddings, n_results=args.k, include=["documents", "metadatas", "distances"]
            )
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]

            sources = [extract_source(m or {}, args.meta_field) for m in metas]
            ctx = build_context([str(d or "") for d in docs], sources, args.context_max_chars)

            messages = [
                {
                    "role": "system",
                    "content": "你是一个严格基于提供上下文回答问题的助手；若上下文不足以回答，请明确说明缺失信息。",
                },
                {"role": "user", "content": f"问题：{q}\n\n上下文：\n{ctx}\n\n请给出回答："},
            ]

            ok_call = True
            answer = ""
            err = None
            err_detail: Optional[Dict[str, Any]] = None
            try:
                j = call_chat(
                    args.base_url,
                    args.connect_timeout,
                    args.timeout,
                    args.trust_env,
                    resolved_model,
                    messages,
                    args.max_tokens,
                    args.temperature,
                )
                # OpenAI-style: choices[0].message.content
                answer = (((j.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            except LLMHTTPError as e:
                ok_call = False
                err = f"{type(e).__name__}: {e.message}"
                # 关键：把服务端返回的 error body（截断）落盘，避免只看到 '400 Bad Request'
                err_detail = e.as_dict()
            except Exception as e:
                ok_call = False
                err = f"{type(e).__name__}: {e}"

            ok_must, missing = (False, must_inc)
            if ok_call:
                ok_must, missing = must_include_ok(answer, must_inc)

            passed = bool(ok_call and ok_must)

            if args.print_case_errors and (not passed):
                if err:
                    sys.stderr.write(f"[eval_rag] CASE_FAIL {i}/{total_cases} id={cid} err={safe_truncate(err, 300)}\n")
                elif not ok_call:
                    sys.stderr.write(f"[eval_rag] CASE_FAIL {i}/{total_cases} id={cid} llm_call_ok=false\n")
                sys.stderr.flush()

            if passed:
                pass_count += 1

            per_case.append(
                {
                    "line_no": line_no,
                    "id": cid,
                    "query": q,
                    "bucket": c.get("bucket"),
                    "pair_id": c.get("pair_id"),
                    "concept_id": c.get("concept_id"),
                    "passed": passed,
                    "llm_call_ok": ok_call,
                    "must_include": must_inc,
                    "missing": missing,
                    "context_chars": len(ctx),
                    "llm_request": {
                        "model": resolved_model,
                        "max_tokens": args.max_tokens,
                        "temperature": args.temperature,
                    },
                    "topk": [
                        {
                            "rank": i + 1,
                            "source": sources[i] if i < len(sources) else "",
                            "distance": dists[i] if i < len(dists) else None,
                        }
                        for i in range(min(args.k, len(sources)))
                    ],
                    "answer": answer,
                    "error": err,
                    "error_detail": err_detail,
                    "elapsed_ms": int((time.time() - case_t0) * 1000),
                }
            )
            # Build one report item and emit to events immediately.
            passed_item = bool(passed) if passed is not None else None
            error_any = err or err_detail or (ok_call is False)
            if error_any:
                status_label = "ERROR"
                severity_level = 4
            elif passed_item is True:
                status_label = "PASS"
                severity_level = 0
            elif passed_item is False:
                status_label = "FAIL"
                severity_level = 3
            else:
                status_label = "INFO"
                severity_level = 1

            # Path contract: always use '/' separators in loc text.
            cases_rel = str(args.cases).replace("\\", "/")
            item: Dict[str, Any] = {
                "tool": "run_eval_rag",
                "title": str(cid or f"line_{line_no}"),
                "status_label": status_label,
                "severity_level": int(severity_level),
                "message": f"passed={passed_item} llm_call_ok={ok_call} missing={len(missing)} bucket={c.get('bucket', '')}",
                "loc": f"{cases_rel}:{line_no}:1",
                "duration_ms": int((time.time() - case_t0) * 1000),
                "detail": dict(per_case[-1]),
            }
            items.append(item)
            _emit_item(item)

            progress.update(current=i, stage="run")

        return _finalize_and_write()

    except KeyboardInterrupt as e:
        it = _termination_item(message="KeyboardInterrupt", exc=e)
        items.append(it)
        _emit_item(it)
        return _finalize_and_write()
    except Exception as e:
        it = _termination_item(message=f"unhandled exception: {type(e).__name__}: {e}", exc=e)
        items.append(it)
        _emit_item(it)
        return _finalize_and_write()
    finally:
        # Best-effort cleanup if _finalize_and_write was not reached.
        try:
            progress.close()
        except Exception:
            pass
        try:
            if events_writer is not None:
                events_writer.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
