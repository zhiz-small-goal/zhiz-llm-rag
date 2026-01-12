#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

Public Release Hygiene Audit (v2)

Changelog v2:
- Fix: simplify absolute path regexes to avoid regex compile errors.
- Fix: CMD wrapper uses ASCII-only content to avoid cmd.exe encoding issues.
- Robustness: regex compilation errors are downgraded to INFO instead of crashing.

See USAGE_public_release_audit.md for usage.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict


def _now_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _desktop_dir() -> Path:
    home = Path.home()
    cand = home / "Desktop"
    if cand.exists() and cand.is_dir():
        return cand
    return home


def _run(cmd: List[str], cwd: Path, timeout: int = 120) -> Tuple[int, str, str]:
    try:
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
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"

def _run_in(cmd: List[str], cwd: Path, input_text: str, timeout: int = 120) -> Tuple[int, str, str]:
    """Run a command with stdin input (text mode).

    Notes:
    - Supports NUL-delimited protocols when input_text contains '\x00'.
    - Returns (rc, stdout, stderr). rc may be 0/1 for some git plumbing commands (e.g., check-ignore).
    """
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"


def _rel(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _is_text_path(p: Path, text_exts: set[str]) -> bool:
    return p.suffix.lower() in text_exts


def _read_text_best_effort(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")


def _mask_secret(s: str) -> str:
    s = s.strip()
    if len(s) <= 10:
        return "*" * len(s)
    return f"{s[:4]}...{s[-2:]} (len={len(s)})"


def _diag_loc(repo: Path, file_path: Path, line_no: int, col_no: int) -> str:
    return f"{_rel(file_path, repo)}:{line_no}:{col_no}"


DEFAULT_CONFIG = {
    "forbidden_tracked_paths": [
        "inventory.csv",
        "chroma.sqlite3",
        "data_raw/",
        "data_processed/",
        "chroma_db/",
        "chroma_db_*",
        "*.sqlite3",
        "*.db",
    ],
    "text_extensions": [
        ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".jsonl",
        ".py", ".ps1", ".cmd", ".bat", ".ini", ".cfg"
    ],
    "image_extensions": [".png", ".jpg", ".jpeg", ".webp", ".gif"],
    "binary_extensions": [".exe", ".dll", ".so", ".dylib"],
    "max_file_size_mb_warn": 5,
    "max_file_size_mb_high": 20,
    "scan_roots": ["."],
    "exclude_dirs": [
        ".git", ".venv", ".venv_ci", ".venv_rag", ".venv_embed",
        "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache",
        ".ruff_cache",
    ],

    # v2: simplified to avoid fragile grouping/escaping
    "absolute_path_regexes": [
        r"(?i)\b[A-Z]:\\[^\r\n\t\"'<>]+",          # <REPO_ROOT>
        r"(?i)\bC:\\Users\\[^\r\n\t\"'<>]+",       # <REPO_ROOT>
    ],

    "secret_regexes": [
        r"(ghp_[A-Za-z0-9]{20,})",
        r"(github_pat_[A-Za-z0-9_]{20,})",
        r"(sk-[A-Za-z0-9]{20,})",
        r"(AKIA[0-9A-Z]{16})",
        r"(-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----)",
        r"(BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY)",
        r"(OPENAI_API_KEY\s*[:=]\s*['\"]?[^\s'\"\r\n]+)",
    ],
    "oss_files_required_any_of": [
        ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    ],
    "oss_files_required_exact": [
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
    ],
    "ci_workflow_glob": ".github/workflows/*.yml",
    "ci_heuristic_patterns": [
        "gitleaks", "trufflehog", "secret", "secrets", "sensitive",
        "check_public_release_hygiene", "public_release", "git ls-files",
    ],
}


def load_config(path: Optional[Path]) -> dict:
    if not path:
        return DEFAULT_CONFIG
    obj = json.loads(path.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_CONFIG)
    merged.update(obj)
    return merged


@dataclass
class Finding:
    severity: str  # HIGH/MED/LOW/INFO
    title: str
    facts: List[str]
    inference: List[str]
    locations: List[str]
    remediation: List[str]


def git_toplevel(repo: Path) -> Optional[Path]:
    code, out, _ = _run(["git", "rev-parse", "--show-toplevel"], cwd=repo, timeout=15)
    if code == 0:
        p = Path(out.strip())
        if p.exists():
            return p
    return None


def git_ls_files(repo: Path) -> List[str]:
    code, out, err = _run(["git", "ls-files", "-z"], cwd=repo, timeout=60)
    if code != 0:
        raise RuntimeError(f"git ls-files failed: {err.strip()}")
    return [i for i in out.split("\x00") if i]


def git_status_untracked(repo: Path) -> List[str]:
    """Return untracked paths from `git status --porcelain=v1 -z --untracked-files=all`."""
    code, out, err = _run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repo,
        timeout=90,
    )
    if code != 0:
        raise RuntimeError(f"git status failed: {err.strip() or out.strip()}")

    items = [x for x in out.split("\x00") if x]
    untracked: List[str] = []
    i = 0
    while i < len(items):
        rec = items[i]
        # rec looks like: "XY path" (space after XY). For renames/copies there is an extra NUL record.
        if len(rec) >= 4 and rec[0:2] == "??" and rec[2] == " ":
            untracked.append(rec[3:].replace("\\", "/"))
            i += 1
            continue
        # Handle rename/copy extra field: skip the next record.
        if len(rec) >= 4 and rec[2] == " " and rec[0] in ("R", "C"):
            i += 2
            continue
        i += 1
    return untracked


def git_check_ignore(repo: Path, paths: List[str]) -> set[str]:
    """Return the subset of paths ignored by gitignore rules.

    Uses `git check-ignore -z --stdin`. rc=0 means at least one ignored, rc=1 means none ignored.
    """
    if not paths:
        return set()
    payload = "\x00".join([p.replace("\\", "/") for p in paths]) + "\x00"
    code, out, err = _run_in(["git", "check-ignore", "-z", "--stdin"], cwd=repo, input_text=payload, timeout=90)
    if code not in (0, 1):
        raise RuntimeError(f"git check-ignore failed: {err.strip() or out.strip()}")
    return {x for x in out.split("\x00") if x}

def git_log_names(repo: Path, max_lines: int) -> str:
    code, out, err = _run(["git", "log", "--name-only", "--pretty=format:"], cwd=repo, timeout=180)
    if code != 0:
        raise RuntimeError(f"git log failed: {err.strip()}")
    if max_lines <= 0:
        return out
    lines = out.splitlines()
    return "\n".join(lines[:max_lines])


def iter_repo_files(repo: Path, cfg: dict) -> Iterable[Path]:
    exclude = set(cfg["exclude_dirs"])
    for root_rel in cfg["scan_roots"]:
        root = (repo / root_rel).resolve()
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.parts)
            if any(ex in parts for ex in exclude):
                continue
            yield p


