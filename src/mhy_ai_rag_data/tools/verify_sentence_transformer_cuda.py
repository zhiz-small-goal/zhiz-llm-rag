#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/verify_sentence_transformer_cuda.py

用途：
  验收 sentence-transformers 在当前环境下是否能把模型加载到 CUDA，并完成一次最小 embedding。
  这是 build_chroma_index.py 使用 --device cuda:0 的直接前置条件之一。

退出码：
  0：PASS（成功在 CUDA 上完成一次 encode）
  2：FAIL（CUDA 不可用 / 模型未在 CUDA 上运行 / encode 失败）
  3：ERROR（脚本异常）

用法：
  python tools\verify_sentence_transformer_cuda.py --model BAAI/bge-m3 --device cuda:0 --text "hello"
"""

from __future__ import annotations

import argparse

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--text", default="hello world")
    args = ap.parse_args()

    try:
        import torch
        from sentence_transformers import SentenceTransformer

        print("=== SENTENCE_TRANSFORMERS CUDA CHECK ===")
        print(f"torch_version={getattr(torch,'__version__',None)}")
        print(f"torch_cuda_build={getattr(torch.version,'cuda',None)}")
        print(f"cuda_available={bool(torch.cuda.is_available())}")
        if not torch.cuda.is_available():
            print("[RESULT] FAIL")
            print("reason=torch.cuda.is_available() is False")
            return 2

        model = SentenceTransformer(args.model, device=args.device)
        # 打印模型参数所在设备
        try:
            p = next(model._first_module().parameters())
            print(f"param_device={p.device}")
        except Exception:
            pass

        vec = model.encode([args.text], normalize_embeddings=False)
        print(f"embed_shape={getattr(vec,'shape',None)}")
        print("[RESULT] PASS")
        return 0
    except Exception as e:
        print("[RESULT] FAIL")
        print(f"error={e}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
