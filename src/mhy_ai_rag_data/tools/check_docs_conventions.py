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
  python tools/check_docs_conventions.py --root . --out data_processed/build_reports/docs_conventions_report.json
  # 默认扫描 docs/ 与 tools/；可使用 --full-repo 扩大范围

退出码：
  0 全部通过
  2 存在违反约定的文件（FAIL）
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from mhy_ai_rag_data.tools.report_order import write_json_report


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


def _tokens(s: str) -> List[str]:
    buf = []
    cur = []
    for ch in s.lower():
        if ch.isalnum():
            cur.append(ch)
        else:
            if cur:
                buf.append("".join(cur))
                cur = []
    if cur:
        buf.append("".join(cur))
    return buf


def _title_matches_stem(title: str, stem: str) -> bool:
    title_tokens = set(_tokens(title))
    stem_tokens = _tokens(stem)
    if stem_tokens:
        return all(tok in title_tokens for tok in stem_tokens)
    return stem.lower() in title.lower()


DEFAULT_DIRS = ["docs", "tools"]
DEFAULT_IGNORE = [
    ".git/**",
    ".venv/**",
    "venv/**",
    "data_processed/**",
    "chroma_db/**",
    "third_party/**",
    "**/__pycache__/**",
    ".ruff_cache/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    "**/node_modules/**",
    "docs/postmortems/**",
    "**/archive/**",
    "**/REFERENCE.md",
]
DEFAULT_GLOB = "**/*.md"
DEFAULT_OUT = "data_processed/build_reports/docs_conventions_report.json"
DEFAULT_CONFIG = ".docs_conventions_config.json"
ALLOW_FREE_TITLE = {"index", "readme", "toc", "overview", "introduction"}


def iter_md_files(root: Path, dirs: Iterable[Path], glob: str, ignore_patterns: List[str]) -> List[Path]:
    """
    Yield markdown files under specified dirs, applying ignore patterns on posix relpath.
    """
    out: List[Path] = []
    seen = set()
    for d in dirs:
        base = (root / d).resolve()
        if not base.exists():
            continue
        for p in base.glob(glob):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, pat) for pat in ignore_patterns):
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
    out.sort()
    return out


def load_config(cfg_path: Path) -> Dict[str, Any]:
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"[docs_check] WARN: config is not a JSON object: {cfg_path}")
            return {}
        return data
    except Exception as e:
        print(f"[docs_check] WARN: failed to load config {cfg_path}: {e}")
        return {}


def _add_blank_lines_after_title(raw: List[str], fm_len: int, title_body_idx: int, blank_count: int) -> bool:
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
    expected_title = "# <H1>"

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
    if not first_line.startswith("#"):
        result["ok"] = False
        result["issues"].append(f"title should be H1 heading: got='{first_line}'")
    # Title content is free-form (no stem keyword requirement)

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
    ap.add_argument(
        "--config",
        default=None,
        help=f"config json path (relative to root); default {DEFAULT_CONFIG}",
    )
    ap.add_argument(
        "--dirs",
        nargs="+",
        default=None,
        help="directories to scan (relative to root). default from config or built-in",
    )
    ap.add_argument(
        "--full-repo",
        action="store_true",
        default=None,
        help="scan the entire repo (overrides --dirs)",
    )
    ap.add_argument("--glob", default=None, help="glob pattern under target dirs")
    ap.add_argument(
        "--out",
        default=None,
        help="output json (relative to root)",
    )
    ap.add_argument(
        "--ignore",
        nargs="+",
        default=None,
        help="ignore patterns (fnmatch on posix relpath, e.g., data_processed/**)",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        default=None,
        help="auto-insert missing blank lines after title (in-place)",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config) if args.config else (root / DEFAULT_CONFIG)
    cfg = load_config(cfg_path)

    full_repo = args.full_repo if args.full_repo is not None else bool(cfg.get("full_repo", False))
    dirs_cfg = cfg.get("dirs", DEFAULT_DIRS)
    glob_cfg = cfg.get("glob", DEFAULT_GLOB)
    ignore_cfg = cfg.get("ignore", DEFAULT_IGNORE)
    out_cfg = cfg.get("out", DEFAULT_OUT)
    fix_cfg = bool(cfg.get("fix", False))

    dirs_arg = args.dirs if args.dirs is not None else dirs_cfg
    glob_arg = args.glob if args.glob is not None else glob_cfg
    ignore_arg = args.ignore if args.ignore is not None else ignore_cfg
    out_arg = args.out if args.out is not None else out_cfg
    fix = args.fix if args.fix is not None else fix_cfg

    target_dirs = [Path(".")] if full_repo else [Path(d) for d in dirs_arg]
    existing_dirs = [str((root / d).resolve()) for d in target_dirs if (root / d).exists()]
    missing_dirs = [str(d) for d in target_dirs if not (root / d).exists()]
    out_path = (root / out_arg).resolve()
    ensure_dir(out_path.parent)

    if not existing_dirs:
        missing_report: Dict[str, Any] = {
            "timestamp": now_iso(),
            "root": str(root),
            "dirs": [str(d) for d in target_dirs],
            "overall": "FAIL",
            "reason": "target dirs not found",
            "files": [],
        }
        write_json_report(out_path, missing_report)
        print(f"[docs_check] FAIL: target dirs not found: {target_dirs}  out={out_path}")
        return 2

    files = iter_md_files(root, target_dirs, glob_arg, ignore_arg)
    results = [check_one(p, fix=fix) for p in files]
    bad = [r for r in results if not r.get("ok")]

    report: Dict[str, Any] = {
        "timestamp": now_iso(),
        "root": str(root),
        "dirs": existing_dirs,
        "missing_dirs": missing_dirs,
        "pattern": glob_arg,
        "ignore": ignore_arg,
        "config": str(cfg_path) if cfg else None,
        "overall": "PASS" if not bad else "FAIL",
        "counts": {"files": len(results), "bad": len(bad)},
        "files": results,
    }
    write_json_report(out_path, report)

    print(f"[docs_check] {report['overall']}  files={len(results)} bad={len(bad)}  out={out_path}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
