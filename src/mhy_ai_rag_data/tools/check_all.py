#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_all

一键自检（工程门禁脚本）。

全局一致报告输出改造：
- 控制台（stdout）：detail 轻->重（最严重留在最后），summary 在末尾，整体以 "\n\n" 结尾
- 落盘：report.json + report.md（.md 内定位可点击 VS Code 跳转）

退出码与 report.summary.overall_rc 对齐：
0：PASS
2：FAIL
3：ERROR
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mhy_ai_rag_data.tools.report_bundle import default_md_path_for_json, write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "check_all",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": False,
    "entrypoint": "python tools/check_all.py",
}


CORE_MODULES: List[str] = [
    "mhy_ai_rag_data.make_inventory",
    "mhy_ai_rag_data.extract_units",
    "mhy_ai_rag_data.validate_rag_units",
    "mhy_ai_rag_data.tools.plan_chunks_from_units",
    "mhy_ai_rag_data.tools.build_chroma_index_flagembedding",
    "mhy_ai_rag_data.check_chroma_build",
    "mhy_ai_rag_data.tools.index_state",
]


def _normalize_rel(p: str) -> str:
    return str(p).replace("\\\\", "/")


def _module_to_source_loc(repo: Path, module: str) -> str:
    rel = "src/" + module.replace(".", "/")
    py = repo / (rel + ".py")
    if py.exists():
        return f"{_normalize_rel(str(py.relative_to(repo)))}:1:1"
    pkg_init = repo / rel / "__init__.py"
    if pkg_init.exists():
        return f"{_normalize_rel(str(pkg_init.relative_to(repo)))}:1:1"
    return "src/:1:1"


def _toc_header(filename: str) -> str:
    base = Path(filename).name
    stem = base
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return f"# {stem}目录："


