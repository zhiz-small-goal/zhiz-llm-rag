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

输出：
- <root>/data_processed/build_reports/eval_rag_report.json

用法：
  python tools/run_eval_rag.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --k 5 --embed-model BAAI/bge-m3
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

from mhy_ai_rag_data.tools.report_stream import StreamWriter, default_run_id, safe_truncate

# 兼容两种运行方式：python -m tools.run_eval_rag 以及 python tools/run_eval_rag.py
try:
    _llm_http_client = importlib.import_module("mhy_ai_rag_data.tools.llm_http_client")
except Exception:  # noqa: BLE001
    _llm_http_client = importlib.import_module("llm_http_client")
chat_completions = _llm_http_client.chat_completions
resolve_model_id = _llm_http_client.resolve_model_id
LLMHTTPError = _llm_http_client.LLMHTTPError


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
    return chat_completions(
        base_url,
        payload,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        trust_env_mode=trust_env_mode,
    )


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
    ap.add_argument("--base-url", default="http://localhost:8000/v1", help="OpenAI-compatible base url")
    ap.add_argument("--connect-timeout", type=float, default=10.0, help="HTTP connect timeout seconds")
    ap.add_argument("--timeout", type=float, default=300.0, help="HTTP read timeout seconds (legacy name: --timeout)")
    ap.add_argument("--trust-env", default="auto", choices=["auto","true","false"], help="trust env proxies: auto(loopback->false), true, false")
    ap.add_argument("--llm-model", default="auto", help="LLM model id to send; default auto: GET /models and prefer *instruct/*chat")
    ap.add_argument("--context-max-chars", type=int, default=12000, help="max context chars to send to LLM")
    ap.add_argument("--max-tokens", type=int, default=256, help="max_tokens for answer")
    ap.add_argument("--temperature", type=float, default=0.0, help="temperature for answer")
    ap.add_argument("--out", default="data_processed/build_reports/eval_rag_report.json", help="output json (relative to root)")
    # real-time observability (optional)
    ap.add_argument("--stream-out", default="", help="optional streaming events output (relative to root), e.g. data_processed/build_reports/eval_rag_report.events.jsonl")
    ap.add_argument("--stream-format", default="jsonl", choices=["jsonl","json-seq"], help="stream file format: jsonl or json-seq (RFC 7464)")
    ap.add_argument("--stream-answer-chars", type=int, default=0, help="if >0, include truncated answer snippet in stream records")
    ap.add_argument("--progress-every-seconds", type=float, default=10.0, help="print progress summary every N seconds; 0 to disable")
    ap.add_argument("--print-case-errors", action="store_true", help="print a one-line error per failed case to console (for live debugging)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cases_path = (root / args.cases).resolve()
    db_path = (root / args.db).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    # stream events: optional旁路工件，用于实时观测（不改变最终 JSON 结构/写入时机）
    run_id = default_run_id("eval_rag")
    stream_path: Optional[Path] = None
    stream_writer: Optional[StreamWriter] = None
    stream_closed = False
    if args.stream_out:
        stream_path = (root / args.stream_out).resolve()
        ensure_dir(stream_path.parent)
        stream_writer = StreamWriter(stream_path, fmt=args.stream_format, flush_per_record=True).open()
        stream_writer.emit({
            "record_type": "meta",
            "run_id": run_id,
            "tool": "run_eval_rag",
            "tool_impl": "src/mhy_ai_rag_data/tools/run_eval_rag.py",
            "argv": sys.argv,
            "root": str(root),
            "out_final": str(out_path),
            "stream_out": str(stream_path),
        })

    def _close_stream() -> None:
        nonlocal stream_closed
        if stream_writer is not None and not stream_closed:
            try:
                stream_writer.close()
            finally:
                stream_closed = True

    def _emit_error_record(message: str, exc: Optional[BaseException] = None) -> None:
        """Emit a structured error record to stream (if enabled).

        This ensures the stream contract is truthful: failures are visible during long runs.
        """
        if stream_writer is None:
            return
        tb = ""
        if exc is not None:
            tb = traceback.format_exc()
        stream_writer.emit({
            "record_type": "error",
            "run_id": run_id,
            "ts_ms": int(time.time() * 1000),
            "message": safe_truncate(message, 2000),
            "traceback": safe_truncate(tb, 8000) if tb else "",
        })

    def _fail(rc: int, message: str, exc: Optional[BaseException] = None) -> int:
        print(f"[eval_rag] FAIL: {message}")
        _emit_error_record(message, exc=exc)
        _close_stream()
        return rc

    if not cases_path.exists():
        return _fail(2, f"cases not found: {cases_path}")
    if not db_path.exists():
        return _fail(2, f"db not found: {db_path}")

    try:
        import chromadb
    except Exception as e:
        return _fail(2, f"chromadb import failed: {type(e).__name__}: {e}", exc=e)

    try:
        import requests  # noqa: F401
    except Exception as e:
        return _fail(2, f"requests import failed: {type(e).__name__}: {e}", exc=e)

    try:
        backend, embedder = load_embedder(args.embed_backend, args.embed_model, args.device)

        # Resolve model id (avoid placeholder like 'gpt-3.5-turbo' when server exposes real ids)
        resolved_model, model_resolve = resolve_model_id(
            args.base_url,
            args.llm_model,
            connect_timeout=args.connect_timeout,
            read_timeout=args.timeout,
            trust_env_mode=args.trust_env,
            fallback_model="gpt-3.5-turbo",
        )
        if stream_writer is not None:
            # 追加一条 meta 记录：把 LLM 解析后的 model/base_url/timeout 写入 stream，便于运行中诊断
            stream_writer.emit({
                "record_type": "meta",
                "run_id": run_id,
                "ts_ms": int(time.time() * 1000),
                "llm": {
                    "base_url": args.base_url,
                    "model_arg": args.llm_model,
                    "resolved_model": resolved_model,
                    "connect_timeout": args.connect_timeout,
                    "read_timeout": args.timeout,
                    "trust_env": args.trust_env,
                },
                "model_resolve": model_resolve,
            })

    except Exception as e:
        return _fail(2, f"embedder/llm init failed: {type(e).__name__}: {e}", exc=e)

    client = chromadb.PersistentClient(path=str(db_path))
    col = client.get_collection(args.collection)

    cases = read_jsonl(cases_path)
    per_case = []
    pass_count = 0

    t0 = time.time()
    last_progress = t0
    total_cases = len(cases)

    try:
        for idx, c in enumerate(cases, start=1):
            cid = c.get("id", "")
            q = c.get("query", "")
            must_inc = c.get("must_include", []) or []
            must_inc = [str(x) for x in must_inc]

            case_t0 = time.time()

            qvec = embed_query(embedder, backend, q)
            query_embeddings: List[Sequence[float]] = [qvec]
            res = col.query(query_embeddings=query_embeddings, n_results=args.k, include=["documents", "metadatas", "distances"])
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]

            sources = [extract_source(m or {}, args.meta_field) for m in metas]
            ctx = build_context([str(d or "") for d in docs], sources, args.context_max_chars)

            messages = [
                {"role": "system", "content": "你是一个严格基于提供上下文回答问题的助手；若上下文不足以回答，请明确说明缺失信息。"},
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
                    cause = ""
                    status = ""
                    if isinstance(err_detail, dict):
                        status = str(err_detail.get("status_code") or "")
                        cause = str(err_detail.get("cause") or "")
                    cause_snip = safe_truncate(cause, 300) if cause else ""

                    # 控制台输出：避免单行过长（Windows 终端常被截断），采用多行、并留出空行分隔。
                    print(f"[eval_rag] CASE_FAIL idx={idx}/{total_cases} id={cid}" + (f" status={status}" if status else ""))
                    print(f"  err  : {safe_truncate(err, 300)}")
                    if cause_snip:
                        print(f"  cause: {cause_snip}")
                    print("")
                elif not ok_call:
                    print(f"[eval_rag] CASE_FAIL idx={idx}/{total_cases} id={cid} llm_call_ok=false")

            if passed:
                pass_count += 1

            per_case.append({
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
                "llm_request": {"model": resolved_model, "max_tokens": args.max_tokens, "temperature": args.temperature},
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
            })

            if stream_writer is not None:
                ans_snip = safe_truncate(answer, args.stream_answer_chars) if args.stream_answer_chars > 0 else ""
                stream_writer.emit({
                    "record_type": "case",
                    "run_id": run_id,
                    "ts_ms": int(time.time() * 1000),
                    "case_index": idx,
                    "cases_total": total_cases,
                    "case_id": cid,
                    "bucket": c.get("bucket"),
                    "pair_id": c.get("pair_id"),
                    "concept_id": c.get("concept_id"),
                    "query": q,
                    "passed": passed,
                    "llm_call_ok": ok_call,
                    "missing": missing,
                    "context_chars": len(ctx),
                    "answer_chars": len(answer),
                    "answer_snippet": ans_snip,
                    "error": err,
                    "error_detail": err_detail,
                    "elapsed_ms": int((time.time() - case_t0) * 1000),
                })

            if args.progress_every_seconds > 0 and (time.time() - last_progress) >= args.progress_every_seconds:
                elapsed = time.time() - t0
                pr = (pass_count / idx) if idx else 0.0
                stream_tag = str(stream_path) if stream_path else "-"
                print(f"[eval_rag] PROGRESS cases_done={idx}/{total_cases} passed_cases={pass_count} pass_rate={pr:.3f} elapsed_s={elapsed:.1f} stream={stream_tag}")
                last_progress = time.time()

    except Exception as e:
        return _fail(1, f"unhandled exception during evaluation: {type(e).__name__}: {e}", exc=e)

    total = len(per_case)
    pass_rate = (pass_count / total) if total else 0.0

    report = {
        "timestamp": now_iso(),
        "root": str(root),
        "db_path": str(db_path),
        "collection": args.collection,
        "k": args.k,
        "embed": {"backend": backend, "model": args.embed_model, "device": args.device},
        "llm": {"base_url": args.base_url, "connect_timeout": args.connect_timeout, "read_timeout": args.timeout, "trust_env": args.trust_env, "model_field": args.llm_model},
        "metrics": {"cases": total, "passed_cases": pass_count, "pass_rate": pass_rate},
        "cases": per_case,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if stream_writer is not None:
        stream_writer.emit({
            "record_type": "summary",
            "run_id": run_id,
            "ts_ms": int(time.time() * 1000),
            "metrics": report.get("metrics"),
            "out_final": str(out_path),
            "elapsed_ms": int((time.time() - t0) * 1000),
        })
        _close_stream()

    print(f"[eval_rag] OK  pass_rate={pass_rate:.3f}  out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
