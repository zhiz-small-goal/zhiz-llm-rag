#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.vscode_links

提供可点击的 VS Code 文件定位链接。

约定
- loc 显示保持为 `file:line:col`（便于 grep/复制）。
- loc_uri 使用确定形式：`vscode://file/<abs_path>:line:col`。

注意
- `abs_path` 使用 `/` 分隔符；Windows 盘符统一小写（c:/...）。
- 路径会进行 URL encode（空格等），但保留 `/` 与 `:`。

环境变量
- RAG_VSCODE_SCHEME: 默认 `vscode`；VS Code Insiders 可设为 `vscode-insiders`。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote


_WIN_DRIVE_ABS = re.compile(r"^(?P<drive>[A-Za-z]):[\\/]")


def normalize_abs_path_posix(path_str: str) -> str:
    """Normalize an absolute path string to posix separators.

    - Windows drive letter is lowercased: C:\\x -> c:/x
    - Backslashes become '/'
    """

    s = (path_str or "").strip()
    s = s.replace("\\", "/")

    m = _WIN_DRIVE_ABS.match(s)
    if m:
        drive = (m.group("drive") or "").lower()
        # keep rest of path after "C:"
        rest = s[2:]
        s = f"{drive}:{rest}"

    return s


def to_vscode_file_uri(abs_path: str, *, line: Optional[int] = None, col: Optional[int] = None) -> str:
    """Build a VS Code URL: vscode://file/<abs_path>:line:col

    abs_path:
      - must be absolute (either POSIX /... or Windows c:/...)
      - will be normalized to posix separators
    """

    s = normalize_abs_path_posix(abs_path)
    if not s:
        return ""
    if s.startswith("vscode://") or s.startswith("vscode-insiders://"):
        return s
    if "://" in s:
        return ""  # avoid turning URLs into file links

    scheme = (os.getenv("RAG_VSCODE_SCHEME") or "vscode").strip() or "vscode"

    # encode only what must be encoded (keep / and :)
    encoded = quote(s, safe="/:")

    suffix = ""
    if isinstance(line, int) and line > 0:
        suffix = f":{line}"
        if isinstance(col, int) and col > 0:
            suffix += f":{col}"

    return f"{scheme}://file/{encoded}{suffix}"


def to_vscode_file_uri_from_path(p: Path, *, line: Optional[int] = None, col: Optional[int] = None) -> str:
    try:
        abs_posix = p.resolve().as_posix()
    except Exception:
        abs_posix = p.as_posix()
    return to_vscode_file_uri(abs_posix, line=line, col=col)
