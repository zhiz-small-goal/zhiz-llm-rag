#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_order

用途
- 为“落盘 JSON 报告”提供统一的**人类可读顺序**与**可点击定位**。

文件输出排序（本模块负责）
- 顶部字段：schema_version/generated_at/tool/root/summary 优先。
- 明细列表：按 severity_level 从大到小排序（最严重在前），同级稳定。
- 仅当列表元素可判定 severity_level 时才排序；否则保持原顺序。

定位字段
- `loc` 展示保持为 `file:line:col` 便于 grep/复制。
- `loc_uri` 生成 `vscode://file/<abs_path>:line:col`，用于 VS Code 可点击跳转。

环境变量
- RAG_VSCODE_SCHEME: 默认 `vscode`；VS Code Insiders 可设为 `vscode-insiders`。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from mhy_ai_rag_data.tools.report_contract import ensure_report_v2, status_label_to_severity_level
from mhy_ai_rag_data.tools.vscode_links import normalize_abs_path_posix, to_vscode_file_uri_strict


# --- ordering knobs (file output) ---

# 认为是“汇总块”的 key：放到最前面（若存在）
SUMMARY_KEYS: Tuple[str, ...] = (
    "summary",
    "metrics",
    "buckets",
    "counts",
    "totals",
)

# 常见明细列表 key：这些 key 下的 list（若元素可判定 severity）会被排序
DETAIL_LIST_KEYS: Tuple[str, ...] = (
    "items",
    "results",
    "cases",
    "checks",
)


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
    "db_path",
    "path",
    "file",
)

_WIN_DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")

# greedy: support Windows drive prefix `C:`
_LOC_LINE_COL_WITH_MSG = re.compile(r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+):")
_LOC_LINE_COL_BARE = re.compile(r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+)$")
_LOC_LINE_WITH_MSG = re.compile(r"^(?P<file>.+):(?P<line>\d+):")
_LOC_LINE_BARE = re.compile(r"^(?P<file>.+):(?P<line>\d+)$")


def _safe_int(v: Any) -> Optional[int]:
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


def _severity_from_mapping(d: Mapping[str, Any]) -> Optional[int]:
    sev = _safe_int(d.get("severity_level"))
    if sev is not None:
        return int(sev)

    # fallback (compat only)
    for k in ("status_label", "status", "overall_status", "overall"):
        if k in d:
            s = d.get(k)
            if isinstance(s, str) and s.strip():
                return status_label_to_severity_level(s)
    return None


def _severity_from_common_bools(d: Mapping[str, Any]) -> Optional[int]:
    """Heuristics for case-like entries.

    - eval_rag: passed / error / error_detail / llm_call_ok
    - eval_retrieval: hit_at_k
    - generic: ok
    """

    if "passed" in d:
        if d.get("error") or d.get("error_detail") or (d.get("llm_call_ok") is False):
            return 4
        if d.get("passed") is False:
            return 3
        if d.get("passed") is True:
            return 0
        return None

    if "hit_at_k" in d:
        v = d.get("hit_at_k")
        if v is False:
            return 3
        if v is True:
            return 0
        return None

    if "ok" in d:
        v = d.get("ok")
        if v is False:
            return 3
        if v is True:
            return 0
        return None

    return None


def _severity_item(d: Mapping[str, Any]) -> Optional[int]:
    sev = _severity_from_mapping(d)
    if sev is not None:
        return sev
    return _severity_from_common_bools(d)


def _should_sort_list(xs: List[Any]) -> bool:
    if not xs:
        return False
    ds = [x for x in xs if isinstance(x, Mapping)]
    if not ds:
        return False
    ranked = [d for d in ds if _severity_item(d) is not None]
    return len(ranked) >= max(3, int(0.6 * len(ds)))


def _sort_list_for_file(xs: List[Any]) -> List[Any]:
    if not _should_sort_list(xs):
        return xs

    # stable sort: severity desc; keep original order for same severity / unranked
    decorated: List[Tuple[int, int, Any]] = []
    for i, x in enumerate(xs):
        sev: Optional[int] = None
        if isinstance(x, Mapping):
            sev = _severity_item(x)
        # unranked goes last
        sort_key = -(sev if sev is not None else -10_000)
        # Explanation: sev None => sort_key very large (goes last) by using --10000 => 10000.
        if sev is None:
            sort_key = 10_000
        decorated.append((sort_key, i, x))

    decorated.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in decorated]


