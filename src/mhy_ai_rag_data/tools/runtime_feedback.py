#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.runtime_feedback

运行时反馈（progress / stage / spinner）。

契约约束
- 仅用于运行时交互反馈：不进入 report items，也不写入 events.jsonl。
- 默认行为：auto 仅在交互式 TTY 且非 CI 环境启用。
- 输出通道：stderr。
- 更新节流：默认最短间隔 200ms；更新不得产生换行（单行重绘）。
- 结束：清理进度行并输出 1 次换行。

本模块不依赖第三方库。
"""

from __future__ import annotations

import os
import sys
from typing import Any
import time
from dataclasses import dataclass
from typing import Optional


def _is_ci() -> bool:
    # Common CI envs
    if os.environ.get("CI"):
        return True
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    if os.environ.get("BUILD_BUILDID"):
        return True
    if os.environ.get("TF_BUILD"):
        return True
    return False


def _isatty(stream: Any) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def should_enable(mode: str, *, stream: Any = None) -> bool:
    """Decide whether runtime feedback is enabled.

    mode: auto|on|off
    """

    m = (mode or "auto").strip().lower()
    if m == "on":
        return True
    if m == "off":
        return False

    # auto
    st = stream if stream is not None else sys.stderr
    if _is_ci():
        return False
    return _isatty(st)


_SPINNER = "|/-\\"


@dataclass
class Progress:
    total: Optional[int] = None
    mode: str = "auto"  # auto|on|off
    min_interval_ms: int = 200
    stream = sys.stderr

    _enabled: bool = False
    _last_update_ms: int = 0
    _start_s: float = 0.0
    _spinner_i: int = 0
    _last_line_len: int = 0

    def start(self) -> "Progress":
        self._enabled = should_enable(self.mode, stream=self.stream)
        self._start_s = time.time()
        self._last_update_ms = 0
        self._spinner_i = 0
        self._last_line_len = 0
        return self

    def update(self, *, current: Optional[int] = None, stage: str = "") -> None:
        if not self._enabled:
            return

        now_ms = int(time.time() * 1000)
        if self._last_update_ms and (now_ms - self._last_update_ms) < max(0, int(self.min_interval_ms)):
            return
        self._last_update_ms = now_ms

        elapsed = max(0.0, time.time() - self._start_s)
        if self.total and current is not None:
            # known total
            cur = max(0, int(current))
            tot = max(1, int(self.total))
            pct = min(100.0, (cur * 100.0) / tot)
            # ETA best-effort
            eta = ""
            if cur > 0 and cur <= tot:
                rate = elapsed / cur
                rem = max(0.0, rate * (tot - cur))
                eta = f" eta_s={rem:.1f}"
            line = f"[{stage}] {cur}/{tot} ({pct:5.1f}%) elapsed_s={elapsed:.1f}{eta}"
        else:
            # unknown total: stage + spinner
            ch = _SPINNER[self._spinner_i % len(_SPINNER)]
            self._spinner_i += 1
            line = f"[{stage}] {ch} elapsed_s={elapsed:.1f}"

        self._write_rewrite(line)

    def _write_rewrite(self, line: str) -> None:
        # pad to clear previous line
        pad = " " * max(0, self._last_line_len - len(line))
        out = "\r" + line + pad
        try:
            self.stream.write(out)
            self.stream.flush()
        except Exception:
            # ignore runtime feedback errors
            return
        self._last_line_len = len(line)

    def close(self) -> None:
        if not self._enabled:
            return
        # clear line + newline
        try:
            self.stream.write("\r" + (" " * self._last_line_len) + "\r")
            self.stream.write("\n")
            self.stream.flush()
        except Exception:
            return
        self._last_line_len = 0
        self._enabled = False
