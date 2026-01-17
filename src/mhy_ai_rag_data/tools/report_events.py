#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_events

面向“高耗时任务即时落盘 + 中断可恢复”的 item 事件流（jsonl）。

设计约束
- 每行 1 个 JSON object，语义为 1 条 report v2 的 `item`。
- 事件流只承载 items；运行时进度（progress/spinner）必须走 stderr 或独立流，不写入 events。
- durability_mode 提供落盘强度选择；fsync 允许节流（避免每条强制 fsync）。

注意
- 本模块不引入三方依赖。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def truncate_file(p: Path) -> None:
    """Truncate a file if it exists; create parent dir if needed."""
    ensure_parent_dir(p)
    with p.open("w", encoding="utf-8", newline="\n"):
        pass


@dataclass
class ItemEventsWriter:
    """Append-only jsonl writer for v2 items."""

    path: Path
    durability_mode: str = "flush"  # none|flush|fsync
    fsync_interval_ms: int = 1000

    _f: Optional[Any] = None
    _last_fsync_ms: int = 0

    def open(self, *, truncate: bool = True) -> "ItemEventsWriter":
        ensure_parent_dir(self.path)
        if truncate:
            truncate_file(self.path)
        self._f = self.path.open("a", encoding="utf-8", newline="\n")
        self._last_fsync_ms = 0
        return self

    def emit_item(self, item: Dict[str, Any]) -> None:
        if self._f is None:
            raise RuntimeError("ItemEventsWriter is not open")

        # 可扩展字段：允许上层附带 ts_ms（便于对账/恢复），但不强制。
        if "ts_ms" not in item:
            item = dict(item)
            item["ts_ms"] = _now_ms()

        line = json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._f.write(line)

        mode = (self.durability_mode or "").strip().lower()
        if mode == "none":
            return

        # flush / fsync 都先 flush
        self._f.flush()

        if mode != "fsync":
            return

        # fsync 节流：仅当间隔达到阈值才 fsync
        now = _now_ms()
        if self._last_fsync_ms <= 0 or (now - self._last_fsync_ms) >= max(0, int(self.fsync_interval_ms)):
            try:
                os.fsync(self._f.fileno())
            finally:
                self._last_fsync_ms = now

    def close(self) -> None:
        if self._f is None:
            return
        try:
            # best-effort final flush
            try:
                self._f.flush()
            except Exception:
                pass
        finally:
            self._f.close()
            self._f = None


def iter_items(path: Path) -> Iterator[Dict[str, Any]]:
    """Iterate items from a jsonl events file.

    - 跳过空行。
    - 对解析失败/非 object 行：跳过（不抛异常，便于从中断文件恢复）。
    """

    if not path.exists():
        return

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            s = (raw or "").strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj
