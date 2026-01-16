#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_build_profile.py

目的
----
用一个 JSON profile（如 build_profile_schemeB.json）驱动 plan -> build -> check 的一致性执行，
把“口径”从手工命令行复制升级为可复现的配置文件。

退出码
------
0：PASS
2：FAIL
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def _run(cmd: list[str], cwd: Path) -> int:
    print("\n$ " + " ".join(map(str, cmd)))
    p = subprocess.run(cmd, cwd=str(cwd), text=True)
    return p.returncode


def _load_profile(p: Path) -> Dict[str, Any]:
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("profile is not a json object")
    return obj


def _boolish(s: str) -> bool:
    return str(s).lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run RAG build pipeline from a JSON profile (plan->build->check).")
    ap.add_argument("--profile", default="build_profile_schemeB.json", help="Path to profile json")
    ap.add_argument(
        "--build-script",
        default="tools/build_chroma_index_flagembedding.py",
        help="Which build script to call (recommended: tools/build_chroma_index_flagembedding.py).",
    )
    ap.add_argument(
        "--force-extract-units",
        default="false",
        help="true/false; force re-generate text_units.jsonl even if it already exists",
    )
    ap.add_argument("--skip-build", default="false", help="true/false; for debugging")
    args = ap.parse_args()

    profile_path = Path(args.profile).resolve()
    if not profile_path.exists():
        print(f"[FATAL] profile not found: {profile_path}")
        return 2

    profile = _load_profile(profile_path)
    root = Path(profile.get("root", ".")).resolve()
    if not root.exists():
        print(f"[FATAL] root not found: {root}")
        return 2

    units_rel = str(profile.get("units", "data_processed/text_units.jsonl"))
    units_path = (root / units_rel).resolve()
    env_out = (root / str(profile.get("env_out", "data_processed/env_report.json"))).resolve()
    plan_out = (root / str(profile.get("planner_out", "data_processed/chunk_plan.json"))).resolve()
    plan_rel = str(profile.get("planner_out", "data_processed/chunk_plan.json"))
    reports_dir = (root / str(profile.get("reports_dir", "data_processed/build_reports"))).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1) capture env
    cap = root / "tools" / "capture_rag_env.py"
    if cap.exists():
        rc = _run([sys.executable, str(cap), "--out", str(env_out)], cwd=root)
        if rc != 0:
            print("STATUS: FAIL (capture_rag_env.py)")
            return 2
    else:
        print("[WARN] tools/capture_rag_env.py missing; skip env capture")

    # 2) extract units when missing / inventory newer / forced
    inv_path = (root / "inventory.csv").resolve()
    force_extract = _boolish(args.force_extract_units)

    need_extract = force_extract or (not units_path.exists())
    if not need_extract and inv_path.exists():
        try:
            need_extract = inv_path.stat().st_mtime > units_path.stat().st_mtime
        except Exception:
            need_extract = True

    if need_extract:
        rc = _run([sys.executable, "extract_units.py"], cwd=root)
        if rc != 0:
            print("STATUS: FAIL (extract_units.py)")
            return 2
        if not units_path.exists():
            print(f"STATUS: FAIL (units still missing after extract_units.py): {units_path}")
            return 2

    # 3) validate units
    rc = _run([sys.executable, "validate_rag_units.py", "--max-samples", "20"], cwd=root)
    if rc != 0:
        print("STATUS: FAIL (validate_rag_units.py)")
        return 2

    include_media_stub = bool(profile.get("include_media_stub", True))
    chunk_chars = int(profile.get("chunk_chars", 1200))
    overlap_chars = int(profile.get("overlap_chars", 120))
    min_chunk_chars = int(profile.get("min_chunk_chars", 200))

    # 4) plan (plan must match build)
    planner = root / "tools" / "plan_chunks_from_units.py"
    if not planner.exists():
        print(f"[FATAL] missing planner: {planner}")
        return 2
    rc = _run(
        [
            sys.executable,
            str(planner),
            "--root",
            ".",
            "--units",
            units_rel,
            "--chunk-chars",
            str(chunk_chars),
            "--overlap-chars",
            str(overlap_chars),
            "--min-chunk-chars",
            str(min_chunk_chars),
            "--include-media-stub",
            "true" if include_media_stub else "false",
            "--out",
            str(plan_out.relative_to(root)),
        ],
        cwd=root,
    )
    if rc != 0:
        print("STATUS: FAIL (plan_chunks_from_units.py)")
        return 2

    # 5) build
    skip_build = _boolish(args.skip_build)
    if not skip_build:
        build_script = str(args.build_script)
        if build_script.endswith(".py"):
            build_script_path = (root / build_script).resolve()
            if not build_script_path.exists():
                # allow passing tools/... by name
                build_script_path = (root / "tools" / build_script).resolve()
        else:
            build_script_path = (root / build_script).resolve()

        if not build_script_path.exists():
            print(f"[FATAL] build script not found: {build_script_path}")
            return 2

        db_rel = str(profile.get("db", "chroma_db"))
        coll = str(profile.get("collection", "rag_chunks"))
        embed_model = str(profile.get("embed_model", "BAAI/bge-m3"))
        device = str(profile.get("device", "cpu"))
        embed_batch = int(profile.get("embed_batch", 32))
        upsert_batch = int(profile.get("upsert_batch", 256))

        cmd = [
            sys.executable,
            str(build_script_path),
            "build",
            "--root",
            ".",
            "--units",
            units_rel,
            "--db",
            db_rel,
            "--collection",
            coll,
            "--plan",
            plan_rel,
            "--embed-model",
            embed_model,
            "--device",
            device,
            "--embed-batch",
            str(embed_batch),
            "--upsert-batch",
            str(upsert_batch),
            "--chunk-chars",
            str(chunk_chars),
            "--overlap-chars",
            str(overlap_chars),
            "--min-chunk-chars",
            str(min_chunk_chars),
        ]
        if include_media_stub:
            cmd.append("--include-media-stub")

        # sync/index_state (optional; safe defaults)
        sync_mode = str(profile.get("sync_mode", "incremental"))
        state_root = str(profile.get("state_root", "data_processed/index_state"))
        on_missing_state = str(profile.get("on_missing_state", "reset"))
        schema_change = str(profile.get("schema_change", "reset"))
        strict_sync = "true" if bool(profile.get("strict_sync", True)) else "false"
        cmd += [
            "--sync-mode",
            sync_mode,
            "--state-root",
            state_root,
            "--on-missing-state",
            on_missing_state,
            "--schema-change",
            schema_change,
            "--strict-sync",
            strict_sync,
        ]

        rc = _run(cmd, cwd=root)
        if rc != 0:
            print("STATUS: FAIL (build)")
            return 2

    # 6) check (count==plan)
    db_rel = str(profile.get("db", "chroma_db"))
    coll = str(profile.get("collection", "rag_chunks"))
    rc = _run(
        [
            sys.executable,
            "check_chroma_build.py",
            "--db",
            db_rel,
            "--collection",
            coll,
            "--plan",
            str(plan_out),
        ],
        cwd=root,
    )
    if rc != 0:
        print("STATUS: FAIL (check_chroma_build.py)")
        return 2

    print("\nSTATUS: PASS (profile-driven plan->build->check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
