#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

Fix Public Release Hygiene (v1)

Goal:
- Provide an "auto-fix attempt" for the issues found by tools/check_public_release_hygiene.py
- Default is SAFE: dry-run, quarantine instead of delete, and only untrack files via git rm --cached.

Usage examples (Windows CMD):
  python tools\fix_public_release_hygiene.py --repo . --dry-run
  python tools\fix_public_release_hygiene.py --repo . --apply --quarantine ".public_release_quarantine"

Important safety:
- This script does NOT rewrite git history.
- This script does NOT delete by default; it quarantines files (move) when requested.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict


DEFAULTS = {
    "deny_globs_for_untrack": [
        "inventory.csv",
        "chroma.sqlite3",
        "chroma_db/",
        "data_raw/",
        "data_processed/",
        "*.sqlite3",
        "*.db",
        "*.mp4",
        "*.gif",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.webp",
        "*.exe",
        "*.dll",
        "*.so",
        "*.dylib",
        "*.bin",
    ],
    "root_screenshots": ["image.png", "image-1.png"],
    "text_extensions": [
        ".md",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".jsonl",
        ".py",
        ".ps1",
        ".cmd",
        ".bat",
        ".ini",
        ".cfg",
    ],
    "exclude_dirs": [
        ".git",
        ".venv",
        ".venv_ci",
        ".venv_rag",
        ".venv_embed",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    ],
    "absolute_path_regexes": [
        r"(?i)\b[A-Z]:\\(?![nrt](?:$|[^A-Za-z0-9_]))[^\\\r\n\t\"'<>]+(?:\\[^\\\r\n\t\"'<>]+)*",
        r"(?i)\bC:\\Users\\(?![nrt](?:$|[^A-Za-z0-9_]))[^\\\r\n\t\"'<>]+(?:\\[^\\\r\n\t\"'<>]+)*",
    ],
    "gitignore_block": [
        "",
        "# --- public-release hygiene (auto-added) ---",
        "data_raw/",
        "data_processed/",
        "chroma_db/",
        "*.sqlite3",
        "*.db",
        "*.mp4",
        "*.gif",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.webp",
        "*.exe",
        "*.dll",
        "*.so",
        "*.dylib",
        "*.bin",
        "# --- end public-release hygiene ---",
        "",
    ],
}


def _now_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _desktop_dir() -> Path:
    home = Path.home()
    cand = home / "Desktop"
    if cand.exists() and cand.is_dir():
        return cand
    return home


def _run(cmd: List[str], cwd: Path, timeout: int = 120) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


def _is_git_repo(repo: Path) -> bool:
    return (repo / ".git").exists()


def _git_ls_files(repo: Path) -> List[str]:
    code, out, err = _run(["git", "ls-files", "-z"], cwd=repo, timeout=60)
    if code != 0:
        raise RuntimeError(err.strip() or "git ls-files failed")
    return [x for x in out.split("\x00") if x]


