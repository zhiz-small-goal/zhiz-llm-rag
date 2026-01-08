"""Console-script entrypoints.

Why this file exists
--------------------
Many modules in this repository keep their CLI parsing in `if __name__ == "__main__"` blocks.
For `pyproject.toml [project.scripts]`, we need a zero-argument callable. The functions here
simply execute the corresponding module as `__main__` via runpy.

This avoids duplicating argparse logic and keeps behavior identical to `python -m ...`.
"""

from __future__ import annotations

import runpy


def inventory() -> None:
    runpy.run_module("mhy_ai_rag_data.make_inventory", run_name="__main__")


def extract_units() -> None:
    runpy.run_module("mhy_ai_rag_data.extract_units", run_name="__main__")


def validate_units() -> None:
    runpy.run_module("mhy_ai_rag_data.validate_rag_units", run_name="__main__")


def plan_chunks() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.plan_chunks_from_units", run_name="__main__")


def build_chroma() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.build_chroma_index_flagembedding", run_name="__main__")


def check_chroma() -> None:
    runpy.run_module("mhy_ai_rag_data.check_chroma_build", run_name="__main__")


def probe_llm() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.probe_llm_server", run_name="__main__")


def check_rag_pipeline() -> None:
    runpy.run_module("mhy_ai_rag_data.check_rag_pipeline", run_name="__main__")


def check_all() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.check_all", run_name="__main__")


def status() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.rag_status", run_name="__main__")


def stamp() -> None:
    """Write/update Chroma DB build stamp (stable freshness basis for status)."""
    runpy.run_module("mhy_ai_rag_data.tools.write_db_build_stamp", run_name="__main__")


def accept() -> None:
    """One-click accept: stamp -> check -> snapshot -> rag-status --strict (+ optional verify/stage2)."""
    runpy.run_module("mhy_ai_rag_data.tools.rag_accept", run_name="__main__")


def init_eval_cases() -> None:
    runpy.run_module("mhy_ai_rag_data.tools.init_eval_cases", run_name="__main__")
