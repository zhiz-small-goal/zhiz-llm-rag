#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REPO-ONLY TOOL

gen_tools_wrappers.py

目的：
  - 为“受管 wrapper”（managed wrappers）生成/刷新一致的模板内容；
  - 在 CI/PR Gate 中用 `--check` 模式确保 wrapper 未被手工改坏（避免入口漂移/双实现）。

关键概念：
  - SSOT 在 src：`src/mhy_ai_rag_data/tools/<name>.py`
  - tools 仅承载“入口 shim”：`tools/<name>.py`
  - 受管 wrapper 清单由 `tools/wrapper_gen_config.json` 的 `managed_wrappers` 控制

用法（在仓库根目录）：
  - 校验（不改文件，适合 CI）：
      python tools/gen_tools_wrappers.py --check
  - 生成/刷新（写入文件，需提交）：
      python tools/gen_tools_wrappers.py --write
  - 允许创建缺失的受管 wrapper（谨慎使用）：
      python tools/gen_tools_wrappers.py --write --bootstrap-missing

对比策略（重要）：
  - 默认（canonical compare）：忽略 CRLF/LF、UTF-8 BOM、行尾空白；只要“内容语义”一致即 PASS。
  - 严格模式（--strict）：保留磁盘真实换行，并要求与生成模板（按当前 OS 的换行约定）逐字一致。

诊断输出（门禁友好）：
  - mismatch 时输出 `file:line:col` 行首定位，并附带截断 unified diff（可用 --diff-max-lines 调整）。

退出码：
  - 0：PASS
  - 2：FAIL（不一致/缺失/配置错误）
  - 3：ERROR（脚本异常）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class Config:
    src_module_prefix: str
    src_tools_dir: Path
    tools_dir: Path
    wrapper_marker: str
    repo_only_marker: str
    ignore_files: Tuple[str, ...]
    managed_wrappers: Tuple[str, ...]
    exclude_wrappers: Tuple[str, ...]
    exclude_self: bool


def _repo_root() -> Path:
    # tools/gen_tools_wrappers.py -> <repo>/tools -> <repo>
    return Path(__file__).resolve().parent.parent


def _load_config(repo: Path, config_path: Path | None) -> Config:
    default = {
        "src_module_prefix": "mhy_ai_rag_data.tools",
        "src_tools_dir": "src/mhy_ai_rag_data/tools",
        "tools_dir": "tools",
        "wrapper_marker": "AUTO-GENERATED WRAPPER",
        "repo_only_marker": "REPO-ONLY TOOL",
        "ignore_files": ["__init__.py", "__main__.py"],
        # 永久排除：生成器自身是 repo-only，不应被当作 wrapper 管理。
        "exclude_wrappers": ["gen_tools_wrappers.py"],
        "exclude_self": True,
        # 只管理你明确列出的 wrapper；避免一次性重写全仓库 wrapper 模板
        "managed_wrappers": ["check_tools_layout.py"],
    }
    if config_path is None:
        config_path = repo / "tools" / "wrapper_gen_config.json"
    if config_path.exists():
        obj = json.loads(config_path.read_text(encoding="utf-8"))
        default.update(obj)

    managed = tuple(str(x) for x in default.get("managed_wrappers", []) if str(x).strip())
    excluded = tuple(str(x) for x in default.get("exclude_wrappers", []) if str(x).strip())
    exclude_self = bool(default.get("exclude_self", True))

    return Config(
        src_module_prefix=str(default["src_module_prefix"]),
        src_tools_dir=(repo / str(default["src_tools_dir"])).resolve(),
        tools_dir=(repo / str(default["tools_dir"])).resolve(),
        wrapper_marker=str(default["wrapper_marker"]),
        repo_only_marker=str(default["repo_only_marker"]),
        ignore_files=tuple(default["ignore_files"]),
        managed_wrappers=managed,
        exclude_wrappers=excluded,
        exclude_self=exclude_self,
    )


def _is_repo_only(cfg: Config, p: Path) -> bool:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return cfg.repo_only_marker in text


def _discover_managed_wrappers(cfg: Config) -> Tuple[str, List[Path]]:
    """Return (source, managed_paths).

    - source=list: explicit allowlist via managed_wrappers
    - source=scan: auto-discovery via wrapper_marker in tools/*.py
    """
    # 明确清单优先；否则回退为“扫描所有包含 wrapper_marker 的 tools/*.py”
    tools_dir = cfg.tools_dir
    if not tools_dir.exists():
        return "none", []

    ignore = set(cfg.ignore_files)
    ignore.update(cfg.exclude_wrappers)
    if cfg.exclude_self:
        ignore.add(Path(__file__).name)

    if cfg.managed_wrappers:
        out: List[Path] = []
        for name in cfg.managed_wrappers:
            if name in ignore:
                continue
            p = tools_dir / name
            # 安全阀：repo-only 工具不应被当作 wrapper 管理
            if p.exists() and _is_repo_only(cfg, p):
                continue
            out.append(p)
        return "list", out

    managed: List[Path] = []
    for p in sorted(tools_dir.glob("*.py")):
        if p.name in ignore:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if cfg.wrapper_marker in text and cfg.repo_only_marker not in text:
            managed.append(p)
    return "scan", managed


