from __future__ import annotations

from pathlib import Path

from mhy_ai_rag_data.project_paths import find_project_root
from typing import Any, Optional
from urllib.parse import unquote

from markdown_it import MarkdownIt

DOC_ROOT_REL = "data_raw"  # 你可以改成别的资料根
ROOT_PREFIXES = ("教程/", "综合指南/")  # 按需扩展

ASSET_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mkv", ".mov"}
DOC_EXT = {".md", ".markdown"}


def _split_query_anchor(raw: str) -> tuple[str, str]:
    """return (clean_path, hint) where hint keeps original #/? part if any."""
    hint = ""
    s = raw.strip()
    if "?" in s:
        s, q = s.split("?", 1)
        hint += f"?{q}"
    if "#" in s:
        s, a = s.split("#", 1)
        hint += f"#{a}" if hint == "" else f"#{a}"
    return s.strip(), hint


def _normalize_target(raw_target: str | int | float) -> tuple[str, str]:
    """Decode URL encoding + normalize slashes + strip query/anchor."""
    s = unquote(str(raw_target).strip()).replace("\\", "/")
    clean, hint = _split_query_anchor(s)
    # drop surrounding angle brackets <...> if present
    if clean.startswith("<") and clean.endswith(">"):
        clean = clean[1:-1].strip()
    return clean, hint


def _resolve_to_project_rel(md_path: Path, target_path: str, project_root: Path) -> Optional[str]:
    """
    Resolve target_path to project_root-relative POSIX path.
    Rules:
      - If target_path starts with known ROOT_PREFIXES, resolve against DOC_ROOT (project_root/DOC_ROOT_REL)
      - Else resolve against md_path.parent (standard relative link)
    """
    doc_root = (project_root / DOC_ROOT_REL).resolve()

    # 站点根风格：例如 "教程/xx.md"、"综合指南/xx.md"
    if any(target_path.startswith(p) for p in ROOT_PREFIXES):
        abs_p = (doc_root / target_path).resolve()
    else:
        abs_p = (md_path.parent / target_path).resolve()

    try:
        return abs_p.relative_to(project_root).as_posix()
    except ValueError:
        return None


def extract_refs_from_md(
    md_path: Path,
    md_text: str,
    project_root: Path,
    preset: str = "commonmark",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (asset_refs, doc_refs).
    Each ref contains:
      - ref_type: image/video/md
      - target_uri: project-root-relative posix path
      - from_locator: line range in source file (1-based)
      - raw: raw src/href (decoded)
      - hint: query/anchor part (optional)
    """
    md = MarkdownIt(preset)
    tokens = md.parse(md_text)

    asset_refs: list[dict[str, Any]] = []
    doc_refs: list[dict[str, Any]] = []
    seen_asset = set()
    seen_doc = set()

    for t in tokens:
        if t.type != "inline" or not t.children:
            continue
        # Token.map is [line_begin, line_end] (0-based). Convert to 1-based for display.
        if t.map and len(t.map) == 2:
            lb, le = t.map[0] + 1, t.map[1]
            from_locator = f"line:{lb}-{le}"
        else:
            from_locator = "line:unknown"

        for c in t.children:
            if c.type == "image":
                src = (c.attrs or {}).get("src", "")
                src, hint = _normalize_target(src)
                if not src or src.startswith(("http://", "https://", "mailto:", "data:")):
                    continue
                rel = _resolve_to_project_rel(md_path, src, project_root)
                if not rel:
                    continue
                ext = Path(rel).suffix.lower()
                if ext not in ASSET_EXT:
                    continue
                ref_type = "video" if ext in {".mp4", ".mkv", ".mov"} else "image"
                if rel in seen_asset:
                    continue
                seen_asset.add(rel)
                asset_refs.append(
                    {
                        "ref_type": ref_type,
                        "target_uri": rel,
                        "from_locator": from_locator,
                        "raw": src,
                        "hint": hint,
                    }
                )

            elif c.type == "link_open":
                href = (c.attrs or {}).get("href", "")
                href, hint = _normalize_target(href)
                if not href or href.startswith(("http://", "https://", "mailto:", "data:")):
                    continue
                rel = _resolve_to_project_rel(md_path, href, project_root)
                if not rel:
                    continue
                ext = Path(rel).suffix.lower()
                if ext in DOC_EXT:
                    if rel in seen_doc:
                        continue
                    seen_doc.add(rel)
                    doc_refs.append(
                        {
                            "ref_type": "md",
                            "target_uri": rel,
                            "from_locator": from_locator,
                            "raw": href,
                            "hint": hint,
                        }
                    )
                elif ext in ASSET_EXT:
                    ref_type = "video" if ext in {".mp4", ".mkv", ".mov"} else "image"
                    if rel in seen_asset:
                        continue
                    seen_asset.add(rel)
                    asset_refs.append(
                        {
                            "ref_type": ref_type,
                            "target_uri": rel,
                            "from_locator": from_locator,
                            "raw": href,
                            "hint": hint,
                        }
                    )

    return asset_refs, doc_refs


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python md_refs.py <path-to-md> [project-root]", file=sys.stderr)
        raise SystemExit(2)

    md_path = Path(sys.argv[1]).resolve()
    project_root = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else find_project_root(None)

    text = md_path.read_text(encoding="utf-8", errors="ignore")
    asset_refs, doc_refs = extract_refs_from_md(
        md_path=md_path,
        md_text=text,
        project_root=project_root,
        preset="commonmark",
    )

    print("ASSET_REFS:")
    print(json.dumps(asset_refs, ensure_ascii=False, indent=2))
    print("\nDOC_REFS:")
    print(json.dumps(doc_refs, ensure_ascii=False, indent=2))
