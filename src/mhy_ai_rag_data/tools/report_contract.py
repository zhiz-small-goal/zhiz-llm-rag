#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_contract

统一报告契约（schema_version=2）与“写文件前转换”。

设计点
- item 模型是唯一对外口径（无迁移期）。
- 兼容仅发生在**写文件前**：允许旧脚本构造 legacy 结构，但落盘/渲染必须转成 v2。
- summary/明细排序要求由 view/排序模块控制；此处只负责结构与严重程度计算。

Item 模型（必填字段）
- tool: str
- title: str
- status_label: str
- severity_level: int
- message: str

可选字段（推荐）
- loc: "file:line:col" 或 list[str]
- loc_uri: vscode://file/...（建议由 report_order 自动补齐）
- duration_ms: int
- detail: any

严重程度
- 采用整数 severity_level（越大越严重）。
- 当 item 缺失 severity_level 时，仅在本模块内部做兜底映射；对外仍会补齐 severity_level。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


# v1.2 映射（仅兜底；对外必须显式给 severity_level）
DEFAULT_STATUS_TO_SEVERITY: Dict[str, int] = {
    # Fallback mapping (compat only)
    # Only these labels are allowed for implicit severity when `severity_level` is missing.
    # Any other label MUST provide an explicit `severity_level`.
    "PASS": 0,
    "INFO": 1,
    "WARN": 2,
    "FAIL": 3,
    "ERROR": 4,
}


def iso_now() -> str:
    # UTC Zulu
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm_label(label: Any) -> str:
    return str(label or "").strip().upper()


def status_label_to_severity_level(label: Any, *, default: int = 1) -> int:
    s = norm_label(label)
    if not s:
        return int(default)
    return int(DEFAULT_STATUS_TO_SEVERITY.get(s, default))


def _safe_int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


def ensure_item_fields(item: Dict[str, Any], *, tool_default: str) -> Dict[str, Any]:
    """Ensure required item fields exist and are correctly typed."""

    out = dict(item)
    out["tool"] = str(out.get("tool") or tool_default)
    out["title"] = str(out.get("title") or out.get("code") or out.get("id") or "")
    out["status_label"] = str(out.get("status_label") or out.get("status") or "INFO")

    sev = _safe_int(out.get("severity_level"))
    if sev is None:
        # fallback mapping is allowed ONLY for PASS/INFO/WARN/FAIL/ERROR
        lab = norm_label(out.get("status_label"))
        if lab in DEFAULT_STATUS_TO_SEVERITY:
            sev = int(DEFAULT_STATUS_TO_SEVERITY[lab])
        else:
            # Contract violation: unknown label without explicit severity_level
            sev = 4
            cv_msg = f"contract_violation: missing severity_level for status_label={lab or '(empty)'}"

            # Make the violation visible in the human message (markdown/console).
            base_msg = str(out.get("message") or out.get("msg") or "").strip()
            out["message"] = (base_msg + "\n" + cv_msg).strip() if base_msg else cv_msg
            det = out.get("detail")
            if isinstance(det, dict):
                det = dict(det)
            else:
                det = {"upstream_detail": det} if det is not None else {}
            det.setdefault("contract_violation", cv_msg)
            det.setdefault("original_status_label", out.get("status_label"))
            out["detail"] = det
    out["severity_level"] = int(sev)

    out["message"] = str(out.get("message") or out.get("msg") or "")

    # normalize optional fields
    if "duration_ms" in out and _safe_int(out.get("duration_ms")) is not None:
        out["duration_ms"] = int(out["duration_ms"])

    return out


@dataclass
class Summary:
    overall_status_label: str
    overall_rc: int
    max_severity_level: int
    counts: Dict[str, int]
    total_items: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status_label": self.overall_status_label,
            "overall_rc": self.overall_rc,
            "max_severity_level": self.max_severity_level,
            "counts": self.counts,
            "total_items": self.total_items,
        }


