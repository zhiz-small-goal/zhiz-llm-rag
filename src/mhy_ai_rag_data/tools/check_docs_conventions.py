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


def _add_blank_lines_after_title(
    raw: List[str], fm_len: int, title_body_idx: int, blank_count: int
) -> bool:
    """
    Ensure there are at least two blank lines after the title line.

    raw: full file lines (including front matter)
    fm_len: number of lines in the front matter block
    title_body_idx: index of the title line inside body (after front matter)
    blank_count: current consecutive blank lines after the title
    """
    if blank_count >= 2:
        return False
    insert_pos = fm_len + title_body_idx + 1
    needed = 2 - blank_count
    raw[insert_pos:insert_pos] = ["\n"] * needed
    return True


def check_one(path: Path, fix: bool = False) -> Dict[str, Any]:
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
        "fixed_blank_lines": False,
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
    blank_count = 0
    for line in body[idx + 1 :]:
        if line.strip() == "":
            blank_count += 1
        else:
            break

    if blank_count < 2:
        if fix and _add_blank_lines_after_title(raw, len(fm), idx, blank_count):
            path.write_text("".join(raw), encoding="utf-8")
            result["fixed_blank_lines"] = True
            blank_count = 2

        if blank_count < 2:
            result["ok"] = False
            result["issues"].append("need two blank lines after title")

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--docs-dir", default="docs", help="docs directory (relative to root)")
    ap.add_argument("--glob", default="**/*.md", help="glob pattern under docs-dir")
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/docs_conventions_report.json",
        help="output json (relative to root)",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="auto-insert missing blank lines after title (in-place)",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    docs_dir = (root / args.docs_dir).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    if not docs_dir.exists():
        missing_report: Dict[str, Any] = {
            "timestamp": now_iso(),
            "root": str(root),
            "docs_dir": str(docs_dir),
            "overall": "FAIL",
            "reason": "docs_dir not found",
            "files": [],
        }
        out_path.write_text(json.dumps(missing_report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[docs_check] FAIL: docs_dir not found: {docs_dir}  out={out_path}")
        return 2

    files = sorted([p for p in docs_dir.glob(args.glob) if p.is_file()])
    results = [check_one(p, fix=args.fix) for p in files]
    bad = [r for r in results if not r.get("ok")]

    report: Dict[str, Any] = {
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
