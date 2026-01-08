#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_docs_conventions.py

目的：
- 对 docs/（或任意目录）下的 Markdown 做“工程约定”检查：
  1) 顶部是否存在目录标题：# {文件名}目录：
  2) 目录标题后是否存在至少两行空行（便于后续插入 TOC 或保持可读性）
  3) 可选：允许 YAML front matter（--- ... ---），并在检查时跳过它

输出：
- <root>/data_processed/build_reports/docs_conventions_report.json

用法：
  python tools/check_docs_conventions.py --root . --docs-dir docs --out data_processed/build_reports/docs_conventions_report.json

退出码：
  0 全部通过
  2 存在违反约定的文件（FAIL）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def strip_bom(s: str) -> str:
    return s.lstrip("\ufeff")


def split_front_matter(lines: List[str]) -> Tuple[List[str], List[str]]:
    """
    支持 YAML front matter：
    - 若文件前两行以内出现 '---'，则把第一段 front matter 作为头部，正文从下一个 '---' 后开始
    """
    if not lines:
        return [], []
    # Allow BOM in the first line
    first = strip_bom(lines[0]).strip()
    if first != "---":
        return [], lines

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[: i + 1], lines[i + 1 :]
    # no closing ---
    return lines, []


def check_one(path: Path) -> Dict[str, Any]:
    relname = path.name
    stem = path.stem  # filename without extension
    expected_title = f"# {stem}目录："

    raw = path.read_text(encoding="utf-8", errors="replace").splitlines(True)  # keep line endings
    fm, body = split_front_matter(raw)

    # Find first non-empty line in body
    idx = None
    for i, line in enumerate(body):
        if line.strip() != "":
            idx = i
            break

    result: Dict[str, Any] = {
        "file": str(path),
        "expected_title": expected_title,
        "has_front_matter": bool(fm),
        "ok": True,
        "issues": [],
    }

    if idx is None:
        result["ok"] = False
        result["issues"].append("empty file body")
        return result

    first_line = strip_bom(body[idx]).rstrip("\n\r")
    if first_line != expected_title:
        result["ok"] = False
        result["issues"].append(f"title mismatch: got='{first_line}'")

    # Check two blank lines after title line (in body)
    # We require that next two lines exist and are blank (or one line blank then EOF is fail)
    after = body[idx + 1 : idx + 3]
    if len(after) < 2 or any(line.strip() != "" for line in after):
        result["ok"] = False
        result["issues"].append("need two blank lines after title")

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--docs-dir", default="docs", help="docs directory (relative to root)")
    ap.add_argument("--glob", default="**/*.md", help="glob pattern under docs-dir")
    ap.add_argument("--out", default="data_processed/build_reports/docs_conventions_report.json", help="output json (relative to root)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    docs_dir = (root / args.docs_dir).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    if not docs_dir.exists():
        report = {"timestamp": now_iso(), "root": str(root), "docs_dir": str(docs_dir), "overall": "FAIL", "reason": "docs_dir not found", "files": []}
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[docs_check] FAIL: docs_dir not found: {docs_dir}  out={out_path}")
        return 2

    files = sorted([p for p in docs_dir.glob(args.glob) if p.is_file()])
    results = [check_one(p) for p in files]
    bad = [r for r in results if not r.get("ok")]

    report = {
        "timestamp": now_iso(),
        "root": str(root),
        "docs_dir": str(docs_dir),
        "pattern": args.glob,
        "overall": "PASS" if not bad else "FAIL",
        "counts": {"files": len(results), "bad": len(bad)},
        "files": results,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[docs_check] {report['overall']}  files={len(results)} bad={len(bad)}  out={out_path}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
