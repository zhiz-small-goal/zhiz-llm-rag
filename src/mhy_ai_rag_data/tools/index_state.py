#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index_state.py

一个“增量构建 + 强一致验收（expected==count）”所需的最小状态文件（manifest）实现。

设计目标（v1）：
- 不依赖枚举 Chroma 全量 ids（数据量大时不可承受）。
- 以 “doc 粒度” 记录上一轮索引的事实：doc_id、content_sha256、n_chunks。
- 支持三类变更：新增、内容变更、删除。
- schema_hash 用于区分“索引口径”版本：chunk_conf / include_media_stub / embed_model 等变化 => 新 schema。

状态文件位置建议：
data_processed/index_state/<collection>/<schema_hash>/index_state.json
以及 LATEST 指针：data_processed/index_state/<collection>/LATEST

注意：
- 该文件属于工程元数据，可提交 Git（小规模）或只留本地（大规模）。
- 若你更偏向“版本化 collection 名称”，可把 schema_hash 也用在 collection 命名上。
"""

from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_schema_hash(
    *,
    embed_model: str,
    chunk_conf: Dict[str, Any],
    include_media_stub: bool,
    id_strategy_version: int = 1,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    计算索引口径哈希：
    - embed_model（建议包含 revision/commit；若没有也至少要包含模型名）
    - chunk_conf（chunk_chars/overlap/min 等）
    - include_media_stub
    - id_strategy_version：chunk_id 生成策略版本（当前 doc_id:chunk_index = 1）
    """
    payload: Dict[str, Any] = {
        "embed_model": str(embed_model),
        "chunk_conf": chunk_conf,
        "include_media_stub": bool(include_media_stub),
        "id_strategy_version": int(id_strategy_version),
    }
    if extra:
        payload["extra"] = extra
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(s)


def latest_schema_file(state_root: Path, collection: str) -> Path:
    return state_root / collection / "LATEST"


def state_dir_for(state_root: Path, collection: str, schema_hash: str) -> Path:
    return state_root / collection / schema_hash


def state_file_for(state_root: Path, collection: str, schema_hash: str) -> Path:
    return state_dir_for(state_root, collection, schema_hash) / "index_state.json"


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(str(tmp), str(path))


def load_json(path: Path) -> Dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict, got {type(result).__name__}")
    return result


def save_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


@dataclass
class DocState:
    doc_id: str
    source_uri: str
    source_type: str
    content_sha256: str
    n_chunks: int
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_uri": self.source_uri,
            "source_type": self.source_type,
            "content_sha256": self.content_sha256,
            "n_chunks": int(self.n_chunks),
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DocState":
        return DocState(
            doc_id=str(d.get("doc_id", "")),
            source_uri=str(d.get("source_uri", "")),
            source_type=str(d.get("source_type", "")),
            content_sha256=str(d.get("content_sha256", "")),
            n_chunks=int(d.get("n_chunks", 0)),
            updated_at=str(d.get("updated_at", "")),
        )


def load_index_state(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return load_json(path)


def write_latest_pointer(state_root: Path, collection: str, schema_hash: str) -> None:
    atomic_write_text(latest_schema_file(state_root, collection), schema_hash.strip() + "\n")


def read_latest_pointer(state_root: Path, collection: str) -> Optional[str]:
    p = latest_schema_file(state_root, collection)
    if not p.exists():
        return None
    s = p.read_text(encoding="utf-8").strip()
    return s or None