def _under_scan_roots(rel_posix: str, cfg: dict) -> bool:
    roots = [str(x).replace("\\", "/").rstrip("/") for x in cfg.get("scan_roots", ["."])]
    if not roots:
        return True
    for r in roots:
        if r in ("", "."):
            return True
        if rel_posix == r or rel_posix.startswith(r + "/"):
            return True
    return False


def select_scan_files(
    repo_root: Path,
    cfg: dict,
    file_scope: str,
    respect_gitignore: bool,
    tracked_list: Optional[List[str]],
) -> Tuple[List[Path], Dict[str, int]]:
    """Select files to scan based on git scope and gitignore rules.

    file_scope:
      - tracked: only files in `git ls-files`
      - tracked_and_untracked_unignored: tracked + untracked but NOT ignored by gitignore
      - worktree_all: existing behavior (walk the worktree regardless of git)

    Returns (files, meta_counts).
    """
    exclude = set(cfg.get("exclude_dirs", []))

    if file_scope == "worktree_all" or tracked_list is None:
        files = list(iter_repo_files(repo_root, cfg))
        return files, {
            "tracked": 0,
            "untracked_total": 0,
            "untracked_ignored": 0,
            "untracked_unignored": 0,
            "scanned": len(files),
        }

    tracked_set = {p.replace("\\", "/") for p in tracked_list}

    untracked_all: List[str] = []
    untracked: List[str] = []
    ignored: set[str] = set()
    if file_scope != "tracked":
        untracked_all = git_status_untracked(repo_root)
        untracked = list(untracked_all)
        if respect_gitignore:
            ignored = git_check_ignore(repo_root, untracked)
            untracked = [p for p in untracked if p not in ignored]

    # De-dupe and filter by scan_roots/exclude_dirs
    candidates = set(tracked_set) | set(untracked)

    files: List[Path] = []
    for rel in sorted(candidates):
        rel = rel.replace("\\", "/")
        if not _under_scan_roots(rel, cfg):
            continue
        if any(part in exclude for part in Path(rel).parts):
            continue
        p = (repo_root / rel)
        if p.is_file():
            files.append(p)

    return files, {
        "tracked": len(tracked_set),
        "untracked_total": len(untracked_all),
        "untracked_ignored": len(ignored),
        "untracked_unignored": len(untracked),
        "scanned": len(files),
    }

