#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_rag_eval_batch.py

批量评估：retriever / pipeline / LLM answer（可选）

用法（项目根目录）：
  python tools/run_rag_eval_batch.py --queries tests/rag_queries_v1.json --k 5
  python tools/run_rag_eval_batch.py --queries tests/rag_queries_v1.json --k 5 --pipeline
  python tools/run_rag_eval_batch.py --queries tests/rag_queries_v1.json --k 5 --answer
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="tests/rag_queries_v1.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--answer", action="store_true")
    args = ap.parse_args()

    cwd = Path(".").resolve()
    qpath = (cwd / args.queries).resolve()
    if not qpath.exists():
        print(f"[FATAL] queries not found: {qpath}")
        return 2

    qobj = json.loads(qpath.read_text(encoding="utf-8"))
    items = qobj.get("items", [])

    out_dir = cwd / "data_processed" / "build_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"rag_eval_{stamp}.json"

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "queries_file": str(Path(args.queries)),
        "k": args.k,
        "pipeline": bool(args.pipeline),
        "answer": bool(args.answer),
        "results": [],
    }

    for it in items:
        qid = it.get("id")
        q = it.get("query")
        kws = it.get("expect_keywords", []) or []
        if not q:
            continue
        one = {"id": qid, "query": q, "expect_keywords": kws, "steps": {}}

        cmd_r = [sys.executable, "retriever_chroma.py", "--q", q, "--k", str(args.k)]
        rc, dt, out = run_capture(cmd_r, cwd)
        one["steps"]["retriever"] = {"cmd": cmd_r, "returncode": rc, "seconds": dt, "stdout": out}
        one["retrieval"] = parse_retriever_output(out)
        one["heuristic"] = {"keywords_in_output": keyword_score(out, kws)}

        if args.pipeline:
            cmd_p = [sys.executable, "check_rag_pipeline.py", "--q", q, "--k", str(args.k)]
            rc2, dt2, out2 = run_capture(cmd_p, cwd)
            one["steps"]["pipeline"] = {"cmd": cmd_p, "returncode": rc2, "seconds": dt2, "stdout": out2}

        if args.answer:
            cmd_a = [sys.executable, "answer_cli.py", "--q", q]
            rc3, dt3, out3 = run_capture(cmd_a, cwd)
            one["steps"]["answer"] = {"cmd": cmd_a, "returncode": rc3, "seconds": dt3, "stdout": out3}

        report["results"].append(one)
        print(f"[OK] {qid}: retriever rc={rc} ({dt:.2f}s)")

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
