#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_order

目标
----
为“落盘报告（JSON）”提供统一的**人类可读顺序**与**可点击定位**：

1) 报告顶部优先出现“汇总块”（如 summary/metrics/counts/totals）。
2) 明细列表（如 results/cases/items）在落盘时优先把 FAIL/ERROR 放前、PASS 放后。
3) 对诊断定位（DIAG_LOC_FILE_LINE_COL）补充 `loc_uri`（`vscode://file/...:line:col`），
   让报告在 VS Code 里可直接点击跳转到文件行列。

说明
----
- 该模块只做**序列化顺序/展示辅助字段**调整：不改变字段语义；JSON 仍是合法对象。
- 仅用于“写文件”的 report（控制台输出的排序策略在另一个需求中处理）。

与 VS Code 的关系
-----------------
- `file:line:col` 在“终端输出”中常被自动识别，但在普通文本/JSON/Markdown 中并不稳定。
- 为了把行为从“启发式识别”升级为“确定的点击跳转”，本模块在落盘阶段生成：
  - `loc`（保留原显示串，便于 grep/复制）
  - `loc_uri`（`vscode://file/<abs_path>:line:col`，便于点击）

环境变量
--------
- `RAG_VSCODE_SCHEME`：默认 `vscode`；若用户用 VS Code Insiders，可设为 `vscode-insiders`。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import quote


# --- ordering knobs (file output) ---

# 认为是“汇总块”的 key：放到最前面（若存在）
SUMMARY_KEYS: Tuple[str, ...] = (
    "summary",
    "metrics",
    "buckets",
    "counts",
    "totals",
)

# 常见明细列表 key：这些 key 下的 list（若元素可判定 PASS/FAIL/ERROR）会被排序
DETAIL_LIST_KEYS: Tuple[str, ...] = (
    "results",
    "cases",
    "items",
    "checks",
)


STATUS_RANK_FILE: Dict[str, int] = {
    # 最严重放最前
    "ERROR": 0,
    "ERR": 0,
    "EXCEPTION": 0,
    "FAIL": 1,
    "FAILED": 1,
    "MISS": 1,
    "STALE": 1,
    "WARN": 2,
    "WARNING": 2,
    "SKIP": 3,
    "SKIPPED": 3,
    "PASS": 4,
    "OK": 4,
    "INFO": 5,
}


# --- path / loc helpers (file output) ---

# 这些 key 下的字符串通常表示“路径”（而不是正则/转义），落盘时统一转成 posix 分隔符。
PATH_KEY_HINTS: Tuple[str, ...] = (
    "root",
    "repo",
    "repo_root",
    "project_root",
    "ssot_path",
    "report_path",
    "log_path",
    "path",
    "file",
)

_WIN_DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")

# greedy: support Windows drive prefix `C:`
_LOC_WITH_MSG = re.compile(r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+):")
_LOC_BARE = re.compile(r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+)$")


def _norm_status(s: Any) -> str:
    return str(s or "").strip().upper()


def _rank_from_status(d: Mapping[str, Any]) -> Optional[int]:
    if "status" in d:
        return STATUS_RANK_FILE.get(_norm_status(d.get("status")))
    return None


def _rank_from_common_bools(d: Mapping[str, Any]) -> Optional[int]:
    """Heuristics for case-like entries.

    - eval_rag: passed / error / error_detail / llm_call_ok
    - eval_retrieval: hit_at_k
    """

    if "passed" in d:
        # error first
        if d.get("error") or d.get("error_detail") or (d.get("llm_call_ok") is False):
            return STATUS_RANK_FILE["ERROR"]
        if d.get("passed") is False:
            return STATUS_RANK_FILE["FAIL"]
        if d.get("passed") is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    if "hit_at_k" in d:
        v = d.get("hit_at_k")
        if v is False:
            return STATUS_RANK_FILE["FAIL"]
        if v is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    if "ok" in d:
        v = d.get("ok")
        if v is False:
            return STATUS_RANK_FILE["FAIL"]
        if v is True:
            return STATUS_RANK_FILE["PASS"]
        return None

    return None


def _rank_item(d: Mapping[str, Any]) -> Optional[int]:
    r = _rank_from_status(d)
    if r is not None:
        return r
    return _rank_from_common_bools(d)


def _should_sort_list(xs: List[Any]) -> bool:
    if not xs:
        return False
    # only attempt when most elements are dict-like
    ds = [x for x in xs if isinstance(x, Mapping)]
    if not ds:
        return False
    ranked = [d for d in ds if _rank_item(d) is not None]
    # allow partial lists but require strong signal
    return len(ranked) >= max(3, int(0.6 * len(ds)))


def _sort_list_for_file(xs: List[Any]) -> List[Any]:
    if not _should_sort_list(xs):
        return xs

    # stable sort: keep original order for same rank / unranked
    decorated: List[Tuple[int, int, Any]] = []
    for i, x in enumerate(xs):
        if isinstance(x, Mapping):
            r = _rank_item(x)
        else:
            r = None
        decorated.append(((r if r is not None else 999), i, x))
    decorated.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in decorated]


