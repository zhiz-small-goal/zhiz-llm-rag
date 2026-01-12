#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""capture_rag_env.py

目的
----
把“模型机/开发机”的关键运行环境抓成一份可回溯报告，用于：
- 对齐两台机器的 Python/依赖版本
- 复现某次构建/检索问题（把 report 附在 issue/日志后面）
- 排查 CUDA/torch 版本与显卡不可用等问题

输出
----
默认输出到 data_processed/env_report.json，包括：
- Python 版本、平台信息
- pip freeze（精简）
- chromadb / FlagEmbedding / sentence-transformers 版本
- torch 版本与 cuda 可用性（如果 torch 已安装）

用法
----
python capture_rag_env.py --out data_processed/env_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


KEY_PACKAGES = [
    "chromadb",
    "FlagEmbedding",
    "sentence-transformers",
    "torch",
    "transformers",
    "huggingface-hub",
    "numpy",
    "pandas",
]


def _run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=False)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 1, "", str(e)


def _pip_show(name: str):
    rc, out, err = _run([sys.executable, "-m", "pip", "show", name])
    if rc != 0 or not out.strip():
        return None
    info = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        info[k.strip()] = v.strip()
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_processed/env_report.json")
    args = ap.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    packages: Dict[str, Any] = {}
    report: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "env": {
            "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV"),
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "packages": packages,
        "pip_freeze": None,
        "torch": None,
    }

    for pkg in KEY_PACKAGES:
        report["packages"][pkg] = _pip_show(pkg)

    rc, out, err = _run([sys.executable, "-m", "pip", "freeze"])
    if rc == 0:
        # keep as list to be diff-friendly
        report["pip_freeze"] = [ln.strip() for ln in out.splitlines() if ln.strip()]
    else:
        report["pip_freeze_error"] = err

    # torch details (optional)
    try:
        import torch

        report["torch"] = {
            "__version__": getattr(torch, "__version__", None),
            "cuda_is_available": bool(torch.cuda.is_available()),
            "cuda_version": getattr(torch.version, "cuda", None),
            "cudnn_version": getattr(torch.backends.cudnn, "version", lambda: None)(),
            "gpu_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
            "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            if torch.cuda.is_available()
            else [],
        }
    except Exception as e:
        report["torch"] = {"error": str(e)}

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