def compute_summary(items: List[Dict[str, Any]]) -> Summary:
    if not items:
        return Summary(
            overall_status_label="PASS",
            overall_rc=0,
            max_severity_level=0,
            counts={"PASS": 0},
            total_items=0,
        )

    max_sev = max(int(_safe_int(it.get("severity_level")) or 0) for it in items)

    counts: Dict[str, int] = {}
    any_error = False
    any_fail = False

    for it in items:
        lab = norm_label(it.get("status_label") or "INFO") or "INFO"
        counts[lab] = counts.get(lab, 0) + 1
        sev = int(_safe_int(it.get("severity_level")) or status_label_to_severity_level(lab))
        if lab in {"ERROR", "ERR", "EXCEPTION"} or sev >= 4:
            any_error = True
        elif lab in {"FAIL", "FAILED"} or sev >= 3:
            any_fail = True

    if any_error:
        overall = "ERROR"
        rc = 3
    elif any_fail:
        overall = "FAIL"
        rc = 2
    else:
        # 若存在 WARN/INFO/等，不强制失败
        overall = "PASS"
        rc = 0

    return Summary(
        overall_status_label=overall,
        overall_rc=rc,
        max_severity_level=max_sev,
        counts=counts,
        total_items=len(items),
    )


def _extract_tool_name(report: Mapping[str, Any]) -> str:
    for k in ("tool", "step"):
        v = report.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    run_meta = report.get("run_meta")
    if isinstance(run_meta, Mapping):
        v = run_meta.get("tool")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "report"


def _extract_root(report: Mapping[str, Any]) -> str:
    for k in ("root", "repo", "repo_root", "project_root"):
        v = report.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _extract_generated_at(report: Mapping[str, Any]) -> str:
    for k in ("generated_at", "timestamp", "ts"):
        v = report.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return iso_now()


