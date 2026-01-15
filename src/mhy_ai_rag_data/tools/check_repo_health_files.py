#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_repo_health_files.py

Minimal repo health checks for public release readiness.
Stdlib-only by design.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from mhy_ai_rag_data.project_paths import find_project_root
from mhy_ai_rag_data.tools.report_order import write_json_report


DEFAULT_PLACEHOLDERS = [
    "[INSERT CONTACT METHOD]",
    "INSERT CONTACT METHOD",
    "project-contact@example.com",
    "contact@example.com",
    "your.email@example.com",
    "your-email@example.com",
    "change_me",
    "replace_me",
    "tbd",
    "todo",
    "example.com",
]


@dataclass(frozen=True)
class FileSpec:
    name: str
    required: bool


FILE_SPECS = [
    FileSpec("CHANGELOG.md", required=True),
    FileSpec(".editorconfig", required=True),
    FileSpec("CITATION.cff", required=False),
    FileSpec("CODE_OF_CONDUCT.md", required=False),
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_text(path: Path, max_bytes: int = 256 * 1024) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def find_placeholders(text: str, markers: Iterable[str]) -> List[str]:
    text_lower = text.lower()
    hits: List[str] = []
    for m in markers:
        if m.lower() in text_lower:
            hits.append(m)
    return hits


def resolve_out_path(repo: Path, out: str) -> Path:
    p = Path(out)
    if not p.is_absolute():
        p = repo / p
    return p.resolve()


def build_report(
    repo: Path,
    mode: str,
    placeholder_markers: List[str],
) -> Dict[str, Any]:
    required_missing: List[str] = []
    optional_missing: List[str] = []
    placeholders: List[Dict[str, Any]] = []
    errors: List[str] = []
    files: List[Dict[str, Any]] = []

    for spec in FILE_SPECS:
        path = repo / spec.name
        exists = path.exists()
        size_bytes = path.stat().st_size if exists else 0
        file_entry: Dict[str, Any] = {
            "name": spec.name,
            "path": str(path),
            "required": spec.required,
            "exists": exists,
            "size_bytes": size_bytes,
            "placeholder_hits": [],
        }

        if not exists:
            if spec.required:
                required_missing.append(spec.name)
            else:
                optional_missing.append(spec.name)
            files.append(file_entry)
            continue

        try:
            text = read_text(path)
        except Exception as e:
            errors.append(f"read_failed:{spec.name}:{type(e).__name__}")
            files.append(file_entry)
            continue

        hits = find_placeholders(text, placeholder_markers)
        if hits:
            file_entry["placeholder_hits"] = hits
            placeholders.append({"file": spec.name, "hits": hits})
        files.append(file_entry)

    placeholders_disallowed = mode == "public-release"
    result = "PASS"
    if required_missing or errors:
        result = "FAIL"
    elif placeholders and placeholders_disallowed:
        result = "FAIL"
    elif optional_missing or placeholders:
        result = "WARN"

    return {
        "schema": "repo_health_report_v1",
        "ts": now_iso(),
        "repo": str(repo),
        "mode": mode,
        "placeholders_disallowed": placeholders_disallowed,
        "summary": {
            "result": result,
            "required_missing": len(required_missing),
            "optional_missing": len(optional_missing),
            "placeholders": len(placeholders),
            "errors": len(errors),
        },
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "placeholders": placeholders,
        "errors": errors,
        "files": files,
    }


def print_summary(report: Dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"result={summary['result']}")
    print(f"required_missing={summary['required_missing']}")
    print(f"optional_missing={summary['optional_missing']}")
    print(f"placeholders={summary['placeholders']}")
    if report["required_missing"]:
        print(f"required_missing_files={','.join(report['required_missing'])}")
    if report["optional_missing"]:
        print(f"optional_missing_files={','.join(report['optional_missing'])}")
    if report["placeholders"]:
        for it in report["placeholders"]:
            hits = ",".join(it.get("hits", []))
            print(f"placeholder={it.get('file')}:{hits}")
    if report["errors"]:
        print(f"errors={','.join(report['errors'])}")


def result_to_rc(result: str) -> int:
    if result == "PASS":
        return 0
    if result == "WARN":
        return 1
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Check repo health/community files for public release readiness.")
    ap.add_argument("--repo", default=".", help="Repo root (default: auto-detect)")
    ap.add_argument(
        "--mode",
        default="public-release",
        choices=["public-release", "draft"],
        help="public-release: placeholders are FAIL; draft: placeholders are WARN",
    )
    ap.add_argument(
        "--out",
        default="",
        help="Write JSON report to this path (relative to repo root). Empty -> no JSON.",
    )
    ap.add_argument(
        "--placeholder",
        action="append",
        default=[],
        help="Extra placeholder token to flag (repeatable).",
    )
    args = ap.parse_args()

    repo = find_project_root(args.repo)
    placeholders = list(DEFAULT_PLACEHOLDERS)
    if args.placeholder:
        placeholders.extend([str(x) for x in args.placeholder if str(x).strip()])

    report = build_report(repo, args.mode, placeholders)
    print_summary(report)

    if args.out:
        out_path = resolve_out_path(repo, args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_report(out_path, report)
        print(f"report_written={out_path}")

    return result_to_rc(report["summary"]["result"])


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt", file=sys.stderr)
        return 2
    except SystemExit:
        raise
    except Exception:
        print("[ERROR] unhandled exception", file=sys.stderr)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(_entry())
