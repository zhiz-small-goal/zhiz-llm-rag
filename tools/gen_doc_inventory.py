#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

gen_doc_inventory.py

Purpose
  Step1 (Level 3 doc system refactor): build a full Markdown inventory + a doc graph.
  - Inventory (human-readable): docs/explanation/doc_inventory.md
  - Graph (machine-readable):   docs/explanation/doc_map.json

Why this exists
  - Human-maintained inventories drift and are hard to review.
  - Step6 doc gates (links/terminology/front-matter) need a stable input set.

What it does
  - Enumerate tracked *.md via `git ls-files "*.md"` (fallback to glob if git unavailable).
  - For each file:
    - Parse YAML front-matter (best-effort)
    - Extract title (front-matter title else first H1)
    - Classify role (reference/guide/runbook/README/archive/postmortem)
    - Collect keyword hit locations (line number + nearest heading)
    - Extract intra-repo doc links (using mhy_ai_rag_data.md_refs)
  - Write outputs with deterministic ordering.

Usage
  python tools/gen_doc_inventory.py --root .
  python tools/gen_doc_inventory.py --root . --write

Exit codes
  0 PASS
  2 FAIL (unexpected coverage mismatch)
  3 ERROR (script exception)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Step1 keyword set (SSOT for inventory stage)
KEYWORDS: List[str] = [
    "index_state.json",
    "index_state.stage.jsonl",
    "resume-status",
    "on-missing-state",
    "writer.lock",
    "strict-sync",
    "sync-mode",
    "collection.count",
    "schema_hash",
]


def _repo_root(cli_root: Optional[str]) -> Path:
    if cli_root:
        return Path(cli_root).resolve()
    # tools/ is at repo root in this project layout
    return Path(__file__).resolve().parent.parent


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _ensure_src_on_path(root: Path) -> None:
    src = root / "src"
    if src.exists():
        sys.path.insert(0, str(src))


