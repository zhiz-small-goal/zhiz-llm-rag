#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_baseline_tools.py

目的：
- 在项目仓库内扫描“基线/快照/报告/哈希/manifest”等关键词与典型实现痕迹，
  用于快速确认是否已经存在与某脚本功能相近的工具，避免冗余。

输出：
- 控制台打印：命中条目（文件路径:行号:行内容）
- 并生成 JSON：<root>/data_processed/build_reports/audit_baseline_tools.json

用法：
  python tools/audit_baseline_tools.py --root . --out data_processed/build_reports/audit_baseline_tools.json

注意：
- 这是“静态扫描”，不保证语义完全等价；它只为“快速缩小检查范围”服务。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple


DEFAULT_PATTERNS = [
    r"\bbaseline\b",
    r"\bsnapshot\b",
    r"\benv_report\b",
    r"\bbuild_reports\b",
    r"\bmanifest\b",
    r"\bfingerprint\b",
    r"\bsha256\b",
    r"\bhashlib\b",
    r"content_sha256",
    r"pip\s+freeze",
    r"capture_rag_env\.py",
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def iter_text_files(root: Path) -> List[Path]:
    exts = {".py", ".md", ".txt", ".json", ".jsonl", ".ps1", ".cmd", ".bat", ".cfg", ".ini", ".toml", ".yml", ".yaml"}
    out: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        # skip large/binary-ish common
        if p.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        # skip virtualenv or caches
        if any(part in {".venv", "venv", "__pycache__", ".git", ".hg", ".svn"} for part in p.parts):
            continue
        out.append(p)
    return out


def scan_file(path: Path, regexes: List[re.Pattern]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return hits
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        for rx in regexes:
            if rx.search(line):
                hits.append({"line": i, "pattern": rx.pattern, "text": line.strip()[:500]})
    return hits


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--out", default="data_processed/build_reports/audit_baseline_tools.json", help="output json relative to root")
    ap.add_argument("--pattern", action="append", default=[], help="additional regex patterns (can repeat)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    pats = list(DEFAULT_PATTERNS) + list(args.pattern or [])
    regexes = [re.compile(p, flags=re.IGNORECASE) for p in pats]

    files = iter_text_files(root)
    results: Dict[str, Any] = {
        "timestamp": now_iso(),
        "root": str(root),
        "patterns": pats,
        "matches": [],
        "counts": {"files_scanned": len(files), "files_matched": 0, "hit_lines": 0},
    }

    for f in files:
        hits = scan_file(f, regexes)
        if hits:
            rel = str(f.relative_to(root))
            results["matches"].append({"file": rel, "hits": hits})
            results["counts"]["files_matched"] += 1
            results["counts"]["hit_lines"] += len(hits)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # stdout (human)
    print(f"[audit] scanned={results['counts']['files_scanned']}  matched={results['counts']['files_matched']}  hit_lines={results['counts']['hit_lines']}")
    for m in results["matches"]:
        file = m["file"]
        for h in m["hits"]:
            print(f"{file}:{h['line']}: {h['text']}")
    print(f"[audit] report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