def match_glob(path_posix: str, pat: str) -> bool:
    if pat.endswith("/"):
        return path_posix.startswith(pat)
    if "*" not in pat:
        return path_posix == pat
    rx = "^" + re.escape(pat).replace("\\*", ".*") + "$"
    return re.match(rx, path_posix) is not None


def _safe_compile_many(patterns: List[str]) -> Tuple[List[re.Pattern], List[str]]:
    ok = []
    bad = []
    for p in patterns:
        try:
            ok.append(re.compile(p))
        except re.error as e:
            bad.append(f"pattern={p!r} error={e}")
    return ok, bad


def scan_forbidden_tracked(repo: Path, cfg: dict, tracked: List[str]) -> Optional[Finding]:
    pats = cfg["forbidden_tracked_paths"]
    bad = []
    for f in tracked:
        fp = f.replace("\\", "/")
        for pat in pats:
            if match_glob(fp, pat.replace("\\", "/")):
                bad.append(fp)
                break
    if not bad:
        return None
    bad = sorted(set(bad))
    return Finding(
        severity="HIGH",
        title="Forbidden files/dirs are tracked by Git",
        facts=[
            "Matched forbidden patterns against `git ls-files` output.",
            f"hits={len(bad)}",
        ],
        inference=[],
        locations=[f"{p}:1:1" for p in bad[:200]],
        remediation=[
            "Move real data/build artifacts out of the public repo; keep only schema/small samples/empty placeholders.",
            "Update .gitignore AND add CI gate to prevent reintroduction.",
            "If these ever appeared in history, enable --history and consider git-filter-repo.",
        ],
    )


def scan_history_for_forbidden(repo: Path, cfg: dict, history_text: str) -> Optional[Finding]:
    pats = [p.replace("\\", "/") for p in cfg["forbidden_tracked_paths"]]
    hits = set()
    for line in history_text.splitlines():
        s = line.strip().replace("\\", "/")
        if not s:
            continue
        for pat in pats:
            if match_glob(s, pat) or (pat.endswith("/") and s.startswith(pat)):
                hits.add(s)
                break
    if not hits:
        return None
    hits = sorted(hits)
    return Finding(
        severity="HIGH",
        title="Forbidden paths appear in Git history (name-only heuristic)",
        facts=[
            "Matched forbidden patterns against `git log --name-only` output.",
            "This indicates the path name appeared in commits; treat as high risk for public release.",
        ],
        inference=[],
        locations=[f"{h}:1:1" for h in hits[:200]],
        remediation=[
            "Rotate/revoke leaked credentials first (if any).",
            "Use git-filter-repo to remove paths / replace sensitive text and force-push; coordinate all clones.",
        ],
    )