def _check_toc(md_path: Path, skip: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
    if skip:
        return True, f"TOC check skipped for {md_path}", {}
    if not md_path.exists():
        return False, f"MISSING: {md_path}", {}

    lines = md_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return False, f"empty file {md_path}", {}

    want = _toc_header(md_path.name)
    got = lines[0].strip()
    if got != want:
        return False, f"TOC header mismatch in {md_path}.", {"want": want, "got": got}

    toc_ok = any(re.match(r"^\s*-\s+\[[^\]]+\]\(#[^)]+\)", ln) for ln in lines[1:120])
    if not toc_ok:
        return False, f"TOC links not found near top of {md_path}", {}

    return True, f"TOC present in {md_path}", {}


def _run_compileall(repo: Path) -> Tuple[bool, str, Dict[str, Any]]:
    cmd = [sys.executable, "-m", "compileall", "-q", "-f", "src"]
    p = subprocess.run(cmd, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ok = p.returncode == 0
    out = (p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")
    tail = out.strip().splitlines()[-30:] if out.strip() else []
    if ok:
        return True, "compileall src", {"cmd": cmd}
    return False, "compileall src failed", {"cmd": cmd, "rc": p.returncode, "tail": tail}


def _run_help(repo: Path, module: str) -> Tuple[bool, str, Dict[str, Any]]:
    cmd = [sys.executable, "-m", module, "-h"]

    env = dict(os.environ)
    src = str((repo / "src").resolve())
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = src + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = src

    p = subprocess.run(cmd, cwd=str(repo), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ok = p.returncode == 0
    combined = (p.stderr or p.stdout or "").strip()
    tail = combined.splitlines()[-20:] if combined else []
    if ok:
        return True, f"python -m {module} -h", {"cmd": cmd}
    return False, f"python -m {module} -h failed", {"cmd": cmd, "rc": p.returncode, "tail": tail}


def _check_exists(repo: Path, rel: str) -> Tuple[bool, str, Dict[str, Any]]:
    p = repo / rel
    if p.exists():
        return True, f"exists {rel}", {}
    return False, f"MISSING: {rel}", {}


def _mk_item(
    repo: Path, title: str, ok: bool, message: str, loc: str, detail: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    it: Dict[str, Any] = {
        "tool": "check_all",
        "title": title,
        "status_label": "PASS" if ok else "FAIL",
        "severity_level": 0 if ok else 3,
        "message": message,
        "loc": loc,
    }
    if detail:
        it["detail"] = detail
    return ensure_item_fields(it, tool_default="check_all")


def main() -> int:
    ap = argparse.ArgumentParser(description="One-click repository gate check (src-layout, imports, TOC).")
    ap.add_argument("--root", default=".", help="Repo root (default: current directory)")
    ap.add_argument("--mode", default="fast", choices=["fast"], help="Check mode (currently only fast).")
    ap.add_argument(
        "--ignore-toc",
        nargs="+",
        default=[],
        help="List of filenames to ignore during TOC check (e.g. README.md)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/check_all_report.json",
        help="output report json (relative to root)",
    )
    ap.add_argument(
        "--md-out",
        default=None,
        help="optional report.md path (relative to root); default: <out>.md",
    )
    args = ap.parse_args()

    repo = Path(args.root).resolve()
    out_path = (repo / str(args.out)).resolve()
    md_path = (repo / str(args.md_out)).resolve() if args.md_out else default_md_path_for_json(out_path)

    t0 = time.time()
    items: List[Dict[str, Any]] = []

    def add_check(title: str, ok: bool, message: str, loc: str, detail: Dict[str, Any] | None = None) -> None:
        items.append(_mk_item(repo, title=title, ok=ok, message=message, loc=loc, detail=detail))

    try:
        # 1) structure
        for rel in [
            "pyproject.toml",
            "src/mhy_ai_rag_data/__init__.py",
            "src/mhy_ai_rag_data/tools/index_state.py",
            "src/mhy_ai_rag_data/tools/build_chroma_index_flagembedding.py",
        ]:
            ok, msg, detail = _check_exists(repo, rel)
            add_check(title=f"structure:{rel}", ok=ok, message=msg, loc=f"{_normalize_rel(rel)}:1:1", detail=detail)

        # 2) python compile (capture output; do not pollute stdout)
        ok, msg, detail = _run_compileall(repo)
        add_check(title="compileall:src", ok=ok, message=msg, loc="src/:1:1", detail=detail)

        # 3) module help (import-time safety)
        for m in CORE_MODULES:
            ok, msg, detail = _run_help(repo, m)
            add_check(title=f"entry:{m}", ok=ok, message=msg, loc=_module_to_source_loc(repo, m), detail=detail)

        # 4) docs TOC
        ignore_toc = set(args.ignore_toc)
        for rel in ["README.md", "docs/OPERATION_GUIDE.md"]:
            should_skip = any(rel.endswith(ig) for ig in ignore_toc)
            ok, msg, detail = _check_toc(repo / rel, skip=should_skip)
            add_check(title=f"toc:{rel}", ok=ok, message=msg, loc=f"{_normalize_rel(rel)}:1:1", detail=detail)

        summary = compute_summary(items)
        report = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "check_all",
            "root": str(repo.as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {
                "mode": str(args.mode),
                "elapsed_ms": int((time.time() - t0) * 1000),
                "argv": sys.argv,
            },
        }

        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=repo,
            console_title="check_all",
            emit_console=True,
        )
        return int(summary.overall_rc)

    except Exception as e:
        add_check(
            title="termination",
            ok=False,
            message=f"unhandled exception: {type(e).__name__}: {e}",
            loc="src/mhy_ai_rag_data/tools/check_all.py:1:1",
            detail={"exception": repr(e)},
        )
        summary = compute_summary(items)
        report = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "check_all",
            "root": str(repo.as_posix()),
            "summary": summary.to_dict(),
            "items": items,
            "data": {"elapsed_ms": int((time.time() - t0) * 1000), "argv": sys.argv},
        }
        write_report_bundle(
            report=report,
            report_json=out_path,
            report_md=md_path,
            repo_root=repo,
            console_title="check_all",
            emit_console=True,
        )
        return int(summary.overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
