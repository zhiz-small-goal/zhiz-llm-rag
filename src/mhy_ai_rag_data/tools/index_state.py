#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.index_state

用途
- 为“增量构建 + 强一致验收（expected_chunks == collection.count）”提供最小状态元数据（manifest）。
- 状态文件用于：在不枚举全量 Chroma ids 的前提下，按 doc 粒度判断新增/变更/删除，从而做可控的增量 sync。

文件布局（建议）
- data_processed/index_state/<collection>/<schema_hash>/index_state.json
- data_processed/index_state/<collection>/LATEST  （指向当前 schema_hash）

输出契约（v2）
- index_state.json 作为“状态元数据”，也纳入统一输出层：schema_version=2 envelope。
  顶层必须包含：schema_version/generated_at/tool/root/summary/items。
- 同时保留机器可消费字段（稳定键）：docs/last_build/schema_hash/db/collection/... 等。

兼容性
- 历史遗留的 v1 index_state（无 schema_version 或缺少 summary/items）在读取时可 best-effort 转换为 v2（内存态）。
  转换规则：保留原始状态字段，并补充 v2 envelope + 一条 WARN item 标注来源。

注意
- 该文件属于工程元数据，可提交 Git（小规模）或只留本地（大规模）。
- 路径相关字符串需使用 '/' 分隔符；item 字段禁止出现反斜杠（\\）。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mhy_ai_rag_data.tools.report_contract import compute_summary, ensure_item_fields, ensure_report_v2, iso_now
from mhy_ai_rag_data.tools.report_order import prepare_report_for_file_output


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
    """计算索引口径哈希。

    组成：
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
    # Keep a final newline for better diff / tooling compatibility.
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _sanitize_no_backslash(obj: Any) -> Any:
    """Recursively replace backslashes in strings.

    verify_report_output_contract 会递归扫描 items 下的字符串字段并拒绝出现 '\\'。
    对于状态元数据 report，我们只承诺 items 中不含反斜杠；这里做一次兜底清洗。
    """

    if isinstance(obj, str):
        return obj.replace("\\", "/")
    if isinstance(obj, dict):
        return {k: _sanitize_no_backslash(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_no_backslash(v) for v in obj]
    return obj


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


def ensure_index_state_report_v2(
    raw: Dict[str, Any],
    *,
    root: Path,
    state_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Normalize index_state to schema_version=2.

    - 若 raw 已经是 v2：调用 ensure_report_v2 做字段归一化，并强制 root 为 repo root。
    - 若 raw 是 v1：保留原始字段（例如 docs/schema_hash/...），补充 v2 envelope。

    注意：
    - 该函数是“读取侧兼容”，不改变落盘文件。
    - envelope 的 items 会至少包含 1 条 WARN，用于可追溯“来自 v1”。
    """

    sv = raw.get("schema_version")
    try:
        sv_i = int(sv) if sv is not None else None
    except Exception:
        sv_i = None

    if sv_i == 2 and isinstance(raw.get("items"), list) and isinstance(raw.get("summary"), dict):
        normalized = ensure_report_v2(raw)
        normalized["root"] = str(root.resolve().as_posix())
        return normalized

    tool_name = "index_state"

    items: List[Dict[str, Any]] = []
    items.append(
        ensure_item_fields(
            _sanitize_no_backslash(
                {
                    "tool": tool_name,
                    "key": "legacy_v1_loaded",
                    "title": "legacy index_state normalized",
                    "status_label": "WARN",
                    "severity_level": 2,
                    "message": "loaded legacy index_state (v1) and normalized to schema_version=2 in memory",
                    "detail": {
                        "state_file": state_file.as_posix() if state_file else "",
                        "has_docs": bool(raw.get("docs")),
                        "schema_hash": str(raw.get("schema_hash") or ""),
                    },
                }
            ),
            tool_default=tool_name,
        )
    )

    out: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_name,
        "root": str(root.resolve().as_posix()),
        "items": items,
        "summary": compute_summary(items).to_dict(),
        "data": {"legacy": {"detected": True}},
    }

    # Preserve legacy fields for consumers (docs/schema_hash/etc.).
    for k, v in raw.items():
        if k in ("schema_version", "generated_at", "tool", "root", "summary", "items", "data"):
            continue
        out.setdefault(k, v)

    return out


