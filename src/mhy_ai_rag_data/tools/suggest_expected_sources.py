#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suggest_expected_sources.py

目的：
- 在你对资料内容不熟、无法确定 expected_sources 时：
  1) 用当前 Chroma 向量库对 query 做 topK 检索
  2) 将每条结果的“来源字段”(metadata 中的 source/path/file 等)标准化为可写入 eval_cases 的形式
  3) 输出：候选列表 + 推荐 expected_sources（默认取前 N 个去重后的来源）

适用：
- 写/维护 data_processed/eval/eval_cases.jsonl 时，快速确定 expected_sources
- 排查某个 query 的“正确归属文档”到底是哪篇（看 topK 的来源集中度）

输出：
- stdout：人类可读的 topK（rank/distance/source/snippet）
- stdout：建议的 expected_sources（可直接复制）
- 可选：写 JSON（--out），或直接 append 到 jsonl（--append-to）

注意：
- expected_sources 的设计目标是“稳定绑定来源”，建议：
  - 绑定到“文件级路径”（而不是 chunk id / 行号 / 临时路径）
  - 必要时给多个候选（top1~top2），避免检索排序微抖导致假 FAIL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def stable_id_from_query(query: str) -> str:
    h = hashlib.sha1(query.strip().encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"case_{h}"


def suggest_must_include(
    query: str, recommended_sources: List[str], hits: List[Dict[str, Any]], pick: int = 2
) -> List[str]:
    """
    基于 query + 推荐来源文件名 + topK snippet，给出 must_include 的候选关键词（用于 gate/回归断言）。

    设计目标：
    - 稳定：优先选“领域名词/对象”（如 关卡/存档/元件/地图/地形），避免选过于细碎的动词或数字。
    - 可解释：尽量来自 query 或来源文件名；不足时再从 snippet 频次推断。
    - 小而精：默认返回 2 个词（可用 --must-pick 调整）。

    注意：
    - 这是启发式，不保证总是最优；但能显著减少 "<TODO: fill must_include>" 的人工维护负担。
    """
    q = (query or "").strip()
    if not q:
        return []

    stop = {
        "如何",
        "怎么",
        "怎样",
        "为什么",
        "是否",
        "可以",
        "能否",
        "能不能",
        "请问",
        "的",
        "了",
        "呢",
        "吗",
        "么",
        "啊",
        "呀",
        "吧",
        "一下",
        "一个",
        "一些",
        "不同",
    }

    domain_terms = [
        "关卡",
        "存档",
        "元件",
        "角色",
        "动作",
        "武器",
        "装备",
        "地图",
        "边界",
        "地形",
        "小地图",
        "导入",
        "导出",
        "技能",
        "组件",
        "脚本",
        "节点图",
        "属性",
    ]

    synonym_map = {
        "建立": "创建",
        "新建": "创建",
        "制作": "创建",
        "设定": "设置",
        "设置": "设置",
        "范围": "范围",
    }

    picked: List[str] = []

    def add_term(t: str):
        t = t.strip()
        if not t or t in stop:
            return
        if t not in picked:
            picked.append(t)

    # 1) query 命中领域词
    for t in domain_terms:
        if t in q:
            add_term(t)

    # 2) 同义归一
    for k, v in synonym_map.items():
        if k in q:
            add_term(v)

    # 常见：关卡问题配套“创建”
    if "关卡" in q and "创建" not in picked:
        add_term("创建")

    # 3) 从推荐来源文件名提取中文片段（>=2）
    for s in (recommended_sources or [])[:3]:
        name = Path(s).name
        for m in re.findall(r"[\u4e00-\u9fff]{2,}", name):
            add_term(m)

    # 4) snippet bi-gram 兜底
    if len(picked) < pick:
        text = " ".join([(h.get("snippet") or "") for h in (hits or [])[:8]])
        cjk = re.findall(r"[\u4e00-\u9fff]+", text)
        joined = "".join(cjk)
        freq: Dict[str, int] = {}
        for i in range(len(joined) - 1):
            bg = joined[i : i + 2]
            if bg in stop:
                continue
            freq[bg] = freq.get(bg, 0) + 1
        for bg, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
            if len(picked) >= pick:
                break
            add_term(bg)

    return picked[: max(1, int(pick))]


def normalize_path_like(s: str) -> str:
    # Normalize slashes, remove redundant prefixes
    x = s.strip().replace("\\", "/")
    x = re.sub(r"^\./+", "", x)
    return x


def rel_to_root_if_possible(root: Path, s: str) -> str:
    """
    若 source 是绝对路径且位于 root 下，则转成相对路径；
    否则保持原样（但做 slash 规范化）。
    """
    x = s.strip()
    if not x:
        return ""
    x = x.replace("\\", "/")
    # windows drive absolute path
    try:
        p = Path(x)
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(root.resolve())
                return normalize_path_like(str(rel))
            except Exception:
                return normalize_path_like(x)
    except Exception:
        return normalize_path_like(x)
    return normalize_path_like(x)


def pick_meta_source(md: Mapping[str, Any], field_priority: List[str]) -> str:
    for k in field_priority:
        v = md.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fallback: any string that looks like a path
    for _, v in md.items():
        if isinstance(v, str) and ("/" in v or "\\" in v) and 1 < len(v) <= 500:
            return v.strip()
    return ""


def append_case(path: Path, case: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")


def embed_query(query: str, backend: str, model_name: str, device: str) -> List[float]:
    if backend == "auto":
        backend = "flagembedding"
        try:
            import importlib

            importlib.import_module("FlagEmbedding")
        except Exception:
            backend = "sentence-transformers"

    if backend not in ("flagembedding", "sentence-transformers"):
        backend = "sentence-transformers"

    if backend == "flagembedding":
        from FlagEmbedding import FlagModel

        model = FlagModel(model_name, query_instruction_for_retrieval=None, use_fp16=("cuda" in device.lower()))
        emb = model.encode([query])
        v = emb[0].tolist() if hasattr(emb[0], "tolist") else list(emb[0])
        return [float(x) for x in v]
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name, device=device)
        emb = model.encode([query], normalize_embeddings=True)
        v = emb[0].tolist() if hasattr(emb[0], "tolist") else list(emb[0])
        return [float(x) for x in v]

    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--query", required=True, help="user query")
    ap.add_argument("--db", default="chroma_db", help="chroma db directory relative to root")
    ap.add_argument("--collection", default="rag_chunks", help="chroma collection name")
    ap.add_argument("--k", type=int, default=8, help="topK retrieval")
    ap.add_argument("--pick", type=int, default=2, help="how many unique sources to recommend as expected_sources")
    ap.add_argument(
        "--meta-field", default="source_uri|source|path|file", help="metadata source field priority, separated by |"
    )
    ap.add_argument(
        "--embed-backend",
        default="auto",
        choices=["auto", "flagembedding", "sentence-transformers"],
        help="embedding backend",
    )
    ap.add_argument("--embed-model", default="BAAI/bge-m3", help="embedding model name")
    ap.add_argument("--device", default="cpu", help="embedding device: cpu/cuda")
    ap.add_argument("--out", default="", help="write a JSON with candidates and recommendation")
    ap.add_argument("--append-to", default="", help="append a full eval case to jsonl (with suggested must_include)")
    ap.add_argument("--must-pick", type=int, default=2, help="how many must_include terms to suggest when appending")
    ap.add_argument(
        "--auto-must-include", action="store_true", help="write suggested must_include even if empty (no TODO)"
    )
    ap.add_argument("--tags", default="suggested", help="comma separated tags (only for --append-to)")
    ap.add_argument("--show-snippet-chars", type=int, default=260, help="print snippet chars per hit")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db_path = (root / args.db).resolve()
    if not db_path.exists():
        print(f"[sources] FAIL: chroma db not found: {db_path}")
        return 2

    # embed
    try:
        qvec = embed_query(args.query, args.embed_backend, args.embed_model, args.device)
    except Exception as e:
        print(f"[sources] FAIL: embed error: {type(e).__name__}: {e}")
        return 2

    # chroma
    try:
        import chromadb
    except Exception as e:
        print(f"[sources] FAIL: chromadb not available: {type(e).__name__}: {e}")
        return 2

    client = chromadb.PersistentClient(path=str(db_path))
    try:
        col = client.get_collection(args.collection)
    except Exception as e:
        print(f"[sources] FAIL: collection not found: {args.collection} ({type(e).__name__}: {e})")
        return 2

    query_embeddings: List[Sequence[float]] = [qvec]
    res = col.query(
        query_embeddings=query_embeddings,
        n_results=int(args.k),
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    mds = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    field_priority = [x.strip() for x in args.meta_field.split("|") if x.strip()]
    hits: List[Dict[str, Any]] = []
    sources_raw: List[str] = []

    for i, (doc, md, dist) in enumerate(zip(docs, mds, dists), start=1):
        md = md or {}
        raw = pick_meta_source(md, field_priority)
        sources_raw.append(raw)
        src = rel_to_root_if_possible(root, raw) if raw else ""
        snippet = (str(doc or "").strip().replace("\r", " ").replace("\n", " "))[: int(args.show_snippet_chars)]
        hits.append(
            {
                "rank": i,
                "distance": dist,
                "source_raw": raw,
                "source": src,
                "snippet": snippet,
            }
        )

    # recommend expected_sources: unique sources, keep first N non-empty
    rec: List[str] = []
    for h in hits:
        s = h.get("source") or ""
        if not s:
            continue
        # heuristic: if it contains '#', strip anchor
        s2 = s.split("#", 1)[0]
        s2 = s2.strip()
        if s2 and s2 not in rec:
            rec.append(s2)
        if len(rec) >= int(args.pick):
            break

    # print
    print(f"[sources] query={args.query}")
    print(f"[sources] db={db_path}  collection={args.collection}  k={args.k}")
    print("")
    for h in hits:
        s = h["source"] or "<EMPTY>"
        print(f"{h['rank']:>2}. dist={h['distance']:.4f}  source={s}")
        if h["snippet"]:
            print(f"    {h['snippet']}")
    print("")
    print("[sources] recommended expected_sources (copy into eval case):")
    if rec:
        print(json.dumps(rec, ensure_ascii=False))
    else:
        print('["<TODO: fill expected_sources>"]')

    payload = {
        "timestamp": now_iso(),
        "query": args.query,
        "root": str(root),
        "db": str(db_path),
        "collection": args.collection,
        "k": int(args.k),
        "meta_field_priority": field_priority,
        "hits": hits,
        "recommended_expected_sources": rec,
    }

    # optional write json
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[sources] wrote: {out_path}")
    # optional append full case (must_include auto-suggested; fallback to TODO)
    if args.append_to:
        apath = Path(args.append_to)
        if not apath.is_absolute():
            apath = (root / apath).resolve()

        case = {
            "id": stable_id_from_query(args.query),
            "query": args.query,
            "expected_sources": rec if rec else ["<TODO: fill expected_sources>"],
            # 默认：尝试自动生成 must_include；生成失败才回退 TODO
            "must_include": [],
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
            "_suggest_sources_meta": {
                "timestamp": payload["timestamp"],
                "k": payload["k"],
                "top_sources_raw": sources_raw[: int(args.k)],
            },
        }

        suggested_must = suggest_must_include(
            query=args.query,
            recommended_sources=rec,
            hits=hits,
            pick=int(args.must_pick),
        )

        # 兼容开关：--auto-must-include 表示“强制写入建议值（即使为空也不写 TODO）”
        if args.auto_must_include:
            case["must_include"] = suggested_must
        else:
            case["must_include"] = suggested_must if suggested_must else ["<TODO: fill must_include>"]

        case["_suggest_must_include_meta"] = {
            "timestamp": payload["timestamp"],
            "must_pick": int(args.must_pick),
            "suggested": suggested_must,
            "method": "heuristic(query+filename+snippet_bigrams)",
        }

        append_case(apath, case)
        print(f"[sources] appended eval case skeleton to: {apath}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
