#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test_pipeline.py

目的
----
在模型机上“一键跑完关键自检”，把数据处理 -> 向量库 -> 检索 -> RAG prompt 构造 的健康状态一次性验收。
该脚本不强制调用 LLM（因为 LLM 服务可能未启动），但会：
- 确认 data_processed/text_units.jsonl 存在或可生成
- 运行 validate_rag_units.py（结构+一致性）
- 如 chroma_db 不存在或 collection 不存在，可选择触发 build（可选）
- 运行 check_chroma_build.py（count + 抽样）
- 运行 retriever_chroma.py / check_rag_pipeline.py（检索+prompt 构造）

用法
----
python smoke_test_pipeline.py --root . --q "存档导入与导出怎么做" --k 5 --build-if-missing false

退出码
------
0：PASS
2：FAIL

说明：该脚本是“串联冒烟”，以退出码为主要信号；它本身不输出统一的 JSON 报告。如需机器可读回归数据，请对其内部调用的 `validate_rag_units.py` / `check_chroma_build.py` / `tools.probe_llm_server` 使用 `--json-out`。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd, cwd: Path) -> int:
    print("\n$ " + " ".join(map(str, cmd)))
    p = subprocess.run(cmd, cwd=str(cwd), text=True)
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--q", default="存档导入与导出怎么做")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--build-if-missing", default="false", help="true/false")
    ap.add_argument(
        "--use-flag-build",
        default="true",
        help="true/false; if true and build, call build_chroma_index_flagembedding.py",
    )
    ap.add_argument("--device", default="cpu", help="cpu/cuda:0")
    ap.add_argument("--embed-model", default="BAAI/bge-m3")
    ap.add_argument(
        "--include-media-stub",
        default="true",
        help="true/false; Scheme B default is true. Must match plan/build/check.",
    )
    ap.add_argument(
        "--chunk-chars",
        type=int,
        default=1200,
        help="Max chars per chunk (must match plan/build/check)",
    )
    ap.add_argument("--overlap-chars", type=int, default=120)
    ap.add_argument("--min-chunk-chars", type=int, default=200)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[FATAL] root not found: {root}")
        return 2

    build_if_missing = str(args.build_if_missing).lower() in {"1", "true", "yes", "y", "on"}
    use_flag_build = str(args.use_flag_build).lower() in {"1", "true", "yes", "y", "on"}
    include_media_stub = str(args.include_media_stub).lower() in {"1", "true", "yes", "y", "on"}

    # 0) extract units
    units = root / "data_processed" / "text_units.jsonl"
    if not units.exists():
        print("[INFO] units missing, running extract_units.py")
        rc = _run([sys.executable, "extract_units.py"], cwd=root)
        if rc != 0:
            print("STATUS: FAIL (extract_units.py)")
            return 2

    # 1) validate units
    rc = _run([sys.executable, "validate_rag_units.py", "--max-samples", "20"], cwd=root)
    if rc != 0:
        print("STATUS: FAIL (validate_rag_units.py)")
        return 2

    # 2) check chroma exists
    db = root / "chroma_db"
    collection_ok = False
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(db))
        cols = [c.name for c in client.list_collections()]
        collection_ok = "rag_chunks" in cols
    except Exception:
        collection_ok = False

    if not collection_ok:
        print("[INFO] chroma collection rag_chunks missing")
        if not build_if_missing:
            print("STATUS: FAIL (collection missing; re-run with --build-if-missing true)")
            return 2

        if use_flag_build:
            script = "build_chroma_index_flagembedding.py"
            if not (root / script).exists():
                print(f"STATUS: FAIL ({script} not found; copy it into project root)")
                return 2
            rc = _run(
                [
                    sys.executable,
                    script,
                    "build",
                    "--root",
                    ".",
                    "--units",
                    "data_processed/text_units.jsonl",
                    "--db",
                    "chroma_db",
                    "--collection",
                    "rag_chunks",
                    "--device",
                    args.device,
                    "--embed-model",
                    args.embed_model,
                    "--chunk-chars",
                    str(args.chunk_chars),
                    "--overlap-chars",
                    str(args.overlap_chars),
                    "--min-chunk-chars",
                    str(args.min_chunk_chars),
                    *(["--include-media-stub"] if include_media_stub else []),
                ],
                cwd=root,
            )
        else:
            rc = _run(
                [
                    sys.executable,
                    "build_chroma_index.py",
                    "build",
                    "--root",
                    ".",
                    "--units",
                    "data_processed/text_units.jsonl",
                    "--db",
                    "chroma_db",
                    "--collection",
                    "rag_chunks",
                    "--device",
                    args.device,
                    "--embed-model",
                    args.embed_model,
                    "--chunk-chars",
                    str(args.chunk_chars),
                    "--overlap-chars",
                    str(args.overlap_chars),
                    "--min-chunk-chars",
                    str(args.min_chunk_chars),
                    *(["--include-media-stub"] if include_media_stub else []),
                ],
                cwd=root,
            )
        if rc != 0:
            print("STATUS: FAIL (build)")
            return 2

    # 3) plan -> check(count==plan) for stable validation
    plan_path = root / "data_processed" / "chunk_plan.json"
    rc = _run(
        [
            sys.executable,
            str(root / "tools" / "plan_chunks_from_units.py"),
            "--root",
            ".",
            "--units",
            "data_processed/text_units.jsonl",
            "--chunk-chars",
            str(args.chunk_chars),
            "--overlap-chars",
            str(args.overlap_chars),
            "--min-chunk-chars",
            str(args.min_chunk_chars),
            "--include-media-stub",
            "true" if include_media_stub else "false",
            "--out",
            str(plan_path.relative_to(root)),
        ],
        cwd=root,
    )
    if rc != 0:
        print("STATUS: FAIL (plan_chunks_from_units.py)")
        return 2

    rc = _run(
        [
            sys.executable,
            "check_chroma_build.py",
            "--db",
            "chroma_db",
            "--collection",
            "rag_chunks",
            "--plan",
            str(plan_path),
        ],
        cwd=root,
    )
    if rc != 0:
        print("STATUS: FAIL (check_chroma_build.py; count mismatch vs plan)")
        return 2

    # 4) retrieval smoke
    rc = _run(
        [
            sys.executable,
            "query_cli.py",
            "--db",
            "chroma_db",
            "--collection",
            "rag_chunks",
            "--q",
            args.q,
            "--k",
            str(args.k),
            "--device",
            args.device,
            "--embed-model",
            args.embed_model,
        ],
        cwd=root,
    )
    if rc != 0:
        print("STATUS: FAIL (query_cli.py)")
        return 2

    # 5) rag prompt build smoke
    rc = _run([sys.executable, "check_rag_pipeline.py", "--q", args.q], cwd=root)
    if rc != 0:
        print("STATUS: FAIL (check_rag_pipeline.py)")
        return 2

    print("\nSTATUS: PASS (pipeline smoke test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
