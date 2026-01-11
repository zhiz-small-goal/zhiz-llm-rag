#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_postmortems_and_troubleshooting.py (v5)

用途：
- 扫描仓库内所有 .md 文件，校验其中指向本地 .md 的引用是否存在。
- 解析 Markdown 链接/图片链接、引用式链接定义、自动链接、以及反引号内的路径。
- 默认在断链时尝试自动定位真实文件并修复路径（可通过 --no-fix 关闭）。
- 忽略 URL、锚点、绝对路径与 fenced code block 内的内容。

用法（在仓库根目录）：
  python tools/verify_postmortems_and_troubleshooting.py
  python tools/verify_postmortems_and_troubleshooting.py --no-fix
  python tools/verify_postmortems_and_troubleshooting.py --strict
  python tools/verify_postmortems_and_troubleshooting.py --any-local
  python tools/verify_postmortems_and_troubleshooting.py --config tools/link_check_config.json
  python tools/verify_postmortems_and_troubleshooting.py --fix-missing-tools-to-placeholder
"""

from __future__ import annotations

import re
import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mhy_ai_rag_data.project_paths import find_project_root
import os
import json

ROOT = find_project_root(None)
# 若你要统一放到其它目录，请用 --config 指定新路径
DEFAULT_CONFIG_PATH = ROOT / "tools" / "link_check_config.json"
DEFAULT_EXTS = {
    ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp",
    ".mp4", ".mov", ".mkv", ".avi", ".webm",
    ".mp3", ".wav", ".ogg", ".flac",
    ".pdf", ".txt", ".csv", ".json", ".jsonl",
}

BACKTICK_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
REF_DEF_LINE_RE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")
AUTOLINK_RE = re.compile(r"<([^>]+)>")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
FENCE_TILDE_RE = re.compile(r"~~~.*?~~~", re.DOTALL)
PURE_EXT_RE = re.compile(r"^\.[A-Za-z0-9]+$")

KIND_LINK = "link"
KIND_REFDEF = "refdef"
KIND_AUTOLINK = "autolink"
KIND_BACKTICK = "backtick"
KIND_BACKTICK_TITLE = "backtick_title"

SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv_rag",
    "__pycache__",
    "chroma_db",
}

def _mask_fenced_blocks(text: str) -> str:
    def _mask(match: re.Match[str]) -> str:
        s = match.group(0)
        return "".join("\n" if c == "\n" else " " for c in s)
    text = FENCE_RE.sub(_mask, text)
    return FENCE_TILDE_RE.sub(_mask, text)

def _is_url_like(token: str) -> bool:
    low = token.lower()
    return (
        low.startswith(("http://", "https://", "mailto:", "tel:"))
        or "://" in low
    )

def _is_absolute_path(token: str) -> bool:
    """判断是否为“操作系统绝对路径”。

    说明：
    - 以盘符开头（如 <REPO_ROOT>
    - 以反斜杠开头（\\foo 或 UNC \\server\\share）视为绝对路径
    - 以正斜杠开头的路径（/docs/a.md）在 GitHub Markdown 中通常表示“仓库根目录相对路径”，不在此处按绝对路径处理；
      是否启用该语义由上层逻辑（treat_leading_slash_as_repo_root）决定。
    """
    if token.startswith("\\\\") or token.startswith("\\"):
        return True
    return bool(re.match(r"^[a-zA-Z]:[\\/]", token))


def _looks_path_like(path_text: str) -> bool:
    # 兜底判定：避免把普通单词当成路径；如需支持无扩展名文件可放宽此规则
    name = Path(path_text).name
    return ("/" in path_text) or ("\\" in path_text) or ("." in name)

def _normalize_exts(exts: list[str]) -> set[str]:
    normalized = set()
    for ext in exts:
        e = ext.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        normalized.add(e)
    return normalized

def _load_config(path: Path) -> dict:
    """
    配置文件示例（JSON）：
      {
        "any_local": false,
        "extensions": [".md", ".png", ".mp4"]
      }
    说明：
    - any_local=true：忽略扩展名列表，校验所有“看起来像路径”的本地链接
    - extensions：白名单扩展名列表，便于扩展图片/视频/文档类型
    """
    config = {
        "any_local": False,
        "check_title_backticks": False,
        "check_backticks": False,
        "treat_leading_slash_as_repo_root": True,
        "extensions": sorted(DEFAULT_EXTS),
        "ignore_prefixes": [
            "data_raw/", "data_processed/", "chroma_db/", ".venv_rag/", ".venv/",
        ],
        "ignore_contains": [
            "llm_probe_report_", "time_report_", "_report_<", "<ts>", "*_report_",
        ],
        # 仅忽略“裸文件名”（不含 / 或 \），用于运行时工件/示例工件。
        # 推荐仍在文档中写成 data_processed/...；此处是为了避免 strict 误报。
        "ignore_bare_filenames": [
            "inventory.csv",
            "check.json",
            "chunk_plan.json",
            "env_report.json",
            "inventory_build_report.json",
            "eval_cases.jsonl",
            "eval_retrieval_report.json",
            "eval_rag_report.json",
        ],
        # 仅对“裸文件名”生效的正则（例如 run_123.events.jsonl）
        "ignore_bare_regexes": [
            r".*\\.events\\.jsonl$",
            r".*\\.progress\\.json$",
        ],
    }
    if not path.exists():
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] invalid config: {path} ({exc}) -> use defaults")
        return config
    if isinstance(raw, dict):
        if "any_local" in raw:
            config["any_local"] = bool(raw["any_local"])
        if "extensions" in raw and isinstance(raw["extensions"], list):
            config["extensions"] = raw["extensions"]
        if "ignore_prefixes" in raw and isinstance(raw["ignore_prefixes"], list):
            config["ignore_prefixes"] = raw["ignore_prefixes"]
        if "ignore_contains" in raw and isinstance(raw["ignore_contains"], list):
            config["ignore_contains"] = raw["ignore_contains"]
        if "ignore_bare_filenames" in raw and isinstance(raw["ignore_bare_filenames"], list):
            config["ignore_bare_filenames"] = raw["ignore_bare_filenames"]
        if "ignore_bare_regexes" in raw and isinstance(raw["ignore_bare_regexes"], list):
            config["ignore_bare_regexes"] = raw["ignore_bare_regexes"]
        if "check_title_backticks" in raw:
            config["check_title_backticks"] = bool(raw["check_title_backticks"])
        if "check_backticks" in raw:
            config["check_backticks"] = bool(raw["check_backticks"])
        if "treat_leading_slash_as_repo_root" in raw:
            config["treat_leading_slash_as_repo_root"] = bool(raw["treat_leading_slash_as_repo_root"])
    return config


def _normalize_for_ignore(path_text: str) -> str:
    s = (path_text or "").replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    # 把 ../ 前缀剥掉（用于匹配“从 docs/ 内引用 repo 根目录产物”的情形）
    while s.startswith("../"):
        s = s[3:]
    return s.lstrip("/")

def _is_ignored_ref(path_text: str, config: dict) -> bool:
    if not path_text:
        return True
    raw = path_text.replace("\\", "/").strip()
    norm = _normalize_for_ignore(raw)

    # 1) 明确的占位/通配/省略：不作为“必须存在”的链接检查
    if ("..." in raw) or ("*" in raw) or ("<" in raw) or (">" in raw):
        return True

    # 2) 按配置的前缀忽略（运行时产物/外部数据目录）
    for p in config.get("ignore_prefixes", []) or []:
        p = str(p).replace("\\", "/")
        if norm.startswith(p) or raw.startswith(p):
            return True

    # 2.1) 忽略“裸文件名”运行时工件（不包含目录分隔符）
    raw_norm = raw.replace("\\", "/")
    is_bare = ("/" not in raw_norm) and ("/" not in norm)
    if is_bare:
        name = Path(norm).name
        for bn in config.get("ignore_bare_filenames", []) or []:
            if name == str(bn):
                return True
        for pat in config.get("ignore_bare_regexes", []) or []:
            try:
                if re.fullmatch(str(pat), name):
                    return True
            except re.error:
                # 配置错误不应导致误判为 FAIL：忽略无效 pattern
                continue

    # 3) 按包含关系忽略（报告文件模板等）
    for s in config.get("ignore_contains", []) or []:
        s = str(s)
        if s and (s in raw or s in norm):
            return True

    return False

def _should_check_path(path_text: str, allowed_exts: set[str], any_local: bool, config: dict) -> bool:
    if _is_ignored_ref(path_text, config):
        return False
    if not _looks_path_like(path_text):
        return False
    if any_local:
        return True
    ext = Path(path_text).suffix.lower()
    return ext in allowed_exts

@dataclass(frozen=True)
class RefHit:
    line: int
    token: str
    path: str
    suffix: str
    kind: str
    start: int
    end: int

def _split_md_ref(raw: str, *, from_backtick: bool, treat_leading_slash_as_repo_root: bool) -> tuple[str, str, str] | None:
    if not raw:
        return None
    t = raw.strip()
    if not t:
        return None
    t = t.rstrip(").,;")
    if t.startswith("<") and ">" in t:
        t = t[1:t.find(">")]
    if any(ch.isspace() for ch in t):
        t = t.split()[0]
    if not t:
        return None
    if _is_url_like(t) or _is_absolute_path(t) or t.startswith("#"):
        return None
    if (not treat_leading_slash_as_repo_root) and t.startswith("/"):
        return None
        return None
    cut = -1
    for sep in ("?", "#"):
        idx = t.find(sep)
        if idx != -1:
            cut = idx if cut == -1 else min(cut, idx)
    if cut != -1:
        path = t[:cut]
        suffix = t[cut:]
    else:
        path = t
        suffix = ""
    if not path:
        return None
    if from_backtick and PURE_EXT_RE.fullmatch(path):
        return None
    return t, path, suffix

def _collect_md_refs_with_lines(text: str, *, check_title_backticks: bool = False, check_backticks: bool = False, treat_leading_slash_as_repo_root: bool = True) -> list[RefHit]:
    out: list[RefHit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        title_spans: list[tuple[int, int]] = []
        for m in LINK_RE.finditer(line):
            title_start, title_end = m.span(1)
            dest_start, dest_end = m.span(2)
            title_spans.append((title_start, title_end))
            parts = _split_md_ref(m.group(2), from_backtick=False, treat_leading_slash_as_repo_root=treat_leading_slash_as_repo_root)
            if parts:
                token, path, suffix = parts
                out.append(RefHit(
                    lineno, token, path, suffix, KIND_LINK, dest_start, dest_end
                ))
            if check_title_backticks:
                title_text = m.group(1)
                for bt in BACKTICK_RE.finditer(title_text):
                    parts = _split_md_ref(bt.group(1), from_backtick=True, treat_leading_slash_as_repo_root=treat_leading_slash_as_repo_root)
                    if parts:
                        token, path, suffix = parts
                        start = title_start + bt.start(1)
                        end = title_start + bt.end(1)
                        out.append(RefHit(
                            lineno, token, path, suffix, KIND_BACKTICK_TITLE, start, end
                        ))
        for m in REF_DEF_LINE_RE.finditer(line):
            parts = _split_md_ref(m.group(1), from_backtick=False, treat_leading_slash_as_repo_root=treat_leading_slash_as_repo_root)
            if parts:
                token, path, suffix = parts
                out.append(RefHit(
                    lineno, token, path, suffix, KIND_REFDEF, m.start(1), m.end(1)
                ))
        for m in AUTOLINK_RE.finditer(line):
            parts = _split_md_ref(m.group(1), from_backtick=False, treat_leading_slash_as_repo_root=treat_leading_slash_as_repo_root)
            if parts:
                token, path, suffix = parts
                out.append(RefHit(
                    lineno, token, path, suffix, KIND_AUTOLINK, m.start(1), m.end(1)
                ))
        if check_backticks:
            for m in BACKTICK_RE.finditer(line):
                span_start, span_end = m.start(1), m.end(1)
                if any(span_start >= s and span_end <= e for s, e in title_spans):
                    continue
                parts = _split_md_ref(m.group(1), from_backtick=True)
                if parts:
                    token, path, suffix = parts
                    out.append(RefHit(
                        lineno, token, path, suffix, KIND_BACKTICK, span_start, span_end
                    ))
    return out

def _iter_md_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if (d not in SKIP_DIRS and not d.startswith("."))
        ]
        for name in filenames:
            if name.lower().endswith(".md"):
                results.append(Path(dirpath) / name)
    return results

def _iter_index_files(root: Path, allowed_exts: set[str], any_local: bool) -> list[Path]:
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if (d not in SKIP_DIRS and not d.startswith("."))
        ]
        for name in filenames:
            if any_local:
                results.append(Path(dirpath) / name)
                continue
            ext = Path(name).suffix.lower()
            if ext in allowed_exts:
                results.append(Path(dirpath) / name)
    return results

def _build_file_index(files: list[Path]) -> list[str]:
    return [p.relative_to(ROOT).as_posix() for p in files]

def _normalize_ref_path(ref_path: str) -> str:
    ref_norm = ref_path.replace("\\", "/")
    while ref_norm.startswith("./"):
        ref_norm = ref_norm[2:]
    while ref_norm.startswith("../"):
        ref_norm = ref_norm[3:]
    return ref_norm.lstrip("/")

def _find_candidates(ref_path: str, rel_paths: list[str]) -> list[str]:
    ref_norm = _normalize_ref_path(ref_path)
    if not ref_norm:
        return []
    ref_lower = ref_norm.lower()
    candidates = [p for p in rel_paths if p.lower().endswith(ref_lower)]
    if candidates:
        return candidates
    name = Path(ref_norm).name.lower()
    if not name:
        return []
    return [p for p in rel_paths if Path(p).name.lower() == name]

def _looks_root_relative(path_text: str) -> bool:
    return not (
        path_text.startswith("./")
        or path_text.startswith("../")
        or path_text.startswith(".\\")
        or path_text.startswith("..\\")
    )

def _resolve_local_target(
    *, base_dir: Path, raw_path: str, treat_leading_slash_as_repo_root: bool
) -> Path:
    """把 Markdown 里的本地路径解析成磁盘路径（用于 exists 校验）。

    解析规则（与 GitHub 渲染语义对齐）：
    - 普通相对路径：相对当前 md 文件所在目录（base_dir）
    - 以 / 开头：若 treat_leading_slash_as_repo_root=true，则视为“仓库根目录相对路径”
    """
    p = (raw_path or "").replace("\\", "/")
    if treat_leading_slash_as_repo_root and p.startswith("/"):
        inner = p.lstrip("/")
        # 防御：仓库根相对路径不应包含 .. 回退
        parts = PurePosixPath(inner).parts
        if any(part == ".." for part in parts):
            return (ROOT / inner).resolve(strict=False)
        return (ROOT / inner).resolve(strict=False)
    return (base_dir / raw_path).resolve(strict=False)


def _apply_replacements(
    lines: list[str],
    replacements: dict[int, list[tuple[int, int, str]]]
) -> bool:
    changed = False
    for lineno, reps in replacements.items():
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue
        line = lines[idx]
        for start, end, new in sorted(reps, key=lambda r: r[0], reverse=True):
            if start < 0 or end > len(line) or start >= end:
                continue
            line = line[:start] + new + line[end:]
        if line != lines[idx]:
            lines[idx] = line
            changed = True
    return changed

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fix", action="store_true", help="仅检测，不自动修复")
    parser.add_argument("--strict", action="store_true", help="存在断链/歧义时返回非 0")
    parser.add_argument("--any-local", action="store_true", help="忽略扩展名列表，校验所有本地路径")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="扩展名与模式配置文件路径（JSON）"
    )
    parser.add_argument(
        "--fix-missing-tools-to-placeholder",
        action="store_true",
        help="当引用 tools/*.py 但文件不存在且无唯一候选时，将其自动改为 tools/<name>.py 占位（避免误导与 strict 误报）"
    )
    return parser.parse_args()

def main() -> int:
    args = _parse_args()
    auto_fix = not args.no_fix
    config = _load_config(Path(args.config))
    allowed_exts = _normalize_exts(config.get("extensions", []))
    any_local = bool(args.any_local or config.get("any_local"))

    md_files = _iter_md_files(ROOT)
    index_files = _iter_index_files(ROOT, allowed_exts, any_local)
    index_rel_paths = _build_file_index(index_files)
    broken: list[tuple[str, int, str, str]] = []
    ambiguous: list[tuple[str, int, str, list[str]]] = []
    fixed: list[tuple[str, int, str, str]] = []
    suggested: list[tuple[str, int, str, str]] = []
    total_refs = 0
    checked_refs = 0

    for md_file in md_files:
        try:
            text = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        masked = _mask_fenced_blocks(text)
        refs = _collect_md_refs_with_lines(
            masked,
            check_title_backticks=bool(config.get("check_title_backticks", False)),
            check_backticks=bool(config.get("check_backticks", False)),
            treat_leading_slash_as_repo_root=bool(config.get("treat_leading_slash_as_repo_root", True)),
        )
        if not refs:
            continue
        total_refs += len(refs)
        base_dir = md_file.parent
        raw_lines = text.splitlines(keepends=True)
        replacements: dict[int, list[tuple[int, int, str]]] = {}
        for hit in refs:
            if not _should_check_path(hit.path, allowed_exts, any_local, config):
                continue
            checked_refs += 1
            target = _resolve_local_target(base_dir=base_dir, raw_path=hit.path, treat_leading_slash_as_repo_root=bool(config.get("treat_leading_slash_as_repo_root", True)))
            if not target.exists():
                src_rel = md_file.relative_to(ROOT).as_posix()
                if hit.kind in (KIND_BACKTICK, KIND_BACKTICK_TITLE):
                    if _looks_root_relative(hit.path):
                        root_target = (ROOT / _normalize_ref_path(hit.path)).resolve(strict=False)
                        if root_target.exists():
                            continue
                candidates = _find_candidates(hit.path, index_rel_paths)
                if len(candidates) == 1:
                    treat_slash = bool(config.get("treat_leading_slash_as_repo_root", True))
                    if treat_slash and hit.path.startswith("/"):
                        fixed_path = f"/{candidates[0]}"
                    else:
                        cand_path = ROOT / candidates[0]
                        rel = os.path.relpath(cand_path, start=base_dir)
                        rel = Path(rel).as_posix()
                        if rel == ".":
                            rel = Path(candidates[0]).name
                        fixed_path = rel
                    fixed_token = f"{fixed_path}{hit.suffix}"
                    if hit.kind == KIND_BACKTICK or not auto_fix:
                        suggested.append((src_rel, hit.line, hit.token, fixed_token))
                    else:
                        replacements.setdefault(hit.line, []).append(
                            (hit.start, hit.end, fixed_token)
                        )
                        fixed.append((src_rel, hit.line, hit.token, fixed_token))
                elif len(candidates) > 1:
                    ambiguous.append((src_rel, hit.line, hit.token, candidates))
                else:
                    # 可选：将缺失的 tools/*.py 自动改为占位形式 tools/<name>.py
                    raw_norm = (hit.path or "").replace("\\", "/")
                    if (
                        auto_fix
                        and bool(args.fix_missing_tools_to_placeholder)
                        and raw_norm.startswith("tools/")
                        and raw_norm.lower().endswith(".py")
                        and ("<" not in raw_norm and ">" not in raw_norm)
                    ):
                        p = Path(raw_norm)
                        parent = p.parent.as_posix()
                        placeholder = f"<{p.stem}>{p.suffix}"
                        fixed_path = f"{parent}/{placeholder}" if parent and parent != "." else placeholder
                        fixed_token = f"{fixed_path}{hit.suffix}"
                        replacements.setdefault(hit.line, []).append(
                            (hit.start, hit.end, fixed_token)
                        )
                        fixed.append((src_rel, hit.line, hit.token, fixed_token))
                        continue

                    if ROOT in target.parents:
                        tgt_rel = target.relative_to(ROOT).as_posix()
                    else:
                        tgt_rel = str(target)
                    broken.append((src_rel, hit.line, hit.token, tgt_rel))

        if auto_fix and replacements:
            changed = _apply_replacements(raw_lines, replacements)
            if changed:
                md_file.write_text("".join(raw_lines), encoding="utf-8")

    def _print_grouped_section(
        title: str,
        rows: list[tuple],
        render: callable,
    ) -> None:
        """Human-friendly console output.

        - Each section is separated by a blank line.
        - Within a section, records are grouped by source file (src), with a blank
          line between different src files.
        """
        print(title)
        last_src: str | None = None
        for row in rows:
            src = row[0]
            if last_src is not None and src != last_src:
                print()
            print(render(row))
            last_src = src

    printed_any_section = False

    if fixed:
        _print_grouped_section(
            "[AUTO-FIXED]",
            sorted(fixed),
            lambda r: f"- {r[0]}:{r[1]}: `{r[2]}` -> `{r[3]}`",
        )
        printed_any_section = True

    if suggested:
        if printed_any_section:
            print()
        _print_grouped_section(
            "[SUGGESTED]",
            sorted(suggested),
            lambda r: f"- {r[0]}:{r[1]}: `{r[2]}` -> `{r[3]}`",
        )
        printed_any_section = True

    if ambiguous:
        if printed_any_section:
            print()
        def _render_amb(r: tuple) -> str:
            src, lineno, old, candidates = r
            sample = ", ".join(candidates[:5])
            more = " ..." if len(candidates) > 5 else ""
            return f"- {src}:{lineno}: `{old}` -> {sample}{more}"
        _print_grouped_section(
            "[AMBIGUOUS REFS]",
            sorted(ambiguous),
            _render_amb,
        )
        printed_any_section = True

    if broken:
        if printed_any_section:
            print()
        _print_grouped_section(
            "[BROKEN MD REFS]",
            sorted(broken),
            lambda r: f"- {r[0]}:{r[1]}: `{r[2]}` -> {r[3]}",
        )
        printed_any_section = True

    if broken or ambiguous:
        if printed_any_section:
            print()
        print("STATUS: FAIL")
        print()
        print(f"checked_md_files={len(md_files)}")
        print(f"parsed_refs={total_refs}")
        print(f"checked_refs={checked_refs}")
        if fixed:
            print(f"auto_fixed={len(fixed)}")
        if suggested:
            print(f"suggested={len(suggested)}")
        if ambiguous:
            print(f"ambiguous={len(ambiguous)}")
        return 2 if args.strict else 0
    if suggested:
        if printed_any_section:
            print()
        print("STATUS: WARN")
        print()
        print(f"checked_md_files={len(md_files)}")
        print(f"parsed_refs={total_refs}")
        print(f"checked_refs={checked_refs}")
        if fixed:
            print(f"auto_fixed={len(fixed)}")
        print(f"suggested={len(suggested)}")
        return 2 if args.strict else 0

    if printed_any_section:
        print()
    print("STATUS: PASS")
    print()
    print(f"checked_md_files={len(md_files)}")
    print(f"parsed_refs={total_refs}")
    print(f"checked_refs={checked_refs}")
    if fixed:
        print(f"auto_fixed={len(fixed)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