def _run(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _git_ls_md(root: Path) -> List[str]:
    rc, out, _err = _run(["git", "ls-files", "*.md"], cwd=root)
    if rc == 0:
        files = [ln.strip() for ln in out.splitlines() if ln.strip()]
        files.sort()
        return files
    # Fallback: full-repo glob (best-effort)
    files = [p.relative_to(root).as_posix() for p in root.rglob("*.md") if p.is_file()]
    files.sort()
    return files


def _git_ls_md_untracked(root: Path) -> List[str]:
    """Untracked markdown files (best-effort).

    Notes
      This is primarily useful when generating the Step1 inventory inside a working
      tree that contains new docs not yet committed.
    """

    rc, out, _err = _run(["git", "ls-files", "--others", "--exclude-standard", "*.md"], cwd=root)
    if rc != 0:
        return []
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    files.sort()
    return files


def _git_last_commit_date(root: Path, rel_path: str) -> Optional[str]:
    rc, out, _err = _run(["git", "log", "-1", "--format=%cs", "--", rel_path], cwd=root)
    if rc != 0:
        return None
    s = out.strip()
    return s or None


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _split_front_matter(text: str) -> Tuple[Optional[str], str]:
    """Return (front_matter_text_or_none, body_text)."""
    # Allow BOM
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    lines = text.splitlines(True)
    if not lines:
        return None, ""
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "".join(lines[: i + 1])
            body = "".join(lines[i + 1 :])
            return fm, body
    # no closing ---
    return "".join(lines), ""


def _parse_front_matter_yaml(front_matter: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
    if not front_matter:
        return False, {}
    # Strip leading/ending --- lines
    raw_lines = [ln.rstrip("\n") for ln in front_matter.splitlines()]
    if raw_lines and raw_lines[0].strip() == "---":
        raw_lines = raw_lines[1:]
    if raw_lines and raw_lines[-1].strip() == "---":
        raw_lines = raw_lines[:-1]
    raw = "\n".join(raw_lines).strip()
    if not raw:
        return True, {}
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(raw)
        if isinstance(obj, dict):
            return True, obj
        return True, {"_front_matter_non_mapping": obj}
    except Exception as e:
        return True, {"_front_matter_parse_error": str(e), "_front_matter_raw": raw}


def _extract_first_h1(body: str) -> Optional[str]:
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# "):
            return s[2:].strip()
        # Stop early if first content is not H1
        if s.startswith("## ") or s.startswith("### "):
            return None
    return None


def _classify_role(rel_path: str) -> Tuple[str, str]:
    """Return (role, role_hint). role must be one of
    reference|guide|runbook|README|archive|postmortem.
    """
    p = rel_path.replace("\\", "/")
    name = Path(p).name

    # Archive / postmortems first
    if p.startswith("docs/archive/") or "/archive/" in p:
        return "archive", "path"
    if p.startswith("docs/postmortems/"):
        return "postmortem", "path"

    # Reference
    if p.startswith("docs/reference/"):
        return "reference", "path"

    # README-like
    if name.lower() == "readme.md" or "readme" in name.lower():
        return "README", "name"

    # Runbook-ish (conservative heuristics)
    upper = name.upper()
    if any(tok in upper for tok in ["OPERATION", "RUNBOOK", "TROUBLESHOOT", "INCIDENT"]):
        return "runbook", "name"
    if p.startswith("docs/howto/") and any(tok in upper for tok in ["OPERATION", "TROUBLESHOOT"]):
        return "runbook", "path+name"

    # Default guide
    return "guide", "default"


def _nearest_heading(lines: List[str], line_idx_0: int) -> Optional[str]:
    # Search upwards for the closest markdown heading.
    for j in range(line_idx_0, -1, -1):
        s = lines[j].strip()
        if re.match(r"^#{1,6} ", s):
            return s
    return None


@dataclass
class Hit:
    keyword: str
    line: int
    heading: Optional[str]
    snippet: str


def _keyword_hits(text: str) -> Dict[str, List[Dict[str, Any]]]:
    lines = text.splitlines()
    out: Dict[str, List[Dict[str, Any]]] = {}
    # Precompile to avoid regex escaping issues
    kws = list(KEYWORDS)
    for kw in kws:
        out[kw] = []

    for i, ln in enumerate(lines):
        low = ln.lower()
        for kw in kws:
            if kw.lower() in low:
                heading = _nearest_heading(lines, i)
                snippet = ln.strip()
                if len(snippet) > 180:
                    snippet = snippet[:177] + "..."
                out[kw].append(
                    {
                        "line": i + 1,
                        "heading": heading,
                        "snippet": snippet,
                    }
                )
    # Drop empty
    out = {k: v for k, v in out.items() if v}
    return out


def _load_md_refs(md_path: Path, md_text: str, project_root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (asset_refs, doc_refs) with best-effort import."""
    try:
        from mhy_ai_rag_data.md_refs import extract_refs_from_md  # type: ignore

        return extract_refs_from_md(md_path=md_path, md_text=md_text, project_root=project_root, preset="commonmark")
    except Exception:
        return [], []


def _action_from_role_and_hits(role: str, has_hits: bool) -> str:
    if not has_hits:
        return "no_action"
    if role in {"archive", "postmortem"}:
        return "only_note"
    return "need_align"


def _json_default(o: Any) -> Any:
    """Best-effort conversion for non-JSON-serializable objects.

    Notes
      PyYAML may parse ISO-like dates into datetime.date. We serialize those as ISO strings.
    """

    # datetime/date
    iso = getattr(o, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass
    # pathlib.Path
    if isinstance(o, Path):
        return o.as_posix()
    return str(o)


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _make_inventory_md(meta: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
    total = meta.get("md_files_total", len(docs))

    # Counts
    role_counts: Dict[str, int] = {}
    action_counts: Dict[str, int] = {}
    kw_counts: Dict[str, int] = {}
    for d in docs:
        role_counts[d["role"]] = role_counts.get(d["role"], 0) + 1
        action_counts[d["action"]] = action_counts.get(d["action"], 0) + 1
        for kw in d.get("keyword_hits", {}).keys():
            kw_counts[kw] = kw_counts.get(kw, 0) + 1

    def _fmt_kv(m: Dict[str, int]) -> str:
        items = sorted(m.items(), key=lambda x: (-x[1], x[0]))
        return "\n".join([f"- `{k}`: {v}" for k, v in items])

    # Group docs
    docs_need_align = [d for d in docs if d["action"] == "need_align"]
    docs_only_note = [d for d in docs if d["action"] == "only_note"]

    # Stable ordering for lists
    docs_need_align.sort(key=lambda x: x["path"])
    docs_only_note.sort(key=lambda x: x["path"])

    def _doc_line(d: Dict[str, Any]) -> str:
        title = d.get("title") or "(no title)"
        return f"- `{d['path']}` — **{title}** (role={d['role']})"

    def _doc_hits_block(d: Dict[str, Any]) -> str:
        hits = d.get("keyword_hits", {})
        if not hits:
            return ""
        parts = []
        for kw in sorted(hits.keys()):
            locs = hits[kw]
            # show up to 3 locations to keep the inventory readable
            shown = locs[:3]
            loc_s = "; ".join([f"L{h['line']}" + (f" ({h['heading']})" if h.get("heading") else "") for h in shown])
            extra = "" if len(locs) <= 3 else f" (+{len(locs) - 3} more)"
            parts.append(f"  - `{kw}`: {loc_s}{extra}")
        return "\n".join(parts)

    lines: List[str] = []
    lines.append("---")
    lines.append("title: Doc Inventory (Level 3 Step1)")
    lines.append("version: v0.1")
    lines.append(f"last_updated: {meta.get('generated_at', '')}")
    lines.append("timezone: America/Los_Angeles")
    lines.append("owner: zhiz")
    lines.append("status: generated")
    lines.append("---")
    lines.append("")
    lines.append("# Doc Inventory (Level 3 Step1)")
    lines.append("")
    lines.append("## 目录")
    lines.append("- [1. Summary](#1-summary)")
    lines.append("- [2. need_align (active docs to align)](#2-need_align-active-docs-to-align)")
    lines.append("- [3. only_note (archive/postmortem hits)](#3-only_note-archivepostmortem-hits)")
    lines.append("- [4. Full list](#4-full-list)")
    lines.append("")

    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- generated_at: `{meta.get('generated_at')}`")
    lines.append(f"- git_head: `{meta.get('git_head')}`")
    lines.append(f"- md_files_total: **{total}**")
    lines.append(f"- keywords (Step1 fixed set): {', '.join([f'`{k}`' for k in KEYWORDS])}")
    lines.append("")
    lines.append("### 1.1 Role counts")
    lines.append(_fmt_kv(role_counts) or "(none)")
    lines.append("")
    lines.append("### 1.2 Action counts")
    lines.append(_fmt_kv(action_counts) or "(none)")
    lines.append("")
    lines.append("### 1.3 Keyword coverage (docs containing keyword)")
    lines.append(_fmt_kv(kw_counts) or "(none)")
    lines.append("")

    lines.append("## 2. need_align (active docs to align)")
    lines.append("")
    if not docs_need_align:
        lines.append("(none)")
    else:
        for d in docs_need_align:
            lines.append(_doc_line(d))
            hb = _doc_hits_block(d)
            if hb:
                lines.append(hb)
    lines.append("")

    lines.append("## 3. only_note (archive/postmortem hits)")
    lines.append("")
    if not docs_only_note:
        lines.append("(none)")
    else:
        for d in docs_only_note:
            lines.append(_doc_line(d))
            hb = _doc_hits_block(d)
            if hb:
                lines.append(hb)
    lines.append("")

    lines.append("## 4. Full list")
    lines.append("")
    for d in docs:
        title = d.get("title") or "(no title)"
        lines.append(f"- `{d['path']}` — **{title}** (role={d['role']}, action={d['action']})")

    lines.append("")
    lines.append("---")
    lines.append("## Notes")
    lines.append("- This file is generated. Edit the generator instead: `tools/gen_doc_inventory.py`.")
    lines.append("- The machine-readable graph is `docs/explanation/doc_map.json`.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="repo root; default inferred")
    ap.add_argument(
        "--out-md",
        default="docs/explanation/doc_inventory.md",
        help="output markdown path (relative to root)",
    )
    ap.add_argument(
        "--out-json",
        default="docs/explanation/doc_map.json",
        help="output json path (relative to root)",
    )
    ap.add_argument(
        "--include-untracked",
        action="store_true",
        help="also scan untracked *.md (git ls-files --others). useful for Step1 in a working tree",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="write outputs; default is dry-run (prints summary only)",
    )
    args = ap.parse_args()

    root = _repo_root(args.root)
    _ensure_src_on_path(root)

    tracked_md_files = _git_ls_md(root)

    md_files = list(tracked_md_files)
    if args.include_untracked:
        for p in _git_ls_md_untracked(root):
            if p not in md_files:
                md_files.append(p)
        md_files.sort()

    # Avoid self-recursion/noise: do not scan the generated inventory markdown.
    out_md_rel = Path(args.out_md).as_posix()
    md_files = [p for p in md_files if p != out_md_rel]

    git_head = None
    rc, out, _err = _run(["git", "rev-parse", "HEAD"], cwd=root)
    if rc == 0:
        git_head = out.strip() or None

    docs: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for rel in md_files:
        abs_p = root / rel
        text = _read_text(abs_p)
        fm_text, body = _split_front_matter(text)
        has_fm, fm_obj = _parse_front_matter_yaml(fm_text)

        title = None
        if isinstance(fm_obj, dict):
            t = fm_obj.get("title")
            if isinstance(t, str) and t.strip():
                title = t.strip()
        if not title:
            title = _extract_first_h1(body)

        role, role_hint = _classify_role(rel)
        hits = _keyword_hits(text)
        action = _action_from_role_and_hits(role, bool(hits))

        last_commit_date = _git_last_commit_date(root, rel)

        asset_refs, doc_refs = _load_md_refs(abs_p, text, root)

        # Build edges for doc refs
        for r in doc_refs:
            tgt = r.get("target_uri")
            if not tgt:
                continue
            edges.append(
                {
                    "from": rel,
                    "to": tgt,
                    "from_locator": r.get("from_locator"),
                    "raw": r.get("raw"),
                    "hint": r.get("hint"),
                    "ref_type": r.get("ref_type"),
                }
            )

        docs.append(
            {
                "path": rel,
                "title": title,
                "role": role,
                "role_hint": role_hint,
                "action": action,
                "has_front_matter": has_fm,
                "front_matter": fm_obj,
                "git_last_commit_date": last_commit_date,
                "keyword_hits": hits,
                "links": {
                    "docs": doc_refs,
                    "assets": asset_refs,
                },
            }
        )

    # Deterministic ordering
    docs.sort(key=lambda d: d["path"])
    edges.sort(key=lambda e: (e.get("from") or "", e.get("to") or "", e.get("from_locator") or ""))

    meta = {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "root": root.as_posix(),
        "git_head": git_head,
        "tracked_md_files_total": len(tracked_md_files),
        "scanned_md_files_total": len(md_files),
        "include_untracked": bool(args.include_untracked),
        "keywords": KEYWORDS,
        "command": "python tools/gen_doc_inventory.py --root . --write",
    }

    # Acceptance (Step1): must cover git ls-files "*.md" 100%.
    scanned = {d["path"] for d in docs}
    missing_tracked = [p for p in tracked_md_files if p not in scanned and p != out_md_rel]
    if missing_tracked:
        print("[FAIL] missing tracked markdown files:")
        for p in missing_tracked[:20]:
            print(f"  - {p}")
        if len(missing_tracked) > 20:
            print(f"  ... (+{len(missing_tracked) - 20} more)")
        return 2

    out_md = root / args.out_md
    out_json = root / args.out_json

    if args.write:
        inv_md = _make_inventory_md(meta, docs)
        _write_text(out_md, inv_md)
        _write_text(out_json, _safe_json({"meta": meta, "docs": docs, "edges": edges}) + "\n")
        print(f"[OK] wrote: {out_md.relative_to(root).as_posix()}")
        print(f"[OK] wrote: {out_json.relative_to(root).as_posix()}")
        return 0

    # Dry-run: print a minimal summary
    docs_with_hits = sum(1 for d in docs if d.get("keyword_hits"))
    print(f"md_files_total={len(md_files)}")
    print(f"docs_with_keyword_hits={docs_with_hits}")
    print("(use --write to write outputs)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[ERROR] {e.__class__.__name__}: {e}")
        raise SystemExit(3)
