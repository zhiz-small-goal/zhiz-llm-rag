#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_bundle

Write a "report bundle" consistently:
- report.json (normalized ordering + loc_uri enrichment)
- report.md  (human entrypoint; clickable VS Code links)
- console rendering (scroll-friendly; summary at end; ends with \n\n)

This is intended as the single sink used by tools that want global consistency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mhy_ai_rag_data.tools.report_contract import ensure_report_v2
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output, write_json_report
from mhy_ai_rag_data.tools.report_render import render_console, render_markdown


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def default_md_path_for_json(json_path: Path) -> Path:
    if json_path.suffix.lower() == ".json":
        return json_path.with_suffix(".md")
    return Path(str(json_path) + ".md")


def write_report_bundle(
    *,
    report: Any,
    report_json: Path,
    report_md: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    console_title: str = "report",
    emit_console: bool = True,
) -> Dict[str, Any]:
    """Write report.json + report.md and optionally emit console text.

    Key behaviors:
    - v2 contract is enforced via ensure_report_v2
    - file output is normalized via prepare_report_for_file_output
    - report.md is written atomically (tmp then rename)
    """

    report_json = report_json.resolve()
    report_md = (report_md or default_md_path_for_json(report_json)).resolve()

    # 1) ensure v2 and normalize for file
    v2 = ensure_report_v2(report)
    if repo_root is not None and isinstance(repo_root, Path):
        v2["root"] = str(repo_root.resolve().as_posix())

    normalized = prepare_report_for_file_output(v2)
    if not isinstance(normalized, dict):
        raise TypeError("prepare_report_for_file_output must return a dict for report bundles")

    # 2) write json (report_order already normalizes; we pass original for clarity)
    write_json_report(report_json, normalized)

    # 3) write markdown (human entrypoint)
    root_path = repo_root.resolve() if repo_root is not None else Path(str(normalized.get("root") or ".")).resolve()
    md = render_markdown(normalized, report_path=report_json, root=root_path, title=console_title)
    _atomic_write_text(report_md, md)

    # 4) console rendering (stdout): ends with \n\n
    if emit_console:
        print(render_console(normalized, title=console_title), end="")

    return normalized
