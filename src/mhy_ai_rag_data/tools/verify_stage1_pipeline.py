#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_stage1_pipeline.py

Stage-1 regression/acceptance checks for:
- data_processed artifacts (text_units, chunk_plan)
- Chroma persistent DB (optional, if chromadb installed)
- LLM OpenAI-compatible endpoint probe (optional, if requests installed)

Usage:
  python verify_stage1_pipeline.py --root . --db chroma_db --collection rag_chunks --base-url http://localhost:8000/v1 --timeout 10

Notes:
- Designed to be platform-agnostic (Windows/Linux).
- Produces a JSON report at: <root>/data_processed/build_reports/stage1_verify.json
"""

from __future__ import annotations


import argparse
import importlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "verify_stage1_pipeline",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": False,
    "entrypoint": "python tools/verify_stage1_pipeline.py",
}


# 兼容两种运行方式：python -m tools.verify_stage1_pipeline 以及 python tools/verify_stage1_pipeline.py
try:
    _llm_http_client = importlib.import_module("mhy_ai_rag_data.tools.llm_http_client")
except Exception:  # noqa: BLE001
    _llm_http_client = importlib.import_module("llm_http_client")
resolve_trust_env = _llm_http_client.resolve_trust_env
get_session = _llm_http_client.get_session


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_jsonl_lines(path: Path, max_scan: int = 2_000_000) -> int:
    # Efficient line count without loading whole file.
    n = 0
    with path.open("rb") as f:
        for _ in f:
            n += 1
            if n >= max_scan:
                break
    return n


def check_required_files(root: Path) -> Tuple[bool, Dict[str, Any]]:
    required = [
        root / "data_processed" / "text_units.jsonl",
        root / "data_processed" / "chunk_plan.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    ok = len(missing) == 0
    details: Dict[str, Any] = {"required": [str(p) for p in required], "missing": missing}
    if ok:
        # quick sanity stats
        details["text_units_lines"] = count_jsonl_lines(required[0])
        try:
            plan = read_json(required[1])
            # We assume chunk_plan.json is either {"chunks":[...]} or a list
            if isinstance(plan, dict) and "chunks" in plan and isinstance(plan["chunks"], list):
                details["planned_chunks"] = len(plan["chunks"])
            elif isinstance(plan, list):
                details["planned_chunks"] = len(plan)
            else:
                details["planned_chunks"] = None
                details["chunk_plan_shape"] = type(plan).__name__
        except Exception as e:
            ok = False
            details["chunk_plan_error"] = f"{type(e).__name__}: {e}"
    return ok, details


def check_chroma_counts(root: Path, db: str, collection: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Optional check:
    - Connect to Chroma persistent client at <root>/<db>
    - Compare collection.count() with planned_chunks from chunk_plan.json
    """
    details: Dict[str, Any] = {"enabled": False}
    db_path = (root / db).resolve()
    if not db_path.exists():
        return False, {"enabled": False, "reason": f"db path not found: {db_path}"}

    try:
        import chromadb
    except Exception as e:
        return False, {"enabled": False, "reason": f"chromadb import failed: {type(e).__name__}: {e}"}

    details["enabled"] = True
    details["db_path"] = str(db_path)
    details["collection"] = collection

    # planned chunks
    plan_path = root / "data_processed" / "chunk_plan.json"
    planned = None
    if plan_path.exists():
        plan = read_json(plan_path)
        if isinstance(plan, dict) and "chunks" in plan and isinstance(plan["chunks"], list):
            planned = len(plan["chunks"])
        elif isinstance(plan, list):
            planned = len(plan)
    details["planned_chunks"] = planned

    try:
        client = chromadb.PersistentClient(path=str(db_path))
        col = client.get_collection(collection)
        count = col.count()
        details["collection_count"] = count
        if planned is not None:
            ok = count == planned
            details["match"] = ok
            return ok, details
        else:
            return True, {**details, "match": None, "note": "planned_chunks unavailable; only counted collection"}
    except Exception as e:
        return False, {**details, "error": f"{type(e).__name__}: {e}"}


