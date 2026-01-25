#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

tools/check_doc_system_gate.py

目标：
- 对 Level 3 文档体系做最小门禁检查（链接/术语/front-matter）。
- 输出 Report v2（schema_version=2），可被统一渲染/聚合消费。

范围（默认）：
- 基于 docs/explanation/doc_map.json 的 docs 列表（Step1 inventory 产物）。
- 对 SSOT/入口文档更严格；对 archive/postmortem 以 warning 为主。

Windows CMD 示例：
python tools\check_doc_system_gate.py --root . --doc-map docs\explanation\doc_map.json --out data_processed\build_reports\doc_system_gate_report.json --md-out data_processed\build_reports\doc_system_gate_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# -------- constants --------

SEV = {
    "PASS": 0,
    "INFO": 10,
    "WARN": 20,
    "FAIL": 30,
    "ERROR": 40,
}

STRICT_FAIL_ROLES = {"reference", "runbook", "README"}
SOFT_WARN_ROLES = {"archive", "postmortem"}

REQUIRED_FM_FIELDS = ["title", "version", "last_updated", "timezone", "owner", "status"]

FORBIDDEN_TERM_PATTERNS = [
    (re.compile(r"index_stage\.json"), "index_stage.json"),
    (re.compile(r"index_state\.stage\.json(?!l)"), "index_state.stage.json"),
]

POLICY_RESET_TRIGGERS = ["policy=reset", "on-missing-state"]
POLICY_RESET_REQUIRED_PHRASES = ["默认评估", "最终生效"]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _strip_code(md_text: str) -> str:
    # Remove fenced code blocks and inline code spans to avoid false-positive link parsing.
    t = CODE_FENCE_RE.sub("", md_text)
    t = INLINE_CODE_RE.sub("", t)
    return t


# -------- helpers --------


def _iso_utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _posix(p: Path) -> str:
    return p.as_posix()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _find_first_line_col(text: str, needle: str) -> Tuple[int, int]:
    idx = text.find(needle)
    if idx < 0:
        return (1, 1)
    before = text[:idx]
    line = before.count("\n") + 1
    last_nl = before.rfind("\n")
    col = (idx - last_nl) if last_nl >= 0 else (idx + 1)
    return (line, col)


def _vscode_uri(abs_path: Path, line: int, col: int) -> str:
    # VS Code URI: vscode://file/<abs_path>:line:col
    # Use posix for stability; VS Code can open drive-letter paths in this format.
    return f"vscode://file/{_posix(abs_path)}:{line}:{col}"


def _github_anchor(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[^\w\u4e00-\u9fff\s\-]", "", t)
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"-+", "-", t).strip("-")
    return t


def _extract_headings(md_text: str) -> List[str]:
    anchors: List[str] = []
    for line in md_text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not m:
            continue
        anchors.append(_github_anchor(m.group(2)))
    return anchors


def _parse_front_matter(md_text: str) -> Dict[str, str]:
    if not md_text.startswith("---\n"):
        return {}
    end = md_text.find("\n---\n", 4)
    if end < 0:
        return {}
    block = md_text[4:end].splitlines()
    out: Dict[str, str] = {}
    for ln in block:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@dataclass
class DocInfo:
    path: str
    role: str
    action: str
    keyword_hit_count: int


def _load_doc_map(doc_map_path: Path) -> List[DocInfo]:
    obj = json.loads(_read_text(doc_map_path))
    docs: List[DocInfo] = []
    for d in obj.get("docs", []):
        p = str(d.get("path") or "").strip()
        role = str(d.get("role") or "").strip() or "guide"
        action = str(d.get("action") or "").strip() or "no_action"
        kh = d.get("keyword_hits") or {}
        hit_count = len(list(kh.keys())) if isinstance(kh, dict) else 0
        if p:
            docs.append(DocInfo(path=p, role=role, action=action, keyword_hit_count=int(hit_count)))
    return docs


