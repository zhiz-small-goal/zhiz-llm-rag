#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mhy_ai_rag_data.tools.check_all

一键自检（工程门禁脚本）。

为何需要这个脚本
----------------
- 关键不变量：src-layout 之后，最容易出问题的是“导入路径/入口脚本/TOC 规范/关键模块缺失”。
- 高频复用：每次改动、换机、覆盖文件、合并补丁，都需要跑一次。
- 人工不可靠：手工执行一串命令容易漏步骤，且难复盘。

fast 模式覆盖内容
-----------------
1) 结构：pyproject.toml、src/mhy_ai_rag_data、关键模块存在。
2) 语法：compileall 编译 src 下所有 .py。
3) 入口：对关键模块执行 `python -m ... -h`，避免 import-time 崩溃。
4) 文档：README.md / docs/OPERATION_GUIDE.md 目录头与 TOC 链接存在。

退出码
------
0：PASS
2：FAIL
"""

from __future__ import annotations

import argparse
import compileall
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


CORE_MODULES: List[str] = [
    "mhy_ai_rag_data.make_inventory",
    "mhy_ai_rag_data.extract_units",
    "mhy_ai_rag_data.validate_rag_units",
    "mhy_ai_rag_data.tools.plan_chunks_from_units",
    "mhy_ai_rag_data.tools.build_chroma_index_flagembedding",
    "mhy_ai_rag_data.check_chroma_build",
    "mhy_ai_rag_data.tools.index_state",
]


def _fail(msg: str) -> Tuple[bool, str]:
    return False, msg


def _pass(msg: str) -> Tuple[bool, str]:
    return True, msg


def _check_exists(repo: Path, rel: str) -> Tuple[bool, str]:
    p = repo / rel
    if p.exists():
        return _pass(f"OK: exists {rel}")
    return _fail(f"MISSING: {rel}")


def _compile_src(src_dir: Path) -> Tuple[bool, str]:
    # quiet=1 仅输出错误；force=True 避免缓存误判
    ok = bool(compileall.compile_dir(str(src_dir), quiet=1, force=True))
    if ok:
        return _pass("OK: compileall src")
    return _fail("FAIL: compileall src (see output above)")


def _run_help(repo: Path, module: str) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", module, "-h"]

    # 子进程默认找不到 src/ 下的包；这里显式注入 PYTHONPATH。
    env = dict(os.environ)
    src = str((repo / "src").resolve())
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = src + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = src

    p = subprocess.run(cmd, cwd=str(repo), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode == 0:
        return _pass(f"OK: python -m {module} -h")
    # argparse 会返回 0；如果是 import-time 崩溃通常非 0，stderr 有栈
    tail = (p.stderr or p.stdout or "").strip().splitlines()[-6:]
    return _fail(f"FAIL: python -m {module} -h (rc={p.returncode})\n" + "\n".join(tail))


def _toc_header(filename: str) -> str:
    # filename 不含路径
    base = Path(filename).name
    stem = base
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return f"# {stem}目录："


def _check_toc(md_path: Path) -> Tuple[bool, str]:
    if not md_path.exists():
        return _fail(f"MISSING: {md_path}")
    lines = md_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return _fail(f"FAIL: empty file {md_path}")

    want = _toc_header(md_path.name)
    if lines[0].strip() != want:
        return _fail(f"FAIL: TOC header mismatch in {md_path}.\n  want: {want}\n  got:  {lines[0].strip()}")

    # 至少包含一条目录链接（- [..](#...)）
    toc_ok = any(re.match(r"^\s*-\s+\[[^\]]+\]\(#[^)]+\)", ln) for ln in lines[1:120])
    if not toc_ok:
        return _fail(f"FAIL: TOC links not found near top of {md_path}")

    return _pass(f"OK: TOC present in {md_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="One-click repository gate check (src-layout, imports, TOC).")
    ap.add_argument("--root", default=".", help="Repo root (default: current directory)")
    ap.add_argument(
        "--mode",
        default="fast",
        choices=["fast"],
        help="Check mode (currently only fast).",
    )
    args = ap.parse_args()

    repo = Path(args.root).resolve()
    src_dir = repo / "src"

    checks: List[Tuple[bool, str]] = []

    # 1) structure
    checks.append(_check_exists(repo, "pyproject.toml"))
    checks.append(_check_exists(repo, "src/mhy_ai_rag_data/__init__.py"))
    checks.append(_check_exists(repo, "src/mhy_ai_rag_data/tools/index_state.py"))
    checks.append(_check_exists(repo, "src/mhy_ai_rag_data/tools/build_chroma_index_flagembedding.py"))

    # 2) python compile
    checks.append(_compile_src(src_dir))

    # 3) module help (import-time safety)
    for m in CORE_MODULES:
        checks.append(_run_help(repo, m))

    # 4) docs TOC
    checks.append(_check_toc(repo / "README.md"))
    checks.append(_check_toc(repo / "docs/OPERATION_GUIDE.md"))

    # report
    failed = [msg for ok, msg in checks if not ok]
    for ok, msg in checks:
        print(("PASS: " if ok else "FAIL: ") + msg)

    if failed:
        print("\nSTATUS: FAIL")
        return 2

    print("\nSTATUS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
