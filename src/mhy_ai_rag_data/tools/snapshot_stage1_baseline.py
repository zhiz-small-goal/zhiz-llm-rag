#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snapshot_stage1_baseline.py

目的：
- 固化 Stage-1 的“可审计基线”：关键产物哈希/manifest、环境信息、（可选）Git 信息
- 让后续 Stage-2 的质量/性能/检索漂移，有可对比的基线证据

输出：
- <root>/data_processed/build_reports/stage1_baseline_snapshot.json

用法：
  python tools/snapshot_stage1_baseline.py --root . --db chroma_db

退出码：
  0 成功
  2 关键产物缺失
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

SMALL_FILE_SHA256_LIMIT = 50 * 1024 * 1024  # 50MB


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: List[str]) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        return p.returncode, p.stdout.strip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def manifest_dir(root: Path) -> Dict[str, Any]:
    """
    对目录做“轻量可审计”manifest：
    - 对所有文件记录：相对路径、大小、mtime
    - 对 <= 50MB 的文件额外记录 sha256（避免对巨大文件做全量哈希）
    """
    out: Dict[str, Any] = {
        "path": str(root),
        "files": [],
        "note": f"sha256 for files <= {SMALL_FILE_SHA256_LIMIT} bytes",
    }
    if not root.exists():
        out["error"] = "path not found"
        return out

    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            entry: Dict[str, Any] = {
                "rel": str(p.relative_to(root)),
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            }
            if st.st_size <= SMALL_FILE_SHA256_LIMIT:
                try:
                    entry["sha256"] = sha256_file(p)
                except Exception as e:
                    entry["sha256_error"] = f"{type(e).__name__}: {e}"
            files.append(entry)
    out["files"] = files
    out["file_count"] = len(files)
    return out


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--db", default="chroma_db", help="chroma db directory name relative to root")
    ap.add_argument("--out", default="", help="override output json path (optional)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    req_units = root / "data_processed" / "text_units.jsonl"
    req_plan = root / "data_processed" / "chunk_plan.json"

    missing = [str(p) for p in [req_units, req_plan] if not p.exists()]
    if missing:
        print("[snapshot] FAIL: missing required artifacts:")
        for m in missing:
            print(" -", m)
        return 2

    report_dir = root / "data_processed" / "build_reports"
    ensure_dir(report_dir)
    out_path = Path(args.out).resolve() if args.out else (report_dir / "stage1_baseline_snapshot.json")

    snap: Dict[str, Any] = {
        "timestamp": now_iso(),
        "root": str(root),
        "python": {"version": sys.version, "executable": sys.executable},
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "artifacts": {
            "text_units": {"path": str(req_units), "size": req_units.stat().st_size, "sha256": sha256_file(req_units)},
            "chunk_plan": {"path": str(req_plan), "size": req_plan.stat().st_size, "sha256": sha256_file(req_plan)},
        },
        "chroma_db_manifest": {},
        "git": {},
        "pip_freeze": "",
    }

    # Chroma DB manifest (optional)
    db_path = (root / args.db).resolve()
    snap["chroma_db_manifest"] = manifest_dir(db_path)

    # Git (optional)
    rc, out = run_cmd(["git", "-C", str(root), "rev-parse", "HEAD"])
    if rc == 0:
        snap["git"]["commit"] = out
        rc2, out2 = run_cmd(["git", "-C", str(root), "status", "--porcelain"])
        snap["git"]["dirty"] = bool(out2.strip())
    else:
        snap["git"]["error"] = out

    # pip freeze (optional)
    rc3, out3 = run_cmd([sys.executable, "-m", "pip", "freeze"])
    snap["pip_freeze"] = out3 if rc3 == 0 else f"ERROR: {out3}"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)

    print(f"[snapshot] OK  out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
