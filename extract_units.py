# extract_units.py
# Purpose:
#   Read inventory.csv and produce data_processed/text_units.jsonl.
#   Contract:
#   - Output JSONL must contain keys required by validate_rag_units.py:
#       doc_id, source_uri, source_type, locator, text, content_sha256, updated_at, note
#   - For markdown units, also include: asset_refs, doc_refs
#
# Notes:
#   This module is the "authoritative" implementation used by the root wrappers:
#     - extract_units.py (runpy wrapper)
#     - tools/run_build_profile.py

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional, Tuple

from mhy_ai_rag_data.md_refs import extract_refs_from_md
from mhy_ai_rag_data.project_paths import find_project_root


# We treat 'md' specially (needs refs extraction), so don't include it here.
TEXT_TYPES = {"txt", "code", "other", "html"}
IMAGE_TYPES = {"image"}
VIDEO_TYPES = {"video"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _find_sidecar_text(media_path: Path) -> Optional[Tuple[str, str]]:
    """For image/video, try to find sidecar caption/transcript files.

    Returns (locator_suffix, text) or None.
    """
    ext = media_path.suffix.lower()
    if ext in {".mp4", ".mkv", ".mov"}:
        candidates = [".srt", ".vtt", ".txt", ".md"]
    else:
        candidates = [".txt", ".md"]

    for cext in candidates:
        p = media_path.with_suffix(cext)
        if p.exists() and p.is_file():
            try:
                return (f"sidecar:{p.name}", _read_text(p))
            except Exception:
                continue
    return None


def _normalize_source_type(row_source_type: str, source_uri: str) -> str:
    """Inventory may map some extensions to 'other'. We add a robust fallback by extension."""
    st = (row_source_type or "").strip().lower()
    ext = Path(source_uri).suffix.lower()

    if ext in {".md", ".markdown"}:
        return "md"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if ext in {".mp4", ".mkv", ".mov"}:
        return "video"
    if ext in {".txt"}:
        return "txt"
    if ext in {".html", ".htm"}:
        return "html"

    return st or "other"


def main() -> None:
    ap = argparse.ArgumentParser(description="Read inventory.csv and produce data_processed/text_units.jsonl")
    ap.add_argument("--root", default=None, help="Project root. Default: auto-detect from cwd")
    ap.add_argument("--inventory", default="inventory.csv", help="Inventory CSV path relative to root")
    ap.add_argument("--out", default="data_processed/text_units.jsonl", help="Output JSONL path relative to root")
    args = ap.parse_args()

    project_root = find_project_root(args.root)
    inv = (project_root / args.inventory).resolve()
    out = (project_root / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if not inv.exists():
        raise SystemExit(f"Missing {inv}")

    n = 0
    with inv.open("r", encoding="utf-8", newline="") as f_in, out.open("w", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        for row in reader:
            doc_id = (row.get("doc_id") or "").strip()
            source_uri = (row.get("source_uri") or "").strip()
            if not doc_id or not source_uri:
                continue

            source_type = _normalize_source_type(row.get("source_type", ""), source_uri)
            note = row.get("note", "")
            content_sha256 = row.get("content_sha256", "")
            updated_at = row.get("updated_at", "")

            path = (project_root / source_uri).resolve()

            # 0) Markdown (special): extract refs via markdown-it-py
            if source_type == "md":
                text = _read_text(path)
                asset_refs, doc_refs = extract_refs_from_md(
                    md_path=path,
                    md_text=text,
                    project_root=project_root,
                    preset="commonmark",
                )
                unit = {
                    "doc_id": doc_id,
                    "source_uri": source_uri,
                    "source_type": "md",
                    "locator": f"file:{source_uri}",
                    "text": text,
                    "asset_refs": asset_refs,
                    "doc_refs": doc_refs,
                    "content_sha256": content_sha256,
                    "updated_at": updated_at,
                    "note": note,
                }
                f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")
                n += 1
                continue

            # 1) Other text types (txt/code/html/other)
            if source_type in TEXT_TYPES:
                text = _read_text(path)
                unit = {
                    "doc_id": doc_id,
                    "source_uri": source_uri,
                    "source_type": source_type,
                    "locator": f"file:{source_uri}",
                    "text": text,
                    "content_sha256": content_sha256,
                    "updated_at": updated_at,
                    "note": note,
                }
                f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")
                n += 1
                continue

            # 2) Images
            if source_type in IMAGE_TYPES:
                sidecar = _find_sidecar_text(path)
                if sidecar:
                    loc_suffix, extra_text = sidecar
                    text = f"[IMAGE]\nfilename={path.name}\npath={source_uri}\n{extra_text}"
                    locator = f"file:{source_uri};{loc_suffix}"
                else:
                    text = f"[IMAGE]\nfilename={path.name}\npath={source_uri}\ncaption=TODO"
                    locator = f"file:{source_uri}"

                unit = {
                    "doc_id": doc_id,
                    "source_uri": source_uri,
                    "source_type": "image",
                    "locator": locator,
                    "text": text,
                    "content_sha256": content_sha256,
                    "updated_at": updated_at,
                    "note": note,
                }
                f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")
                n += 1
                continue

            # 3) Videos
            if source_type in VIDEO_TYPES:
                sidecar = _find_sidecar_text(path)
                if sidecar:
                    loc_suffix, extra_text = sidecar
                    text = f"[VIDEO]\nfilename={path.name}\npath={source_uri}\n{extra_text}"
                    locator = f"file:{source_uri};{loc_suffix}"
                else:
                    text = f"[VIDEO]\nfilename={path.name}\npath={source_uri}\ntranscript=TODO"
                    locator = f"file:{source_uri}"

                unit = {
                    "doc_id": doc_id,
                    "source_uri": source_uri,
                    "source_type": "video",
                    "locator": locator,
                    "text": text,
                    "content_sha256": content_sha256,
                    "updated_at": updated_at,
                    "note": note,
                }
                f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")
                n += 1
                continue

            # 4) Fallback for unknown binary types
            text = f"[BINARY]\nfilename={path.name}\npath={source_uri}\nkind={source_type}"
            unit = {
                "doc_id": doc_id,
                "source_uri": source_uri,
                "source_type": source_type,
                "locator": f"file:{source_uri}",
                "text": text,
                "content_sha256": content_sha256,
                "updated_at": updated_at,
                "note": note,
            }
            f_out.write(json.dumps(unit, ensure_ascii=False) + "\n")
            n += 1

    print(f"Wrote {n} units to {out}")


if __name__ == "__main__":
    main()