def _expected_wrapper_text(cfg: Config, name: str) -> str:
    # name: "foo.py"
    stem = Path(name).stem
    target_mod = f"{cfg.src_module_prefix}.{stem}"
    rel_gen = "tools/gen_tools_wrappers.py"
    rel_src = os.path.relpath(cfg.src_tools_dir / f"{stem}.py", cfg.tools_dir.parent).replace("\\", "/")

    # NOTE: content is deterministic; keep edits minimal and stable.
    return (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        f'"""{cfg.wrapper_marker}\n\n'
        f"Generated-By: {rel_gen}\n"
        f"Target-Module: {target_mod}\n"
        f"SSOT: {rel_src}\n\n"
        "兼容入口：允许运行 `python tools/<name>.py ...`，但真实实现固定在 src（SSOT）。\n"
        "不要手工修改本文件；请运行：python tools/gen_tools_wrappers.py --write\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "import runpy\n"
        "import sys\n"
        "import traceback\n"
        "from pathlib import Path\n\n\n"
        "def _ensure_src_on_path() -> None:\n"
        "    # 保证在未 editable install 的情况下也能导入 src 侧实现\n"
        "    repo = Path(__file__).resolve().parent\n"
        "    if repo.name == 'tools':\n"
        "        repo = repo.parent\n"
        "    src = repo / 'src'\n"
        "    if src.exists():\n"
        "        sys.path.insert(0, str(src))\n\n\n"
        "def main() -> int:\n"
        "    _ensure_src_on_path()\n"
        f"    runpy.run_module('{target_mod}', run_name='__main__')\n"
        "    return 0\n\n\n"
        "def _entry() -> int:\n"
        "    try:\n"
        "        return main()\n"
        "    except KeyboardInterrupt:\n"
        "        print('[ERROR] KeyboardInterrupt', file=sys.stderr)\n"
        "        return 3\n"
        "    except SystemExit as e:\n"
        "        code = e.code\n"
        "        if code is None:\n"
        "            return 0\n"
        "        if isinstance(code, int):\n"
        "            return code\n"
        "        print(f'[ERROR] SystemExit: {code}', file=sys.stderr)\n"
        "        return 3\n"
        "    except Exception:\n"
        "        print('[ERROR] unhandled exception', file=sys.stderr)\n"
        "        traceback.print_exc()\n"
        "        return 3\n\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(_entry())\n"
    )


def _validate_src_exists(cfg: Config, stem: str) -> Tuple[bool, str]:
    src_py = cfg.src_tools_dir / f"{stem}.py"
    if not src_py.exists():
        return False, f"missing SSOT: {src_py}"
    return True, ""


def _canonical_text(s: str, *, strip_trailing_ws: bool = True, ensure_final_nl: bool = True) -> str:
    """Normalize text for robust comparisons.

    - Normalize newlines to \n
    - Drop UTF-8 BOM if present
    - Optionally strip trailing whitespace per line
    - Optionally ensure exactly one final newline
    """
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if strip_trailing_ws:
        s = "\n".join(line.rstrip() for line in s.split("\n"))
    if ensure_final_nl:
        s = s.rstrip("\n") + "\n"
    return s


def _read_text(path: Path, *, strict_newlines: bool) -> str:
    """Read UTF-8 text.

    strict_newlines=False uses universal newline translation (CRLF/LF -> \n).
    strict_newlines=True preserves disk newlines (newline="").
    """
    if strict_newlines:
        with path.open("r", encoding="utf-8", errors="strict", newline="") as f:
            return f.read()
    return path.read_text(encoding="utf-8", errors="strict")


def _first_diff_loc(a: str, b: str) -> tuple[int, int]:
    """Return (line, col) 1-based of first textual difference; best-effort."""
    a_lines = a.split("\n")
    b_lines = b.split("\n")
    n = min(len(a_lines), len(b_lines))
    for i in range(n):
        if a_lines[i] != b_lines[i]:
            col = 1
            m = min(len(a_lines[i]), len(b_lines[i]))
            for j in range(m):
                if a_lines[i][j] != b_lines[i][j]:
                    col = j + 1
                    break
            return (i + 1, col)
    return (n + 1, 1)


