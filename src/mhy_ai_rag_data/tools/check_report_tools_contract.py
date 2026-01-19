#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_report_tools_contract

Static gate for Report Output v2 tool coverage:
- Parse coverage registry: docs/reference/report_tools_registry.toml
- Extract REPORT_TOOL_META from tool modules via AST (no imports, no side effects)
- Compare registry <-> meta bidirectionally

This tool writes a v2 report bundle (report.json + report.md + console rendering).
"""

from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, iso_now


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "check_report_tools_contract",
    "kind": "VERIFY_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": False,
    "entrypoint": "python tools/check_report_tools_contract.py",
}


_ALLOWED_KINDS = {
    # baseline kinds from planning
    "CHECK_REPORT",
    "INDEX_REPORT",
    "STATE_REPORT",
    "EVAL_REPORT",
    "GATE_REPORT",
    # helper kinds (still v2 outputs)
    "VERIFY_REPORT",
    "RENDER_REPORT",
}

_ALLOWED_CHANNELS = {"console", "file", "events", "checkpoint"}


@dataclass(frozen=True)
class RegistryTool:
    id: str
    module: str
    kind: str
    contract_version: int
    entrypoint: str
    channels: List[str]
    high_cost: bool
    supports_selftest: bool


def _read_toml(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if tomllib is None:
        return None, "tomllib_unavailable"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None, "toml_root_not_object"
        return data, None
    except Exception as e:  # noqa: BLE001
        return None, f"toml_parse_error: {type(e).__name__}: {e}"


def _extract_report_tool_meta(module_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extract REPORT_TOOL_META dict without importing the module."""

    try:
        src = module_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return None, f"read_error: {type(e).__name__}: {e}"

    try:
        tree = ast.parse(src, filename=str(module_path))
    except SyntaxError as e:
        return None, f"syntax_error: {e.msg}"

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "REPORT_TOOL_META":
                    try:
                        val = ast.literal_eval(node.value)
                        if isinstance(val, dict):
                            return val, None
                        return None, "meta_not_dict"
                    except Exception as e:  # noqa: BLE001
                        return None, f"meta_not_literal: {type(e).__name__}: {e}"
    return None, "meta_missing"


def _as_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    return None


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


