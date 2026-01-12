#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

generate_review_spec_docs.py

Purpose
  Generate the human-readable Review Spec (Markdown) from SSOT JSON.

Why this exists
  - Avoid double-writing: SSOT is the single source of truth.
  - Keep the generated Reference doc deterministic and reviewable in PRs.

Usage
  python tools/generate_review_spec_docs.py --check
  python tools/generate_review_spec_docs.py --write
  python tools/generate_review_spec_docs.py --root . --write

Exit codes (contract)
  0 PASS
  2 FAIL  (generated doc is out-of-date / invalid args)
  3 ERROR (unexpected exception)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _repo_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).resolve()
    return Path(__file__).resolve().parent.parent


def _read_json(p: Path) -> Dict[str, Any]:
    try:
        text = p.read_text(encoding="utf-8")
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("SSOT JSON must be an object")
        return obj
    except json.JSONDecodeError as e:
        # DIAG_LOC: path:line:col
        print(f"{p.as_posix()}:{e.lineno}:{e.colno}: [FAIL] JSON parse failed: {e.msg}")
        raise


def _gen_md(spec: Dict[str, Any]) -> str:
    meta = spec.get("meta") or {}
    scope = spec.get("scope") or {}
    process = spec.get("process") or {}
    checklists = spec.get("checklists") or []
    refs = spec.get("references") or []

    def _g(k: str, default: str = "") -> str:
        v = meta.get(k, default)
        return str(v) if v is not None else default

    title = _g("title", "Review Spec")
    version = _g("version", "0.0.0")
    last_updated = _g("last_updated", "")
    tz = _g("timezone", "")
    source = _g("source_file", "")
    gen_art = _g("generated_artifact", "")

    lines: List[str] = []
    lines += [
        "---",
        f"title: {title}",
        f"version: v{version}",
        f"last_updated: {last_updated}",
        f"timezone: {tz}",
        f"source: {source}",
        f"generated_artifact: {gen_art}",
        "---",
        "",
        "# 项目审查规范（Review Spec）",
        "",
        "> SSOT（机器可读）：`docs/reference/review/review_spec.v1.json`",
        "> 生成产物（人类阅读）：`docs/reference/review/REVIEW_SPEC.md`（本文件）",
        "",
        "本规范用于在仓库内以一致口径审查：文档、代码、复用、安全与报告输出。核心思想是“证据化审查”：每条关键判断都应能通过可定位证据复核（文件路径/行列、命令、报告产物、schema）。",
        "",
        "## 目录",
        "- [1. 概览](#1-概览)",
        "- [2. 适用范围与优先级](#2-适用范围与优先级)",
        "- [3. 审查工作流（PR 边界）](#3-审查工作流pr-边界)",
        "- [4. 审查清单（按优先级）](#4-审查清单按优先级)",
        "- [5. 证据包与报告模板](#5-证据包与报告模板)",
        "- [6. 演进接口与版本策略](#6-演进接口与版本策略)",
        "- [7. 引用](#7-引用)",
        "",
        "## 1. 概览",
        "",
        f"- 项目类型：{scope.get('project_type', '')}",
        f"- 当前阶段：{scope.get('stage', '')}",
        f"- 审查优先级（高→低）：{' > '.join(scope.get('priority_order', []))}",
        "",
        "## 2. 适用范围与优先级",
        "",
        "### 2.1 适用范围（paths）",
        "",
    ]
    for p in scope.get("applies_to", []) or []:
        lines.append(f"- `{p}`")
    lines += [
        "",
        "### 2.2 不在范围内（out-of-scope）",
        "",
    ]
    for p in scope.get("out_of_scope", []) or []:
        lines.append(f"- {p}")
    lines += [
        "",
        "## 3. 审查工作流（PR 边界）",
        "",
        str(process.get("overview", "")).strip(),
        "",
        "### 3.1 角色",
        "",
        f"- Author：{(process.get('roles') or {}).get('author', '')}",
        f"- Reviewer：{(process.get('roles') or {}).get('reviewer', '')}",
        "",
        "### 3.2 流程（MUST）",
        "",
    ]
    for idx, st in enumerate(process.get("workflow", []) or [], start=1):
        lines.append(f"**Step {idx}：{st.get('step', '')}**")
        for m in st.get("must", []) or []:
            lines.append(f"- MUST: {m}")
        lines.append("")

    lines += [
        "## 4. 审查清单（按优先级）",
        "",
        "说明：每个条目包含 Level（MUST/SHOULD/MAY）、要求、理由与证据。若条目有 automation 字段，表示可接入 gate/CI 进行自动化校验。",
        "",
    ]

    for area_idx, area in enumerate(checklists, start=1):
        area_name = str(area.get("area", "")).strip()
        lines += [f"### 4.{area_idx} {area_name}", ""]
        for item in area.get("items", []) or []:
            iid = str(item.get("id", "")).strip()
            lvl = str(item.get("level", "")).strip()
            stmt = str(item.get("statement", "")).strip()
            lines.append(f"- **{iid}** `[{lvl}]`：{stmt}")
            rat = str(item.get("rationale", "")).strip()
            if rat:
                lines.append(f"  - Why：{rat}")
            ev = item.get("evidence", []) or []
            if ev:
                lines.append("  - Evidence：")
                for e in ev:
                    lines.append(f"    - {e}")
            auto = item.get("automation")
            if isinstance(auto, dict) and auto:
                tool = str(auto.get("tool", "")).strip()
                mode = str(auto.get("mode", "")).strip()
                lines.append(f"  - Automation：`{tool}`（mode={mode}）")
        lines.append("")

    lines += [
        "## 5. 证据包与报告模板",
        "",
        "### 5.1 PR 证据包（建议最小集）",
        "",
        "- 变更摘要：目标/范围/影响面/回滚方式（如适用）",
        "- 验证命令：至少包含 1 条本地可复核命令（例如 `python tools/gate.py --profile fast --root .`）",
        "- 产物路径：若产出 JSON 报告或中间文件，给出相对路径",
        "- 定位信息：诊断尽量使用 `file:line:col`（编辑器可跳转）",
        "",
        "### 5.2 报告模板",
        "",
        f"- 人类可读模板：`{((spec.get('reporting') or {}).get('templates') or {}).get('md', '')}`",
        f"- 机器可读模板：`{((spec.get('reporting') or {}).get('templates') or {}).get('json', '')}`",
        "",
        "### 5.3 与 Gate/CI 的关系",
        "",
        "本规范自身通过 `tools/validate_review_spec.py` 在 gate 中进行“SSOT 校验 + 生成产物一致性检查”。当 SSOT 变更但未同步刷新生成文档时，gate 将 FAIL，避免口径漂移。",
        "",
        "## 6. 演进接口与版本策略",
        "",
        f"- 版本策略：SemVer（{((spec.get('evolution') or {}).get('compat') or {}).get('semver', '')}）",
        f"- 兼容策略：{((spec.get('evolution') or {}).get('compat') or {}).get('policy', '')}",
        "",
        "### 6.1 扩展点（extensions）",
        "",
        "- `extensions`：预留给新增维度/新字段；优先以扩展字段落地，再评估是否升级主结构版本。",
        "- `reporting.extensions`：预留给报告额外字段（例如统计指标、回归对照组）。",
        "",
        "## 7. 引用",
        "",
        "下列引用用于解释本规范的组织方式与通用审查实践；项目内实现以仓库 SSOT/源码为准。",
        "",
    ]
    for r in refs:
        if not isinstance(r, dict):
            continue
        lines.append(
            f"- {r.get('title', '')} | {r.get('url', '')} | {r.get('version_or_date', '')} | {r.get('kind', '')} | {r.get('locator', '')}"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate Review Spec docs from SSOT JSON.")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    ap.add_argument(
        "--in", dest="in_path", default=None, help="SSOT JSON path (default: docs/reference/review/review_spec.v1.json)"
    )
    ap.add_argument(
        "--out",
        dest="out_path",
        default=None,
        help="Output Markdown path (default: docs/reference/review/REVIEW_SPEC.md)",
    )
    ap.add_argument("--check", action="store_true", help="Check if output is up-to-date (do not write).")
    ap.add_argument("--write", action="store_true", help="Write output file.")
    args = ap.parse_args(argv)

    if bool(args.check) == bool(args.write):
        print("[FAIL] must specify exactly one of --check or --write")
        return 2

    root = _repo_root(args.root)
    in_rel = args.in_path or "docs/reference/review/review_spec.v1.json"
    out_rel = args.out_path or "docs/reference/review/REVIEW_SPEC.md"
    in_p = (root / in_rel).resolve()
    out_p = (root / out_rel).resolve()
    print("[INFO] repo_root =", root)
    print("[INFO] in =", in_p)
    print("[INFO] out =", out_p)

    try:
        spec = _read_json(in_p)
        generated = _gen_md(spec)

        if args.check:
            if not out_p.exists():
                print(f"{out_p.as_posix()}:1:1: [FAIL] output does not exist; run with --write")
                return 2
            current = out_p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
            if current != generated:
                print(f"{out_p.as_posix()}:1:1: [FAIL] output is out-of-date; run with --write")
                return 2
            print("[PASS] Review Spec doc is up-to-date")
            return 0

        # --write
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(generated, encoding="utf-8", newline="\n")
        print("[PASS] wrote:", out_p.as_posix())
        return 0

    except SystemExit:
        raise
    except Exception as e:
        print("[ERROR]", repr(e))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
