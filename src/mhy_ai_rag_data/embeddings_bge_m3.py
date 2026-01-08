
"""基于 BAAI/bge-m3 的查询向量计算封装。

注意：本模块假定已经通过 FlagEmbedding 安装了 BGEM3FlagModel。
"""

from typing import List

from FlagEmbedding import BGEM3FlagModel

from mhy_ai_rag_data.rag_config import EMBED_MODEL_NAME, EMBED_DEVICE, EMBED_BATCH

_MODEL: BGEM3FlagModel | None = None


def _get_model() -> BGEM3FlagModel:
    """懒加载并缓存 BGEM3FlagModel 实例。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = BGEM3FlagModel(EMBED_MODEL_NAME, use_fp16=True, device=EMBED_DEVICE)
    return _MODEL


def embed_query(text: str) -> list[float]:
    """将单条查询文本编码为 dense 向量。

    返回值为 list[float]，可直接用于 chroma.query 的 query_embeddings。
    """
    model = _get_model()
    outputs = model.encode([text], batch_size=EMBED_BATCH)
    dense_vecs = outputs["dense_vecs"]
    vec = dense_vecs[0]
    # 兼容 numpy 数组 / list 等
    return vec.tolist() if hasattr(vec, "tolist") else list(vec)