def _items_from_errors(errors: Any, *, tool: str, status_label: str, severity_level: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(errors, list):
        return out
    for e in errors:
        if not isinstance(e, Mapping):
            continue
        code = str(e.get("code") or "")
        msg = str(e.get("message") or "")
        it = {
            "tool": tool,
            "title": code or status_label,
            "status_label": status_label,
            "severity_level": severity_level,
            "message": msg,
        }
        if "loc" in e:
            it["loc"] = e.get("loc")
        if "detail" in e:
            it["detail"] = e.get("detail")
        out.append(it)
    return out


def _items_from_gate_results(results: Any, *, tool: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(results, list):
        return out
    for r in results:
        if not isinstance(r, Mapping):
            continue
        step_id = str(r.get("id") or "")
        status = str(r.get("status") or "INFO")
        sev = status_label_to_severity_level(status)
        msg = f"rc={r.get('rc')} elapsed_ms={r.get('elapsed_ms')}"
        it = {
            "tool": tool,
            "title": step_id or "gate_step",
            "status_label": status,
            "severity_level": sev,
            "message": msg,
            "detail": dict(r),
        }
        out.append(it)
    return out


def _items_from_eval_cases(cases: Any, *, tool: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(cases, list):
        return out
    for c in cases:
        if not isinstance(c, Mapping):
            continue
        case_id = str(c.get("case_id") or c.get("id") or "")

        # retrieval eval
        if "hit_at_k" in c:
            hit = c.get("hit_at_k")
            status = "PASS" if hit is True else ("FAIL" if hit is False else "INFO")
            sev = 0 if hit is True else (3 if hit is False else 1)
            msg = f"hit_at_k={hit} bucket={c.get('bucket', '')}"
            it = {
                "tool": tool,
                "title": case_id or "case",
                "status_label": status,
                "severity_level": sev,
                "message": msg,
                "detail": dict(c),
            }
            out.append(it)
            continue

        # rag eval
        if "passed" in c:
            passed = c.get("passed")
            is_error = bool(c.get("error") or c.get("error_detail") or (c.get("llm_call_ok") is False))
            if is_error:
                status = "ERROR"
                sev = 4
            else:
                status = "PASS" if passed is True else ("FAIL" if passed is False else "INFO")
                sev = 0 if passed is True else (3 if passed is False else 1)
            msg = f"passed={passed} bucket={c.get('bucket', '')}"
            it = {
                "tool": tool,
                "title": case_id or "case",
                "status_label": status,
                "severity_level": sev,
                "message": msg,
                "detail": dict(c),
            }
            out.append(it)
            continue

        # generic fallback
        status = str(c.get("status") or "INFO")
        sev = status_label_to_severity_level(status)
        it = {
            "tool": tool,
            "title": case_id or "case",
            "status_label": status,
            "severity_level": sev,
            "message": str(c.get("message") or ""),
            "detail": dict(c),
        }
        out.append(it)

    return out


def ensure_report_v2(obj: Any) -> Dict[str, Any]:
    """Ensure top-level report uses schema_version=2.

    - If already looks like v2 (dict with schema_version==2 and has items+summary), it is normalized.
    - Otherwise converts best-effort legacy structures into v2.
    """

    if isinstance(obj, Mapping):
        sv = obj.get("schema_version")
        sv_i = _safe_int(sv)
        if sv_i == 2 and isinstance(obj.get("items"), list) and isinstance(obj.get("summary"), Mapping):
            tool = _extract_tool_name(obj)
            normalized_items = [
                ensure_item_fields(dict(it), tool_default=tool)
                for it in (obj.get("items") or [])
                if isinstance(it, Mapping)
            ]
            summary = compute_summary(normalized_items).to_dict()
            out: Dict[str, Any] = dict(obj)
            out["schema_version"] = 2
            out["tool"] = tool
            out["generated_at"] = _extract_generated_at(obj)
            out.setdefault("root", _extract_root(obj))
            out["items"] = normalized_items
            out["summary"] = summary
            return out

    # legacy conversion
    if not isinstance(obj, Mapping):
        tool = "report"
        error_items = [
            {
                "tool": tool,
                "title": "non_object_report",
                "status_label": "ERROR",
                "severity_level": 4,
                "message": "report is not a JSON object",
                "detail": {"type": str(type(obj))},
            }
        ]
        return {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": tool,
            "root": "",
            "summary": compute_summary(error_items).to_dict(),
            "items": error_items,
            "data": {"legacy": obj},
        }

    report = dict(obj)
    tool = _extract_tool_name(report)

    items: List[Dict[str, Any]] = []

    # 1) explicit items (legacy might already have items but without summary)
    raw_items = report.get("items")
    if isinstance(raw_items, list):
        for it in raw_items:
            if isinstance(it, Mapping):
                items.append(ensure_item_fields(dict(it), tool_default=tool))

    # 2) common legacy fields -> items
    if not items:
        # errors/warnings
        items.extend(_items_from_errors(report.get("errors"), tool=tool, status_label="ERROR", severity_level=4))
        items.extend(_items_from_errors(report.get("warnings"), tool=tool, status_label="WARN", severity_level=2))

        # gate-like results
        if report.get("results"):
            items.extend(_items_from_gate_results(report.get("results"), tool=tool))

        # eval-like cases
        if report.get("cases"):
            items.extend(_items_from_eval_cases(report.get("cases"), tool=tool))

        # if still empty: single summary item from status
        if not items:
            status = str(report.get("status") or "INFO")
            items.append(
                ensure_item_fields(
                    {
                        "tool": tool,
                        "title": tool,
                        "status_label": status,
                        "message": str(report.get("message") or ""),
                        "detail": dict(report),
                    },
                    tool_default=tool,
                )
            )

    items = [ensure_item_fields(it, tool_default=tool) for it in items]
    summary = compute_summary(items).to_dict()

    # keep legacy payload under data for audit/debug; avoid duplicating items/summary
    data: Dict[str, Any] = {}
    for k, v in report.items():
        if k in {"schema_version", "items", "summary"}:
            continue
        data[k] = v

    return {
        "schema_version": 2,
        "generated_at": _extract_generated_at(report),
        "tool": tool,
        "root": _extract_root(report),
        "summary": summary,
        "items": items,
        "data": data,
    }


def compact_json(obj: Any, *, limit: int = 1200) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(obj)
    if limit > 0 and len(s) > limit:
        return s[:limit] + "..."
    return s