def scan_absolute_paths(repo: Path, cfg: dict, files: Iterable[Path]) -> Optional[Finding]:
    text_exts = set(cfg["text_extensions"])
    regexes, bad = _safe_compile_many(cfg["absolute_path_regexes"])
    if bad:
        return Finding(
            severity="INFO",
            title="Absolute-path regex compilation failed (scan skipped)",
            facts=bad,
            inference=["Your local file might have been edited or regex patterns are incompatible; v2 uses simpler defaults."],
            locations=["tools/check_public_release_hygiene.py:1:1"],
            remediation=["Replace absolute_path_regexes with simpler patterns, or use v2 script as provided."],
        )

    locs = []
    for p in files:
        if not _is_text_path(p, text_exts):
            continue
        text = _read_text_best_effort(p)
        for i, line in enumerate(text.splitlines(), start=1):
            for rx in regexes:
                for m in rx.finditer(line):
                    col = m.start() + 1
                    locs.append(_diag_loc(repo, p, i, col))
                    if len(locs) >= 500:
                        break
                if len(locs) >= 500:
                    break
            if len(locs) >= 500:
                break
        if len(locs) >= 500:
            break
    if not locs:
        return None
    return Finding(
        severity="MED",
        title="Absolute paths / environment fingerprints found in text files",
        facts=[f"hits(truncated)={len(locs)}"],
        inference=[],
        locations=locs,
        remediation=[
            "Replace absolute paths with <REPO_ROOT> or relative examples.",
            "Prefer removing screenshots or redacting before committing.",
        ],
    )


def scan_secrets(repo: Path, cfg: dict, files: Iterable[Path]) -> Optional[Finding]:
    text_exts = set(cfg["text_extensions"])
    regexes, bad = _safe_compile_many(cfg["secret_regexes"])
    if bad:
        return Finding(
            severity="INFO",
            title="Secret regex compilation failed (scan skipped)",
            facts=bad,
            inference=[],
            locations=["tools/check_public_release_hygiene.py:1:1"],
            remediation=["Use simpler secret patterns or v2 script defaults."],
        )

    locs = []
    samples = []
    for p in files:
        if not _is_text_path(p, text_exts):
            continue
        text = _read_text_best_effort(p)
        for i, line in enumerate(text.splitlines(), start=1):
            for rx in regexes:
                m = rx.search(line)
                if m:
                    col = m.start(1) + 1 if m.lastindex else m.start() + 1
                    token = m.group(1) if m.lastindex else m.group(0)
                    locs.append(_diag_loc(repo, p, i, col))
                    samples.append(f"{_rel(p, repo)}:{i}:{col} token={_mask_secret(token)}")
                    if len(locs) >= 200:
                        break
            if len(locs) >= 200:
                break
        if len(locs) >= 200:
            break
    if not locs:
        return None
    return Finding(
        severity="HIGH",
        title="Possible secrets / private keys detected",
        facts=[
            "Only masked tokens are shown to avoid further leakage.",
            f"hits(truncated)={len(locs)}",
            *samples[:20],
        ],
        inference=[],
        locations=locs,
        remediation=[
            "If confirmed valid: revoke/rotate first, then clean working tree and history.",
            "Move secrets to env vars or local .env and ensure ignored.",
            "Add CI/pre-commit blocking rules to prevent recurrence.",
        ],
    )


def scan_binaries_and_large_files(repo: Path, cfg: dict, files: Iterable[Path], tracked_set: Optional[set[str]]) -> Optional[Finding]:
    bin_exts = set(cfg["binary_extensions"])
    warn_mb = float(cfg["max_file_size_mb_warn"])
    high_mb = float(cfg["max_file_size_mb_high"])
    locs = []
    high = False

    for p in files:
        size_mb = p.stat().st_size / (1024 * 1024)
        is_bin = p.suffix.lower() in bin_exts
        is_large_warn = size_mb >= warn_mb
        if not (is_bin or is_large_warn):
            continue

        relp = _rel(p, repo).replace("\\", "/")
        tracked = (tracked_set is not None and relp in tracked_set)
        tags = []
        if is_bin:
            tags.append("binary")
        if size_mb >= high_mb:
            tags.append("huge")
            high = True
        elif size_mb >= warn_mb:
            tags.append("large")
        locs.append(f"{relp}:1:1 size={size_mb:.2f}MB tags={','.join(tags)} tracked={tracked}")
        if len(locs) >= 200:
            break

    if not locs:
        return None

    sev = "HIGH" if high else "MED"
    return Finding(
        severity=sev,
        title="Binary/executable files or large files detected",
        facts=[
            f"thresholds: WARN>={warn_mb}MB, HIGH>={high_mb}MB, bin_exts={sorted(bin_exts)}",
            f"hits(truncated)={len(locs)}",
        ],
        inference=[],
        locations=[x.split()[0] for x in locs[:200]],
        remediation=[
            "Avoid tracking binaries in main branch; prefer install instructions or Release assets.",
            "If kept: document source/license/checksum and update policy.",
        ],
    )


