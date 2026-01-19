#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.update_postmortems_index

目的
- 自动生成/校验 `docs/postmortems/INDEX.md`，避免手工维护索引导致的漂移/残留/断链。
- 让“新增 postmortem 文件”成为可门禁的工程动作：本地可 --write 自动更新；CI 可 --check 保证一致。

与项目契约对齐
- tools/ 分层：SSOT 在 `src/mhy_ai_rag_data/tools/`；`tools/*.py` 仅作为 wrapper（见 tools/check_tools_layout.py）。
- 退出码：0=PASS；2=FAIL；3=ERROR（见 docs/reference/REFERENCE.md 3.1）。
- 诊断格式：尽量输出 `file:line:col: message`（见 AGENTS.md 7）。

用法（在仓库根目录）
  # 自动写回（推荐：本地/钩子）
  python tools/update_postmortems_index.py --write

  # 门禁检查（推荐：CI）
  python tools/update_postmortems_index.py --check

可选
  --strict      元信息缺失即 FAIL（仍可在 --write 下写回索引，但退出码为 2）
  --json-out    输出一份 JSON 报告到指定路径（schema_version=1）
  --json-stdout 把同一份 JSON 报告打印到 stdout
"""

from __future__ import annotations


import argparse
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, iso_now


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "update_postmortems_index",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": False,
    "entrypoint": "python tools/update_postmortems_index.py",
}


# Optional dependency (present in project deps, but keep tool usable in "no-install" mode)
yaml: Optional[ModuleType]
try:
    import yaml as _yaml

    yaml = _yaml
except Exception:  # pragma: no cover
    yaml = None


BEGIN_MARK = "<!-- AUTO-GENERATED:BEGIN postmortems-index -->"
END_MARK = "<!-- AUTO-GENERATED:END postmortems-index -->"


def _pass(msg: str) -> int:
    print("[PASS]", msg)
    return 0


def _fail(msg: str) -> int:
    print("[FAIL]", msg)
    return 2


def _diag(path: Path, line: int, col: int, msg: str) -> str:
    # DIAG_LOC_FILE_LINE_COL
    return f"{path.as_posix()}:{line}:{col}: {msg}"


def find_repo_root(start: Path) -> Path:
    """Find repo root by looking for pyproject.toml and docs/."""
    p = start.resolve()
    for _ in range(12):
        if (p / "pyproject.toml").exists() and (p / "docs").exists():
            return p
        if (p / ".git").exists() and (p / "docs").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8", newline="\n")


def split_front_matter(text: str) -> Tuple[str, str]:
    """Return (front_matter, body). If no YAML front matter, front_matter is ''."""
    # Strip UTF-8 BOM if present
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    if not text.startswith("---\n") and not text.startswith("---\r\n") and text.strip().splitlines()[:1] != ["---"]:
        return "", text

    lines = text.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return "", text

    for i in range(1, min(len(lines), 400)):
        if lines[i].strip() == "---":
            fm = "".join(lines[: i + 1])
            body = "".join(lines[i + 1 :])
            return fm, body
    # no closing fence -> treat as no front matter
    return "", text


def parse_yaml_front_matter(fm: str) -> Dict[str, Any]:
    if not fm:
        return {}
    # fm includes leading/ending --- lines
    lines = [ln for ln in fm.splitlines() if ln.strip() != "---"]
    raw = "\n".join(lines).strip()
    if not raw:
        return {}
    if yaml is not None:
        try:
            obj = yaml.safe_load(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    # fallback: minimal "key: value" parser (top-level only)
    out: Dict[str, Any] = {}
    for ln in raw.splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*:\s*(.*)\s*$", ln)
        if not m:
            continue
        k = m.group(1).strip()
        v = m.group(2).strip().strip('"').strip("'")
        out[k] = v
    return out


def first_h1(body: str) -> Optional[str]:
    """Pick the first H1 line (may be a '<stem>目录：' style)."""
    for ln in body.splitlines()[:240]:
        m = re.match(r"^#\s+(.+?)\s*$", ln)
        if not m:
            continue
        return m.group(1).strip()
    return None


def extract_date_from_filename(name: str) -> Optional[str]:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{2})-(\d{2})-(\d{2})", name)
    if m:
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def pretty_title_from_filename(filename: str) -> str:
    """Derive a human-friendly title from filename when YAML/title is missing."""
    stem = Path(filename).stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[_-]*", "", stem)
    stem = re.sub(r"^\d{2}-\d{2}-\d{2}[_-]*", "", stem)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem if stem else filename


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    return [str(v).strip()] if str(v).strip() else []


def extract_keywords(meta: Dict[str, Any], body: str) -> Optional[str]:
    # YAML first
    for k in ("keywords", "keyword", "tags", "关键字", "关键词"):
        if k in meta:
            items = _as_list(meta.get(k))
            if items:
                return " / ".join(items)

    # header style: [关键词] xxx
    for ln in body.splitlines()[:80]:
        m = re.match(r"^\s*\[(关键词|关键字)\]\s*(.+?)\s*$", ln)
        if m:
            return m.group(2).strip()

    # inline: 关键词：xxx
    m = re.search(r"^\s*(关键词|关键字)\s*[:：]\s*(.+?)\s*$", body, flags=re.M)
    if m:
        return m.group(2).strip()

    return None


_STOPWORDS = {
    "postmortem",
    "md",
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "docs",
    "doc",
    "tool",
    "tools",
    "index",
}


def tokenize(s: str) -> List[str]:
    parts = re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", s)
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        # drop single-char Chinese noise
        if len(p) == 1 and re.match(r"^[\u4e00-\u9fff]$", p):
            continue
        pl = p.lower()
        if pl in _STOPWORDS:
            continue
        if p not in out:
            out.append(p)
    return out


def derive_keywords(filename: str, title: str, meta: Dict[str, Any]) -> Optional[str]:
    stem = Path(filename).stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[_-]*", "", stem)
    stem = re.sub(r"^\d{2}-\d{2}-\d{2}[_-]*", "", stem)
    src = " ".join([title, stem.replace("_", " ").replace("-", " ")]).strip()
    toks = tokenize(src)
    return " / ".join(toks[:12]) if toks else None


def extract_title(meta: Dict[str, Any], body: str, filename: str) -> str:
    # 1) YAML title
    v = meta.get("title")
    if isinstance(v, str) and v.strip():
        return v.strip()

    # 2) First H1
    h1 = first_h1(body)
    if h1:
        # If it's the docs-conventions style '<stem>目录：', strip and prettify.
        if h1.endswith("目录："):
            t = h1[:-3].strip()
            if t.lower().endswith(".md"):
                t = t[:-3].strip()
            return pretty_title_from_filename(t)
        return h1.strip()

    # 3) Filename-derived
    return pretty_title_from_filename(filename)


def extract_date(meta: Dict[str, Any], filename: str) -> Optional[str]:
    for k in ("date", "last_updated"):
        v = meta.get(k)
        if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v.strip()):
            return v.strip()[:10]
    return extract_date_from_filename(filename)


@dataclass(frozen=True)
class Entry:
    file: str
    date: Optional[str]
    title: str
    keywords: Optional[str]


def extract_entry(md_path: Path) -> Tuple[Entry, List[Dict[str, Any]]]:
    """Return (Entry, issues). issues items are JSON-friendly dicts with loc/message."""
    text = read_text(md_path)
    fm, body = split_front_matter(text)
    meta = parse_yaml_front_matter(fm)

    filename = md_path.name
    title = extract_title(meta, body, filename)
    date = extract_date(meta, filename)

    kw = extract_keywords(meta, body)
    if not kw:
        kw = derive_keywords(filename, title, meta)

    issues: List[Dict[str, Any]] = []
    if not date:
        issues.append(
            {
                "loc": _diag(md_path, 1, 1, "missing date (YAML date/last_updated or filename prefix YYYY-MM-DD)"),
                "code": "MISSING_DATE",
                "file": md_path.as_posix(),
                "line": 1,
                "col": 1,
            }
        )
    if not title or title.strip() == filename:
        # only warn when title is fully absent; filename as title is acceptable but less useful
        issues.append(
            {
                "loc": _diag(md_path, 1, 1, "title falls back to filename; consider YAML title or a meaningful H1"),
                "code": "WEAK_TITLE",
                "file": md_path.as_posix(),
                "line": 1,
                "col": 1,
            }
        )
    if not kw:
        issues.append(
            {
                "loc": _diag(md_path, 1, 1, "missing keywords; consider YAML keywords/tags or a [关键词] header"),
                "code": "MISSING_KEYWORDS",
                "file": md_path.as_posix(),
                "line": 1,
                "col": 1,
            }
        )

    return Entry(file=filename, date=date, title=title, keywords=kw), issues


def generate_block(entries: Iterable[Entry], link_text_mode: str = "docs_path") -> str:
    groups: Dict[str, List[Entry]] = {}
    undated: List[Entry] = []

    for e in entries:
        if e.date:
            groups.setdefault(e.date, []).append(e)
        else:
            undated.append(e)

    out: List[str] = []
    for d in sorted(groups.keys(), reverse=True):
        out.append(f"## {d}")
        for e in sorted(groups[d], key=lambda x: x.file):
            out.append(f"- **{e.title}**")
            if link_text_mode == "filename":
                link_text = e.file
            else:
                link_text = f"docs/postmortems/{e.file}"
            out.append(f"  - 文件：[`{link_text}`]({e.file})")
            if e.keywords:
                out.append(f"  - 关键字：{e.keywords}")
        out.append("")

    if undated:
        out.append("## 未标注日期")
        for e in sorted(undated, key=lambda x: x.file):
            out.append(f"- **{e.title}**")
            link_text = e.file if link_text_mode == "filename" else f"docs/postmortems/{e.file}"
            out.append(f"  - 文件：[`{link_text}`]({e.file})")
            if e.keywords:
                out.append(f"  - 关键字：{e.keywords}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def upsert_generated_section(old: str, block: str) -> str:
    if BEGIN_MARK in old and END_MARK in old:
        pre, rest = old.split(BEGIN_MARK, 1)
        _, post = rest.split(END_MARK, 1)
        return pre.rstrip() + "\n\n" + BEGIN_MARK + "\n" + block + END_MARK + "\n" + post.lstrip()

    # No markers yet: keep header until first dated heading "## YYYY-MM-DD"
    lines = old.splitlines()
    cut = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+\d{4}-\d{2}-\d{2}\s*$", ln.strip()):
            cut = i
            break
    header = "\n".join(lines[:cut]).rstrip() if cut is not None else old.rstrip()
    return header + "\n\n" + BEGIN_MARK + "\n" + block + END_MARK + "\n"


def build_report(
    *,
    status: str,
    inputs: Dict[str, Any],
    metrics: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # Convert errors to v2 items
    items: List[Dict[str, Any]] = []
    for err in errors:
        # Determine severity_level based on error code
        code = err.get("code", "")
        if code == "EXCEPTION":
            status_label = "ERROR"
            severity_level = 4
        elif code in ("MISSING_DIR", "INDEX_STALE"):
            status_label = "FAIL"
            severity_level = 3
        elif code in ("MISSING_DATE", "MISSING_KEYWORDS", "WEAK_TITLE"):
            status_label = "WARN"
            severity_level = 2
        else:
            status_label = "INFO"
            severity_level = 1

        items.append(
            {
                "tool": "update_postmortems_index",
                "title": code or "UNKNOWN",
                "status_label": status_label,
                "severity_level": severity_level,
                "message": err.get("loc", ""),
                "detail": {
                    "file": err.get("file", ""),
                    "line": err.get("line", 0),
                    "col": err.get("col", 0),
                },
            }
        )

    # Compute summary
    summary = compute_summary(items)

    # Build v2 report
    return {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": "update_postmortems_index",
        "summary": summary.to_dict(),
        "items": items,
        "data": {
            # Preserve original v1 structure for backward compatibility
            "step": "postmortems_index",
            "status": status,
            "inputs": inputs,
            "metrics": metrics,
            "errors": errors,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate/check docs/postmortems/INDEX.md from docs/postmortems/*.md.")
    ap.add_argument("--root", default=".", help="Repo root (default: current directory)")
    ap.add_argument("--postmortems-dir", default="docs/postmortems", help="Postmortems dir under repo root")
    ap.add_argument("--index-file", default="docs/postmortems/INDEX.md", help="Index file under repo root")
    ap.add_argument("--glob", default="*.md", help="Glob pattern under postmortems dir (default: *.md)")
    ap.add_argument("--link-text", default="docs_path", choices=["docs_path", "filename"], help="link text style")
    ap.add_argument("--check", action="store_true", help="Check mode: do not write; FAIL if index out-of-date")
    ap.add_argument("--write", action="store_true", help="Write mode: update index file if needed")
    ap.add_argument(
        "--strict", action="store_true", help="FAIL if any postmortem lacks date/title/keywords (see output)"
    )
    ap.add_argument("--json-out", default=None, help="Write JSON report to this path")
    ap.add_argument("--json-stdout", action="store_true", help="Print JSON report to stdout")
    args = ap.parse_args(argv)

    if args.check and args.write:
        return _fail("choose only one: --check or --write")
    if not args.check and not args.write:
        # Default to write for "auto index" ergonomics; CI should use --check explicitly.
        args.write = True

    if args.json_out and args.json_stdout:
        return _fail("choose only one: --json-out or --json-stdout")

    report_errors: List[Dict[str, Any]] = []
    try:
        repo_root = find_repo_root(Path(args.root))
        pm_dir = (repo_root / args.postmortems_dir).resolve()
        idx_path = (repo_root / args.index_file).resolve()

        if not pm_dir.exists():
            msg = f"missing postmortems dir: {pm_dir}"
            report_errors.append(
                {"loc": _diag(pm_dir, 1, 1, msg), "code": "MISSING_DIR", "file": pm_dir.as_posix(), "line": 1, "col": 1}
            )
            rep = build_report(status="FAIL", inputs={"root": str(repo_root)}, metrics={}, errors=report_errors)
            if args.json_out:
                write_report_bundle(
                    report=rep,
                    report_json=Path(args.json_out),
                    repo_root=repo_root,
                    console_title="update_postmortems_index",
                    emit_console=not bool(args.json_stdout),
                )
            if args.json_stdout:
                print(json.dumps(rep, ensure_ascii=False, indent=2))
            return _fail(msg)

        entries: List[Entry] = []
        meta_issues: List[Dict[str, Any]] = []

        for p in sorted(pm_dir.glob(args.glob)):
            if p.name.upper() == "INDEX.MD":
                continue
            # Allow README.md inside postmortems without being indexed as a postmortem doc.
            if p.name.upper() == "README.MD":
                continue
            e, issues = extract_entry(p)
            entries.append(e)
            meta_issues.extend(issues)

        block = generate_block(entries, link_text_mode=args.link_text)

        old = (
            read_text(idx_path)
            if idx_path.exists()
            else (
                "# Postmortems Index\n\n"
                "> 目的：按“时间 + 主题 + 关键字”快速定位复盘文档。细节请进入各文档正文。\n\n\n"
                "## 相关资产（跨复盘复用）\n"
                "- [Postmortem 提示词模板（参考）](../reference/postmortem_prompt_template.md)\n"
                "- [Lessons / 经验库（可迁移）](../explanation/LESSONS.md)\n"
                "- [Preflight Checklist（重构/换机/换环境后必跑）](../howto/PREFLIGHT_CHECKLIST.md)\n"
                "\n"
            )
        )

        new = upsert_generated_section(old, block)
        changed = old != new

        # Strict policy: treat missing date/keywords as FAIL
        strict_fail = False
        if args.strict:
            for it in meta_issues:
                if it.get("code") in ("MISSING_DATE", "MISSING_KEYWORDS"):
                    strict_fail = True
                    break

        # check/write behavior
        rc: int
        if args.check:
            if changed:
                report_errors.append(
                    {
                        "loc": _diag(idx_path, 1, 1, "index out-of-date; run with --write"),
                        "code": "INDEX_STALE",
                        "file": idx_path.as_posix(),
                        "line": 1,
                        "col": 1,
                    }
                )
                print(_diag(idx_path, 1, 1, "index out-of-date; run with --write"))
                print("Diff (unified):")
                diff = difflib.unified_diff(
                    old.splitlines(True),
                    new.splitlines(True),
                    fromfile=str(idx_path),
                    tofile=str(idx_path) + " (generated)",
                )
                print("".join(diff))
                rc = 2
            else:
                rc = 0
        else:
            if changed:
                write_text(idx_path, new)
                print("[INFO]", f"updated index: {idx_path}")
            rc = 0

        # Emit meta issues (always print; in strict they flip exit code)
        if meta_issues:
            # keep deterministic output
            print("[INFO] metadata issues (diagnostic):")
            for it in meta_issues:
                print(it.get("loc", ""))
            report_errors.extend(meta_issues)

        # Strict overrides rc
        if strict_fail and rc == 0:
            rc = 2

        status = "PASS" if rc == 0 else "FAIL"
        rep = build_report(
            status=status,
            inputs={
                "repo_root": str(repo_root),
                "postmortems_dir": str(pm_dir),
                "index_file": str(idx_path),
                "mode": "check" if args.check else "write",
                "strict": bool(args.strict),
                "glob": args.glob,
                "link_text": args.link_text,
            },
            metrics={
                "postmortem_files_scanned": len(entries),
                "index_changed": bool(changed),
                "meta_issues": len(meta_issues),
            },
            errors=report_errors,
        )
        if args.json_out:
            write_report_bundle(
                report=rep,
                report_json=Path(args.json_out),
                repo_root=repo_root,
                console_title="update_postmortems_index",
                emit_console=not bool(args.json_stdout),
            )
        if args.json_stdout:
            print(json.dumps(rep, ensure_ascii=False, indent=2))

        if rc == 0:
            return _pass("postmortems index ok" if args.check else "postmortems index updated/ok")
        return _fail("postmortems index gate failed")

    except SystemExit:
        raise
    except Exception as e:
        msg = f"unexpected exception: {repr(e)}"
        print("[ERROR]", msg)
        report_errors.append({"loc": msg, "code": "EXCEPTION", "file": "", "line": 0, "col": 0})
        try:
            if "args" in locals() and getattr(args, "json_out", None):
                rep = build_report(status="ERROR", inputs={}, metrics={}, errors=report_errors)
                write_report_bundle(
                    report=rep,
                    report_json=Path(args.json_out),
                    repo_root=repo_root,
                    console_title="update_postmortems_index",
                    emit_console=not bool(args.json_stdout),
                )
        except Exception:
            pass
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
