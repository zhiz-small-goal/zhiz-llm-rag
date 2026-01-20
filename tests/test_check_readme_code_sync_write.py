from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if p.returncode != 0:
        raise AssertionError(
            f"command failed\ncmd={cmd}\nrc={p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}\n"
        )
    return p


def test_check_readme_code_sync_write_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs/reference").mkdir(parents=True, exist_ok=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "src/mhy_ai_rag_data/tools").mkdir(parents=True, exist_ok=True)

    (repo / "docs/reference/readme_code_sync.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "scope:",
                "  readme_globs:",
                "    - tools/*README*.md",
                "frontmatter:",
                "  required_keys: [title, version, last_updated]",
                "auto_blocks:",
                "  markers:",
                "    options:",
                "      begin: '<!-- AUTO:BEGIN options -->'",
                "      end: '<!-- AUTO:END options -->'",
                "    output_contract:",
                "      begin: '<!-- AUTO:BEGIN output-contract -->'",
                "      end: '<!-- AUTO:END output-contract -->'",
                "    artifacts:",
                "      begin: '<!-- AUTO:BEGIN artifacts -->'",
                "      end: '<!-- AUTO:END artifacts -->'",
                "checks:",
                "  enforce:",
                "    - frontmatter_present",
                "    - frontmatter_required_keys",
                "    - auto_block_markers_well_formed",
                "    - options_match_when_present",
                "    - output_contract_match_when_present",
                "    - artifacts_match_when_present",
                "    - output_contract_refs_when_v2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "docs/reference/readme_code_sync_index.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "readmes:",
                "  - path: tools/demo_tool_README.md",
                "    tool_id: demo_tool",
                "    cli_framework: argparse",
                "    impl:",
                "      module: mhy_ai_rag_data.tools.demo_tool",
                "      wrapper: tools/demo_tool.py",
                "    contracts:",
                "      output: report-output-v2",
                "    generation:",
                "      options: static-ast",
                "      output_contract: ssot",
                "    mapping_status: ok",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "src/mhy_ai_rag_data/tools/demo_tool.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import argparse",
                "",
                "",
                "def main() -> int:",
                "    ap = argparse.ArgumentParser()",
                "    ap.add_argument('--foo', required=True, help='foo flag')",
                "    ap.add_argument('--bar', default='x', help='bar flag')",
                "    ap.parse_args([])",
                "    return 0",
                "",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    readme = repo / "tools/demo_tool_README.md"
    readme.write_text(
        "\n".join(
            [
                "---",
                'title: "demo_tool 使用说明"',
                "version: v0.1",
                "last_updated: 2026-01-20",
                "tool_id: demo_tool",
                "impl:",
                "  module: mhy_ai_rag_data.tools.demo_tool",
                "contracts:",
                "  output: report-output-v2",
                "generation:",
                "  options: static-ast",
                "mapping_status: ok",
                "---",
                "",
                "# demo_tool",
                "",
                "manual text",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--write",
        "--out",
        "data_processed/build_reports/readme_code_sync_report.json",
    ]
    _run(cmd, cwd=repo)

    after_first = readme.read_text(encoding="utf-8")
    assert "<!-- AUTO:BEGIN options -->" in after_first
    assert "`--foo`" in after_first
    assert "`--bar`" in after_first

    cmd_check = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--check",
        "--out",
        "data_processed/build_reports/readme_code_sync_report.json",
    ]
    _run(cmd_check, cwd=repo)

    _run(cmd, cwd=repo)
    after_second = readme.read_text(encoding="utf-8")
    assert after_second == after_first, "second --write should be idempotent"


def test_write_skips_non_tool_readme(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs/reference").mkdir(parents=True, exist_ok=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)

    (repo / "docs/reference/readme_code_sync.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "scope:",
                "  readme_globs:",
                "    - tools/README.md",
                "frontmatter:",
                "  required_keys: [title, version, last_updated]",
                "auto_blocks:",
                "  markers:",
                "    options:",
                "      begin: '<!-- AUTO:BEGIN options -->'",
                "      end: '<!-- AUTO:END options -->'",
                "    output_contract:",
                "      begin: '<!-- AUTO:BEGIN output-contract -->'",
                "      end: '<!-- AUTO:END output-contract -->'",
                "    artifacts:",
                "      begin: '<!-- AUTO:BEGIN artifacts -->'",
                "      end: '<!-- AUTO:END artifacts -->'",
                "checks:",
                "  enforce: [frontmatter_present, frontmatter_required_keys, auto_block_markers_well_formed]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "docs/reference/readme_code_sync_index.yaml").write_text(
        "version: 1\nreadmes: []\n",
        encoding="utf-8",
    )

    readme = repo / "tools/README.md"
    readme.write_text(
        "\n".join(
            [
                "---",
                'title: "tools 目录说明"',
                "version: v0.1",
                "last_updated: 2026-01-20",
                "---",
                "",
                "# tools/",
                "",
                "directory overview",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    before = readme.read_text(encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--write",
        "--out",
        "data_processed/build_reports/readme_code_sync_report.json",
    ]
    _run(cmd, cwd=repo)
    after = readme.read_text(encoding="utf-8")
    assert after == before, "tools/README.md should not get AUTO blocks introduced"
