from __future__ import annotations

import json
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

    report_json = repo / "data_processed/build_reports/readme_code_sync_report.json"
    report_md = report_json.with_suffix(".md")
    assert report_json.exists()
    assert report_md.exists()
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert int(payload.get("schema_version") or 0) == 2

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


def test_help_snapshot_options_block_is_generated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs/reference").mkdir(parents=True, exist_ok=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "src/mhy_ai_rag_data/tools").mkdir(parents=True, exist_ok=True)
    (repo / "src/mhy_ai_rag_data/__init__.py").write_text("", encoding="utf-8")
    (repo / "src/mhy_ai_rag_data/tools/__init__.py").write_text("", encoding="utf-8")

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
                "  - path: tools/demo_help_tool_README.md",
                "    tool_id: demo_help_tool",
                "    cli_framework: other",
                "    impl:",
                "      module: mhy_ai_rag_data.tools.demo_help_tool",
                "    contracts:",
                "      output: none",
                "    generation:",
                "      options: help-snapshot",
                "      output_contract: none",
                "    mapping_status: ok",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "src/mhy_ai_rag_data/tools/demo_help_tool.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import argparse",
                "",
                "",
                "def main(argv: list[str] | None = None) -> int:",
                "    ap = argparse.ArgumentParser(description='demo help tool')",
                "    ap.add_argument('--foo', required=True, help='foo flag')",
                "    ap.add_argument('--bar', default='x', help='bar flag')",
                "    ap.parse_args(argv)",
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

    readme = repo / "tools/demo_help_tool_README.md"
    readme.write_text(
        "\n".join(
            [
                "---",
                'title: "demo_help_tool 使用说明"',
                "version: v0.1",
                "last_updated: 2026-01-20",
                "tool_id: demo_help_tool",
                "impl:",
                "  module: mhy_ai_rag_data.tools.demo_help_tool",
                "contracts:",
                "  output: none",
                "generation:",
                "  options: help-snapshot",
                "mapping_status: ok",
                "---",
                "",
                "# demo_help_tool",
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
        "",
    ]
    _run(cmd, cwd=repo)

    after_first = readme.read_text(encoding="utf-8")
    assert "<!-- AUTO:BEGIN options -->" in after_first
    assert "`--foo`" in after_first
    assert "`--bar`" in after_first
    assert "foo flag" in after_first
    assert "bar flag" in after_first

    # idempotent
    _run(cmd, cwd=repo)
    after_second = readme.read_text(encoding="utf-8")
    assert after_second == after_first

    cmd_check = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--check",
        "--out",
        "",
    ]
    _run(cmd_check, cwd=repo)


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


def test_check_fails_when_exceptions_nonempty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs/reference").mkdir(parents=True, exist_ok=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)

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
                "checks:",
                "  enforce:",
                "    - exceptions_empty",
                "exceptions:",
                "  path: docs/reference/readme_code_sync_exceptions.yaml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "docs/reference/readme_code_sync_index.yaml").write_text(
        "version: 1\nreadmes: []\n",
        encoding="utf-8",
    )

    (repo / "docs/reference/readme_code_sync_exceptions.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "last_updated: 2026-01-20",
                "exceptions:",
                "  - path: tools/demo_tool_README.md",
                "    tool_id: demo_tool",
                "    reason: test exception",
                "    checks:",
                "      skip: [options]",
                "    owner: '@me'",
                "    review:",
                "      trigger: 'test'",
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
        "--check",
        "--out",
        "data_processed/build_reports/readme_code_sync_report.json",
    ]
    p = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    assert p.returncode == 2, f"expected FAIL rc=2, got {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}\n"

    report_json = repo / "data_processed/build_reports/readme_code_sync_report.json"
    report = json.loads(report_json.read_text(encoding="utf-8"))
    summary = report.get("summary") or {}
    assert summary.get("overall_status_label") == "FAIL"
    assert summary.get("overall_rc") == 2

    items = report.get("items") or []
    assert any(
        isinstance(it, dict) and it.get("title") == "exceptions_nonempty" and it.get("status_label") == "FAIL"
        for it in items
    ), f"expected exceptions_nonempty FAIL item, got titles={[it.get('title') for it in items if isinstance(it, dict)]}"


def test_check_out_empty_prints_console_without_artifacts(tmp_path: Path) -> None:
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

    cmd_write = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--write",
        "--out",
        "",
    ]
    p_write = subprocess.run(cmd_write, cwd=str(repo), text=True, capture_output=True)
    assert p_write.returncode == 0, f"write mode failed: stdout={p_write.stdout}\nstderr={p_write.stderr}"
    after_write = readme.read_text(encoding="utf-8")
    assert "<!-- AUTO:BEGIN options -->" in after_write

    default_report = repo / "data_processed/build_reports/readme_code_sync_report.json"
    assert not default_report.exists()
    assert not default_report.with_suffix(".md").exists()

    cmd_check = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--check",
        "--out",
        "",
    ]
    p_check = subprocess.run(cmd_check, cwd=str(repo), text=True, capture_output=True)
    assert p_check.returncode == 0, f"check failed: stdout={p_check.stdout}\nstderr={p_check.stderr}"
    assert "check_readme_code_sync" in p_check.stdout
    assert "overall: PASS rc=0" in p_check.stdout
    assert readme.read_text(encoding="utf-8") == after_write
    assert not default_report.exists()
    assert not default_report.with_suffix(".md").exists()


def test_check_out_empty_reports_failures_in_console(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs/reference").mkdir(parents=True, exist_ok=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)

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
                "checks:",
                "  enforce:",
                "    - frontmatter_present",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "docs/reference/readme_code_sync_index.yaml").write_text(
        "version: 1\nreadmes: []\n",
        encoding="utf-8",
    )

    readme = repo / "tools/demo_README.md"
    readme.write_text("# missing frontmatter\n", encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "mhy_ai_rag_data.tools.check_readme_code_sync",
        "--root",
        str(repo),
        "--check",
        "--out",
        "",
    ]
    p = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    assert p.returncode == 2, f"expected rc=2 for FAIL, got {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
    assert "frontmatter_missing" in p.stdout
    assert "overall: FAIL rc=2" in p.stdout
    report_json = repo / "data_processed/build_reports/readme_code_sync_report.json"
    assert not report_json.exists()
    assert readme.read_text(encoding="utf-8").startswith("# missing frontmatter")


def test_write_reports_missing_required_keys_and_writes_bundle(tmp_path: Path) -> None:
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
    ]
    p = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    assert p.returncode == 2, f"expected rc=2 for missing required keys\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"

    report_json = repo / "data_processed/build_reports/readme_code_sync_report.json"
    report_md = report_json.with_suffix(".md")
    assert report_json.exists(), "write mode should emit report bundle by default"
    assert report_md.exists()

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    assert summary.get("overall_status_label") == "FAIL"
    assert summary.get("overall_rc") == 2
    items = payload.get("items") or []
    assert any(
        isinstance(it, dict)
        and it.get("title") == "frontmatter_required_keys_missing"
        and it.get("status_label") == "FAIL"
        for it in items
    ), (
        f"expected frontmatter_required_keys_missing FAIL item, got titles={[it.get('title') for it in items if isinstance(it, dict)]}"
    )

    content = readme.read_text(encoding="utf-8")
    assert "<!-- AUTO:BEGIN" not in content, "write mode should not inject blocks when required keys are missing"
