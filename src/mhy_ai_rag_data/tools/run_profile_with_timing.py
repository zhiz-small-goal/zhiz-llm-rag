#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_profile_with_timing.py

目的：
  在 Windows/单机环境下，把 SchemeB 的“validate -> plan -> build -> check”（可选 smoke test）
  每一步的耗时记录下来，并输出：
    1) 控制台汇总表
    2) JSON 报告：data_processed/build_reports/time_report_*.json

用法（在项目根目录）：
  python tools\run_profile_with_timing.py --profile build_profile_schemeB.json --smoke

说明：
  - 这是一个“外部计时 wrapper”，不依赖 tools/run_build_profile.py 的内部实现。
  - 它会读取 profile 里的关键参数（db/collection/device/embed_batch/upsert_batch/chunk 参数等），
    并用同一套参数调用现有脚本：validate_rag_units.py、plan_chunks_from_units.py、build_chroma_index_flagembedding.py、check_chroma_build.py。
  - 若 profile 缺少某些字段，会使用合理默认值（与你现有脚本默认保持一致）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Sequence


def _run(cmd: Sequence[str], cwd: Path) -> Tuple[int, float]:
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=str(cwd))
    dt = time.perf_counter() - t0
    return p.returncode, dt


def _load_profile(profile_path: Path) -> Dict[str, Any]:
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Cannot read profile json: {profile_path} :: {e}") from e