def _classify_severity(role: str, base: str) -> str:
    if role in SOFT_WARN_ROLES and base in {"FAIL", "ERROR"}:
        return "WARN"
    if role in STRICT_FAIL_ROLES and base == "WARN":
        # keep WARN as WARN; strictness is handled per-check where needed
        return "WARN"
    return base


def _mk_item(
    tool: str, key: str, title: str, status: str, message: str, loc: str, loc_uri: str, detail: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "tool": tool,
        "key": key,
        "title": title,
        "status_label": status,
        "severity_level": SEV.get(status, 20),
        "message": message,
        "detail": detail,
        "loc": loc,
        "loc_uri": loc_uri,
    }


def _overall(counts: Dict[str, int]) -> Tuple[str, int]:
    if counts.get("ERROR", 0) > 0:
        return ("ERROR", 3)
    if counts.get("FAIL", 0) > 0:
        return ("FAIL", 2)
    if counts.get("WARN", 0) > 0:
        return ("WARN", 0)
    return ("PASS", 0)


# -------- checks --------


def check_front_matter(doc: DocInfo, abs_path: Path, text: str) -> List[Tuple[str, str]]:
    fm = _parse_front_matter(text)
    missing = [k for k in REQUIRED_FM_FIELDS if k not in fm]
    if not missing:
        return []
    base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
    status = _classify_severity(doc.role, base)
    msg = f"front-matter 缺字段: {', '.join(missing)}"
    return [(status, msg)]


def check_terms(doc: DocInfo, abs_path: Path, text: str) -> List[Tuple[str, str]]:
    issues: List[Tuple[str, str]] = []
    # NOTE:
    # - We intentionally scan per-line to allow a narrow exemption for explanatory lines.
    # - Some docs (including this tool's README) may mention a forbidden term *as an example* while
    #   also stating the correct term on the same line (e.g. "应为 ...jsonl").
    # - In that specific case, treating it as a violation would make the gate self-inconsistent.
    for pat, label in FORBIDDEN_TERM_PATTERNS:
        for line in text.splitlines():
            if not pat.search(line):
                continue
            # Exemption: same-line corrective guidance.
            # Keep this intentionally narrow to avoid hiding real regressions in code blocks.
            if ("应为" in line or "请使用" in line or "应使用" in line) and "index_state.stage.jsonl" in line:
                continue
            base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
            status = _classify_severity(doc.role, base)
            issues.append((status, f"禁止术语命中: {label}（请使用 index_state.stage.jsonl）"))
    return issues


def check_policy_reset_explain(doc: DocInfo, abs_path: Path, text: str) -> List[Tuple[str, str]]:
    if not any(k in text for k in POLICY_RESET_TRIGGERS):
        return []
    missing = [p for p in POLICY_RESET_REQUIRED_PHRASES if p not in text]
    if not missing:
        return []
    # 对入口更严格：reference/runbook/README 缺失视为 FAIL
    base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
    status = _classify_severity(doc.role, base)
    return [(status, f"policy=reset 解释缺口: 缺少 {', '.join(missing)}（需同时覆盖“默认评估/最终生效”两阶段）")]