def _short_udiff(path_label: str, actual: str, expected: str, *, max_lines: int) -> str:
    import difflib

    diff = difflib.unified_diff(
        actual.splitlines(True),
        expected.splitlines(True),
        fromfile=f"{path_label} (actual)",
        tofile=f"{path_label} (expected)",
        n=3,
    )
    out: list[str] = []
    for i, line in enumerate(diff):
        out.append(line.rstrip("\n"))
        if i + 1 >= max_lines:
            out.append("... (diff truncated)")
            break
    return "\n".join(out)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config", default=None, help="path to wrapper_gen_config.json (default: tools/wrapper_gen_config.json)"
    )
    ap.add_argument(
        "--check", action="store_true", help="check managed wrappers match expected template; do not modify files"
    )
    ap.add_argument("--write", action="store_true", help="rewrite managed wrappers to expected template")
    ap.add_argument(
        "--bootstrap-missing",
        action="store_true",
        help="in --write mode, create missing managed wrappers if SSOT exists",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="strict compare: preserve disk newlines and require exact match (including CRLF/LF); recommended only after migration",
    )
    ap.add_argument(
        "--diff-max-lines",
        type=int,
        default=80,
        help="max unified-diff lines to print per mismatched wrapper (default: 80)",
    )
    ap.add_argument(
        "--no-diff", action="store_true", help="do not print unified diff on mismatch (still prints file:line:col)"
    )
    ap.add_argument(
        "--keep-trailing-ws",
        action="store_true",
        help="do not strip trailing whitespace in canonical compare (default strips)",
    )
    args = ap.parse_args(argv)

    if args.check and args.write:
        print("[FATAL] choose only one: --check or --write")
        return 2
    mode = "check" if args.check or not args.write else "write"

    repo = _repo_root()
    cfg_path = Path(args.config) if args.config else (repo / "tools" / "wrapper_gen_config.json")
    cfg = _load_config(repo, cfg_path)

    source, managed = _discover_managed_wrappers(cfg)
    if not managed:
        print("[WARN] no managed wrappers configured/found.")
        return 0

    mismatched: List[Path] = []
    mismatch_details: dict[Path, tuple[int, int, str]] = {}
    missing_ssot: List[Tuple[Path, str]] = []
    missing_wrapper: List[Path] = []
    rewritten: List[Path] = []

    for tool_py in managed:
        name = tool_py.name
        stem = tool_py.stem

        ok, msg = _validate_src_exists(cfg, stem)
        if not ok:
            missing_ssot.append((tool_py, msg))
            continue

        expected = _expected_wrapper_text(cfg, name)

        if not tool_py.exists():
            if mode == "write" and args.bootstrap_missing:
                tool_py.write_text(expected, encoding="utf-8", newline=os.linesep)
                rewritten.append(tool_py)
            else:
                missing_wrapper.append(tool_py)
            continue

        try:
            actual_raw = _read_text(tool_py, strict_newlines=bool(args.strict))
        except UnicodeDecodeError as e:
            mismatched.append(tool_py)
            mismatch_details[tool_py] = (1, 1, f"[ERROR] UTF-8 decode failed: {e}")
            continue

        if args.strict:
            expected_cmp = expected.replace("\n", os.linesep)
            expected_cmp = expected_cmp.rstrip("\r\n") + os.linesep
            actual_cmp = actual_raw
        else:
            strip_ws = not bool(args.keep_trailing_ws)
            expected_cmp = _canonical_text(expected, strip_trailing_ws=strip_ws, ensure_final_nl=True)
            actual_cmp = _canonical_text(actual_raw, strip_trailing_ws=strip_ws, ensure_final_nl=True)

        if actual_cmp != expected_cmp:
            if mode == "write":
                tool_py.write_text(expected, encoding="utf-8", newline=os.linesep)
                rewritten.append(tool_py)
            else:
                mismatched.append(tool_py)
                line, col = _first_diff_loc(actual_cmp, expected_cmp)
                diff_txt = ""
                if not args.no_diff:
                    try:
                        label = str(tool_py.relative_to(repo))
                    except Exception:
                        label = str(tool_py)
                    diff_txt = _short_udiff(label, actual_cmp, expected_cmp, max_lines=int(args.diff_max_lines))
                mismatch_details[tool_py] = (line, col, diff_txt)

    print(f"[gen_tools_wrappers] mode={mode}")
    print(f"[gen_tools_wrappers] config={cfg_path}")
    print(f"[gen_tools_wrappers] discovery_source={source}")
    print(f"[gen_tools_wrappers] managed_wrappers={len(managed)}")

    if missing_ssot:
        print("[FAIL] wrappers with missing SSOT:")
        for p, msg in missing_ssot:
            print(f" - {p}: {msg}")

    if missing_wrapper:
        print("[FAIL] missing managed wrapper files (use --write --bootstrap-missing):")
        for p in missing_wrapper:
            print(f" - {p}")

    if mismatched:
        print("[FAIL] wrappers not up-to-date (run --write to refresh):")
        for p in mismatched:
            print(f" - {p}")
        for p in mismatched:
            line, col, diff_txt = mismatch_details.get(p, (1, 1, ""))
            try:
                rel = str(p.relative_to(repo))
            except Exception:
                rel = str(p)
            print(f"{rel}:{line}:{col} [FAIL] wrapper drift detected")
            if diff_txt:
                print(diff_txt)

    if rewritten:
        print("[OK] rewritten wrappers:")
        for p in rewritten:
            print(f" - {p}")

    if missing_ssot or missing_wrapper or mismatched:
        return 2
    return 0


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("[ERROR] KeyboardInterrupt", file=sys.stderr)
        return 3
    except SystemExit:
        raise
    except Exception:
        print("[ERROR] unhandled exception", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(_entry())
