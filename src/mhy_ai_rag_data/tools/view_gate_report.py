#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.view_gate_report

人类入口渲染器：从 gate_report.json（schema_version=2，item 模型）生成：
- 控制台输出：detail 轻->重；summary 在末尾；整体以 \n\n 结尾。
- Markdown 文件：summary 在顶部；detail 重->轻；关键路径/定位使用可点击的 VS Code 链接。

约束（无迁移期）
- 仅接受 schema_version=2。
- Markdown 中必须显式输出 `vscode://file/...`（或 `vscode-insiders://file/...`）链接，
  不能只在 code block 里输出纯字符串路径（VS Code 不保证可点击）。

注意：本脚本只渲染，不改动原 report 内容。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mhy_ai_rag_data.tools.vscode_links import to_vscode_file_uri, to_vscode_file_uri_from_path


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("report must be a JSON object")
    return obj


def _as_list_str(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _clip(s: str, n: int = 160) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else (s[:n] + "...")


def _stable_sorted_items(items: List[Dict[str, Any]], *, asc: bool) -> List[Tuple[int, int, Dict[str, Any]]]:
    out: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, it in enumerate(items):
        sevs = it.get("severity_level")
        if sevs is None:
            sev_i = 1
        else:
            try:
                sev_i = int(sevs)
            except Exception:
                sev_i = 1
        out.append((sev_i, idx, it))
    out.sort(key=lambda t: (t[0], t[1]), reverse=not asc)
    return out


def _md_link(display_text: str, uri: str) -> str:
    display_text = (display_text or "").strip()
    uri = (uri or "").strip()
    if not display_text:
        display_text = uri
    if display_text and uri:
        return f"[{display_text}]({uri})"
    return display_text or uri


def _md_link_path(p: Path, *, line: int = 1, col: int = 1) -> str:
    try:
        abs_posix = p.resolve().as_posix()
    except Exception:
        abs_posix = p.as_posix()
    uri = to_vscode_file_uri(abs_posix, line=line, col=col)
    return _md_link(abs_posix, uri)


_LOC_RSPLIT = re.compile(r"^(?P<path>.+):(?P<line>\d+):(?P<col>\d+)$")


def _try_build_loc_uri_from_loc(loc: Any, *, root: Path) -> str:
    """从 `file:line:col` 推导 vscode://file URI。

    兼容 Windows 盘符（d:/...）与相对路径。
    """

    loc_list = _as_list_str(loc)
    if not loc_list:
        return ""

    m = _LOC_RSPLIT.match(loc_list[0].strip())
    if not m:
        return ""

    path_s = (m.group("path") or "").strip()
    try:
        line = int(m.group("line"))
        col = int(m.group("col"))
    except Exception:
        return ""

    # 若为相对路径，按 root 解析成绝对路径
    p = Path(path_s)
    if not p.is_absolute():
        p = (root / p).resolve()

    return to_vscode_file_uri_from_path(p, line=line, col=col)


def _fmt_loc_md(loc: Any, loc_uri: Any, *, root: Path) -> str:
    loc_s = ", ".join(_as_list_str(loc))
    uri_s = ", ".join(_as_list_str(loc_uri))

    # 若 loc_uri 缺失但 loc 是 file:line:col，尝试推导
    if loc_s and not uri_s:
        uri_s = _try_build_loc_uri_from_loc(loc_s, root=root)

    if loc_s and uri_s:
        # 在 md 中保持 loc 为可复制文本，同时作为链接文字
        return _md_link(loc_s, uri_s)
    return loc_s


def _extract_log_path_from_detail(detail: Any) -> str:
    if isinstance(detail, dict):
        v = detail.get("log_path") or detail.get("log")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _render_console(report: Dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    items = report.get("items") or []
    if not isinstance(items, list):
        items = []

    lines: List[str] = []
    lines.append(
        f"[gate_report] tool={report.get('tool', '')} root={report.get('root', '')} generated_at={report.get('generated_at', '')}\n\n"
    )

    # detail: 轻->重（滚屏友好：越严重越靠后）
    for sev, _idx, it in _stable_sorted_items(items, asc=True):
        lab = str(it.get("status_label") or "INFO").upper()
        title = str(it.get("title") or "")
        msg = str(it.get("message") or "")
        loc = ", ".join(_as_list_str(it.get("loc")))
        header = f"[{lab}] (sev={sev}) {title}"
        lines.append(header + "\n")
        if msg:
            lines.append("  " + _clip(msg, 400) + "\n")
        if loc:
            lines.append("  loc: " + loc + "\n")
        log_path = _extract_log_path_from_detail(it.get("detail"))
        if log_path:
            lines.append("  log: " + log_path + "\n")
        # 每条 detail 之间 1 行空行
        lines.append("\n")

    # summary: 在末尾
    counts = summary.get("counts") or {}
    if not isinstance(counts, dict):
        counts = {}
    max_sev = summary.get("max_severity_level")
    total_items = summary.get("total_items")
    overall = summary.get("overall_status_label")
    rc = summary.get("overall_rc")

    lines.append("[summary]\n")
    lines.append(f"  overall: {overall} (rc={rc})\n")
    lines.append(f"  max_severity_level: {max_sev}\n")
    lines.append(f"  total_items: {total_items}\n")

    # counts 输出：保持稳定，并更贴近严重度递增阅读
    preferred = ["PASS", "INFO", "WARN", "WARNING", "FAIL", "ERROR"]
    seen = set()
    for k in preferred:
        if k in counts and k not in seen:
            lines.append(f"  count[{k}]: {counts.get(k)}\n")
            seen.add(k)
    for k in sorted(counts.keys()):
        if k in seen:
            continue
        lines.append(f"  count[{k}]: {counts.get(k)}\n")

    # 控制台末尾额外空行（整体以 \n\n 结尾）
    if not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append("\n")
    return "".join(lines)


def _render_markdown(report: Dict[str, Any], *, report_path: Path, root: Path) -> str:
    summary = report.get("summary") or {}
    items = report.get("items") or []
    if not isinstance(items, list):
        items = []

    lines: List[str] = []
    lines.append("# Gate report\n\n")

    # 顶部元信息：显式可点击路径
    lines.append(f"- generated_at: `{report.get('generated_at', '')}`\n")
    lines.append(f"- tool: `{report.get('tool', '')}`\n")
    lines.append(f"- root: `{report.get('root', '')}`\n")

    # report_path 必须可点击（不能只放反引号）
    lines.append(f"- report_path: {_md_link_path(report_path)}\n")

    lines.append(f"- overall: `{summary.get('overall_status_label', '')}` (rc={summary.get('overall_rc', '')})\n")
    lines.append(f"- max_severity_level: `{summary.get('max_severity_level', '')}`\n")
    lines.append(f"- total_items: `{summary.get('total_items', '')}`\n")

    counts = summary.get("counts") or {}
    if isinstance(counts, dict) and counts:
        lines.append("\n## Summary counts\n")
        preferred = ["ERROR", "FAIL", "WARN", "WARNING", "INFO", "PASS"]
        seen = set()
        for k in preferred:
            if k in counts and k not in seen:
                lines.append(f"- {k}: {counts.get(k)}\n")
                seen.add(k)
        for k in sorted(counts.keys()):
            if k in seen:
                continue
            lines.append(f"- {k}: {counts.get(k)}\n")

    lines.append("\n## Details\n")

    # detail: 重->轻（文件阅读优先异常）
    for sev, _idx, it in _stable_sorted_items(items, asc=False):
        lab = str(it.get("status_label") or "INFO").upper()
        title = str(it.get("title") or "")
        msg = str(it.get("message") or "")
        loc_md = _fmt_loc_md(it.get("loc"), it.get("loc_uri"), root=root)

        lines.append(f"### [{lab}] (sev={sev}) {title}\n\n")

        if msg:
            lines.append(f"- message: {_clip(msg, 600)}\n")

        # 若 detail 中包含 log_path，必须显式输出可点击链接（不能只藏在 JSON 中）
        log_path = _extract_log_path_from_detail(it.get("detail"))
        if log_path:
            uri = to_vscode_file_uri(log_path, line=1, col=1)
            lines.append(f"- log_path: {_md_link(log_path, uri)}\n")

        if loc_md:
            lines.append(f"- loc: {loc_md}\n")

        # detail 保留在 JSON block 以便追溯（允许长内容）；但关键路径已在正文层可点击
        detail = it.get("detail")
        if detail is not None:
            try:
                detail_json = json.dumps(detail, ensure_ascii=False, indent=2)
                lines.append("- detail:\n\n```json\n")
                lines.append(detail_json)
                lines.append("\n```\n")
            except Exception:
                pass

        lines.append("\n")

    lines.append(f"\n- generated_by: view_gate_report ({now_iso()})\n")
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render gate_report.json (schema_version=2)")
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument(
        "--report",
        default="data_processed/build_reports/gate_report.json",
        help="gate_report.json path (relative to root)",
    )
    ap.add_argument("--md-out", default="", help="optional markdown output path")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve()

    try:
        report = _load_json(report_path)
    except Exception as e:
        print(f"[gate_report] FAIL: cannot read report: {report_path} :: {e}")
        return 2

    if int(report.get("schema_version") or 0) != 2:
        print(f"[gate_report] FAIL: schema_version!=2: {report.get('schema_version')}")
        return 2

    # 控制台输出（滚屏友好）
    console = _render_console(report)
    print(console, end="")

    # 可选：落盘 md（summary 顶部、重->轻、关键路径可点击）
    if args.md_out:
        out_path = Path(args.md_out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        md = _render_markdown(report, report_path=report_path, root=root)
        out_path.write_text(md, encoding="utf-8")
        print(f"[gate_report] wrote markdown: {out_path.as_posix()}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
