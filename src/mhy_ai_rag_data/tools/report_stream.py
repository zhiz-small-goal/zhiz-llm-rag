#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.report_stream

目标：为长任务脚本提供“实时可观测”的旁路工件输出。

支持格式：
- jsonl: 每行一个 JSON 对象（工程惯例，最适合 Get-Content -Wait 观察）
- json-seq: RFC 7464 JSON Text Sequences（RS + JSON + LF）

设计原则：
- 旁路输出：不得改变最终汇总 JSON 的结构与写入时机。
- 单写者：默认假设单进程顺序写入；若并发写入需要上层做分文件或锁。
- 可增量消费：每条记录写入后可 flush；消费端应容错最后一条半写记录。

落盘强度（durability）
- durability_mode = none|flush|fsync（默认：flush）
  - none : 不主动 flush/fsync（由 OS/缓冲策略决定）。
  - flush: 每条记录 flush。
  - fsync: 每条记录 flush，且按 fsync_interval_ms 节流执行 fsync。

兼容性
- 旧字段 flush_per_record/fsync_per_record 保留；当 durability_mode 为空时按旧字段行为。

记录字段建议（写端尽量补齐）：
- record_type: meta|case|error|summary
- run_id: 本次运行唯一标识
- ts_ms: 毫秒时间戳

注：本模块不依赖第三方库，便于在 CI/离线环境中稳定使用。
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional, TextIO


StreamFormat = Literal["jsonl", "json-seq"]

# RFC 7464: Record Separator (RS) = 0x1E
_RS = "\x1e"


def now_ts_ms() -> int:
    return int(time.time() * 1000)


def default_run_id(prefix: str) -> str:
    ts = time.strftime("%Y%m%dT%H%M%S%z")
    pid = os.getpid()
    rnd = secrets.token_hex(3)
    return f"{prefix}-{ts}-{pid}-{rnd}"


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def safe_truncate(text: str, n: int) -> str:
    if n <= 0:
        return ""
    if len(text) <= n:
        return text
    return text[:n]


def _norm_durability_mode(mode: str) -> str:
    return (mode or "").strip().lower()


@dataclass
class StreamWriter:
    path: Path
    fmt: StreamFormat = "jsonl"

    # legacy knobs (kept for backward compatibility)
    flush_per_record: bool = True
    fsync_per_record: bool = False

    # new knob (preferred)
    durability_mode: str = ""  # none|flush|fsync ; empty => use legacy knobs
    fsync_interval_ms: int = 1000

    _f: Optional[TextIO] = None
    _last_fsync_ms: int = 0

    def open(self) -> "StreamWriter":
        ensure_parent_dir(self.path)
        self._f = open(self.path, "a", encoding="utf-8", newline="\n")
        self._last_fsync_ms = 0
        return self

    def emit(self, record: Dict[str, Any]) -> None:
        if self._f is None:
            raise RuntimeError("StreamWriter is not open")

        # 补齐基础字段（若上层已提供，则不覆盖）
        record.setdefault("ts_ms", now_ts_ms())

        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if self.fmt == "jsonl":
            line = payload + "\n"
        elif self.fmt == "json-seq":
            line = _RS + payload + "\n"
        else:
            raise RuntimeError(f"Unsupported stream format: {self.fmt}")

        self._f.write(line)

        mode = _norm_durability_mode(self.durability_mode)
        if mode:
            # new behavior
            if mode == "none":
                return
            self._f.flush()
            if mode != "fsync":
                return
            now = now_ts_ms()
            if self._last_fsync_ms <= 0 or (now - self._last_fsync_ms) >= max(0, int(self.fsync_interval_ms)):
                try:
                    os.fsync(self._f.fileno())
                finally:
                    self._last_fsync_ms = now
            return

        # legacy behavior
        if self.flush_per_record:
            self._f.flush()
            if self.fsync_per_record:
                os.fsync(self._f.fileno())

    def close(self) -> None:
        if self._f is not None:
            try:
                self._f.flush()
            finally:
                self._f.close()
                self._f = None