def _reorder_dict_keys_for_file(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict whose key order is tuned for human reading in file."""

    out: Dict[str, Any] = {}

    # 1) summary-like blocks first
    for k in SUMMARY_KEYS:
        if k in d:
            out[k] = d[k]

    # 2) top-level status/errors early if present
    for k in ("status", "overall_status", "errors"):
        if k in d and k not in out:
            out[k] = d[k]

    # 3) rest preserve original insertion order
    for k, v in d.items():
        if k in out:
            continue
        out[k] = v
    return out


def _rank_mapping_value(v: Any) -> Optional[int]:
    """Rank a mapping entry by severity (lower is more severe).

    This is used for dicts that behave like a set of check items, e.g.
    {"check_a": {"status": "FAIL"}, "check_b": {"status": "PASS"}}.
    """

    if not isinstance(v, Mapping):
        return None

    # 1) explicit status fields
    for key in ("status", "overall", "overall_status"):
        s = v.get(key)
        if isinstance(s, str):
            return STATUS_RANK_FILE.get(s.upper(), 500)

    # 2) boolean ok / passed / hit_at_k
    b = _rank_from_common_bools(v)
    if b is not None:
        return b
    return None


def _should_sort_mapping(d: Dict[str, Any]) -> bool:
    if len(d) < 3:
        return False
    ranked = [1 for v in d.values() if _rank_mapping_value(v) is not None]
    return len(ranked) >= max(2, int(0.6 * len(d)))


def _sort_mapping_by_value_severity(d: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder mapping entries by severity when it looks like a check-map."""

    if not _should_sort_mapping(d):
        return d

    decorated: List[Tuple[int, int, str, Any]] = []
    for i, (k, v) in enumerate(d.items()):
        r = _rank_mapping_value(v)
        decorated.append(((r if r is not None else 999), i, k, v))
    decorated.sort(key=lambda t: (t[0], t[1]))

    out: Dict[str, Any] = {}
    for _, _, k, v in decorated:
        out[k] = v
    return out


def prepare_report_for_file_output(obj: Any) -> Any:
    """Normalize an object for file report output.

    - Reorder dict keys (summary-like first)
    - Sort known detail lists when items are rankable
    - Normalize path strings (for known path-keys)
    - Add `loc_uri` for clickable VS Code navigation
    - Recurse into nested dict/list
    """

    repo_root = _extract_repo_root(obj)
    return _prepare_any(obj, repo_root)


def _prepare_any(x: Any, repo_root: Optional[Path]) -> Any:
    if isinstance(x, Path):
        return x.as_posix()

    if isinstance(x, list):
        xs = [_prepare_any(v, repo_root) for v in x]
        return _sort_list_for_file(xs)

    if isinstance(x, dict):
        d2: Dict[str, Any] = {}
        for k, v in x.items():
            d2[k] = _prepare_any(v, repo_root)

        # normalize strings for known path keys (do not touch arbitrary strings)
        for pk in PATH_KEY_HINTS:
            if pk not in d2:
                continue
            d2[pk] = _normalize_path_value(d2[pk])

        # sort common detail lists by severity
        for lk in DETAIL_LIST_KEYS:
            if lk in d2 and isinstance(d2[lk], list):
                d2[lk] = _sort_list_for_file(d2[lk])

        # For dicts that behave like a set of checks, order by value severity.
        d3 = _sort_mapping_by_value_severity(d2)

        # add loc_uri when possible
        _augment_loc_uri_in_place(d3, repo_root)

        return _reorder_dict_keys_for_file(d3)

    return x


def _normalize_path_value(v: Any) -> Any:
    """Normalize known-path values for file output.

    - str: convert "\\" -> "/" (exclude URLs)
    - list[str]: normalize each
    """

    if isinstance(v, str):
        return _normalize_path_str(v)
    if isinstance(v, list):
        out: List[Any] = []
        for it in v:
            out.append(_normalize_path_value(it))
        return out
    return v


def _normalize_path_str(s: str) -> str:
    s = str(s)
    if "://" in s:
        return s
    return s.replace("\\", "/")


def _extract_repo_root(obj: Any) -> Optional[Path]:
    """Try to extract a repo root from the top-level report."""

    if not isinstance(obj, dict):
        return None

    for k in ("root", "repo", "repo_root", "project_root"):
        v = obj.get(k)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s:
            continue
        # keep original separator for Path parsing; only normalize when building URI.
        try:
            p = Path(s)
        except Exception:
            continue
        if p.is_absolute():
            return p
        # Windows drive on non-Windows host: Path("C:/x") is not absolute on posix.
        if _WIN_DRIVE_ABS.match(s.replace("\\", "/")):
            return Path(s.replace("\\", "/"))

    return None


def _augment_loc_uri_in_place(d: Dict[str, Any], repo_root: Optional[Path]) -> None:
    """Add `loc_uri` to dicts that look like diagnostics entries.

    Supported patterns:
    - dict has file/line/col
    - dict has loc string or loc list (DIAG_LOC_FILE_LINE_COL)

    The function mutates `d` in-place.
    """

    # recurse first
    for v in d.values():
        if isinstance(v, dict):
            _augment_loc_uri_in_place(v, repo_root)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    _augment_loc_uri_in_place(it, repo_root)

    if "loc_uri" in d:
        return

    # pattern A: explicit file/line/col
    if isinstance(d.get("file"), str) and ("line" in d or "col" in d):
        file_str = str(d.get("file") or "")
        line = _to_int_or_none(d.get("line"))
        col = _to_int_or_none(d.get("col"))
        uri = _build_vscode_file_uri(file_str, line, col, repo_root)
        if uri:
            d["loc_uri"] = uri
            d.update(_diag_key_order_hint(d))
        return

    # pattern B: loc string/list
    loc_v = d.get("loc")
    if isinstance(loc_v, str):
        parsed = _parse_diag_loc(loc_v)
        if parsed is None:
            return
        file_str, line, col = parsed
        uri = _build_vscode_file_uri(file_str, line, col, repo_root)
        if uri:
            d["loc_uri"] = uri
            d.update(_diag_key_order_hint(d))
        return

    if isinstance(loc_v, list):
        locs = [str(x) for x in loc_v]
        uris: List[str] = []
        for s in locs:
            parsed = _parse_diag_loc(s)
            if parsed is None:
                uris.append("")
                continue
            file_str, line, col = parsed
            uris.append(_build_vscode_file_uri(file_str, line, col, repo_root))
        if any(u for u in uris):
            d["loc_uri"] = uris
            d.update(_diag_key_order_hint(d))
        return


def _diag_key_order_hint(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure `loc_uri` appears near `loc` when dict is later re-serialized.

    Python dict preserves insertion order. This helper re-inserts `loc_uri` right after `loc`.
    It returns an empty dict if no re-ordering is needed.
    """

    if "loc" not in d or "loc_uri" not in d:
        return {}

    # Only reorder when loc_uri was appended at end.
    keys = list(d.keys())
    if keys and keys[-1] != "loc_uri":
        return {}

    loc_uri = d.pop("loc_uri")
    # rebuild preserving earlier keys, then insert after loc
    out: Dict[str, Any] = {}
    for k in keys:
        if k == "loc_uri":
            continue
        out[k] = d.get(k)
        if k == "loc":
            out["loc_uri"] = loc_uri
    d.clear()
    d.update(out)
    return {}


def _to_int_or_none(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


def _parse_diag_loc(loc: str) -> Optional[Tuple[str, int, int]]:
    """Parse DIAG_LOC style string.

    Accept both:
    - "file:line:col: message"
    - "file:line:col"

    Notes:
    - Use greedy match for `file` to support Windows drive prefix `C:`.
    """

    s = (loc or "").strip()
    if not s:
        return None

    m = _LOC_WITH_MSG.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), int(m.group("col")))

    m = _LOC_BARE.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), int(m.group("col")))

    return None


def _looks_like_abs_path(p: str) -> bool:
    if p.startswith("/"):
        return True
    if p.startswith("//"):
        return True
    if _WIN_DRIVE_ABS.match(p):
        return True
    return False


def _build_vscode_file_uri(file_str: str, line: Optional[int], col: Optional[int], repo_root: Optional[Path]) -> str:
    """Build a clickable VS Code URL: vscode://file/<abs_path>:line:col

    - abs_path uses posix separators
    - spaces are URL-encoded
    """

    s = (file_str or "").strip()
    if not s:
        return ""
    if s.startswith("vscode://") or s.startswith("vscode-insiders://"):
        return s
    if "://" in s:
        return ""

    scheme = (os.getenv("RAG_VSCODE_SCHEME") or "vscode").strip() or "vscode"

    # normalize separators for detection/assembly
    s2 = s.replace("\\", "/")

    if _looks_like_abs_path(s2):
        abs_posix = s2
    else:
        if repo_root is None:
            return ""
        try:
            abs_posix = (repo_root / s2).resolve().as_posix()
        except Exception:
            return ""

    # encode only what must be encoded (keep / and :)
    encoded = quote(abs_posix, safe="/:")

    suffix = ""
    if isinstance(line, int) and line > 0:
        suffix = f":{line}"
        if isinstance(col, int) and col > 0:
            suffix += f":{col}"

    return f"{scheme}://file/{encoded}{suffix}"


def write_json_report(path: Path, report: Any) -> None:
    """Write a JSON report to file with normalized ordering."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = prepare_report_for_file_output(report)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
