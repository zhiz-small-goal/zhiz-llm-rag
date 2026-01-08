#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_eval_cases.py

目的：
- 初始化 Stage-2 评测用例集（retrieval + rag），形成可版本化的回归基线
- 用例格式采用 JSONL，便于增量维护与 diff 审阅

输出：
- <root>/data_processed/eval/eval_cases.jsonl

用法：
  python tools/init_eval_cases.py --root . --out data_processed/eval/eval_cases.jsonl
  python tools/init_eval_cases.py --root . --force  # 覆盖重建（谨慎）

字段说明（每行一个 case）：
- id: 用例唯一标识
- query: 用户问题
- expected_sources: 期望命中文档路径（相对 root 的路径片段；支持多个）
- must_include: 生成答案应包含的关键词/短语（用于轻量断言）
- tags: 用例标签（可选）

退出码：
  0 成功
  2 输出文件已存在且未指定 --force
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


SAMPLE_CASES: List[Dict[str, Any]] = [
    {
        "id": "tutorial_save_import_export",
        "query": "存档导入与导出怎么做？",
        "expected_sources": ["data_raw/教程/05_1.4存档导入与导出.md"],
        "must_include": ["导入", "导出"],
        "tags": ["tutorial", "baseline"],
    },
    {
        "id": "custom_components",
        "query": "如何自定义元件？",
        "expected_sources": ["data_raw/综合指南/06_元件库.md"],
        "must_include": ["自定义", "元件"],
        "tags": ["custom", "element"],
    },
    {
        "id": "customize_game_character_actions",
        "query": "如何自定义角色游戏内动作？",
        "expected_sources": ["data_raw/综合指南/99_技能.md"],
        "must_include": ["角色", "动作"],
        "tags": ["tutorial", "role"],
    },
    {
        "id": "designing_game_weapons",
        "query": "想设计新武器弓箭该怎么做？",
        "expected_sources": ["data_raw/综合指南/143_结构体.md", "data_raw/教程/35_3.15装备——可用于角色穿戴的特殊道具.md"],
        "must_include": ["自定义", "装备"],
        "tags": ["gameweapons"],
    },
    {
        "id": "define_map_boundaries",
        "query": "如何设定地图边界？",
        "expected_sources": ["data_raw/教程/02_1.1编辑器界面基础认识.md"],
        "must_include": ["关卡", "范围"],
        "tags": ["map", "define"],
    },
]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--out", default="data_processed/eval/eval_cases.jsonl", help="output jsonl path relative to root")
    ap.add_argument("--force", action="store_true", help="overwrite if exists")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_path = (root / args.out).resolve()
    ensure_dir(out_path.parent)

    if out_path.exists() and not args.force:
        print(f"[init_eval] FAIL: output exists: {out_path} (use --force to overwrite)")
        return 2

    with out_path.open("w", encoding="utf-8") as f:
        for c in SAMPLE_CASES:
            c2 = dict(c)
            c2.setdefault("bucket", "official")
            c2.setdefault("pair_id", None)
            c2.setdefault("concept_id", None)
            f.write(json.dumps(c2, ensure_ascii=False) + "\n")

    print(f"[init_eval] OK  wrote={out_path}  cases={len(SAMPLE_CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
