#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rag_accept.py

一键验收入口：
- 默认只跑核心序列：stamp -> check -> snapshot -> rag-status --strict
- 其它步骤需显式开启（verify / Stage-2 评测）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mhy_ai_rag_data.project_paths import find_project_root


def _read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj, None
        return None, "profile_not_object"
    except Exception as e:  # noqa: BLE001
        return None, f"json_parse_error: {type(e).__name__}: {e}"


def _load_profile(path: Optional[Path]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if path is None:
        return None, None
    if not path.exists():
        return None, f"profile_not_found: {path}"
    return _read_json(path)


def _resolve(root: Path, p: str) -> Path:
    x = Path(p)
    return (root / x).resolve() if not x.is_absolute() else x.resolve()


def _pick(
    args_val: Optional[str],
    profile: Optional[Dict[str, Any]],
    profile_keys: List[str],
    default: str,
) -> str:
    if args_val:
        return args_val
    if profile:
        for k in profile_keys:
            v = profile.get(k)
            if v not in (None, ""):
                return str(v)
    return default


def _run(cmd: List[str], *, cwd: Path) -> int:
    print("\n$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(cwd))
    return p.returncode


def _profile_default(root: Path) -> Optional[Path]:
    p = root / "build_profile_schemeB.json"
    return p if p.exists() else None


def _core_steps(
    *,
    root: Path,
    profile_path: Optional[Path],
    db: Path,
    collection: str,
    plan: Path,
    reports_dir: Path,
    state_root: Path,
) -> List[Tuple[str, List[str]]]:
    check_report = reports_dir / "check.json"
    snapshot_out = reports_dir / "stage1_baseline_snapshot.json"
    status_out = reports_dir / "status.json"
    status_cmd = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.rag_status",
        "--root",
        str(root),
        "--db",
        str(db),
        "--collection",
        collection,
        "--plan",
        str(plan),
        "--reports-dir",
        str(reports_dir),
        "--state-root",
        str(state_root),
        "--strict",
        "--json-out",
        str(status_out),
    ]
    if profile_path is not None:
        status_cmd.extend(["--profile", str(profile_path)])

    return [
        (
            "stamp",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.tools.write_db_build_stamp",
                "--root",
                str(root),
                "--db",
                str(db),
                "--collection",
                collection,
                "--state-root",
                str(state_root),
                "--plan",
                str(plan),
                "--writer",
                "rag-accept",
            ],
        ),
        (
            "check",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.check_chroma_build",
                "--db",
                str(db),
                "--collection",
                collection,
                "--plan",
                str(plan),
                "--json-out",
                str(check_report),
            ],
        ),
        (
            "snapshot",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.tools.snapshot_stage1_baseline",
                "--root",
                str(root),
                "--db",
                str(db),
                "--out",
                str(snapshot_out),
            ],
        ),
        (
            "status",
            status_cmd,
        ),
    ]


def _verify_steps(
    *,
    root: Path,
    db: Path,
    collection: str,
    base_url: str,
    connect_timeout: float,
    timeout: float,
    trust_env: str,
    with_llm: bool,
) -> List[Tuple[str, List[str]]]:
    cmd = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.verify_stage1_pipeline",
        "--root",
        str(root),
        "--db",
        str(db),
        "--collection",
        collection,
        "--base-url",
        base_url,
        "--connect-timeout",
        str(connect_timeout),
        "--timeout",
        str(timeout),
        "--trust-env",
        trust_env,
    ]
    if not with_llm:
        cmd.append("--skip-llm")
    return [("verify_stage1", cmd)]


def _stage2_steps(
    *,
    root: Path,
    db: Path,
    collection: str,
    cases: Path,
    reports_dir: Path,
    k: int,
    embed_backend: str,
    embed_model: str,
    device: str,
    base_url: str,
    connect_timeout: float,
    timeout: float,
    trust_env: str,
    llm_model: str,
    context_max_chars: int,
    max_tokens: int,
    temperature: float,
    full: bool,
) -> List[Tuple[str, List[str]]]:
    validation_out = reports_dir / "eval_cases_validation.json"
    retrieval_out = reports_dir / "eval_retrieval_report.json"
    rag_out = reports_dir / "eval_rag_report.json"
    summary_out = reports_dir / "stage2_summary.md"

    steps = [
        (
            "validate_eval_cases",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.tools.validate_eval_cases",
                "--root",
                str(root),
                "--cases",
                str(cases),
                "--out",
                str(validation_out),
            ],
        ),
        (
            "eval_retrieval",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.tools.run_eval_retrieval",
                "--root",
                str(root),
                "--db",
                str(db),
                "--collection",
                collection,
                "--cases",
                str(cases),
                "--k",
                str(k),
                "--embed-backend",
                embed_backend,
                "--embed-model",
                embed_model,
                "--device",
                device,
                "--out",
                str(retrieval_out),
            ],
        ),
    ]
    if full:
        steps.append(
            (
                "eval_rag",
                [
                    sys.executable,
                    "-m",
                    "mhy_ai_rag_data.tools.run_eval_rag",
                    "--root",
                    str(root),
                    "--db",
                    str(db),
                    "--collection",
                    collection,
                    "--cases",
                    str(cases),
                    "--k",
                    str(k),
                    "--embed-backend",
                    embed_backend,
                    "--embed-model",
                    embed_model,
                    "--device",
                    device,
                    "--base-url",
                    base_url,
                    "--connect-timeout",
                    str(connect_timeout),
                    "--timeout",
                    str(timeout),
                    "--trust-env",
                    trust_env,
                    "--llm-model",
                    llm_model,
                    "--context-max-chars",
                    str(context_max_chars),
                    "--max-tokens",
                    str(max_tokens),
                    "--temperature",
                    str(temperature),
                    "--out",
                    str(rag_out),
                ],
            )
        )
    steps.append(
        (
            "stage2_summary",
            [
                sys.executable,
                "-m",
                "mhy_ai_rag_data.tools.view_stage2_reports",
                "--root",
                str(root),
                "--cases",
                str(cases),
                "--validation",
                str(validation_out),
                "--retrieval",
                str(retrieval_out),
                "--rag",
                str(rag_out),
                "--md-out",
                str(summary_out),
            ],
        )
    )
    return steps


