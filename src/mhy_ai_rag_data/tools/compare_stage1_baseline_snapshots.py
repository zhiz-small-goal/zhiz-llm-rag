#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_stage1_baseline_snapshots.py

目的：
- 对比两份 stage1_baseline_snapshot.json（或同 schema 的快照），输出差异报告
- 重点对比：
  1) artifacts(text_units/chunk_plan) 的 sha256/size
  2) chroma_db_manifest 的文件集合与每个文件的 sha256/size/mtime
  3) git commit/dirty（若存在）
  4) pip_freeze（可选：仅比较前 N 行或全文 hash）

用法：
  python tools/compare_stage1_baseline_snapshots.py --a data_processed/build_reports/stage1_baseline_snapshot.json --b <other.json>
  python tools/compare_stage1_baseline_snapshots.py --a a.json --b b.json --out data_processed/build_reports/baseline_diff.json

退出码：
  0: 两份快照在“关键字段”上等价（PASS）
  2: 存在差异（FAIL）或输入文件缺失/格式错误
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def index_files(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in (manifest.get("files") or []):
        rel = str(f.get("rel") or "")
        if rel:
            out[rel.replace("/", "\\")] = f
    return out


def diff_kv(a: Dict[str, Any], b: Dict[str, Any], keys: List[str]) -> List[Dict[str, Any]]:
    diffs = []
    for k in keys:
        av = a.get(k)
        bv = b.get(k)
        if av != bv:
            diffs.append({"key": k, "a": av, "b": bv})
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="snapshot A json path")
    ap.add_argument("--b", required=True, help="snapshot B json path")
    ap.add_argument("--out", default="", help="output diff report json (optional)")
    ap.add_argument("--compare-pip-freeze", action="store_true", help="compare pip_freeze content hash (default off)")
    args = ap.parse_args()

    pa = Path(args.a).resolve()
    pb = Path(args.b).resolve()
    if not pa.exists() or not pb.exists():
        print(f"[baseline_diff] FAIL: missing input file(s): a={pa.exists()} b={pb.exists()}")
        return 2

    try:
        ja = load_json(pa)
        jb = load_json(pb)
    except Exception as e:
        print(f"[baseline_diff] FAIL: json load error: {type(e).__name__}: {e}")
        return 2

    report: Dict[str, Any] = {
        "timestamp": now_iso(),
        "a": str(pa),
        "b": str(pb),
        "overall": "PASS",
        "diffs": {
            "artifacts": [],
            "chroma_files_added": [],
            "chroma_files_removed": [],
            "chroma_files_changed": [],
            "git": [],
            "pip_freeze": [],
        },
        "notes": [],
    }

    # 1) artifacts
    a_art = (ja.get("artifacts") or {})
    b_art = (jb.get("artifacts") or {})
    for name in ["text_units", "chunk_plan"]:
        da = (a_art.get(name) or {})
        db = (b_art.get(name) or {})
        d = diff_kv(da, db, ["size", "sha256"])
        if d:
            report["diffs"]["artifacts"].append({"artifact": name, "diff": d})

    # 2) chroma manifest
    a_m = (ja.get("chroma_db_manifest") or {})
    b_m = (jb.get("chroma_db_manifest") or {})
    a_files = index_files(a_m)
    b_files = index_files(b_m)

    a_set = set(a_files.keys())
    b_set = set(b_files.keys())
    added = sorted(list(b_set - a_set))
    removed = sorted(list(a_set - b_set))
    report["diffs"]["chroma_files_added"] = added
    report["diffs"]["chroma_files_removed"] = removed

    common = sorted(list(a_set & b_set))
    for rel in common:
        fa = a_files.get(rel, {})
        fb = b_files.get(rel, {})
        # 优先比 sha256；若缺失 sha256（>50MB），再比 size+mtime
        if ("sha256" in fa) or ("sha256" in fb):
            d = diff_kv(fa, fb, ["sha256", "size"])
        else:
            d = diff_kv(fa, fb, ["size", "mtime"])
        if d:
            report["diffs"]["chroma_files_changed"].append({"rel": rel, "diff": d})

    # 3) git
    ga = (ja.get("git") or {})
    gb = (jb.get("git") or {})
    gdiff = diff_kv(ga, gb, ["commit", "dirty"])
    if gdiff:
        report["diffs"]["git"] = gdiff

    # 4) pip freeze (optional)
    if args.compare_pip_freeze:
        ha = sha256_text(str(ja.get("pip_freeze") or ""))
        hb = sha256_text(str(jb.get("pip_freeze") or ""))
        if ha != hb:
            report["diffs"]["pip_freeze"] = [{"key": "pip_freeze_sha256", "a": ha, "b": hb}]
            report["notes"].append("pip_freeze differs by sha256; enable full diff externally if needed.")
    else:
        report["notes"].append("pip_freeze not compared (use --compare-pip-freeze to compare by hash).")

    # overall
    has_any_diff = any(
        report["diffs"][k] for k in ["artifacts", "chroma_files_added", "chroma_files_removed", "chroma_files_changed", "git", "pip_freeze"]
    )
    report["overall"] = "FAIL" if has_any_diff else "PASS"

    # write report
    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = pa.parent / f"baseline_diff_{int(time.time())}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[baseline_diff] overall={report['overall']} out={out_path}")
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