def _as_str(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _as_str_list(v: Any) -> Optional[List[str]]:
    if not isinstance(v, list):
        return None
    out: List[str] = []
    for x in v:
        s = _as_str(x)
        if s is None:
            return None
        out.append(s)
    return out


def _load_registry(registry_path: Path) -> Tuple[Dict[str, RegistryTool], List[Dict[str, Any]]]:
    """Return (by_id, items). Items are v2 items for problems."""

    items: List[Dict[str, Any]] = []
    by_id: Dict[str, RegistryTool] = {}

    data, err = _read_toml(registry_path)
    if err:
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "registry_read_failed",
                    "title": "registry read failed",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": err,
                    "loc": f"{registry_path.as_posix()}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return by_id, items

    tools = data.get("tool") if isinstance(data, dict) else None
    if not isinstance(tools, list):
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "registry_missing_tool_list",
                    "title": "registry missing [[tool]] list",
                    "status_label": "ERROR",
                    "severity_level": 4,
                    "message": "expected TOML key: [[tool]]",
                    "loc": f"{registry_path.as_posix()}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )
        return by_id, items

    for idx, raw in enumerate(tools):
        if not isinstance(raw, dict):
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_tool_not_object:{idx}",
                        "title": "registry tool entry not object",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"entry #{idx} is {type(raw).__name__}, expected object",
                        "loc": f"{registry_path.as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        tid = _as_str(raw.get("id"))
        module = _as_str(raw.get("module"))
        kind = _as_str(raw.get("kind"))
        cv = _as_int(raw.get("contract_version"))
        entrypoint = _as_str(raw.get("entrypoint"))
        channels = _as_str_list(raw.get("channels"))
        high_cost = _as_bool(raw.get("high_cost"))
        supports_selftest = _as_bool(raw.get("supports_selftest"))

        missing = [
            n
            for n, v in (
                ("id", tid),
                ("module", module),
                ("kind", kind),
                ("contract_version", cv),
                ("entrypoint", entrypoint),
                ("channels", channels),
                ("high_cost", high_cost),
                ("supports_selftest", supports_selftest),
            )
            if v is None
        ]
        if missing:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_tool_missing_fields:{idx}",
                        "title": "registry tool entry missing/invalid fields",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"missing/invalid: {', '.join(missing)}",
                        "loc": f"{registry_path.as_posix()}:1:1",
                        "detail": {"entry": raw},
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        assert tid and module and kind and cv is not None and entrypoint and channels is not None
        assert high_cost is not None and supports_selftest is not None

        if tid in by_id:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_duplicate_id:{tid}",
                        "title": "registry duplicate id",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"duplicate id in registry: {tid}",
                        "loc": f"{registry_path.as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        if kind not in _ALLOWED_KINDS:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_invalid_kind:{tid}",
                        "title": "registry invalid kind",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"kind={kind} not in allowed kinds",
                        "loc": f"{registry_path.as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )

        bad_channels = [c for c in channels if c not in _ALLOWED_CHANNELS]
        if bad_channels:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"registry_invalid_channels:{tid}",
                        "title": "registry invalid channels",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"unknown channels: {bad_channels}",
                        "loc": f"{registry_path.as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )

        by_id[tid] = RegistryTool(
            id=tid,
            module=module,
            kind=kind,
            contract_version=int(cv),
            entrypoint=entrypoint,
            channels=channels,
            high_cost=bool(high_cost),
            supports_selftest=bool(supports_selftest),
        )

    return by_id, items


def _scan_meta(*, repo_root: Path, scan_dir: Path) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    items: List[Dict[str, Any]] = []
    metas: Dict[str, Dict[str, Any]] = {}

    for p in sorted(scan_dir.glob("*.py")):
        meta, err = _extract_report_tool_meta(p)
        if err == "meta_missing":
            continue
        rel = p.relative_to(repo_root).as_posix()

        if err:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_parse_failed:{rel}",
                        "title": "REPORT_TOOL_META parse failed",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": err,
                        "loc": f"{rel}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        assert meta is not None
        tid = _as_str(meta.get("id"))
        if not tid:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_missing_id:{rel}",
                        "title": "REPORT_TOOL_META missing id",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "REPORT_TOOL_META.id missing/invalid",
                        "loc": f"{rel}:1:1",
                        "detail": {"meta": meta},
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        if tid in metas:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"meta_duplicate_id:{tid}",
                        "title": "REPORT_TOOL_META duplicate id",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": f"duplicate id across modules: {tid}",
                        "loc": f"{rel}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        metas[tid] = {"meta": meta, "path": rel}

    return metas, items


def _compare(reg: RegistryTool, meta: Mapping[str, Any]) -> List[str]:
    mismatches: List[str] = []

    def _cmp(k: str, want: Any) -> None:
        got = meta.get(k)
        if got != want:
            mismatches.append(f"{k}: registry={want!r} meta={got!r}")

    _cmp("id", reg.id)
    _cmp("kind", reg.kind)
    _cmp("contract_version", reg.contract_version)
    _cmp("entrypoint", reg.entrypoint)
    _cmp("high_cost", reg.high_cost)
    _cmp("supports_selftest", reg.supports_selftest)

    # channels: compare as sets (order not important)
    got_ch = meta.get("channels")
    if isinstance(got_ch, list):
        got_set = {str(x) for x in got_ch}
        want_set = set(reg.channels)
        if got_set != want_set:
            mismatches.append(f"channels: registry={sorted(want_set)!r} meta={sorted(got_set)!r}")
    else:
        mismatches.append(f"channels: registry={reg.channels!r} meta={got_ch!r}")

    return mismatches


def _rc_from_summary(summary: Mapping[str, Any]) -> int:
    try:
        return int(summary.get("overall_rc", 0))
    except Exception:
        return 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Check report tools contract coverage (registry <-> REPORT_TOOL_META).")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument(
        "--registry",
        default="docs/reference/report_tools_registry.toml",
        help="Coverage SSOT registry (TOML)",
    )
    ap.add_argument(
        "--scan-dir",
        default="src/mhy_ai_rag_data/tools",
        help="Directory to scan for tool modules (REPORT_TOOL_META)",
    )
    ap.add_argument(
        "--out",
        default="data_processed/build_reports/check_report_tools_contract.json",
        help="Report JSON output path",
    )
    ap.add_argument("--mode", default="static", choices=["static"], help="static only in this milestone")
    ap.add_argument(
        "--strict",
        default="false",
        help="true/false: missing registry<->meta entries are FAIL (otherwise WARN)",
    )

    args = ap.parse_args()

    repo_root = Path(args.root).resolve()
    registry_path = (
        (repo_root / args.registry).resolve() if not Path(args.registry).is_absolute() else Path(args.registry)
    )
    scan_dir = (repo_root / args.scan_dir).resolve() if not Path(args.scan_dir).is_absolute() else Path(args.scan_dir)
    out_json = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    strict = str(args.strict).strip().lower() in {"1", "true", "yes", "y", "on"}

    items: List[Dict[str, Any]] = []

    # 1) registry
    reg_by_id, reg_items = _load_registry(registry_path)
    items.extend(reg_items)

    # 2) scan meta
    metas_by_id, meta_items = _scan_meta(repo_root=repo_root, scan_dir=scan_dir)
    items.extend(meta_items)

    # If registry is unreadable, stop early.
    if any(it.get("key") == "registry_read_failed" and it.get("status_label") == "ERROR" for it in items):
        report = {
            "schema_version": 2,
            "generated_at": iso_now(),
            "tool": "check_report_tools_contract",
            "root": repo_root.as_posix(),
            "items": items,
            "summary": compute_summary(items).to_dict(),
            "data": {"mode": "static", "strict": strict, "registry": registry_path.as_posix()},
        }
        normalized = write_report_bundle(
            report=report,
            report_json=out_json,
            repo_root=repo_root,
            console_title="check_report_tools_contract",
        )
        return _rc_from_summary(normalized.get("summary", {}))

    # 3) registry -> meta
    for tid, reg in sorted(reg_by_id.items()):
        found = metas_by_id.get(tid)
        if not found:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"tool_missing_meta:{tid}",
                        "title": "tool missing REPORT_TOOL_META",
                        "status_label": "FAIL" if strict else "WARN",
                        "severity_level": 3 if strict else 2,
                        "message": f"registry has tool id={tid} but module has no REPORT_TOOL_META (or was not found during scan)",
                        "detail": {"module": reg.module, "entrypoint": reg.entrypoint},
                        "loc": f"{registry_path.relative_to(repo_root).as_posix()}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )
            continue

        meta = found["meta"]
        mism = _compare(reg, meta)
        if mism:
            items.append(
                ensure_item_fields(
                    {
                        "tool": "check_report_tools_contract",
                        "key": f"tool_meta_mismatch:{tid}",
                        "title": "registry/meta mismatch",
                        "status_label": "FAIL",
                        "severity_level": 3,
                        "message": "; ".join(mism[:6]),
                        "detail": {"mismatches": mism, "module": reg.module, "path": found.get("path")},
                        "loc": f"{found.get('path')}:1:1",
                    },
                    tool_default="check_report_tools_contract",
                )
            )

    # 4) meta -> registry
    for tid, found in sorted(metas_by_id.items()):
        if tid in reg_by_id:
            continue
        status = "FAIL" if strict else "WARN"
        sev = 3 if strict else 2
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": f"tool_missing_registry:{tid}",
                    "title": "tool missing registry entry",
                    "status_label": status,
                    "severity_level": sev,
                    "message": f"module defines REPORT_TOOL_META.id={tid} but registry has no matching entry",
                    "detail": {"path": found.get("path"), "meta": found.get("meta")},
                    "loc": f"{found.get('path')}:1:1",
                },
                tool_default="check_report_tools_contract",
            )
        )

    # 5) success sentinel
    if not any(str(it.get("status_label")).upper() in {"FAIL", "ERROR"} for it in items):
        items.append(
            ensure_item_fields(
                {
                    "tool": "check_report_tools_contract",
                    "key": "ok",
                    "title": "registry/meta consistent",
                    "status_label": "PASS",
                    "severity_level": 0,
                    "message": f"checked registry={registry_path.relative_to(repo_root).as_posix()} vs meta scan_dir={scan_dir.relative_to(repo_root).as_posix()}",
                },
                tool_default="check_report_tools_contract",
            )
        )

    report = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": "check_report_tools_contract",
        "root": repo_root.as_posix(),
        "items": items,
        "summary": compute_summary(items).to_dict(),
        "data": {
            "mode": "static",
            "strict": strict,
            "registry": registry_path.relative_to(repo_root).as_posix()
            if registry_path.is_absolute()
            else str(registry_path),
            "scan_dir": scan_dir.relative_to(repo_root).as_posix() if scan_dir.is_absolute() else str(scan_dir),
            "env": {"python": os.environ.get("PYTHON", ""), "cwd": os.getcwd()},
        },
    }

    normalized = write_report_bundle(
        report=report,
        report_json=out_json,
        repo_root=repo_root,
        console_title="check_report_tools_contract",
    )
    return _rc_from_summary(normalized.get("summary", {}))


if __name__ == "__main__":
    raise SystemExit(main())