def main() -> int:
    ap = argparse.ArgumentParser(description="One-click accept for Stage-1 (with optional verify/Stage-2 eval).")
    ap.add_argument("--root", default=None, help="project root (auto-detect if omitted)")
    ap.add_argument("--profile", default=None, help="build profile json (optional)")
    ap.add_argument("--db", default=None, help="chroma db path (override profile/default)")
    ap.add_argument("--collection", default=None, help="collection name (override profile/default)")
    ap.add_argument("--plan", default=None, help="chunk_plan.json path (override profile/default)")
    ap.add_argument("--reports-dir", default=None, help="build_reports dir (override profile/default)")
    ap.add_argument("--state-root", default=None, help="index_state root (override profile/default)")

    ap.add_argument("--verify-stage1", action="store_true", help="run verify_stage1_pipeline")
    ap.add_argument("--verify-llm", action="store_true", help="enable LLM probe in verify_stage1_pipeline")

    ap.add_argument("--stage2", action="store_true", help="run Stage-2 retrieval eval (stable default)")
    ap.add_argument("--stage2-full", action="store_true", help="run Stage-2 retrieval + RAG eval (requires LLM)")

    ap.add_argument("--cases", default=None, help="eval cases jsonl (override default)")
    ap.add_argument("--k", type=int, default=5, help="topK for eval (Stage-2)")
    ap.add_argument("--embed-backend", default=None, help="auto|flagembedding|sentence-transformers")
    ap.add_argument("--embed-model", default=None, help="embed model name")
    ap.add_argument("--device", default=None, help="cpu|cuda:0")

    ap.add_argument("--base-url", default="http://localhost:8000/v1", help="OpenAI-compatible base URL")
    ap.add_argument("--connect-timeout", type=float, default=10.0, help="HTTP connect timeout seconds")
    ap.add_argument("--timeout", type=float, default=300.0, help="HTTP read timeout seconds")
    ap.add_argument("--trust-env", default="auto", choices=["auto", "true", "false"], help="trust env proxies")
    ap.add_argument("--llm-model", default="auto", help="LLM model id; default auto: run-time resolve via GET /models")
    ap.add_argument("--context-max-chars", type=int, default=12000, help="max context chars for rag eval")
    ap.add_argument("--max-tokens", type=int, default=256, help="max tokens for rag eval")
    ap.add_argument("--temperature", type=float, default=0.0, help="temperature for rag eval")
    args = ap.parse_args()

    root = find_project_root(args.root)

    profile_path = Path(args.profile).resolve() if args.profile else _profile_default(root)
    profile, prof_err = _load_profile(profile_path)
    if prof_err:
        print(f"[WARN] {prof_err}")

    collection = _pick(args.collection, profile, ["collection"], "rag_chunks")
    db = _resolve(root, _pick(args.db, profile, ["db"], "chroma_db"))
    plan = _resolve(root, _pick(args.plan, profile, ["planner_out", "plan", "chunk_plan"], "data_processed/chunk_plan.json"))
    reports_dir = _resolve(root, _pick(args.reports_dir, profile, ["reports_dir"], "data_processed/build_reports"))
    state_root = _resolve(root, _pick(args.state_root, profile, ["state_root"], "data_processed/index_state"))

    cases = _resolve(root, _pick(args.cases, profile, ["eval_cases"], "data_processed/eval/eval_cases.jsonl"))
    embed_backend = _pick(args.embed_backend, profile, ["embed_backend"], "auto")
    embed_model = _pick(args.embed_model, profile, ["embed_model"], "BAAI/bge-m3")
    device = _pick(args.device, profile, ["device"], "cpu")

    reports_dir.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    steps = _core_steps(
        root=root,
        profile_path=profile_path,
        db=db,
        collection=collection,
        plan=plan,
        reports_dir=reports_dir,
        state_root=state_root,
    )

    if args.verify_stage1:
        steps = (
            steps[:2]
            + _verify_steps(
                root=root,
                db=db,
                collection=collection,
                base_url=args.base_url,
                connect_timeout=args.connect_timeout,
                timeout=args.timeout,
                trust_env=args.trust_env,
                with_llm=args.verify_llm,
            )
            + steps[2:]
        )

    for name, cmd in steps:
        rc = _run(cmd, cwd=root)
        if rc != 0:
            print(f"[FAIL] step={name} rc={rc}")
            return rc

    if args.stage2_full:
        args.stage2 = True

    if args.stage2:
        stage2_steps = _stage2_steps(
            root=root,
            db=db,
            collection=collection,
            cases=cases,
            reports_dir=reports_dir,
            k=args.k,
            embed_backend=embed_backend,
            embed_model=embed_model,
            device=device,
            base_url=args.base_url,
            connect_timeout=args.connect_timeout,
            timeout=args.timeout,
            trust_env=args.trust_env,
            llm_model=args.llm_model,
            context_max_chars=args.context_max_chars,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            full=args.stage2_full,
        )
        for name, cmd in stage2_steps:
            rc = _run(cmd, cwd=root)
            if rc != 0:
                print(f"[FAIL] step={name} rc={rc}")
                return rc

    print("[OK] rag-accept finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
