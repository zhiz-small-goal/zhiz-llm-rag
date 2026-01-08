from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if p.returncode != 0:
        raise AssertionError(
            "command failed\n"
            f"cmd={cmd}\n"
            f"rc={p.returncode}\n"
            f"stdout:\n{p.stdout}\n"
            f"stderr:\n{p.stderr}\n"
        )
    return p


def _which(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise AssertionError(f"missing console script on PATH: {name}")
    return p


def test_mini_pipeline_stage1(tmp_path: Path) -> None:
    """A minimal, lightweight integration test.

    Invariants
      - rag-inventory can scan a tiny data_raw/ tree.
      - rag-extract-units can produce units JSONL.
      - rag-validate-units passes on that output.

    Non-goals
      - No embedding/model downloads.
      - No Chroma ingestion.
    """

    root = tmp_path / "mini_repo"
    raw = root / "data_raw"
    d1 = raw / "教程"
    d2 = raw / "综合指南"
    d1.mkdir(parents=True, exist_ok=True)
    d2.mkdir(parents=True, exist_ok=True)

    # Include non-ASCII paths to exercise Windows+UTF8 behavior.
    (d1 / "01_hello.md").write_text("# 标题\n\n这是一段内容。\n", encoding="utf-8")
    (d2 / "02_world.md").write_text("# World\n\nno links\n", encoding="utf-8")

    rag_inventory = _which("rag-inventory")
    rag_extract = _which("rag-extract-units")
    rag_validate = _which("rag-validate-units")
    rag_plan = _which("rag-plan")

    _run([rag_inventory, "--root", str(root)])
    inv = root / "inventory.csv"
    assert inv.exists(), "inventory.csv should be created"

    out_units = root / "data_processed" / "text_units.jsonl"
    _run(
        [
            rag_extract,
            "--root",
            str(root),
            "--inventory",
            "inventory.csv",
            "--out",
            "data_processed/text_units.jsonl",
        ]
    )
    assert out_units.exists(), "units jsonl should be created"
    assert out_units.read_text(encoding="utf-8").strip(), "units jsonl should be non-empty"

    _run(
        [
            rag_validate,
            "--root",
            str(root),
            "--inventory",
            "inventory.csv",
            "--units",
            "data_processed/text_units.jsonl",
        ]
    )

    # Stage-1 also includes planning (chunk plan) and must not require Stage-2 deps.
    out_plan = root / "data_processed" / "chunk_plan.json"
    _run(
        [
            rag_plan,
            "--root",
            str(root),
            "--units",
            "data_processed/text_units.jsonl",
            "--chunk-chars",
            "1200",
            "--overlap-chars",
            "120",
            "--min-chunk-chars",
            "200",
            "--include-media-stub",
            "false",
            "--out",
            "data_processed/chunk_plan.json",
        ]
    )
    assert out_plan.exists(), "chunk_plan.json should be created"
    assert "planned_chunks" in out_plan.read_text(encoding="utf-8"), "plan output should contain planned_chunks"