def scan_images_presence(repo: Path, cfg: dict, files: Iterable[Path]) -> Optional[Finding]:
    img_exts = set(cfg["image_extensions"])
    imgs = []
    for p in files:
        if p.suffix.lower() in img_exts:
            imgs.append(_rel(p, repo).replace("\\", "/"))
            if len(imgs) >= 200:
                break
    if not imgs:
        return None
    return Finding(
        severity="MED",
        title="Image attachments present (manual review recommended)",
        facts=[f"hits(truncated)={len(imgs)}"],
        inference=["Screenshots often include paths/usernames/stacks; prefer deleting or redacting before public release."],
        locations=[f"{p}:1:1" for p in imgs],
        remediation=[
            "Delete non-essential screenshots; if needed, redact/crop and label as sanitized example.",
        ],
    )


def scan_oss_files(repo: Path, cfg: dict) -> Optional[Finding]:
    missing = []
    for group in cfg["oss_files_required_any_of"]:
        if not any((repo / x).exists() for x in group):
            missing.append(f"LICENSE (any of {group})")
    for name in cfg["oss_files_required_exact"]:
        if not (repo / name).exists():
            missing.append(name)
    if not missing:
        return None
    return Finding(
        severity="MED",
        title="Missing OSS governance files (LICENSE/SECURITY/CONTRIBUTING/CoC)",
        facts=["missing: " + ", ".join(missing)],
        inference=[],
        locations=[f"{m}:1:1" for m in missing],
        remediation=[
            "Add LICENSE consistent with your project metadata.",
            "Add SECURITY.md (reporting + supported versions).",
            "Add CONTRIBUTING.md (dev setup + gates + PR rules).",
            "Optionally add CODE_OF_CONDUCT.md.",
        ],
    )


def scan_ci_heuristic(repo: Path, cfg: dict) -> Optional[Finding]:
    wf_files = list(repo.glob(cfg["ci_workflow_glob"]))
    if not wf_files:
        return Finding(
            severity="INFO",
            title="No CI workflow found (hint)",
            facts=["No .github/workflows/*.yml detected."],
            inference=["If you plan to accept PRs, add CI and run this script as a gate."],
            locations=[f"{cfg['ci_workflow_glob']}:1:1"],
            remediation=["Create CI workflow and add `python tools/check_public_release_hygiene.py --repo . --history 0`."],
        )

    text = ""
    for p in wf_files[:20]:
        text += "\n" + _read_text_best_effort(p).lower()

    pats = [p.lower() for p in cfg["ci_heuristic_patterns"]]
    hit = any(k in text for k in pats)
    if hit:
        return Finding(
            severity="INFO",
            title="CI workflow seems to contain scan-related keywords (hint)",
            facts=["Heuristic keyword hit found in workflow content."],
            inference=["Still verify whether it covers your exact rules (data artifacts, absolute paths, secrets)."],
            locations=[f"{_rel(p, repo)}:1:1" for p in wf_files[:20]],
            remediation=["Prefer adding this script as an explicit gate for auditability."],
        )

    return Finding(
        severity="INFO",
        title="Heuristic: CI workflow may miss hygiene scans (manual verification needed)",
        facts=["This is a heuristic check; it can be a false positive/negative."],
        inference=["Add explicit hygiene gate to reduce accidental leakage."],
        locations=[f"{_rel(p, repo)}:1:1" for p in wf_files[:20]],
        remediation=["Add `python tools/check_public_release_hygiene.py --repo . --history 0` to CI."],
    )


