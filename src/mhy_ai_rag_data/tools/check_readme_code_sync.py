#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_readme_code_sync

Gate: README <-> code alignment for tools/.

Inputs
  - SSOT config: docs/reference/readme_code_sync.yaml
  - Mapping index: docs/reference/readme_code_sync_index.yaml

Checks (FAIL => exit code 2)
  1) frontmatter_present
  2) frontmatter_required_keys
  3) auto_block_markers_well_formed
  4) options_match_when_present (AUTO options block must match generated content when present)
  5) output_contract_match_when_present (AUTO output-contract block must match generated content when present)
  6) artifacts_match_when_present (AUTO artifacts block must match generated content when present)
  7) output_contract_refs_when_v2 (minimal: require the v2 contract tag to be present in frontmatter or body)

Notes
  - --check focuses on structural validity + minimal signals.
  - --write regenerates (and inserts) deterministic AUTO blocks to reduce drift.
  - Markers are treated as standalone lines (avoid triggering on examples in code blocks).

Exit codes
  0 PASS
  2 FAIL (contract violation)
  3 ERROR (unhandled exception)
"""

from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import json
import re
import time
import traceback
from dataclasses import dataclass

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
from mhy_ai_rag_data.tools.report_contract import ensure_report_v2
from mhy_ai_rag_data.tools.report_render import render_console
from mhy_ai_rag_data.tools.selftest_utils import add_selftest_args, maybe_run_selftest_from_args


# Tool self-description for report-output-v2 gates (static-AST friendly)
REPORT_TOOL_META = {
    "id": "check_readme_code_sync",
    "kind": "CHECK_REPORT",
    "contract_version": 2,
    "channels": ["file", "console"],
    "high_cost": False,
    "supports_selftest": True,
    "entrypoint": "python tools/check_readme_code_sync.py",
}

DEFAULT_OUT = "data_processed/build_reports/readme_code_sync_report.json"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, max_bytes: int = 4 * 1024 * 1024) -> str:
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def split_front_matter(text: str) -> Tuple[Optional[str], str]:
    """Return (frontmatter_yaml, body_text). frontmatter_yaml excludes the --- lines."""
    text = normalize_newlines(text)
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    lines = text.split("\n")
    if not lines:
        return None, ""

    if lines[0].strip() != "---":
        return None, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, ""

    fm = "\n".join(lines[1:end_idx]).strip() + "\n"
    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def load_yaml_dict(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def match_any(path_posix: str, patterns: List[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(path_posix, pat):
            return True
    return False


def collect_readmes(repo: Path, globs: List[str], excludes: List[str]) -> List[Path]:
    out: List[Path] = []
    for g in globs:
        for p in repo.glob(g):
            if not p.is_file():
                continue
            rel = p.relative_to(repo).as_posix()
            if excludes and match_any(rel, excludes):
                continue
            out.append(p)

    # de-dup + stable order
    seen: Set[str] = set()
    uniq: List[Path] = []
    for p in sorted(out, key=lambda x: x.as_posix()):
        rel = p.relative_to(repo).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        uniq.append(p)
    return uniq


def check_marker_pair(text: str, begin: str, end: str) -> Tuple[bool, str]:
    """Validate AUTO markers.

    IMPORTANT: markers are treated as standalone lines only.
    This avoids false positives when docs mention marker strings in backticks/code blocks.
    """
    lines = normalize_newlines(text).splitlines()
    bidx = [i for i, ln in enumerate(lines) if ln.strip() == begin]
    eidx = [i for i, ln in enumerate(lines) if ln.strip() == end]

    if not bidx and not eidx:
        return True, "absent"
    if len(bidx) != 1 or len(eidx) != 1:
        return False, f"marker count mismatch: begin={len(bidx)} end={len(eidx)}"
    if eidx[0] < bidx[0]:
        return False, "marker order invalid"
    return True, "ok"


def extract_auto_block(text: str, begin: str, end: str) -> Optional[str]:
    lines = normalize_newlines(text).splitlines()
    bidx = [i for i, ln in enumerate(lines) if ln.strip() == begin]
    eidx = [i for i, ln in enumerate(lines) if ln.strip() == end]
    if len(bidx) != 1 or len(eidx) != 1:
        return None
    if eidx[0] < bidx[0]:
        return None
    inner = "\n".join(lines[bidx[0] + 1 : eidx[0]])
    if inner and not inner.endswith("\n"):
        inner += "\n"
    return inner


FLAG_RE = re.compile(r"(?<![\w-])(--[A-Za-z0-9][A-Za-z0-9_-]*)(?![\w-])")


def extract_flags_from_text(s: str) -> Set[str]:
    return set(FLAG_RE.findall(s or ""))


def module_to_file(repo: Path, module: str) -> Path:
    return repo / "src" / (module.replace(".", "/") + ".py")


def extract_argparse_flags_from_file(path: Path) -> Set[str]:
    """Best-effort static extraction for argparse parser.add_argument calls."""
    text = read_text(path)
    if not text:
        return set()

    try:
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return set()

    flags: Set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr != "add_argument":
            continue

        for a in node.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                v = a.value.strip()
                if v.startswith("--"):
                    flags.add(v)

    flags.discard("--help")
    return flags


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def _stable_json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_value_repr(v: Any) -> str:
    if isinstance(v, (type(None), bool, int, float, str)):
        return repr(v)
    if isinstance(v, (list, dict)):
        return _stable_json(v)
    return repr(v)


def _try_literal_eval(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


@dataclass(frozen=True)
class ArgparseOption:
    flags: Tuple[str, ...]
    required: Optional[bool]
    default_repr: Optional[str]
    action: Optional[str]
    type_repr: Optional[str]
    nargs_repr: Optional[str]
    help: Optional[str]

    @property
    def sort_key(self) -> str:
        return self.flags[0] if self.flags else ""


def extract_argparse_options_from_file(path: Path) -> List[ArgparseOption]:
    """Best-effort static extraction for argparse parser.add_argument calls.

    Only long flags (`--flag`) are extracted; positional args are ignored.
    """
    text = read_text(path)
    if not text:
        return []

    try:
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return []

    out: List[ArgparseOption] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr != "add_argument":
            continue

        flags: List[str] = []
        for a in node.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                v = a.value.strip()
                if v.startswith("--"):
                    flags.append(v)
        if not flags:
            continue

        kw: Dict[str, ast.AST] = {}
        for k in node.keywords or []:
            if not isinstance(k, ast.keyword) or not isinstance(k.arg, str) or k.value is None:
                continue
            kw[k.arg] = k.value

        required_val: Optional[bool] = None
        if "required" in kw:
            lit = _try_literal_eval(kw["required"])
            if isinstance(lit, bool):
                required_val = lit

        default_repr: Optional[str] = None
        if "default" in kw:
            lit = _try_literal_eval(kw["default"])
            default_repr = _stable_value_repr(lit) if lit is not None else _safe_unparse(kw["default"])

        action: Optional[str] = None
        if "action" in kw:
            lit = _try_literal_eval(kw["action"])
            action = str(lit) if isinstance(lit, str) else _safe_unparse(kw["action"])

        type_repr: Optional[str] = None
        if "type" in kw:
            lit = _try_literal_eval(kw["type"])
            type_repr = _stable_value_repr(lit) if lit is not None else _safe_unparse(kw["type"])

        nargs_repr: Optional[str] = None
        if "nargs" in kw:
            lit = _try_literal_eval(kw["nargs"])
            nargs_repr = _stable_value_repr(lit) if lit is not None else _safe_unparse(kw["nargs"])

        help_text: Optional[str] = None
        if "help" in kw:
            lit = _try_literal_eval(kw["help"])
            help_text = str(lit) if isinstance(lit, str) else _safe_unparse(kw["help"])

        out.append(
            ArgparseOption(
                flags=tuple(flags),
                required=required_val,
                default_repr=default_repr,
                action=action,
                type_repr=type_repr,
                nargs_repr=nargs_repr,
                help=help_text,
            )
        )

    return sorted(out, key=lambda x: (x.sort_key, x.flags))


def _escape_md_table_cell(s: str) -> str:
    return (s or "").replace("\n", " ").replace("|", "\\|").strip()


def build_options_block_from_ast(opts: List[ArgparseOption], *, sort_flags: str = "lexicographic") -> str:
    if not opts:
        return "_(no long flags detected by static AST)_\n"

    rows: List[Tuple[str, ArgparseOption]] = []
    for opt in opts:
        flags = sorted(opt.flags) if sort_flags == "lexicographic" else list(opt.flags)
        rows.append((flags[0] if flags else "", opt))
    rows.sort(key=lambda x: x[0])

    out: List[str] = []
    out.append("| Flag | Required | Default | Notes |")
    out.append("|---|---:|---|---|")

    for _, opt in rows:
        flags = sorted(opt.flags) if sort_flags == "lexicographic" else list(opt.flags)
        flags_cell = " ".join(f"`{_escape_md_table_cell(f)}`" for f in flags)
        req_cell = "true" if opt.required is True else ("false" if opt.required is False else "—")
        default_cell = _escape_md_table_cell(opt.default_repr or "—")

        notes_parts: List[str] = []
        if opt.action:
            notes_parts.append(f"action={_escape_md_table_cell(opt.action)}")
        if opt.type_repr:
            notes_parts.append(f"type={_escape_md_table_cell(opt.type_repr)}")
        if opt.nargs_repr:
            notes_parts.append(f"nargs={_escape_md_table_cell(opt.nargs_repr)}")
        if opt.help:
            notes_parts.append(_escape_md_table_cell(opt.help))
        notes_cell = "；".join([p for p in notes_parts if p]) or "—"

        out.append(f"| {flags_cell} | {req_cell} | {default_cell} | {notes_cell} |")

    return "\n".join(out).rstrip() + "\n"


def _normalize_block_content(s: str) -> str:
    s = normalize_newlines(s or "")
    if s and not s.endswith("\n"):
        s += "\n"
    return s


def _diff_blocks(expected: str, actual: str) -> str:
    want = _normalize_block_content(expected)
    got = _normalize_block_content(actual)
    return "\n".join(
        difflib.unified_diff(
            want.splitlines(),
            got.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )


def _detect_has_out_flag_from_opts(opts: List[ArgparseOption]) -> bool:
    for opt in opts:
        if "--out" in opt.flags:
            return True
    return False


def extract_default_out_from_file(path: Path) -> Optional[str]:
    """Try to extract DEFAULT_OUT = "..." from a module file."""
    text = read_text(path)
    if not text:
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "DEFAULT_OUT":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "DEFAULT_OUT":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    return None


def _load_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_report_tools_registry(repo: Path) -> Dict[str, Any]:
    """Load docs/reference/report_tools_registry.toml (best-effort)."""
    return _load_toml(repo / "docs/reference/report_tools_registry.toml")


def registry_entry_for_tool(registry: Dict[str, Any], tool_id: str) -> Optional[Dict[str, Any]]:
    tools = registry.get("tool")
    if not isinstance(tools, list):
        return None
    for t in tools:
        if not isinstance(t, dict):
            continue
        if str(t.get("id") or "") == tool_id:
            return t
    return None


def build_options_block_from_flags(flags: Set[str]) -> str:
    """Deprecated: keep for backward compatibility; prefer AST table generation."""
    if not flags:
        return "_(no long flags detected)_\n"
    lines = ["| Flag |", "|---|"]
    for f in sorted(flags):
        lines.append(f"| `{f}` |")
    return "\n".join(lines) + "\n"


def build_options_block(
    *,
    gen_mode: str,
    code_path: Optional[Path],
    sort_flags: str = "lexicographic",
) -> Tuple[str, Set[str], bool]:
    """Return (options_md, flags, has_out_flag) with deterministic output."""
    if gen_mode != "static-ast":
        s = f"_(generation.options={gen_mode!r}; not generated by static-ast)_\n"
        return s, set(), False
    if code_path is None or not code_path.exists():
        return "_(impl source missing; cannot extract argparse options)_\n", set(), False

    opts = extract_argparse_options_from_file(code_path)
    flags: Set[str] = set()
    for o in opts:
        for f in o.flags:
            if f.startswith("--"):
                flags.add(f)
    flags.discard("--help")

    md = build_options_block_from_ast(opts, sort_flags=sort_flags)
    return md, flags, _detect_has_out_flag_from_opts(opts)


def build_output_contract_block(*, contracts_output: str, default_out: Optional[str], has_out_flag: bool) -> str:
    lines: List[str] = []
    lines.append(f"- `contracts.output`: `{contracts_output}`")
    if contracts_output == "report-output-v2":
        lines.append("- `schema_version`: `2`")
        if default_out:
            md_out = default_out[:-5] + ".md" if default_out.endswith(".json") else (default_out + ".md")
            lines.append(f"- 默认输出: `{default_out}`（JSON） + `{md_out}`（Markdown）")
        if has_out_flag:
            lines.append('- 关闭落盘: `--out ""`（空字符串）')
        lines.append("- 规则 SSOT: `docs/reference/REPORT_OUTPUT_ENGINEERING_RULES.md`")
        lines.append("- 工具登记 SSOT: `docs/reference/report_tools_registry.toml`")
    return "\n".join(lines) + "\n"


def build_artifacts_block(
    *, contracts_output: str, registry_entry: Optional[Dict[str, Any]], default_out: Optional[str]
) -> str:
    lines: List[str] = []
    if registry_entry and isinstance(registry_entry.get("artifacts"), list):
        lines.append("- artifacts（registry）：")
        for a in registry_entry.get("artifacts") or []:
            if isinstance(a, str):
                lines.append(f"  - `{a}`")
    elif contracts_output == "report-output-v2" and default_out:
        md_out = default_out[:-5] + ".md" if default_out.endswith(".json") else (default_out + ".md")
        lines.append("- artifacts（推断自 DEFAULT_OUT）：")
        lines.append(f"  - `{default_out}`")
        lines.append(f"  - `{md_out}`")
    else:
        lines.append("（无可机读 artifacts 信息。）")

    return "\n".join(lines) + "\n"


AUTO_SECTION_H2 = "## 自动生成区块（AUTO）"
AUTO_SECTION_H2_LEGACY = "## 自动生成参考（README↔源码对齐）"


def generate_auto_section(
    *,
    tool_id: str,
    entrypoints: List[str],
    markers: Dict[str, Any],
    options_md: str,
    output_contract_md: str,
    artifacts_md: str,
) -> str:
    def _mk(name: str) -> Tuple[str, str]:
        spec = markers.get(name) if isinstance(markers, dict) else None
        spec = spec if isinstance(spec, dict) else {}
        b = str(spec.get("begin") or "")
        e = str(spec.get("end") or "")
        return b, e

    ob, oe = _mk("options")
    cb, ce = _mk("output_contract")
    ab, ae = _mk("artifacts")

    lines: List[str] = []
    lines.append(AUTO_SECTION_H2)
    lines.append("")
    lines.append(
        "> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。"
    )
    if tool_id:
        lines.append(f"> tool_id: `{tool_id}`")
    if entrypoints:
        eps = ", ".join(f"`{x}`" for x in entrypoints)
        lines.append(f"> entrypoints: {eps}")
    lines.append("")

    # options
    if ob and oe:
        lines.append(ob)
        lines.append(options_md.rstrip())
        lines.append(oe)
        lines.append("")

    # output contract
    if cb and ce:
        lines.append(cb)
        lines.append(output_contract_md.rstrip())
        lines.append(ce)
        lines.append("")

    # artifacts
    if ab and ae:
        lines.append(ab)
        lines.append(artifacts_md.rstrip())
        lines.append(ae)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def strip_existing_auto_section(text: str) -> str:
    t = normalize_newlines(text)
    if t.startswith("\ufeff"):
        t = t.lstrip("\ufeff")
    # normalize trailing newlines
    t = t.rstrip("\n") + "\n"

    idxs = []
    for h2 in [AUTO_SECTION_H2, AUTO_SECTION_H2_LEGACY]:
        j = t.find("\n" + h2)
        if j != -1:
            idxs.append(j)
    idx = min(idxs) if idxs else -1
    if idx == -1:
        if t.startswith(AUTO_SECTION_H2) or t.startswith(AUTO_SECTION_H2_LEGACY):
            idx = 0
        else:
            return t

    prefix = t[:idx].rstrip()
    if prefix.endswith("\n---"):
        prefix = prefix[: -len("\n---")].rstrip()
    return prefix.rstrip("\n") + "\n"


def apply_auto_section(text: str, section: str) -> str:
    base = strip_existing_auto_section(text).rstrip("\n")
    sec = section.strip("\n")
    if base:
        return base + "\n\n---\n\n" + sec + "\n"
    return sec + "\n"


def _block_present(text: str, begin: str, end: str) -> bool:
    ok, msg = check_marker_pair(text, begin, end)
    return ok and msg != "absent"


def _load_exceptions(repo: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    ex_rel = nested_get(as_dict(cfg.get("exceptions")), "path")
    if not isinstance(ex_rel, str) or not ex_rel:
        return {}
    ex_path = (repo / ex_rel).resolve()
    if not ex_path.exists():
        return {}
    try:
        obj = yaml.safe_load(ex_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _is_skip_by_exception(ex: Dict[str, Any], rel: str, check: str) -> bool:
    items = ex.get("exceptions") or []
    if not isinstance(items, list):
        return False
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("path") or "") != rel:
            continue
        checks = it.get("checks") or {}
        if not isinstance(checks, dict):
            continue
        skip = checks.get("skip") or []
        if isinstance(skip, list) and check in [str(x) for x in skip]:
            return True
    return False


def _render_block(begin: str, end: str, inner: str) -> str:
    inner = _normalize_block_content(inner)
    return f"{begin}\n{inner}{end}\n"


def _replace_block(text: str, begin: str, end: str, new_inner: str) -> Tuple[str, bool]:
    text = normalize_newlines(text)
    lines = text.splitlines()

    bidx = [i for i, ln in enumerate(lines) if ln.strip() == begin]
    eidx = [i for i, ln in enumerate(lines) if ln.strip() == end]
    if len(bidx) != 1 or len(eidx) != 1:
        return text, False
    bi, ei = bidx[0], eidx[0]
    if ei < bi:
        return text, False

    new_lines = list(lines[: bi + 1])
    inner = _normalize_block_content(new_inner)
    new_lines.extend(inner.splitlines())
    new_lines.extend(lines[ei:])
    new_text = "\n".join(new_lines) + "\n"
    return new_text, new_text != text


def _append_missing_blocks(text: str, blocks: List[str], *, with_heading: bool) -> Tuple[str, bool]:
    text = normalize_newlines(text)
    if not text.endswith("\n"):
        text += "\n"

    chunks: List[str] = []
    if with_heading:
        chunks.append(f"{AUTO_SECTION_H2}\n")
    chunks.extend(blocks)
    payload = "\n".join([c.rstrip("\n") for c in chunks]).rstrip("\n") + "\n"

    if not text.endswith("\n\n"):
        text += "\n"

    return (text + payload), True


def _insert_blocks_after_last_marker_end(
    text: str,
    *,
    end_markers: Set[str],
    blocks: List[str],
    with_heading: bool,
) -> Tuple[str, bool]:
    """Insert blocks right after the last existing AUTO:END marker (standalone line)."""
    text = normalize_newlines(text)
    lines = text.splitlines()
    last = -1
    for i, ln in enumerate(lines):
        if ln.strip() in end_markers:
            last = i
    if last == -1:
        return _append_missing_blocks(text, blocks, with_heading=with_heading)

    insert_lines: List[str] = []
    if with_heading:
        insert_lines.append(AUTO_SECTION_H2)
    for b in blocks:
        insert_lines.extend(normalize_newlines(b).splitlines())

    new_lines = list(lines[: last + 1])
    if new_lines and new_lines[-1].strip() != "":
        new_lines.append("")
    new_lines.extend(insert_lines)
    if insert_lines and insert_lines[-1].strip() != "":
        new_lines.append("")
    new_lines.extend(lines[last + 1 :])
    return ("\n".join(new_lines) + "\n"), True


def as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def nested_get(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _resolve_impl_source(
    repo: Path, idx_entry: Optional[Dict[str, Any]], fm: Optional[Dict[str, Any]]
) -> Optional[Path]:
    """Resolve a usable source file path for static AST extraction.

    Precedence:
      1) impl.module -> src/<module>.py
      2) impl.wrapper -> <repo>/<wrapper>
    """
    mod = None
    wrapper = None
    if idx_entry:
        mod = nested_get(as_dict(idx_entry.get("impl")), "module")
        wrapper = nested_get(as_dict(idx_entry.get("impl")), "wrapper")
    if fm:
        mod = nested_get(as_dict(fm.get("impl")), "module") or mod
        wrapper = nested_get(as_dict(fm.get("impl")), "wrapper") or wrapper

    if isinstance(mod, str) and mod:
        p = module_to_file(repo, mod)
        if p.exists():
            return p
    if isinstance(wrapper, str) and wrapper:
        p = (repo / wrapper).resolve()
        if p.exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate: tools/ README <-> code alignment.")
    add_selftest_args(ap)
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument("--check", action="store_true", help="Only check consistency (default).")
    mx.add_argument("--write", action="store_true", help="Rewrite/insert deterministic AUTO blocks.")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--config", default="docs/reference/readme_code_sync.yaml", help="SSOT config path")
    ap.add_argument("--index", default="docs/reference/readme_code_sync_index.yaml", help="Mapping index path")
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        nargs="?",
        const="",
        help="Write report-output-v2 JSON to this path (relative to repo root). Empty -> no JSON.",
    )
    args = ap.parse_args()

    # Default mode is --check if user did not specify either.
    if not getattr(args, "check", False) and not getattr(args, "write", False):
        args.check = True

    repo = Path(getattr(args, "root", ".")).resolve()
    loc = Path(__file__).resolve()
    try:
        loc = loc.relative_to(repo)
    except Exception:
        pass

    rc = maybe_run_selftest_from_args(args=args, meta=REPORT_TOOL_META, repo_root=repo, loc_source=loc)
    if rc is not None:
        return rc

    try:
        cfg_path = (repo / args.config).resolve()
        idx_path = (repo / args.index).resolve()

        cfg = load_yaml_dict(cfg_path)
        exceptions = _load_exceptions(repo, cfg)
        globs = list(as_dict(cfg.get("scope")).get("readme_globs") or [])
        excludes = list(as_dict(cfg.get("scope")).get("exclude_globs") or [])

        fm_req = list(as_dict(cfg.get("frontmatter")).get("required_keys") or [])
        markers = as_dict(cfg.get("auto_blocks")).get("markers") or {}
        enforce = list(as_dict(cfg.get("checks")).get("enforce") or [])
        norm = as_dict(cfg.get("normalization") or {})
        sort_flags = str(norm.get("sort_flags") or "lexicographic")

        index_map: Dict[str, Dict[str, Any]] = {}
        if idx_path.exists():
            idx = load_yaml_dict(idx_path)
            for item in idx.get("readmes") or []:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    index_map[item["path"]] = item

        readmes = collect_readmes(repo, globs=globs, excludes=excludes)

        if getattr(args, "write", False):
            registry = load_report_tools_registry(repo)

            write_items: List[Dict[str, Any]] = []
            changed = 0

            for p_readme in readmes:
                rel = p_readme.relative_to(repo).as_posix()
                raw = read_text(p_readme)
                raw_nl = normalize_newlines(raw)

                idx_entry = index_map.get(rel)

                fm_yaml, body = split_front_matter(raw_nl)
                if fm_yaml is None:
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "frontmatter_missing",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"{rel}: missing YAML frontmatter; cannot write AUTO section",
                            "detail": {"file": rel},
                        }
                    )
                    continue

                try:
                    fm_parsed = yaml.safe_load(fm_yaml)
                    frontmatter = fm_parsed if isinstance(fm_parsed, dict) else {}
                except Exception as exc:
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "frontmatter_parse_error",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"{rel}: frontmatter parse error; cannot write AUTO section",
                            "detail": {"file": rel, "error": repr(exc)},
                        }
                    )
                    continue

                missing = [k for k in fm_req if k not in frontmatter]
                if missing:
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "frontmatter_required_keys_missing",
                            "status_label": "FAIL",
                            "severity_level": 3,
                            "message": f"{rel}: missing required frontmatter keys: {missing}",
                            "detail": {"file": rel, "missing": missing},
                        }
                    )
                    continue

                if not idx_entry:
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "mapping_missing",
                            "status_label": "INFO",
                            "severity_level": 1,
                            "message": f"{rel}: no mapping in index; AUTO section skipped",
                            "detail": {"file": rel},
                        }
                    )
                    continue

                mapping_status = str(idx_entry.get("mapping_status") or frontmatter.get("mapping_status") or "")
                if mapping_status and mapping_status != "ok":
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "mapping_not_ok",
                            "status_label": "WARN",
                            "severity_level": 2,
                            "message": f"{rel}: mapping_status={mapping_status}; AUTO section skipped",
                            "detail": {"file": rel, "mapping_status": mapping_status},
                        }
                    )
                    continue

                tool_id = str(idx_entry.get("tool_id") or frontmatter.get("tool_id") or "")

                contracts_output = str(
                    nested_get(as_dict(idx_entry.get("contracts")), "output")
                    or nested_get(as_dict(frontmatter.get("contracts")), "output")
                    or "none"
                )

                gen_mode = nested_get(as_dict(idx_entry.get("generation")), "options") or nested_get(
                    as_dict(frontmatter.get("generation")), "options"
                )
                gen_mode = str(gen_mode or "static-ast")

                default_out: Optional[str] = None
                code_path = _resolve_impl_source(repo, idx_entry, frontmatter)
                if code_path is not None:
                    default_out = extract_default_out_from_file(code_path)

                options_md, _, has_out_flag = build_options_block(
                    gen_mode=gen_mode, code_path=code_path, sort_flags=sort_flags
                )

                output_contract_md = build_output_contract_block(
                    contracts_output=contracts_output,
                    default_out=default_out,
                    has_out_flag=has_out_flag,
                )

                reg_entry = registry_entry_for_tool(registry, tool_id) if tool_id else None
                artifacts_md = build_artifacts_block(
                    contracts_output=contracts_output,
                    registry_entry=reg_entry,
                    default_out=default_out,
                )
                marker_specs = markers if isinstance(markers, dict) else {}
                blocks_to_append: List[str] = []
                any_existing_marker = False
                wrote_any = False
                seen_end_markers: Set[str] = set()

                def _spec(name: str) -> Tuple[str, str]:
                    s = marker_specs.get(name)
                    s = s if isinstance(s, dict) else {}
                    return (str(s.get("begin") or ""), str(s.get("end") or ""))

                for name, inner in [
                    ("options", options_md),
                    ("output_contract", output_contract_md),
                    ("artifacts", artifacts_md),
                ]:
                    begin_marker, end_marker = _spec(name)
                    if not begin_marker or not end_marker:
                        continue
                    ok, msg = check_marker_pair(raw_nl, begin_marker, end_marker)
                    if not ok and msg != "absent":
                        write_items.append(
                            {
                                "tool": "check_readme_code_sync",
                                "title": "auto_block_marker_invalid",
                                "status_label": "FAIL",
                                "severity_level": 3,
                                "message": f"{rel}: marker invalid for block={name}",
                                "detail": {"file": rel, "block": name, "detail": msg},
                            }
                        )
                        wrote_any = False
                        blocks_to_append = []
                        break

                    if msg == "absent":
                        blocks_to_append.append(_render_block(begin_marker, end_marker, inner).rstrip("\n"))
                    else:
                        any_existing_marker = True
                        seen_end_markers.add(end_marker)
                        raw_nl, did = _replace_block(raw_nl, begin_marker, end_marker, inner)
                        wrote_any = wrote_any or did

                if blocks_to_append:
                    raw_nl, _ = _insert_blocks_after_last_marker_end(
                        raw_nl,
                        end_markers=seen_end_markers,
                        blocks=blocks_to_append,
                        with_heading=not any_existing_marker,
                    )
                    wrote_any = True

                if wrote_any:
                    p_readme.write_text(raw_nl, encoding="utf-8")
                    changed += 1
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "auto_blocks_written",
                            "status_label": "INFO",
                            "severity_level": 1,
                            "message": f"{rel}: AUTO blocks written",
                            "detail": {"file": rel, "tool_id": tool_id},
                        }
                    )
                else:
                    write_items.append(
                        {
                            "tool": "check_readme_code_sync",
                            "title": "auto_blocks_up_to_date",
                            "status_label": "PASS",
                            "severity_level": 0,
                            "message": f"{rel}: AUTO blocks up-to-date",
                            "detail": {"file": rel, "tool_id": tool_id},
                        }
                    )

            write_items.append(
                {
                    "tool": "check_readme_code_sync",
                    "title": "write_summary",
                    "status_label": "INFO" if changed else "PASS",
                    "severity_level": 1 if changed else 0,
                    "message": f"write_mode: changed={changed} readmes={len(readmes)}",
                    "detail": {"changed": changed, "readmes": len(readmes)},
                }
            )

            report_v2 = {
                "schema_version": 2,
                "generated_at": now_iso(),
                "tool": "check_readme_code_sync",
                "root": repo.as_posix(),
                "summary": {"mode": "write"},
                "items": write_items,
                "data": {
                    "config": args.config,
                    "index": args.index,
                },
            }

            out_arg = str(getattr(args, "out", "") or "").strip()
            if out_arg:
                report_path = (repo / out_arg).resolve()
                ensure_dir(report_path.parent)
                write_report_bundle(
                    report=report_v2,
                    report_json=report_path,
                    repo_root=repo,
                    console_title="check_readme_code_sync",
                    emit_console=True,
                )
            else:
                v2 = ensure_report_v2(report_v2)
                print(render_console(v2, title="check_readme_code_sync"), end="")

            return 2 if any(it.get("status_label") == "FAIL" for it in write_items) else 0

        issues: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        for p in readmes:
            rel = p.relative_to(repo).as_posix()
            raw = read_text(p)
            raw_nl = normalize_newlines(raw)

            idx_entry = index_map.get(rel)
            idxd: Dict[str, Any] = idx_entry if isinstance(idx_entry, dict) else {}

            fm_yaml, body = split_front_matter(raw_nl)
            fm: Dict[str, Any] = {}
            if fm_yaml is None:
                if "frontmatter_present" in enforce:
                    issues.append(
                        {
                            "type": "frontmatter_missing",
                            "file": rel,
                            "detail": "missing YAML frontmatter (--- ... ---) at the top of file",
                        }
                    )
            else:
                try:
                    parsed = yaml.safe_load(fm_yaml)
                    if isinstance(parsed, dict):
                        fm = parsed
                    else:
                        fm = {}
                except Exception as exc:
                    issues.append(
                        {
                            "type": "frontmatter_parse_error",
                            "file": rel,
                            "detail": f"frontmatter YAML parse error: {exc!r}",
                        }
                    )

            if fm and "frontmatter_required_keys" in enforce:
                missing = [k for k in fm_req if k not in fm]
                if missing:
                    issues.append(
                        {
                            "type": "frontmatter_required_keys_missing",
                            "file": rel,
                            "detail": f"missing required keys: {missing}",
                        }
                    )

            # Marker checks are always based on the whole file text.
            if "auto_block_markers_well_formed" in enforce and isinstance(markers, dict):
                for name, spec in markers.items():
                    if not isinstance(spec, dict):
                        continue
                    begin = str(spec.get("begin") or "")
                    end = str(spec.get("end") or "")
                    if not begin or not end:
                        continue
                    ok, msg = check_marker_pair(raw_nl, begin, end)
                    if not ok:
                        issues.append(
                            {
                                "type": "auto_block_marker_invalid",
                                "file": rel,
                                "block": name,
                                "detail": msg,
                            }
                        )

            # Code-based checks require usable mapping.
            mapping_status_opt: Optional[str] = None
            if isinstance(idxd.get("mapping_status"), str):
                mapping_status_opt = str(idxd.get("mapping_status"))
            if isinstance(fm.get("mapping_status"), str):
                mapping_status_opt = str(fm.get("mapping_status"))

            mapping_ok = (mapping_status_opt is None) or (mapping_status_opt == "ok")

            # options_match_when_present
            if "options_match_when_present" in enforce and isinstance(markers, dict):
                opt_spec = as_dict(markers.get("options"))
                begin = str(opt_spec.get("begin") or "")
                end = str(opt_spec.get("end") or "")

                if begin and end and _block_present(raw_nl, begin, end):
                    if _is_skip_by_exception(exceptions, rel, "options"):
                        warnings.append(
                            {
                                "type": "options_check_skipped",
                                "file": rel,
                                "detail": "skipped by exceptions",
                            }
                        )
                    elif not mapping_ok:
                        warnings.append(
                            {
                                "type": "options_check_skipped",
                                "file": rel,
                                "detail": f"mapping_status={mapping_status_opt}; options check skipped",
                            }
                        )
                    else:
                        block = extract_auto_block(raw_nl, begin, end)
                        if block is None:
                            pass
                        else:
                            gen_mode = str(
                                nested_get(as_dict(idxd.get("generation")), "options")
                                or nested_get(as_dict(fm.get("generation")), "options")
                                or "static-ast"
                            )
                            code_path = _resolve_impl_source(repo, idx_entry, fm) if gen_mode == "static-ast" else None
                            if gen_mode == "static-ast" and code_path is None:
                                issues.append(
                                    {
                                        "type": "options_source_missing",
                                        "file": rel,
                                        "detail": f"generation.options={gen_mode!r} requires impl.module or impl.wrapper (existing file)",
                                    }
                                )

                            expected_md, _, _ = build_options_block(
                                gen_mode=gen_mode, code_path=code_path, sort_flags=sort_flags
                            )
                            if _normalize_block_content(block) != _normalize_block_content(expected_md):
                                issues.append(
                                    {
                                        "type": "options_block_mismatch",
                                        "file": rel,
                                        "detail": "AUTO options block content does not match generated output",
                                        "diff": _diff_blocks(expected_md, block)[:8000],
                                    }
                                )

            # output_contract_match_when_present
            if "output_contract_match_when_present" in enforce and isinstance(markers, dict):
                spec = as_dict(markers.get("output_contract"))
                begin = str(spec.get("begin") or "")
                end = str(spec.get("end") or "")

                if begin and end and _block_present(raw_nl, begin, end):
                    if _is_skip_by_exception(exceptions, rel, "output_contract"):
                        warnings.append(
                            {
                                "type": "output_contract_check_skipped",
                                "file": rel,
                                "detail": "skipped by exceptions",
                            }
                        )
                    elif not mapping_ok:
                        warnings.append(
                            {
                                "type": "output_contract_check_skipped",
                                "file": rel,
                                "detail": f"mapping_status={mapping_status_opt}; output-contract check skipped",
                            }
                        )
                    else:
                        block = extract_auto_block(raw_nl, begin, end)
                        if block is not None:
                            contracts_output = str(
                                nested_get(as_dict(idxd.get("contracts")), "output")
                                or nested_get(as_dict(fm.get("contracts")), "output")
                                or "none"
                            )
                            src_path = _resolve_impl_source(repo, idx_entry, fm)
                            default_out = extract_default_out_from_file(src_path) if src_path is not None else None

                            gen_mode = str(
                                nested_get(as_dict(idxd.get("generation")), "options")
                                or nested_get(as_dict(fm.get("generation")), "options")
                                or "static-ast"
                            )
                            code_path = src_path if gen_mode == "static-ast" else None
                            _, _, has_out_flag = build_options_block(
                                gen_mode=gen_mode, code_path=code_path, sort_flags=sort_flags
                            )
                            expected = build_output_contract_block(
                                contracts_output=contracts_output,
                                default_out=default_out,
                                has_out_flag=has_out_flag,
                            )
                            if _normalize_block_content(block) != _normalize_block_content(expected):
                                issues.append(
                                    {
                                        "type": "output_contract_block_mismatch",
                                        "file": rel,
                                        "detail": "AUTO output-contract block content does not match generated output",
                                        "diff": _diff_blocks(expected, block)[:8000],
                                    }
                                )

            # artifacts_match_when_present
            if "artifacts_match_when_present" in enforce and isinstance(markers, dict):
                spec = as_dict(markers.get("artifacts"))
                begin = str(spec.get("begin") or "")
                end = str(spec.get("end") or "")

                if begin and end and _block_present(raw_nl, begin, end):
                    if _is_skip_by_exception(exceptions, rel, "artifacts"):
                        warnings.append(
                            {
                                "type": "artifacts_check_skipped",
                                "file": rel,
                                "detail": "skipped by exceptions",
                            }
                        )
                    elif not mapping_ok:
                        warnings.append(
                            {
                                "type": "artifacts_check_skipped",
                                "file": rel,
                                "detail": f"mapping_status={mapping_status_opt}; artifacts check skipped",
                            }
                        )
                    else:
                        block = extract_auto_block(raw_nl, begin, end)
                        if block is not None:
                            registry = load_report_tools_registry(repo)
                            tool_id = str(idxd.get("tool_id") or frontmatter.get("tool_id") or "")
                            reg_entry = registry_entry_for_tool(registry, tool_id) if tool_id else None

                            contracts_output = str(
                                nested_get(as_dict(idxd.get("contracts")), "output")
                                or nested_get(as_dict(fm.get("contracts")), "output")
                                or "none"
                            )
                            src_path = _resolve_impl_source(repo, idx_entry, fm)
                            default_out = extract_default_out_from_file(src_path) if src_path is not None else None

                            expected = build_artifacts_block(
                                contracts_output=contracts_output,
                                registry_entry=reg_entry,
                                default_out=default_out,
                            )
                            if _normalize_block_content(block) != _normalize_block_content(expected):
                                issues.append(
                                    {
                                        "type": "artifacts_block_mismatch",
                                        "file": rel,
                                        "detail": "AUTO artifacts block content does not match generated output",
                                        "diff": _diff_blocks(expected, block)[:8000],
                                    }
                                )

            # output_contract_refs_when_v2
            if "output_contract_refs_when_v2" in enforce:
                out_tag: Optional[str] = None
                out_tag = nested_get(as_dict(idxd.get("contracts")), "output")
                out_tag = nested_get(as_dict(fm.get("contracts")), "output") or out_tag

                if out_tag == "report-output-v2":
                    # Minimal signal requirement: either the tag appears in frontmatter or the body.
                    # (In Step 4 we will enforce richer, generated output-contract blocks.)
                    has_tag_in_fm = bool(
                        fm and nested_get(as_dict(fm.get("contracts")), "output") == "report-output-v2"
                    )
                    has_tag_in_body = "report-output-v2" in raw_nl
                    if not has_tag_in_fm and not has_tag_in_body:
                        issues.append(
                            {
                                "type": "output_contract_signal_missing",
                                "file": rel,
                                "detail": "contracts.output=report-output-v2 but no visible signal in README",
                            }
                        )

        status = "PASS" if not issues else "FAIL"
        exit_code = 0 if not issues else 2

        # v2 report bundle
        check_items: List[Dict[str, Any]] = []
        for w in warnings:
            check_items.append(
                {
                    "tool": "check_readme_code_sync",
                    "title": str(w.get("type") or "warning"),
                    "status_label": "WARN",
                    "severity_level": 2,
                    "message": f"{w.get('file')}: {w.get('detail', '')}",
                    "detail": w,
                }
            )
        for it in issues:
            check_items.append(
                {
                    "tool": "check_readme_code_sync",
                    "title": str(it.get("type") or "issue"),
                    "status_label": "FAIL",
                    "severity_level": 3,
                    "message": f"{it.get('file')}: {it.get('detail', it.get('type', ''))}",
                    "detail": it,
                }
            )

        report_v2 = {
            "schema_version": 2,
            "generated_at": now_iso(),
            "tool": "check_readme_code_sync",
            "root": repo.as_posix(),
            "summary": {
                "readmes": len(readmes),
                "warnings": len(warnings),
                "issues": len(issues),
                "status": status,
            },
            "items": check_items,
            "data": {
                "config": str(Path(args.config).as_posix()),
                "index": str(Path(args.index).as_posix()),
                "required_frontmatter_keys": fm_req,
                "enforce": enforce,
            },
        }

        out_arg = str(getattr(args, "out", "") or "").strip()
        if out_arg:
            out_path = (repo / out_arg).resolve()
            ensure_dir(out_path.parent)
            write_report_bundle(
                report=report_v2,
                report_json=out_path,
                repo_root=repo,
                console_title="check_readme_code_sync",
                emit_console=True,
            )
        else:
            v2 = ensure_report_v2(report_v2)
            print(render_console(v2, title="check_readme_code_sync"), end="")

        return exit_code

    except Exception as e:
        msg = f"unhandled exception: {e!r}"
        print("[check_readme_code_sync][ERROR]", msg)
        print(traceback.format_exc())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