def _rel(p: Path, repo: Path) -> str:
    try:
        return str(p.relative_to(repo)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _match_glob(path_posix: str, pat: str) -> bool:
    pat = pat.replace("\\", "/")
    if pat.endswith("/"):
        return path_posix.startswith(pat)
    if "*" not in pat:
        return path_posix == pat
    rx = "^" + re.escape(pat).replace("\\*", ".*") + "$"
    return re.match(rx, path_posix) is not None


def _iter_files(repo: Path, cfg: dict) -> Iterable[Path]:
    exclude = set(cfg["exclude_dirs"])
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if any(part in exclude for part in p.parts):
            continue
        yield p


def _ensure_gitignore(repo: Path, cfg: dict, apply: bool, actions: List[str]) -> None:
    gi = repo / ".gitignore"
    existing = gi.read_text(encoding="utf-8", errors="ignore").splitlines() if gi.exists() else []
    block = cfg["gitignore_block"]
    # idempotent: if marker exists, skip
    if any("public-release hygiene (auto-added)" in line for line in existing):
        actions.append("gitignore: marker exists; skip")
        return
    actions.append(f"gitignore: append block to {gi}")
    if apply:
        text = "\n".join(existing + block) + "\n"
        gi.write_text(text, encoding="utf-8")


def _untrack_deny(repo: Path, cfg: dict, apply: bool, actions: List[str]) -> None:
    if not _is_git_repo(repo):
        actions.append("git: not a repo; skip untrack")
        return
    tracked = _git_ls_files(repo)
    deny = cfg["deny_globs_for_untrack"]
    hits = []
    for f in tracked:
        fp = f.replace("\\", "/")
        if any(_match_glob(fp, pat) for pat in deny):
            hits.append(fp)
    if not hits:
        actions.append("git: no tracked denylist hits")
        return

    # Use 'git rm --cached' in batches to avoid command line length issues.
    actions.append(f"git: untrack {len(hits)} paths via git rm --cached (keep local files)")
    if not apply:
        return

    batch = []
    for h in hits:
        batch.append(h)
        if len(batch) >= 200:
            _git_rm_cached(repo, batch)
            batch = []
    if batch:
        _git_rm_cached(repo, batch)


def _git_rm_cached(repo: Path, rel_paths: List[str]) -> None:
    # Use '--' to separate paths, and do not fail entire run if a path disappears.
    cmd = ["git", "rm", "--cached", "-r", "--force", "--"] + rel_paths
    code, out, err = _run(cmd, cwd=repo, timeout=300)
    if code != 0:
        raise RuntimeError(f"git rm --cached failed: {err.strip() or out.strip()}")


def _quarantine_path(quarantine: Path, rel_posix: str) -> Path:
    return quarantine / Path(rel_posix)


def _move_to_quarantine(src: Path, repo: Path, quarantine: Path, apply: bool, actions: List[str]) -> None:
    relp = _rel(src, repo)
    dst = _quarantine_path(quarantine, relp)
    actions.append(f"quarantine: move {relp} -> {_rel(dst, quarantine)}")
    if not apply:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    # If already exists, add suffix
    if dst.exists():
        dst = dst.with_name(dst.name + f".{_now_tag()}")
    shutil.move(str(src), str(dst))


def _redact_abs_paths(repo: Path, cfg: dict, apply: bool, actions: List[str]) -> None:
    text_exts = set(cfg["text_extensions"])
    regexes = [re.compile(r) for r in cfg["absolute_path_regexes"]]
    changed = 0
    for p in _iter_files(repo, cfg):
        if p.suffix.lower() not in text_exts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            text = p.read_text(encoding="utf-8", errors="ignore")
        orig = text
        for rx in regexes:
            text = rx.sub("<REPO_ROOT>", text)
        if text != orig:
            changed += 1
            actions.append(f"redact: {_rel(p, repo)}")
            if apply:
                p.write_text(text, encoding="utf-8")
    actions.append(f"redact: changed_files={changed}")


def _handle_root_screenshots(repo: Path, cfg: dict, quarantine: Path, apply: bool, actions: List[str]) -> None:
    for name in cfg["root_screenshots"]:
        p = repo / name
        if p.exists() and p.is_file():
            _move_to_quarantine(p, repo, quarantine, apply, actions)


def _create_stub_files(repo: Path, apply: bool, actions: List[str]) -> None:
    # Intentionally minimal templates with TODO markers to avoid wrong legal claims.
    stubs: Dict[str, str] = {
        "LICENSE": (
            "TODO: Choose a license and replace this file.\n"
            "Common choices: MIT, Apache-2.0, MPL-2.0, GPL-3.0.\n"
            "This repository currently has no explicit license.\n"
        ),
        "SECURITY.md": (
            "# Security Policy\n\n"
            "## Reporting a Vulnerability\n\n"
            "- Please open a private report via email (TODO) or use GitHub Security Advisories (if enabled).\n"
            "- Include: affected version/commit, reproduction steps, impact assessment.\n\n"
            "## Supported Versions\n\n"
            "- TODO: Define what versions/branches are supported.\n"
        ),
        "CONTRIBUTING.md": (
            "# Contributing\n\n"
            "## Development Setup\n\n"
            "- TODO: Describe how to create venv, install deps, run tests.\n\n"
            "## Gates\n\n"
            "- Public release hygiene: `python tools/check_public_release_hygiene.py --repo . --history 0`\n\n"
            "## Pull Requests\n\n"
            "- TODO: Add coding style, review policy, and CI expectations.\n"
        ),
        "CODE_OF_CONDUCT.md": (
            "# Code of Conduct\n\n"
            "TODO: Adopt a standard Code of Conduct (e.g. Contributor Covenant) and paste it here.\n"
        ),
    }
    for name, content in stubs.items():
        p = repo / name
        if p.exists():
            actions.append(f"oss: {name} exists; skip")
            continue
        actions.append(f"oss: create stub {name}")
        if apply:
            p.write_text(content, encoding="utf-8")


def _write_fix_report(repo: Path, actions: List[str], apply: bool, out: Optional[str]) -> Path:
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = [
        "---",
        "title: Public Release Hygiene Fix Report",
        "version: v1",
        f"generated_at: {ts}",
        f"repo: {repo}",
        f"mode: {'APPLY' if apply else 'DRY_RUN'}",
        "---",
        "",
        "# 目录",
        "- [概要](#概要)",
        "- [动作清单](#动作清单)",
        "",
        "# 概要",
        "",
        f"- 生成时间：{ts}",
        f"- 模式：{'APPLY' if apply else 'DRY_RUN'}",
        f"- 动作数：{len(actions)}",
        "",
        "# 动作清单",
        "",
    ]
    md += [f"- {a}" for a in actions]
    report = "\n".join(md) + "\n"
    out_path = (
        Path(out).expanduser().resolve() if out else (_desktop_dir() / f"public_release_fix_report_{_now_tag()}.md")
    )
    try:
        out_path.write_text(report, encoding="utf-8")
    except Exception:
        out_path = repo / f"public_release_fix_report_{_now_tag()}.md"
        out_path.write_text(report, encoding="utf-8")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="repo path (default=.)")
    ap.add_argument("--apply", action="store_true", help="apply changes (default: dry-run)")
    ap.add_argument("--quarantine", default=".public_release_quarantine", help="quarantine dir (relative to repo)")
    ap.add_argument("--out", default=None, help="fix report output path; default desktop")
    ap.add_argument("--skip-git", action="store_true", help="skip git untrack step")
    ap.add_argument("--skip-gitignore", action="store_true", help="skip .gitignore update")
    ap.add_argument("--skip-redact", action="store_true", help="skip absolute-path redaction")
    ap.add_argument("--skip-screenshots", action="store_true", help="skip root screenshot quarantine")
    ap.add_argument("--skip-oss", action="store_true", help="skip OSS stub creation")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    cfg = DEFAULTS
    apply = bool(args.apply)

    quarantine = (repo / args.quarantine).resolve()
    actions: List[str] = []

    actions.append(f"repo={repo}")
    actions.append(f"quarantine={quarantine}")
    if apply:
        quarantine.mkdir(parents=True, exist_ok=True)

    if not args.skip_gitignore:
        _ensure_gitignore(repo, cfg, apply, actions)

    if not args.skip_git:
        try:
            _untrack_deny(repo, cfg, apply, actions)
        except Exception as e:
            actions.append(f"git: ERROR {e}")

    if not args.skip_redact:
        try:
            _redact_abs_paths(repo, cfg, apply, actions)
        except Exception as e:
            actions.append(f"redact: ERROR {e}")

    if not args.skip_screenshots:
        try:
            _handle_root_screenshots(repo, cfg, quarantine, apply, actions)
        except Exception as e:
            actions.append(f"screenshots: ERROR {e}")

    if not args.skip_oss:
        try:
            _create_stub_files(repo, apply, actions)
        except Exception as e:
            actions.append(f"oss: ERROR {e}")

    out_path = _write_fix_report(repo, actions, apply, args.out)
    print(f"[OK] fix_report_written={out_path}")

    # Exit code policy: DRY_RUN always 0; APPLY 0 (even if non-fatal errors were appended) to avoid breaking flows.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
