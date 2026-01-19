#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_rag_eval_batch.py

批量评估（retriever / pipeline / LLM answer 可选），并以 schema_version=2 的 items 报告输出。

全局一致输出改造点：
- 控制台（stdout）：detail 轻->重（最严重留在最后），summary 在末尾，整体以 "\n\n" 结尾
- 落盘：report.json + report.md（.md 内定位可点击 VS Code 跳转）
- 高耗时可恢复（可选）：items-only 的 report.events.jsonl（每条 flush；可选 fsync 节流）
- 运行时反馈：progress 输出到 stderr（auto|on|off；TTY 且非 CI 才启用）

用法（项目根目录）：
  python -m mhy_ai_rag_data.tools.run_rag_eval_batch --queries tests/rag_queries_v1.json --k 5
  python -m mhy_ai_rag_data.tools.run_rag_eval_batch --queries tests/rag_queries_v1.json --k 5 --pipeline
  python -m mhy_ai_rag_data.tools.run_rag_eval_batch --queries tests/rag_queries_v1.json --k 5 --answer
"""

from __future__ import annotations


import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter
from mhy_ai_rag_data.tools.runtime_feedback import Progress


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "run_rag_eval_batch",
    "kind": "EVAL_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": True,
    "supports_selftest": False,
    "entrypoint": "python tools/run_rag_eval_batch.py",
}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _normalize_rel(s: str) -> str:
    return (s or "").replace("\\", "/").lstrip("./")


def _events_path_for_out_json(out_json: Path) -> Path:
    if out_json.suffix.lower() == ".json":
        return out_json.with_suffix(".events.jsonl")
    return Path(str(out_json) + ".events.jsonl")


def run_capture(cmd: List[str], cwd: Path) -> Tuple[int, float, str]:
    t0 = time.perf_counter()
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
    )
    return p.returncode, (time.perf_counter() - t0), p.stdout


def parse_retriever_output(out: str) -> Dict[str, Any]:
    res: Dict[str, Any] = {"retrieved": None, "hits": []}
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("retrieved="):
            try:
                res["retrieved"] = int(s.split("=", 1)[1].strip())
            except Exception:
                pass
        if s.startswith("S") and "doc_id=" in s and "source_uri=" in s:
            try:
                _, rest = s.split(":", 1)
                kv = {}
                for token in rest.strip().split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        kv[k] = v
                res["hits"].append(kv)
            except Exception:
                pass
    return res


def keyword_score(text: str, keywords: List[str]) -> Dict[str, Any]:
    hit = 0
    misses = []
    for kw in keywords:
        if kw and kw in text:
            hit += 1
        else:
            misses.append(kw)
    return {"hit": hit, "total": len(keywords), "misses": misses}


def _status_from_keywords(score: Dict[str, Any]) -> Tuple[str, int]:
    """Map heuristic keyword score to (status_label, severity_level)."""

    total = int(score.get("total") or 0)
    hit = int(score.get("hit") or 0)
    if total <= 0:
        return ("INFO", 1)
    if hit >= total:
        return ("PASS", 0)
    if hit <= 0:
        return ("FAIL", 3)
    return ("WARN", 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--queries", default="tests/rag_queries_v1.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--answer", action="store_true")
    ap.add_argument(
        "--out",
        default="",
        help="output json (relative to root). default: data_processed/build_reports/rag_eval_<stamp>.json",
    )
    ap.add_argument("--md-out", default="", help="optional report.md path (relative to root); default: <out>.md")
    ap.add_argument(
        "--events-out",
        default="off",
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
    qpath = (root / args.queries).resolve()

    out_dir = (root / "data_processed" / "build_reports").resolve()
    _ensure_dir(out_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = (root / args.out).resolve() if args.out else (out_dir / f"rag_eval_{stamp}.json")
    _ensure_dir(out_path.parent)
    md_path = (root / args.md_out).resolve() if args.md_out else default_md_path_for_json(out_path)

    # runtime feedback (stderr only)
    progress = Progress(total=None, mode=args.progress, min_interval_ms=int(args.progress_min_interval_ms)).start()
    progress.update(stage="init")

    # events stream (items only; for recovery)
    events_writer: Optional[ItemEventsWriter] = None
    events_path: Optional[Path] = None
    events_mode = str(args.events_out or "off").strip().lower()
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
    t0 = time.time()

    def _emit_item(raw: Dict[str, Any]) -> None:
        it = ensure_item_fields(raw, tool_default="run_rag_eval_batch")
        items.append(it)
        if events_writer is not None:
            events_writer.emit_item(it)

    def _termination_item(message: str) -> Dict[str, Any]:
        return {
            "tool": "run_rag_eval_batch",
            "title": "TERMINATED",
            "status_label": "ERROR",
            "severity_level": 4,
            "message": message,
            "loc": "src/mhy_ai_rag_data/tools/run_rag_eval_batch.py:1:1",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    def _finalize_and_write() -> int:
        summary = compute_summary(items)
        report: Dict[str, Any] = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "run_rag_eval_batch",
            "root": str(root.resolve().as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {
                "queries_file": str(qpath.resolve().as_posix()),
                "k": int(args.k),
                "pipeline": bool(args.pipeline),
                "answer": bool(args.answer),
                "elapsed_ms": int((time.time() - t0) * 1000),
            },
        }
        if events_path is not None:
            report["data"]["events_path"] = str(events_path.resolve().as_posix())

        progress.close()
        if events_writer is not None:
            events_writer.close()

        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=root,
            console_title="rag_eval_batch",
            emit_console=True,
        )
        return int(summary.overall_rc)

    try:
        if not qpath.exists():
            _emit_item(_termination_item(f"queries not found: {qpath.as_posix()}"))
            return _finalize_and_write()

        qobj = json.loads(qpath.read_text(encoding="utf-8"))
        # Support both formats: direct array or {"items": [...]}
        if isinstance(qobj, list):
            qitems = qobj
        else:
            qitems = qobj.get("items", []) if isinstance(qobj, dict) else []

        total = len(qitems)
        progress.total = total if total > 0 else None

        cwd = root

        for idx, it in enumerate(qitems, start=1):
            progress.update(current=idx, stage="batch")

            qid = it.get("id")
            q = it.get("query") or it.get("q")
            kws = it.get("expect_keywords", []) or []
            if not q:
                _emit_item(
                    {
                        "tool": "run_rag_eval_batch",
                        "title": str(qid or f"item_{idx}"),
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "missing query",
                        "loc": _normalize_rel(str(args.queries)),
                    }
                )
                continue

            started = time.time()
            one: Dict[str, Any] = {"id": qid, "query": q, "expect_keywords": kws, "steps": {}}

            cmd_r = [sys.executable, "retriever_chroma.py", "--q", str(q), "--k", str(args.k)]
            rc, dt, out = run_capture(cmd_r, cwd)
            one["steps"]["retriever"] = {"cmd": cmd_r, "returncode": rc, "seconds": dt, "stdout": out}
            one["retrieval"] = parse_retriever_output(out)
            one["heuristic"] = {"keywords_in_output": keyword_score(out, [str(x) for x in kws])}

            # optional steps
            if args.pipeline:
                cmd_p = [sys.executable, "check_rag_pipeline.py", "--q", str(q), "--k", str(args.k)]
                rc2, dt2, out2 = run_capture(cmd_p, cwd)
                one["steps"]["pipeline"] = {"cmd": cmd_p, "returncode": rc2, "seconds": dt2, "stdout": out2}
            if args.answer:
                cmd_a = [sys.executable, "answer_cli.py", "--q", str(q)]
                rc3, dt3, out3 = run_capture(cmd_a, cwd)
                one["steps"]["answer"] = {"cmd": cmd_a, "returncode": rc3, "seconds": dt3, "stdout": out3}

            # status/severity decision: prioritize subprocess failures, then keyword heuristic
            status_label = "INFO"
            severity_level = 1
            msg_parts: List[str] = []
            msg_parts.append(f"retriever_rc={rc} dt_s={dt:.2f}")
            if rc != 0:
                status_label, severity_level = ("ERROR", 4)
                msg_parts.append("retriever_failed")
            else:
                sc = one["heuristic"]["keywords_in_output"]
                status_label, severity_level = _status_from_keywords(sc)
                msg_parts.append(f"kw_hit={sc.get('hit')}/{sc.get('total')}")
                misses = sc.get("misses") or []
                if misses:
                    msg_parts.append("misses=" + ",".join([str(x) for x in misses[:5] if str(x)]))

            if args.pipeline:
                pr = one["steps"].get("pipeline", {}).get("returncode")
                if isinstance(pr, int) and pr != 0:
                    status_label, severity_level = ("FAIL", max(int(severity_level), 3))
                    msg_parts.append(f"pipeline_rc={pr}")
            if args.answer:
                ar = one["steps"].get("answer", {}).get("returncode")
                if isinstance(ar, int) and ar != 0:
                    status_label, severity_level = ("FAIL", max(int(severity_level), 3))
                    msg_parts.append(f"answer_rc={ar}")

            _emit_item(
                {
                    "tool": "run_rag_eval_batch",
                    "title": str(qid or f"item_{idx}"),
                    "status_label": status_label,
                    "severity_level": int(severity_level),
                    "message": " ".join(msg_parts),
                    "loc": _normalize_rel(str(args.queries)),
                    "duration_ms": int((time.time() - started) * 1000),
                    "detail": one,
                }
            )

        return _finalize_and_write()

    except KeyboardInterrupt:
        _emit_item(_termination_item("KeyboardInterrupt"))
        return _finalize_and_write()
    except Exception as e:
        _emit_item(_termination_item(f"unhandled exception: {type(e).__name__}: {e}"))
        return _finalize_and_write()


if __name__ == "__main__":
    raise SystemExit(main())