def probe_llm(
    base_url: str, connect_timeout: float, read_timeout: float, trust_env_mode: str
) -> Tuple[bool, Dict[str, Any]]:
    """
    Optional check:
    - GET {base_url}/models or {base_url}/v1/models depending on user input
    - POST chat completion with a tiny prompt

    base_url should look like: http://localhost:8000/v1
    """
    details: Dict[str, Any] = {
        "enabled": False,
        "base_url": base_url,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "trust_env": trust_env_mode,
    }
    details["enabled"] = True
    base = base_url.rstrip("/")
    trust_env = resolve_trust_env(base_url, trust_env_mode)
    sess = get_session(trust_env=trust_env)

    def url(p: str) -> str:
        return f"{base}{p}"

    ok = True
    try:
        r = sess.get(url("/models"), timeout=(connect_timeout, read_timeout))
        details["get_models_status"] = r.status_code
        ok = ok and (200 <= r.status_code < 300)
        # keep response small
        try:
            j = r.json()
            details["models_keys"] = list(j.keys())[:10] if isinstance(j, dict) else None

            # Choose a model id from /models when available (prefer instruct/chat).
            chosen_model = None
            try:
                if isinstance(j, dict):
                    data = j.get("data")
                    ids = []
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and isinstance(item.get("id"), str):
                                ids.append(item["id"])
                    for key in ("instruct", "chat"):
                        for mid in ids:
                            if key in str(mid).lower():
                                chosen_model = mid
                                break
                        if chosen_model:
                            break
                    if not chosen_model and ids:
                        chosen_model = ids[0]
            except Exception:
                chosen_model = None
            details["chosen_model"] = chosen_model

        except Exception:
            details["models_keys"] = None
    except Exception as e:
        ok = False
        details["get_models_error"] = f"{type(e).__name__}: {e}"

    # chat completion probe
    try:
        payload = {
            "model": (details.get("chosen_model") or "gpt-3.5-turbo"),  # prefer server /models id when available
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0,
            "max_tokens": 8,
        }
        r = sess.post(url("/chat/completions"), json=payload, timeout=(connect_timeout, read_timeout))
        details["chat_status"] = r.status_code
        ok = ok and (200 <= r.status_code < 300)
        # do not log full text; just presence of choices
        try:
            j = r.json()
            details["chat_has_choices"] = bool(j.get("choices")) if isinstance(j, dict) else None
        except Exception:
            details["chat_has_choices"] = None
    except Exception as e:
        ok = False
        details["chat_error"] = f"{type(e).__name__}: {e}"

    return ok, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Project root (contains data_processed/ ...)")
    ap.add_argument("--db", default="chroma_db", help="Chroma persistent directory name")
    ap.add_argument("--collection", default="rag_chunks", help="Chroma collection name")
    ap.add_argument("--base-url", default="http://localhost:8000/v1", help="OpenAI-compatible base URL")
    ap.add_argument("--connect-timeout", type=float, default=10.0, help="HTTP connect timeout seconds")
    ap.add_argument("--timeout", type=float, default=10.0, help="HTTP read timeout seconds (legacy name: --timeout)")
    ap.add_argument(
        "--trust-env",
        default="auto",
        choices=["auto", "true", "false"],
        help="trust env proxies: auto(loopback->false), true, false",
    )
    ap.add_argument("--skip-chroma", action="store_true", help="Skip chroma checks")
    ap.add_argument("--skip-llm", action="store_true", help="Skip LLM probe")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    report_dir = root / "data_processed" / "build_reports"
    ensure_dir(report_dir)
    out_path = report_dir / "stage1_verify.json"

    report: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "root": str(root),
        "checks": {},
        "overall": "UNKNOWN",
    }

    ok_files, det_files = check_required_files(root)
    report["checks"]["artifacts"] = {"ok": ok_files, "details": det_files}

    ok_chroma, det_chroma = (True, {"skipped": True})
    if not args.skip_chroma:
        ok_chroma, det_chroma = check_chroma_counts(root, args.db, args.collection)
    report["checks"]["chroma"] = {"ok": ok_chroma, "details": det_chroma}

    ok_llm, det_llm = (True, {"skipped": True})
    if not args.skip_llm:
        ok_llm, det_llm = probe_llm(args.base_url, args.connect_timeout, args.timeout, args.trust_env)
    report["checks"]["llm"] = {"ok": ok_llm, "details": det_llm}

    overall_ok = bool(ok_files and ok_chroma and ok_llm)
    report["overall"] = "PASS" if overall_ok else "FAIL"

    # v2 report
    items = []
    for name, chk in report["checks"].items():
        ok = bool(chk.get("ok"))
        status_label = "PASS" if ok else "FAIL"
        severity_level = 0 if ok else 3
        items.append(
            {
                "tool": "verify_stage1_pipeline",
                "title": name,
                "status_label": status_label,
                "severity_level": severity_level,
                "message": f"{name}={'PASS' if ok else 'FAIL'}",
                "detail": chk.get("details"),
            }
        )

    report_v2 = {
        "schema_version": 2,
        "generated_at": _now_iso(),
        "tool": "verify_stage1_pipeline",
        "root": root.as_posix(),
        "summary": {},
        "items": items,
        "data": report,
    }

    write_report_bundle(
        report=report_v2,
        report_json=out_path,
        repo_root=root,
        console_title="verify_stage1_pipeline",
        emit_console=True,
    )

    return 0 if overall_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
