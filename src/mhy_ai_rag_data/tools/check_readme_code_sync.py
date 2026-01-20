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
  4) options_match_when_present (only when AUTO options block exists and mapping is usable)
  5) output_contract_refs_when_v2 (minimal: require the v2 contract tag to be present in frontmatter or body)

Notes
  - This tool is intentionally conservative in Step 3: it focuses on structural validity.
  - Step 4 will add --write to regenerate AUTO blocks.

Exit codes
  0 PASS
  2 FAIL (contract violation)
  3 ERROR (unhandled exception)
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from mhy_ai_rag_data.tools.report_bundle import write_report_bundle
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
    bc = text.count(begin)
    ec = text.count(end)

    if bc == 0 and ec == 0:
        return True, "absent"

    if bc != 1 or ec != 1:
        return False, f"marker count mismatch: begin={bc} end={ec}"

    bpos = text.find(begin)
    epos = text.find(end)
    if bpos < 0 or epos < 0 or epos < bpos:
        return False, "marker order invalid"

    return True, "ok"


def extract_auto_block(text: str, begin: str, end: str) -> Optional[str]:
    bpos = text.find(begin)
    epos = text.find(end)
    if bpos < 0 or epos < 0:
        return None
    if epos < bpos:
        return None
    return text[bpos + len(begin) : epos]


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


def as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def nested_get(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate: tools/ README <-> code alignment.")
    add_selftest_args(ap)
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument("--check", action="store_true", help="Only check consistency (default).")
    mx.add_argument("--write", action="store_true", help="Rewrite AUTO blocks (Step4+; not implemented in Step3).")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--config", default="docs/reference/readme_code_sync.yaml", help="SSOT config path")
    ap.add_argument("--index", default="docs/reference/readme_code_sync_index.yaml", help="Mapping index path")
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Write report-output-v2 JSON to this path (relative to repo root). Empty -> no JSON.",
    )
    args = ap.parse_args()

    # Default mode is --check if user did not specify either.
    if not getattr(args, "check", False) and not getattr(args, "write", False):
        args.check = True

    if getattr(args, "write", False):
        print("[check_readme_code_sync] --write is reserved for Step4+; current version is check-only.")
        return 3

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
        globs = list(as_dict(cfg.get("scope")).get("readme_globs") or [])
        excludes = list(as_dict(cfg.get("scope")).get("exclude_globs") or [])

        fm_req = list(as_dict(cfg.get("frontmatter")).get("required_keys") or [])
        markers = as_dict(cfg.get("auto_blocks")).get("markers") or {}
        enforce = list(as_dict(cfg.get("checks")).get("enforce") or [])

        index_map: Dict[str, Dict[str, Any]] = {}
        if idx_path.exists():
            idx = load_yaml_dict(idx_path)
            for item in idx.get("readmes") or []:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    index_map[item["path"]] = item

        readmes = collect_readmes(repo, globs=globs, excludes=excludes)

        issues: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        for p in readmes:
            rel = p.relative_to(repo).as_posix()
            raw = read_text(p)
            raw_nl = normalize_newlines(raw)

            idx_entry = index_map.get(rel)

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
                except Exception as e:
                    issues.append(
                        {
                            "type": "frontmatter_parse_error",
                            "file": rel,
                            "detail": f"frontmatter YAML parse error: {e!r}",
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
            mapping_status = None
            if idx_entry and isinstance(idx_entry.get("mapping_status"), str):
                mapping_status = idx_entry.get("mapping_status")
            if fm and isinstance(fm.get("mapping_status"), str):
                mapping_status = fm.get("mapping_status")

            mapping_ok = (mapping_status is None) or (mapping_status == "ok")

            # options_match_when_present
            if "options_match_when_present" in enforce and isinstance(markers, dict):
                opt_spec = as_dict(markers.get("options"))
                begin = str(opt_spec.get("begin") or "")
                end = str(opt_spec.get("end") or "")

                if begin and end and (begin in raw_nl):
                    if not mapping_ok:
                        warnings.append(
                            {
                                "type": "options_check_skipped",
                                "file": rel,
                                "detail": f"mapping_status={mapping_status}; options check skipped",
                            }
                        )
                    else:
                        block = extract_auto_block(raw_nl, begin, end)
                        if block is None:
                            # Marker pairing issues already handled above.
                            pass
                        else:
                            readme_flags = extract_flags_from_text(block)

                            # Determine extraction mode + module
                            gen_mode = None
                            mod = None
                            if idx_entry:
                                gen_mode = nested_get(as_dict(idx_entry.get("generation")), "options")
                                mod = nested_get(as_dict(idx_entry.get("impl")), "module")
                            if fm:
                                gen_mode = nested_get(as_dict(fm.get("generation")), "options") or gen_mode
                                mod = nested_get(as_dict(fm.get("impl")), "module") or mod

                            if gen_mode != "static-ast" or not isinstance(mod, str) or not mod:
                                warnings.append(
                                    {
                                        "type": "options_check_skipped",
                                        "file": rel,
                                        "detail": f"generation.options={gen_mode!r} impl.module={mod!r}; static-ast extraction not available",
                                    }
                                )
                            else:
                                code_path = module_to_file(repo, mod)
                                if not code_path.exists():
                                    warnings.append(
                                        {
                                            "type": "options_check_skipped",
                                            "file": rel,
                                            "detail": f"module file not found: {code_path.relative_to(repo).as_posix()}",
                                        }
                                    )
                                else:
                                    code_flags = extract_argparse_flags_from_file(code_path)
                                    if not code_flags:
                                        warnings.append(
                                            {
                                                "type": "options_check_low_confidence",
                                                "file": rel,
                                                "detail": "no flags extracted from code (argparse add_argument not found)",
                                            }
                                        )
                                    else:
                                        extra = sorted(readme_flags - code_flags)
                                        missing = sorted(code_flags - readme_flags)
                                        if extra or missing:
                                            issues.append(
                                                {
                                                    "type": "options_mismatch",
                                                    "file": rel,
                                                    "impl_module": mod,
                                                    "code_file": code_path.relative_to(repo).as_posix(),
                                                    "readme_flags": sorted(readme_flags),
                                                    "code_flags": sorted(code_flags),
                                                    "extra_in_readme": extra,
                                                    "missing_in_readme": missing,
                                                }
                                            )

            # output_contract_refs_when_v2
            if "output_contract_refs_when_v2" in enforce:
                out_tag = None
                if idx_entry:
                    out_tag = nested_get(as_dict(idx_entry.get("contracts")), "output")
                if fm:
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
        items: List[Dict[str, Any]] = []
        for w in warnings:
            items.append(
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
            items.append(
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
            "items": items,
            "data": {
                "config": str(Path(args.config).as_posix()),
                "index": str(Path(args.index).as_posix()),
                "required_frontmatter_keys": fm_req,
                "enforce": enforce,
            },
        }

        print(
            f"[check_readme_code_sync] readmes={len(readmes)} warnings={len(warnings)} issues={len(issues)} status={status}"
        )

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

        return exit_code

    except Exception as e:
        msg = f"unhandled exception: {e!r}"
        print("[check_readme_code_sync][ERROR]", msg)
        print(traceback.format_exc())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