def _reorder_dict_keys_for_file(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict whose key order is tuned for human reading in file."""

    out: Dict[str, Any] = {}

    # 0) v2 envelope top keys
    for k in ("schema_version", "generated_at", "tool", "root"):
        if k in d:
            out[k] = d[k]

    # 1) summary-like blocks
    for k in SUMMARY_KEYS:
        if k in d and k not in out:
            out[k] = d[k]

    # 2) common status/errors keys
    for k in ("status", "overall_status", "errors", "warnings"):
        if k in d and k not in out:
            out[k] = d[k]

    # 3) items before data when present
    for k in ("items", "results", "cases"):
        if k in d and k not in out:
            out[k] = d[k]

    # 4) rest preserve original insertion order
    for k, v in d.items():
        if k in out:
            continue
        out[k] = v
    return out


def _severity_mapping_value(v: Any) -> Optional[int]:
    if not isinstance(v, Mapping):
        return None
    sev = _severity_item(v)
    return sev


def _should_sort_mapping(d: Dict[str, Any]) -> bool:
    if len(d) < 3:
        return False
    ranked = [1 for v in d.values() if _severity_mapping_value(v) is not None]
    return len(ranked) >= max(2, int(0.6 * len(d)))


def _sort_mapping_by_value_severity(d: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder mapping entries by severity when it looks like a check-map."""

    if not _should_sort_mapping(d):
        return d

    decorated: List[Tuple[int, int, str, Any]] = []
    for i, (k, v) in enumerate(d.items()):
        sev = _severity_mapping_value(v)
        sort_key = -(sev if sev is not None else -10_000)
        if sev is None:
            sort_key = 10_000
        decorated.append((sort_key, i, k, v))

    decorated.sort(key=lambda t: (t[0], t[1]))
    out: Dict[str, Any] = {}
    for _, _, k, v in decorated:
        out[k] = v
    return out


def prepare_report_for_file_output(obj: Any) -> Any:
    """Normalize an object for file report output.

    - v2 envelope conversion (top-level only)
    - Reorder dict keys
    - Sort known detail lists/mappings when items are rankable
    - Normalize path strings (for known path-keys)
    - Add `loc_uri` for clickable VS Code navigation
    - Recurse into nested dict/list
    """

    # Only convert when obj looks like a report dict; keep non-dict as-is
    if isinstance(obj, Mapping):
        obj = ensure_report_v2(obj)

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

        # normalize strings for known path keys
        for pk in PATH_KEY_HINTS:
            if pk not in d2:
                continue
            d2[pk] = _normalize_path_value(d2[pk])

        # normalize loc text (path separators)
        if "loc" in d2:
            d2["loc"] = _normalize_loc_value(d2.get("loc"))

        # sort common detail lists by severity
        for lk in DETAIL_LIST_KEYS:
            if lk in d2 and isinstance(d2[lk], list):
                d2[lk] = _sort_list_for_file(d2[lk])

        d3 = _sort_mapping_by_value_severity(d2)

        # Free-text normalization for item-like dicts.
        # The verifier enforces that *any* string field inside items[] must not
        # contain backslashes. Some tools may embed Windows paths in message/
        # detail/traceback strings. Normalize those separators here so that
        # file output + markdown + verification are consistent.
        if _looks_like_item(d3):
            d3 = _normalize_item_string_fields(d3)
        _augment_loc_uri_in_place(d3, repo_root)
        return _reorder_dict_keys_for_file(d3)

    return x


def _normalize_path_value(v: Any) -> Any:
    if isinstance(v, str):
        return _normalize_path_str(v)
    if isinstance(v, list):
        return [_normalize_path_value(it) for it in v]
    return v


def _looks_like_item(d: Mapping[str, Any]) -> bool:
    # Minimal heuristic: items use the v2 item model fields.
    # Keep this strict to avoid touching arbitrary free-text blocks.
    if not isinstance(d.get("tool"), str):
        return False
    if not isinstance(d.get("title"), str):
        return False
    if "severity_level" in d or "status_label" in d:
        return True
    return False


def _normalize_item_string_fields(x: Any) -> Any:
    """Replace backslashes with '/' recursively for item dicts.

    Note: This is intentionally broader than loc/path keys. It targets the
    verifier rule that item fields must not contain '\\'.
    """

    if isinstance(x, str):
        return x.replace("\\", "/")
    if isinstance(x, list):
        return [_normalize_item_string_fields(v) for v in x]
    if isinstance(x, dict):
        return {k: _normalize_item_string_fields(v) for k, v in x.items()}
    return x


def _normalize_path_str(s: str) -> str:
    s = str(s)
    if "://" in s:
        return s
    # posix separators + windows drive lowercasing when possible
    return normalize_abs_path_posix(s)


def _normalize_loc_value(v: Any) -> Any:
    """Normalize `loc` text to use '/' separators.

    Contract: all paths shown in reports use '/' as separator, including `loc`.
    We keep `loc` as pure text (path[:line[:col]]), only normalizing separators and drive casing.
    """

    if isinstance(v, str):
        # `normalize_abs_path_posix` is safe for relative paths too.
        return normalize_abs_path_posix(v)
    if isinstance(v, list):
        return [(_normalize_loc_value(x) if isinstance(x, (str, list)) else x) for x in v]
    return v


def _extract_repo_root(obj: Any) -> Optional[Path]:
    if not isinstance(obj, dict):
        return None

    for k in ("root", "repo", "repo_root", "project_root"):
        v = obj.get(k)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s:
            continue
        try:
            p = Path(s.replace("\\", "/"))
        except Exception:
            continue
        # Windows drive path on posix: treat as absolute for joining.
        if p.is_absolute() or _WIN_DRIVE_ABS.match(s.replace("\\", "/")):
            return p

    return None


def _augment_loc_uri_in_place(d: Dict[str, Any], repo_root: Optional[Path]) -> None:
    """Add `loc_uri` to dicts that look like diagnostics entries."""

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
        line = _safe_int(d.get("line"))
        col = _safe_int(d.get("col"))
        uri = _build_vscode_file_uri(file_str, line=line, col=col, repo_root=repo_root)
        if uri:
            d["loc_uri"] = uri
            _diag_key_order_hint_in_place(d)
        return

    # pattern B: loc string/list
    loc_v = d.get("loc")
    if isinstance(loc_v, str):
        parsed = _parse_diag_loc(loc_v)
        if parsed is None:
            return
        file_str, line, col = parsed
        uri = _build_vscode_file_uri(file_str, line=line, col=col, repo_root=repo_root)
        if uri:
            d["loc_uri"] = uri
            _diag_key_order_hint_in_place(d)
        return

    if isinstance(loc_v, list):
        uris: List[str] = []
        any_ok = False
        for s in [str(x) for x in loc_v]:
            parsed = _parse_diag_loc(s)
            if parsed is None:
                uris.append("")
                continue
            file_str, line, col = parsed
            u = _build_vscode_file_uri(file_str, line=line, col=col, repo_root=repo_root)
            uris.append(u)
            if u:
                any_ok = True
        if any_ok:
            d["loc_uri"] = uris
            _diag_key_order_hint_in_place(d)
        return


def _diag_key_order_hint_in_place(d: Dict[str, Any]) -> None:
    """Ensure `loc_uri` appears right after `loc` when possible."""

    if "loc" not in d or "loc_uri" not in d:
        return

    keys = list(d.keys())
    if not keys or keys[-1] != "loc_uri":
        return

    loc_uri = d.pop("loc_uri")
    out: Dict[str, Any] = {}
    for k in keys:
        if k == "loc_uri":
            continue
        out[k] = d.get(k)
        if k == "loc":
            out["loc_uri"] = loc_uri
    d.clear()
    d.update(out)


def _parse_diag_loc(loc: str) -> Optional[Tuple[str, int, int]]:
    """Parse a diagnostic location.

    Accepted forms (loc is pure text; separators normalized elsewhere):
    - path
    - path:line
    - path:line:col
    Also tolerates trailing ': ...' message after the col/line.

    Returns:
      (file, line, col) where line/col are always positive ints.
      When missing, we default to 1:1 so loc_uri remains clickable.
    """

    s = (loc or "").strip()
    if not s:
        return None
    if "://" in s:
        return None

    # 1) full form: path:line:col[:message]
    m = _LOC_LINE_COL_WITH_MSG.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), int(m.group("col")))

    m = _LOC_LINE_COL_BARE.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), int(m.group("col")))

    # 2) line-only: path:line[:message]
    m = _LOC_LINE_WITH_MSG.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), 1)

    m = _LOC_LINE_BARE.match(s)
    if m:
        return (m.group("file"), int(m.group("line")), 1)

    # 3) path-only
    return (s, 1, 1)


def _looks_like_abs_path(p: str) -> bool:
    if p.startswith("/"):
        return True
    if p.startswith("//"):
        return True
    if _WIN_DRIVE_ABS.match(p):
        return True
    return False


def _build_vscode_file_uri(file_str: str, *, line: Optional[int], col: Optional[int], repo_root: Optional[Path]) -> str:
    s = (file_str or "").strip()
    if not s:
        return ""
    if s.startswith("vscode://") or s.startswith("vscode-insiders://"):
        return s
    if "://" in s:
        return ""

    s2 = s.replace("\\", "/")

    if _looks_like_abs_path(s2):
        abs_posix = normalize_abs_path_posix(s2)
    else:
        if repo_root is None:
            return ""
        try:
            abs_posix = (repo_root / s2).resolve().as_posix()
        except Exception:
            return ""

    # loc_uri contract: always include :line:col. When missing, default to 1:1.
    return to_vscode_file_uri_strict(abs_posix, line=line, col=col)


def write_json_report(path: Path, report: Any) -> None:
    """Write a JSON report to file with normalized ordering."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = prepare_report_for_file_output(report)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
