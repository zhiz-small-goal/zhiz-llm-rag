from __future__ import annotations

import argparse
import csv
import hashlib
import uuid
import sys
from pathlib import Path
from datetime import datetime
from typing import Any

from mhy_ai_rag_data.project_paths import find_project_root


# ---- scan ignore policy ----
# Goal: make inventory stable across runs by skipping transient build artifacts
# (python cache, editor temp files, OS thumbnails). Keep this conservative.
IGNORED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
}

IGNORED_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

IGNORED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".swp",
    ".swo",
}

# ========= 你只需要改这里：自由增删字段 =========
NOTE_CONFIG: dict[str, Any] = {
    "access": "public",
    "use": "allow",
    "pii": "no",
    # 例子：你可随时加
    # "domain": "rag",
    # "doc_version": "2025.12",
    # "freshness": "low",
}
# ============================================

EXT_MAP = {
    ".pdf": "pdf",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
    ".html": "html",
    ".htm": "html",
    ".c": "code",
    ".cc": "code",
    ".cpp": "code",
    ".h": "code",
    ".hpp": "code",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".java": "code",
    ".rs": "code",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp4": "video",
    ".mkv": "video",
    ".mov": "video",
    ".mp3": "audio",
    ".wav": "audio",
}

FIELDS = [
    "doc_id",
    "source_uri",
    "filename",
    "source_type",
    "content_sha256",
    "size_bytes",
    "updated_at",
    "note",
]


def to_posix_rel(project_root: Path, path: Path) -> str:
    return path.relative_to(project_root).as_posix()


def iso_time_from_mtime(mtime_sec: float) -> str:
    return datetime.fromtimestamp(mtime_sec).strftime("%Y-%m-%dT%H:%M:%S")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return str(v)


def build_note(conf: dict[str, Any]) -> str:
    """Serialize NOTE_CONFIG to a stable 'k=v;k=v' string.

    Keys are sorted for determinism.
    Defensive: forbid ';' and '=' in keys/values to keep the format parseable.
    """
    parts = []
    for k in sorted(conf.keys()):
        key = str(k).strip()
        val = _normalize_value(conf[k]).strip()
        if not key:
            continue
        if any(x in key for x in (";", "=")) or any(x in val for x in (";", "=")):
            raise ValueError(f"Invalid note field: {key}={val} contains ';' or '='")
        parts.append(f"{key}={val}")
    return ";".join(parts)


def _should_ignore(p: Path) -> bool:
    # directory filter (any ancestor under data_raw)
    for part in p.parts:
        if part in IGNORED_DIR_NAMES:
            return True
    if p.name in IGNORED_FILE_NAMES:
        return True
    if p.suffix.lower() in IGNORED_SUFFIXES:
        return True
    # common editor backups: xxx~
    if p.name.endswith("~"):
        return True
    return False


def load_existing_doc_ids(out_csv: Path) -> dict[str, str]:
    """增量复用：source_uri -> doc_id。

    语义：保持 doc_id 对稳定文件的稳定性，以减少下游“删除/新增”波动。
    """
    if not out_csv.exists():
        return {}
    mapping: dict[str, str] = {}
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            su = (row.get("source_uri") or "").strip()
            di = (row.get("doc_id") or "").strip()
            if su and di:
                mapping[su] = di
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan data_raw/ and write inventory.csv")
    ap.add_argument("--root", default=None, help="Project root (default: auto-detect from CWD)")
    args = ap.parse_args()

    project_root = find_project_root(args.root)
    raw_dir = project_root / "data_raw"
    out_csv = project_root / "inventory.csv"

    if not raw_dir.exists():
        print(f"[FAIL] missing directory: {raw_dir}", file=sys.stderr)
        raise SystemExit(2)

    existing = load_existing_doc_ids(out_csv)
    note_value = build_note(NOTE_CONFIG)

    rows: list[dict[str, str]] = []
    for p in raw_dir.rglob("*"):
        if not p.is_file():
            continue
        if _should_ignore(p):
            continue

        st = p.stat()
        source_uri = to_posix_rel(project_root, p)
        filename = p.name
        source_type = EXT_MAP.get(p.suffix.lower(), "other")

        doc_id = existing.get(source_uri) or str(uuid.uuid4())

        rows.append(
            {
                "doc_id": doc_id,
                "source_uri": source_uri,
                "filename": filename,
                "source_type": source_type,
                "content_sha256": sha256_file(p),
                "size_bytes": str(st.st_size),
                "updated_at": iso_time_from_mtime(st.st_mtime),
                "note": note_value,  # 从字典配置生成
            }
        )

    rows.sort(key=lambda r: r["source_uri"])

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_csv}")


if __name__ == "__main__":
    main()
