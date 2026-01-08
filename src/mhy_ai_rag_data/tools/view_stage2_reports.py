#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
view_stage2_reports_v2.py

目的：
- 汇总 Stage-2 常见输出文件（eval_cases / validation / retrieval / rag），给出关键指标与失败样本摘要
- 额外：把 “line=xx” 转成 VSCode 可点击的 `path:line` 形式，方便 Ctrl+Click 跳转

用法：
  python tools/view_stage2_reports_v2.py --root .
  python tools/view_stage2_reports_v2.py --root . --md-out data_processed/build_reports/stage2_summary.md

退出码：
  0: 成功汇总（即使评测 FAIL 也会输出汇总；“评测是否通过”看报告自身的 overall/指标字段）
  2: 关键输入文件缺失（无法汇总）
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def read_jsonl_cases(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except Exception:
            out.append({"_parse_error": True, "_raw": s})
    return out


def clip(s: str, n: int = 180) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "..."


def fmt_list(xs: List[str], max_n: int = 6) -> str:
    if not xs:
        return "[]"
    ys = xs[:max_n]
    extra = len(xs) - len(ys)
    if extra > 0:
        return "[" + ", ".join(ys) + f", ... +{extra} more]"
    return "[" + ", ".join(ys) + "]"


def vscode_loc(path: Path, line: Optional[int] = None) -> str:
    """
    生成 VSCode 终端常见可点击的定位格式：
    - file:line
    说明：Windows 下会出现盘符 "<REPO_ROOT>" 的 ":"，VSCode 仍能识别 `<REPO_ROOT>
    """
    if line is None:
        return str(path)
    return f"{path}:{line}"


def build_id_to_line(cases: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    将 eval_cases.jsonl 的 id 映射到“文件行号”（1-based）。
    注：这里的 line 指 jsonl 的第几行（与 validate 报告一致），不是源 md 文档行号。
    """
    m: Dict[str, int] = {}
    for idx, c in enumerate(cases, start=1):
        if c.get("_parse_error"):
            continue
        cid = str(c.get("id", "")).strip()
        if cid and cid not in m:
            m[cid] = idx
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--cases", default="data_processed/eval/eval_cases.jsonl", help="eval cases jsonl (relative to root)")
    ap.add_argument("--validation", default="data_processed/build_reports/eval_cases_validation.json", help="validation report json")
    ap.add_argument("--retrieval", default="data_processed/build_reports/eval_retrieval_report.json", help="retrieval eval report json")
    ap.add_argument("--rag", default="data_processed/build_reports/eval_rag_report.json", help="rag eval report json")
    ap.add_argument("--md-out", default="", help="optional: write a markdown summary file")
    ap.add_argument("--show-fails", type=int, default=5, help="how many failing cases to show per report")
    args = ap.parse_args()

    root = Path(args.root).resolve()

    cases_path = (root / args.cases).resolve()
    val_path = (root / args.validation).resolve()
    ret_path = (root / args.retrieval).resolve()
    rag_path = (root / args.rag).resolve()

    cases = read_jsonl_cases(cases_path)
    val = read_json(val_path)
    ret = read_json(ret_path)
    rag = read_json(rag_path)

    missing = []
    if cases is None:
        missing.append(str(cases_path))
    if val is None:
        missing.append(str(val_path))

    if missing:
        print("[stage2_summary] FAIL: missing required file(s):")
        for m in missing:
            print(" - " + m)
        return 2

    id2line = build_id_to_line(cases)

    lines: List[str] = []
    lines.append("# Stage-2 报告汇总\n\n")
    lines.append(f"- 生成时间：`{now_iso()}`\n")
    lines.append(f"- root：`{root}`\n\n")

    # cases
    total_lines = len(cases)
    parse_errors = sum(1 for c in cases if c.get("_parse_error"))
    ok_cases = total_lines - parse_errors
    lines.append("## 1) 用例集（eval_cases.jsonl）\n")
    lines.append(f"- 路径：`{cases_path}`\n")
    lines.append(f"- 行数：{total_lines}（可解析用例：{ok_cases}，解析错误行：{parse_errors}）\n")
    if ok_cases:
        sample = next((c for c in cases if not c.get("_parse_error")), None)
        if sample:
            lines.append("- 样例字段：`id/query/expected_sources/must_include/tags`\n")
            lines.append(f"- 样例 id：`{sample.get('id','')}`\n")

    # validation
    lines.append("\n## 2) 用例集门禁（eval_cases_validation.json）\n")
    lines.append(f"- 路径：`{val_path}`\n")
    lines.append(f"- overall：`{val.get('overall')}`\n")
    counts = val.get("counts") or {}
    lines.append(f"- 统计：errors={counts.get('errors')}  warnings={counts.get('warnings')}  cases={counts.get('cases')}\n")
    errs = val.get("errors") or []
    warns = val.get("warnings") or []
    if errs:
        lines.append(f"- 主要 errors（前 {args.show_fails} 条；含可点击定位）：\n")
        for e in errs[: args.show_fails]:
            line_no = e.get("line")
            loc = vscode_loc(cases_path, int(line_no)) if isinstance(line_no, int) else vscode_loc(cases_path)
            lines.append(f"  - {loc}  {json.dumps(e, ensure_ascii=False)}\n")
    if warns:
        lines.append(f"- 主要 warnings（前 {args.show_fails} 条；含可点击定位）：\n")
        for w in warns[: args.show_fails]:
            line_no = w.get("line")
            loc = vscode_loc(cases_path, int(line_no)) if isinstance(line_no, int) else vscode_loc(cases_path)
            lines.append(f"  - {loc}  {json.dumps(w, ensure_ascii=False)}\n")

    # retrieval
    lines.append("\n## 3) 检索回归（eval_retrieval_report.json）\n")
    if ret is None:
        lines.append("- 未发现该报告：说明你尚未运行 `run_eval_retrieval.py`，或输出路径不同。\n")
    else:
        lines.append(f"- 路径：`{ret_path}`\n")
        metrics = ret.get("metrics") or {}
        lines.append(f"- hit_rate：{metrics.get('hit_rate')}\n")
        buckets = ret.get("buckets") or {}
        if isinstance(buckets, dict) and buckets:
            lines.append("- buckets（分桶指标）：\n")
            for b in sorted(buckets.keys()):
                st = buckets.get(b) or {}
                lines.append(f"  - {b}: cases={st.get('cases')} hit_cases={st.get('hit_cases')} hit_rate={st.get('hit_rate')}\n")
        cases_ret = ret.get("cases") or []
        fail_cases = [c for c in cases_ret if not c.get("hit_at_k")]
        lines.append(f"- 用例数：{len(cases_ret)}，未命中：{len(fail_cases)}\n")
        if fail_cases:
            lines.append(f"- 未命中样例（前 {args.show_fails} 条；含可点击定位）：\n")
            for c in fail_cases[: args.show_fails]:
                cid = str(c.get("id",""))
                line_no = id2line.get(cid)
                loc = vscode_loc(cases_path, line_no) if line_no else vscode_loc(cases_path)
                topk = c.get("topk") or []
                srcs: List[str] = []
                for t in topk[:3]:
                    srcs.append(str(t.get("source","")))
                lines.append(f"  - {loc}  id={cid}  query={clip(str(c.get('query','')))}\n")
                lines.append(f"    expected={fmt_list([str(x) for x in (c.get('expected_sources') or [])])}\n")
                lines.append(f"    top_sources={fmt_list(srcs)}\n")

    # rag
    lines.append("\n## 4) 端到端回归（eval_rag_report.json）\n")
    if rag is None:
        lines.append("- 未发现该报告：说明你尚未运行 `run_eval_rag.py`，或输出路径不同。\n")
    else:
        lines.append(f"- 路径：`{rag_path}`\n")
        metrics = rag.get("metrics") or {}
        lines.append(f"- pass_rate：{metrics.get('pass_rate')}\n")
        cases_rag = rag.get("cases") or []
        fail_cases = [c for c in cases_rag if not c.get("passed")]
        lines.append(f"- 用例数：{len(cases_rag)}，未通过：{len(fail_cases)}\n")
        if fail_cases:
            lines.append(f"- 未通过样例（前 {args.show_fails} 条；含可点击定位）：\n")
            for c in fail_cases[: args.show_fails]:
                cid = str(c.get("id",""))
                line_no = id2line.get(cid)
                loc = vscode_loc(cases_path, line_no) if line_no else vscode_loc(cases_path)
                lines.append(f"  - {loc}  id={cid}  query={clip(str(c.get('query','')))}\n")
                lines.append(f"    missing={fmt_list([str(x) for x in (c.get('missing') or [])])}\n")
                lines.append(f"    answer_snippet={clip(str(c.get('answer','')), 220)}\n")

    md = "".join(lines)
    print(md)

    if args.md_out:
        out_path = Path(args.md_out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"\n[stage2_summary] wrote markdown: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