def check_links(doc: DocInfo, abs_path: Path, text: str, root: Path) -> List[Tuple[str, str, str]]:
    """
    Return list of (status, message, needle_for_loc)
    """
    issues: List[Tuple[str, str, str]] = []
    headings = set(_extract_headings(text))
    scan_text = _strip_code(text)
    # allow duplicate anchors in github; we only check existence
    for m in LINK_RE.finditer(scan_text):
        target = m.group(1).strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:", "vscode://")):
            continue
        if target.startswith("#"):
            anchor = _github_anchor(target[1:])
            if anchor and anchor not in headings:
                base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
                status = _classify_severity(doc.role, base)
                issues.append((status, f"锚点不存在: {target}", target))
            continue

        # split anchor
        path_part, anchor_part = target, ""
        if "#" in target:
            path_part, anchor_part = target.split("#", 1)

        # ignore images / non-md
        if any(path_part.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
            continue
        # normalize
        ref_path = (abs_path.parent / path_part).resolve()
        if not str(ref_path).startswith(str(root.resolve())):
            # out-of-repo relative; warn
            base = "WARN" if doc.role not in STRICT_FAIL_ROLES else "WARN"
            status = _classify_severity(doc.role, base)
            issues.append((status, f"链接指向仓外路径（需审阅）: {target}", target))
            continue
        if not ref_path.exists():
            base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
            status = _classify_severity(doc.role, base)
            issues.append((status, f"链接文件不存在: {target}", target))
            continue
        if anchor_part:
            ref_text = _read_text(ref_path)
            ref_heads = set(_extract_headings(ref_text))
            anc = _github_anchor(anchor_part)
            if anc and anc not in ref_heads:
                base = "FAIL" if doc.role in STRICT_FAIL_ROLES else "INFO"
                status = _classify_severity(doc.role, base)
                issues.append((status, f"链接锚点不存在: {target}", target))
    return issues


# -------- main --------


def main() -> int:
    ap = argparse.ArgumentParser(description="Doc-system gate: links/terms/front-matter consistency (Report v2).")
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--doc-map", default="docs/explanation/doc_map.json", help="Step1 doc_map.json path")
    ap.add_argument(
        "--out", default="data_processed/build_reports/doc_system_gate_report.json", help="Report v2 JSON output"
    )
    ap.add_argument("--md-out", default="", help="Optional: Markdown output path")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    doc_map_path = (root / args.doc_map).resolve()
    if not doc_map_path.exists():
        print(f"[doc_system_gate] ERROR: doc_map not found: {doc_map_path}")
        return 3

    docs = _load_doc_map(doc_map_path)
    tool = "doc_system_gate"

    # scope: only docs related to WAL/resume terminology (keyword hits) plus SSOT/runbook anchors
    ALWAYS_INCLUDE = {
        "docs/reference/DOC_SYSTEM_SSOT.md",
        "docs/reference/build_chroma_cli_and_logs.md",
        "docs/reference/GLOSSARY_WAL_RESUME.md",
        "docs/reference/index_state_and_stamps.md",
        "docs/howto/OPERATION_GUIDE.md",
    }

    items: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {k: 0 for k in SEV.keys()}

    for d in docs:
        if d.keyword_hit_count <= 0 and d.path not in ALWAYS_INCLUDE:
            continue
        abs_path = (root / d.path).resolve()
        if not abs_path.exists():
            # treat missing doc file as FAIL for strict roles, WARN otherwise
            base = "FAIL" if d.role in STRICT_FAIL_ROLES else "WARN"
            status = _classify_severity(d.role, base)
            counts[status] = counts.get(status, 0) + 1
            loc = f"{d.path}:1:1"
            loc_uri = _vscode_uri(abs_path, 1, 1)
            items.append(
                _mk_item(
                    tool,
                    key=f"missing_file::{d.path}",
                    title="文档文件缺失",
                    status=status,
                    message=f"doc_map 指向的文件不存在：{d.path}",
                    loc=loc,
                    loc_uri=loc_uri,
                    detail={"role": d.role},
                )
            )
            continue

        text = _read_text(abs_path)

        # front-matter
        for status, msg in check_front_matter(d, abs_path, text):
            counts[status] = counts.get(status, 0) + 1
            line, col = 1, 1
            loc = f"{d.path}:{line}:{col}"
            loc_uri = _vscode_uri(abs_path, line, col)
            items.append(
                _mk_item(
                    tool, f"front_matter::{d.path}", "front-matter 校验", status, msg, loc, loc_uri, {"role": d.role}
                )
            )

        # forbidden terms
        for status, msg in check_terms(d, abs_path, text):
            needle = "index_stage.json" if "index_stage.json" in msg else "index_state.stage.json"
            line, col = _find_first_line_col(text, needle)
            counts[status] = counts.get(status, 0) + 1
            loc = f"{d.path}:{line}:{col}"
            loc_uri = _vscode_uri(abs_path, line, col)
            items.append(
                _mk_item(
                    tool,
                    f"terms::{needle}::{d.path}",
                    "术语一致性检查",
                    status,
                    msg,
                    loc,
                    loc_uri,
                    {"role": d.role, "term": needle},
                )
            )

        # policy reset explain
        for status, msg in check_policy_reset_explain(d, abs_path, text):
            needle = "policy=reset" if "policy=reset" in text else "on-missing-state"
            line, col = _find_first_line_col(text, needle)
            counts[status] = counts.get(status, 0) + 1
            loc = f"{d.path}:{line}:{col}"
            loc_uri = _vscode_uri(abs_path, line, col)
            items.append(
                _mk_item(
                    tool,
                    f"policy_reset::{d.path}",
                    "policy=reset 两阶段解释",
                    status,
                    msg,
                    loc,
                    loc_uri,
                    {"role": d.role},
                )
            )

        # links
        for status, msg, needle in check_links(d, abs_path, text, root):
            line, col = _find_first_line_col(text, needle)
            counts[status] = counts.get(status, 0) + 1
            loc = f"{d.path}:{line}:{col}"
            loc_uri = _vscode_uri(abs_path, line, col)
            items.append(
                _mk_item(
                    tool,
                    f"links::{d.path}::{needle}",
                    "仓内链接检查",
                    status,
                    msg,
                    loc,
                    loc_uri,
                    {"role": d.role, "target": needle},
                )
            )

    # PASS item (optional) if no issues
    if sum(v for k, v in counts.items() if k != "PASS") == 0:
        counts["PASS"] = 1
        items.append(
            _mk_item(
                tool,
                "ok",
                "文档门禁",
                "PASS",
                "未发现门禁问题。",
                "docs/explanation/doc_map.json:1:1",
                _vscode_uri(doc_map_path, 1, 1),
                {},
            )
        )

    overall_status, overall_rc = _overall(counts)

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": _iso_utc_now(),
        "tool": tool,
        "root": _posix(root),
        "summary": {
            "overall_status": overall_status,
            "overall_rc": overall_rc,
            "counts": {k: int(v) for k, v in counts.items() if int(v) > 0},
        },
        "items": sorted(items, key=lambda it: (it.get("severity_level", 20), it.get("title", ""), it.get("key", ""))),
        "meta": {
            "doc_map": _posix(doc_map_path),
            "scope": "keyword_hits_only + ALWAYS_INCLUDE",
            "strict_roles": sorted(list(STRICT_FAIL_ROLES)),
            "soft_roles": sorted(list(SOFT_WARN_ROLES)),
        },
    }

    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # optional markdown
    if args.md_out:
        md_path = (root / args.md_out).resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        # file-view: summary first, then most severe first
        inv = sorted(items, key=lambda it: (-it.get("severity_level", 20), it.get("title", ""), it.get("key", "")))
        lines = []
        lines.append(f"# doc_system_gate 报告（{overall_status}）")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- overall_status: `{overall_status}`")
        lines.append(f"- overall_rc: `{overall_rc}`")
        lines.append(f"- counts: `{report['summary']['counts']}`")
        lines.append("")
        lines.append("## Items（高严重度优先）")
        lines.append("")
        for it in inv:
            loc = it.get("loc", "")
            loc_uri = it.get("loc_uri", "")
            title = it.get("title", "")
            status = it.get("status_label", "")
            msg = it.get("message", "")
            link = f"[{loc}]({loc_uri})" if loc_uri else loc
            lines.append(f"- **{status}** {title} — {msg}  （{link}）")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # console: details from low->high, summary last (scroll-friendly)
    print(f"[doc_system_gate] tool={tool} root={_posix(root)} out={_posix(out_path)}")
    for it in report["items"]:
        print(f"[{it['status_label']}] {it['title']}: {it['message']} ({it['loc']})")
    print(f"[doc_system_gate] SUMMARY overall_status={overall_status} counts={report['summary']['counts']}")
    return int(overall_rc)


if __name__ == "__main__":
    raise SystemExit(main())