def load_index_state(path: Path, *, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load index_state.json.

    返回：
    - None：文件不存在
    - dict：
      - 若 root 传入：会对 v1 进行 v2 归一化（内存态），便于统一验收与渲染。
      - 若 root 未传入：返回原始 JSON 对象（兼容旧调用方）。
    """

    if not path.exists():
        return None

    raw = load_json(path)
    if root is None:
        return raw

    return ensure_index_state_report_v2(raw, root=root, state_file=path)


def write_latest_pointer(state_root: Path, collection: str, schema_hash: str) -> None:
    atomic_write_text(latest_schema_file(state_root, collection), schema_hash.strip() + "\n")


def read_latest_pointer(state_root: Path, collection: str) -> Optional[str]:
    p = latest_schema_file(state_root, collection)
    if not p.exists():
        return None
    s = p.read_text(encoding="utf-8").strip()
    return s or None


def write_index_state_report(
    *,
    root: Path,
    state_root: Path,
    collection: str,
    schema_hash: str,
    db: Path,
    embed_model: str,
    chunk_conf: Dict[str, Any],
    include_media_stub: bool,
    docs: Dict[str, Any],
    last_build: Dict[str, Any],
    items: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """Write index_state.json as a schema_version=2 report.

    该函数是“写入侧 SSOT”：尽量让 build/upsert/sync 只关注业务字段，输出契约由这里统一保证。

    - items：允许调用方补充更细粒度的构建信息（例如 collection.count 不可用等）。
      若未提供，将生成最小 PASS item。
    """

    root = root.resolve()
    state_root = state_root.resolve()
    db = db.resolve()

    out_path = state_file_for(state_root, str(collection), str(schema_hash)).resolve()

    tool_name = "index_state"

    raw_items: List[Dict[str, Any]] = []
    if items:
        raw_items.extend(items)
    else:
        raw_items.append(
            {
                "tool": tool_name,
                "key": "state_written",
                "title": "index_state written",
                "status_label": "PASS",
                "severity_level": 0,
                "message": f"wrote {out_path.as_posix()} (collection={collection} schema_hash={schema_hash})",
                "detail": {
                    "state_file": out_path.as_posix(),
                    "collection": str(collection),
                    "schema_hash": str(schema_hash),
                },
            }
        )

    normalized_items = [ensure_item_fields(_sanitize_no_backslash(it), tool_default=tool_name) for it in raw_items]

    report: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at": iso_now(),
        "tool": tool_name,
        "root": str(root.as_posix()),
        "summary": compute_summary(normalized_items).to_dict(),
        "items": normalized_items,
        # state payload (stable keys for consumers)
        "schema_hash": str(schema_hash),
        "db": str(db.as_posix()),
        "collection": str(collection),
        "embed_model": str(embed_model),
        "chunk_conf": chunk_conf,
        "include_media_stub": bool(include_media_stub),
        "updated_at": iso_now(),
        "docs": docs,
        "last_build": last_build,
        "data": {
            "state": {
                "schema_hash": str(schema_hash),
                "db": str(db.as_posix()),
                "collection": str(collection),
                "updated_at": iso_now(),
            }
        },
    }

    final_obj = prepare_report_for_file_output(report)
    if not isinstance(final_obj, dict):
        raise RuntimeError("prepare_report_for_file_output did not return dict")

    save_json_atomic(out_path, final_obj)
    write_latest_pointer(state_root, str(collection), str(schema_hash))

    return out_path