def render_report(repo: Path, findings: List[Finding], cfg_path: Optional[Path], used_git: bool, history: bool, cfg: dict, file_scope: str, respect_gitignore: bool, file_meta: Dict[str, int]) -> str:
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    highs = sum(1 for f in findings if f.severity == "HIGH")
    meds = sum(1 for f in findings if f.severity == "MED")
    lows = sum(1 for f in findings if f.severity == "LOW")
    infos = sum(1 for f in findings if f.severity == "INFO")

    lines = []
    lines += ["---",
              "title: Public Release Hygiene Report",
              f"generated_at: {ts}",
              f"repo: {repo}",
              f"config: {str(cfg_path) if cfg_path else 'DEFAULT_CONFIG'}",
              f"git_available: {used_git}",
              f"history_scan: {history}",
              f"file_scope: {file_scope}",
              f"respect_gitignore: {respect_gitignore}",
              f"file_meta: {json.dumps(file_meta, ensure_ascii=False)}",
              "---",
              ""]
    lines += ["# 目录",
              "- [概要](#概要)",
              "- [发现清单](#发现清单)",
              "- [附录：配置摘要](#附录配置摘要)",
              ""]
    lines += ["# 概要",
              "",
              f"- HIGH: {highs} / MED: {meds} / LOW: {lows} / INFO: {infos}",
              f"- 生成时间：{ts}",
              f"- 仓库根：{repo}",
              f"- 扫描范围：file_scope={file_scope}, respect_gitignore={respect_gitignore}",
              f"- 文件计数：scanned={file_meta.get('scanned', 0)}, tracked={file_meta.get('tracked', 0)}, untracked_unignored={file_meta.get('untracked_unignored', 0)}, untracked_ignored={file_meta.get('untracked_ignored', 0)}",
              "",
              "说明：Facts 为可核验命中；Inference 为启发式/风险提示。",
              ""]
    lines += ["# 发现清单", ""]
    if not findings:
        lines.append("未发现任何问题（在当前配置与扫描范围内）。")
    else:
        for idx, f in enumerate(findings, start=1):
            lines.append(f"## {idx}. [{f.severity}] {f.title}")
            lines.append("")
            if f.facts:
                lines.append("### Facts（可核验）")
                lines += [f"- {x}" for x in f.facts]
                lines.append("")
            if f.inference:
                lines.append("### Inference（推断/风险提示）")
                lines += [f"- {x}" for x in f.inference]
                lines.append("")
            if f.locations:
                lines.append("### Locations（DIAG_LOC_FILE_LINE_COL）")
                for x in f.locations[:200]:
                    lines.append(f"- {x}")
                if len(f.locations) > 200:
                    lines.append(f"- ...（截断，原始命中数={len(f.locations)}）")
                lines.append("")
            if f.remediation:
                lines.append("### Remediation（缓解/建议）")
                lines += [f"- {x}" for x in f.remediation]
                lines.append("")

    lines += ["# 附录：配置摘要", "",
              "```json",
              json.dumps({
                  "forbidden_tracked_paths": cfg["forbidden_tracked_paths"],
                  "exclude_dirs": cfg["exclude_dirs"],
                  "text_extensions": cfg["text_extensions"],
                  "image_extensions": cfg["image_extensions"],
                  "binary_extensions": cfg["binary_extensions"],
                  "max_file_size_mb_warn": cfg["max_file_size_mb_warn"],
                  "max_file_size_mb_high": cfg["max_file_size_mb_high"],
                  "absolute_path_regexes": cfg["absolute_path_regexes"],
              }, ensure_ascii=False, indent=2),
              "```",
              ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="repo path (default=.)")
    ap.add_argument("--config", default=None, help="optional json config path")
    ap.add_argument("--history", type=int, default=0, help="history scan 0/1 (default=0)")
    ap.add_argument(
        "--max-history-lines",
        type=int,
        default=200000,
        help="max lines for history scan (default=200000; <=0 means no limit)",
    )
    ap.add_argument(
        "--file-scope",
        default="tracked_and_untracked_unignored",
        choices=["tracked", "tracked_and_untracked_unignored", "worktree_all"],
        help="file selection scope for content scans (default=tracked_and_untracked_unignored)",
    )
    ap.add_argument(
        "--respect-gitignore",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="when including untracked files, exclude paths ignored by gitignore (default=True)",
    )
    ap.add_argument("--out", default=None, help="output report path (default: repo-local build_reports)")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    cfg_path = Path(args.config).resolve() if args.config else None
    cfg = load_config(cfg_path)

    # Prefer scanning at repo toplevel for stable relative paths.
    top = git_toplevel(repo)
    repo_root = top if top else repo

    findings: List[Finding] = []
    used_git = False
    tracked_set: Optional[set[str]] = None
    tracked_list: Optional[List[str]] = None

    if top:
        used_git = True
        try:
            tracked_list = git_ls_files(repo_root)
            tracked_set = {p.replace("\\", "/") for p in tracked_list}
            f = scan_forbidden_tracked(repo_root, cfg, tracked_list)
            if f:
                findings.append(f)
        except Exception as e:
            findings.append(
                Finding(
                    severity="INFO",
                    title="Git tracked-file check failed (hint)",
                    facts=[f"error: {e}"],
                    inference=["If you need tracked/history checks, ensure git works and run inside repo root."],
                    locations=[f"{repo_root}:1:1"],
                    remediation=["Install git or fix PATH; run from git repo root."],
                )
            )

        if args.history == 1:
            try:
                hist = git_log_names(repo_root, args.max_history_lines)
                f2 = scan_history_for_forbidden(repo_root, cfg, hist)
                if f2:
                    findings.append(f2)
            except Exception as e:
                findings.append(
                    Finding(
                        severity="INFO",
                        title="Git history scan failed (hint)",
                        facts=[f"error: {e}"],
                        inference=["Try --history 0 first, or adjust --max-history-lines."],
                        locations=[f"{repo_root}:1:1"],
                        remediation=["Disable history scan or increase limits if needed."],
                    )
                )

    # Select files for content scans.
    effective_scope = args.file_scope
    effective_respect_gitignore = bool(args.respect_gitignore)

    if not used_git and args.file_scope != "worktree_all":
        # Without git, we cannot accurately respect gitignore; fall back.
        findings.append(
            Finding(
                severity="INFO",
                title="Git not available; file-scope degraded to worktree_all",
                facts=[f"requested_file_scope={args.file_scope}"],
                inference=["Content scans will traverse the worktree; results may include ignored local data artifacts."],
                locations=[f"{repo_root}:1:1"],
                remediation=["Install git and rerun for tracked/gitignore-aware scan."],
            )
        )
        effective_scope = "worktree_all"
        effective_respect_gitignore = False

    files, file_meta = select_scan_files(
        repo_root=repo_root,
        cfg=cfg,
        file_scope=effective_scope,
        respect_gitignore=effective_respect_gitignore,
        tracked_list=tracked_list,
    )

    # Content scans
    for f in [
        scan_absolute_paths(repo_root, cfg, files),
        scan_secrets(repo_root, cfg, files),
        scan_binaries_and_large_files(repo_root, cfg, files, tracked_set),
        scan_images_presence(repo_root, cfg, files),
        scan_oss_files(repo_root, cfg),
        scan_ci_heuristic(repo_root, cfg),
    ]:
        if f:
            findings.append(f)

    order = {"HIGH": 0, "MED": 1, "LOW": 2, "INFO": 3}
    findings.sort(key=lambda x: order.get(x.severity, 9))

    report = render_report(
        repo_root,
        findings,
        cfg_path,
        used_git,
        args.history == 1,
        cfg,
        effective_scope,
        effective_respect_gitignore,
        file_meta,
    )

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = repo_root / "data_processed" / "build_reports" / f"public_release_hygiene_report_{_now_tag()}.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    try:
        out_path.write_text(report, encoding="utf-8")
    except Exception:
        fallback = _desktop_dir() / f"public_release_hygiene_report_{_now_tag()}.md"
        fallback.write_text(report, encoding="utf-8")
        out_path = fallback

    try:
        shown = _rel(out_path, repo_root)
    except Exception:
        shown = str(out_path)
    print(f"[OK] report_written={shown}")

    highs = sum(1 for f in findings if f.severity == "HIGH")
    return 2 if highs > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