def _get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="Profile JSON path, e.g. build_profile_schemeB.json")
    ap.add_argument("--smoke", action="store_true", help="Run retriever_chroma.py and check_rag_pipeline.py after PASS")
    ap.add_argument("--max-samples", type=int, default=20, help="validate_rag_units.py --max-samples")
    args = ap.parse_args()

    cwd = Path(".").resolve()
    profile_path = (cwd / args.profile).resolve()
    if not profile_path.exists():
        print(f"[FATAL] profile not found: {profile_path}")
        return 2

    prof = _load_profile(profile_path)

    # ---- extract parameters (tolerant) ----
    units = _get(prof, "paths", "units", default="data_processed/text_units.jsonl")
    db = _get(prof, "chroma", "db", default=str(prof.get("db", "chroma_db")))
    collection = _get(prof, "chroma", "collection", default=str(prof.get("collection", "rag_chunks")))

    embed_model = _get(prof, "embedding", "model", default=str(prof.get("embed_model", "BAAI/bge-m3")))
    device = _get(prof, "embedding", "device", default=str(prof.get("device", "cpu")))
    embed_batch = int(_get(prof, "embedding", "embed_batch", default=int(prof.get("embed_batch", 32))))
    upsert_batch = int(_get(prof, "chroma", "upsert_batch", default=int(prof.get("upsert_batch", 256))))

    chunk_chars = int(_get(prof, "chunking", "chunk_chars", default=int(prof.get("chunk_chars", 1200))))
    overlap_chars = int(_get(prof, "chunking", "overlap_chars", default=int(prof.get("overlap_chars", 120))))
    min_chunk_chars = int(_get(prof, "chunking", "min_chunk_chars", default=int(prof.get("min_chunk_chars", 200))))

    include_media_stub = bool(_get(prof, "chunking", "include_media_stub", default=bool(prof.get("include_media_stub", True))))
    include_media_flag = "true" if include_media_stub else "false"

    # sync/index_state (optional)
    sync_mode = str(_get(prof, "sync", "mode", default=str(prof.get("sync_mode", "incremental"))))
    state_root = str(_get(prof, "sync", "state_root", default=str(prof.get("state_root", "data_processed/index_state"))))
    on_missing_state = str(_get(prof, "sync", "on_missing_state", default=str(prof.get("on_missing_state", "reset"))))
    schema_change = str(_get(prof, "sync", "schema_change", default=str(prof.get("schema_change", "reset"))))
    strict_sync = _get(prof, "sync", "strict_sync", default=prof.get("strict_sync", True))
    strict_sync_flag = "true" if bool(strict_sync) else "false"

    # outputs
    out_dir = cwd / "data_processed" / "build_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"time_report_{stamp}.json"

    steps = []
    started_at = datetime.now().isoformat(timespec="seconds")

    def add_step(name: str, cmd: List[str]):
        steps.append({"name": name, "cmd": cmd})

    # capture env is optional; you already have it, but keep for completeness
    add_step("capture_env", [sys.executable, "tools/capture_rag_env.py", "--out", "data_processed/env_report.json"])
    add_step("validate_units", [sys.executable, "validate_rag_units.py", "--max-samples", str(args.max_samples)])
    add_step("plan_chunks", [
        sys.executable, "tools/plan_chunks_from_units.py",
        "--root", ".", "--units", units,
        "--chunk-chars", str(chunk_chars), "--overlap-chars", str(overlap_chars), "--min-chunk-chars", str(min_chunk_chars),
        "--include-media-stub", include_media_flag,
        "--out", "data_processed/chunk_plan.json"
    ])
    add_step("build_chroma_flagembedding", [
        sys.executable, "tools/build_chroma_index_flagembedding.py", "build",
        "--root", ".", "--units", units,
        "--db", db, "--collection", collection,
        "--plan", "data_processed/chunk_plan.json",
        "--embed-model", embed_model, "--device", device,
        "--embed-batch", str(embed_batch), "--upsert-batch", str(upsert_batch),
        "--chunk-chars", str(chunk_chars), "--overlap-chars", str(overlap_chars), "--min-chunk-chars", str(min_chunk_chars),
        "--include-media-stub" if include_media_stub else "",
        "--sync-mode", sync_mode,
        "--state-root", state_root,
        "--on-missing-state", on_missing_state,
        "--schema-change", schema_change,
        "--strict-sync", strict_sync_flag
    ])
    # remove empty arg if include_media_stub is false
    steps[-1]["cmd"] = [c for c in steps[-1]["cmd"] if c]

    add_step("check_chroma_build", [
        sys.executable, "check_chroma_build.py",
        "--db", db, "--collection", collection,
        "--plan", "data_processed/chunk_plan.json"
    ])

    if args.smoke:
        add_step("smoke_retriever", [sys.executable, "retriever_chroma.py", "--q", "存档导入与导出怎么做", "--k", "5"])
        add_step("smoke_pipeline", [sys.executable, "check_rag_pipeline.py", "--q", "如何自定义资产", "--k", "5"])

    results = []
    total_t0 = time.perf_counter()
    for s in steps:
        name = s["name"]
        cmd = s["cmd"]
        rc, dt = _run(cmd, cwd)
        results.append({"name": name, "returncode": rc, "seconds": dt, "cmd": cmd})
        if rc != 0:
            break
    total_dt = time.perf_counter() - total_t0

    finished_at = datetime.now().isoformat(timespec="seconds")
    ok = all(r["returncode"] == 0 for r in results)

    report = {
        "started_at": started_at,
        "finished_at": finished_at,
        "total_seconds": total_dt,
        "profile": str(profile_path),
        "params": {
            "units": units,
            "db": db,
            "collection": collection,
            "embed_model": embed_model,
            "device": device,
            "embed_batch": embed_batch,
            "upsert_batch": upsert_batch,
            "chunk_chars": chunk_chars,
            "overlap_chars": overlap_chars,
            "min_chunk_chars": min_chunk_chars,
            "include_media_stub": include_media_stub,
        },
        "steps": results,
        "status": "PASS" if ok else "FAIL",
    }

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # print summary
    print("\n=== TIME SUMMARY ===")
    for r in results:
        print(f"{r['name']:<26}  {r['seconds']:>8.2f}s  rc={r['returncode']}")
    print(f"{'TOTAL':<26}  {total_dt:>8.2f}s")
    print(f"REPORT: {report_path}")
    print(f"STATUS: {report['status']}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
