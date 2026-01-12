#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/verify_torch_cuda.py

用途：
  验收当前 Python 环境中的 PyTorch 是否为 CUDA 构建，以及 CUDA 在运行时是否可用。
  用于阻断类似：
    AssertionError: Torch not compiled with CUDA enabled

退出码：
  0：PASS（torch.version.cuda 非空 且 torch.cuda.is_available() 为 True）
  2：FAIL（CPU-only torch 或 CUDA 不可用）
  3：ERROR（脚本异常）

用法：
  python tools\verify_torch_cuda.py
"""

from __future__ import annotations


def main() -> int:
    try:
        import torch

        info = {
            "torch_version": getattr(torch, "__version__", None),
            "torch_cuda_build": getattr(torch.version, "cuda", None),
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()) if hasattr(torch.cuda, "device_count") else None,
        }
        print("=== TORCH CUDA CHECK ===")
        for k, v in info.items():
            print(f"{k}={v}")

        if info["torch_cuda_build"] and info["cuda_available"]:
            try:
                name0 = torch.cuda.get_device_name(0)
                print(f"device0_name={name0}")
            except Exception:
                pass
            print("[RESULT] PASS")
            return 0

        print("[RESULT] FAIL")
        if not info["torch_cuda_build"]:
            print("reason=CPU-only torch (torch.version.cuda is None)")
            print(
                "hint=Install CUDA-enabled PyTorch wheels (see PyTorch official 'previous versions' page for --index-url cuXXX)."
            )
        else:
            print("reason=CUDA runtime not available (torch.cuda.is_available() is False)")
            print("hint=Check NVIDIA driver, then reinstall matching CUDA-enabled PyTorch build.")
        return 2
    except Exception as e:
        print("[RESULT] ERROR")
        print(f"error={e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
