"""RAG prompt 构造封装。

负责：
- 将检索到的 SourceChunk 列表拼接为上下文片段（带 [Sx] 标记）
- 构造适合 ChatCompletion 风格接口的 messages 列表
"""

from __future__ import annotations

from typing import List

from mhy_ai_rag_data.rag_config import RAG_MAX_CONTEXT_CHARS
from mhy_ai_rag_data.retriever_chroma import SourceChunk


def build_context(sources: List[SourceChunk]) -> str:
    """将检索到的 sources 拼成一个大的上下文字符串。

    每个片段带 [Sx] 标记，并附带 doc_id / source_uri，便于 LLM 在回答中引用。
    同时受 RAG_MAX_CONTEXT_CHARS 限制，避免超长。
    """
    parts: list[str] = []
    total = 0

    for s in sources:
        header = f"[{s.sid}] doc_id={s.doc_id} source_uri={s.source_uri} locator={s.locator}\n"
        body = (s.text or "").strip()
        piece = header + body + "\n"
        piece_len = len(piece)
        if parts and total + piece_len > RAG_MAX_CONTEXT_CHARS:
            break
        parts.append(piece)
        total += piece_len

    return "\n\n".join(parts)


def build_messages(question: str, sources: List[SourceChunk]) -> list[dict]:
    """构造 ChatCompletion 所需的 messages 列表。"""
    context = build_context(sources)

    system = (
        "你是一名技术助教，只能使用给定资料回答问题。"
        "如果资料不足以得出结论，请明确说明“资料不足”并指出需要补充的资料类型，不要编造细节。"
        "回答结构：先给出 1–3 条结论，每条后用 [Sx] 标注引用来源；然后分步骤解释依据和推理过程。"
    )

    user = (
        "下面是与问题相关的资料片段，每个片段以 [Sx] 开头：\n\n"
        f"{context}\n\n"
        f"问题：{question}\n\n"
        "要求：\n"
        "1）只基于上述资料回答，不要引入外部知识；\n"
        "2）结论部分尽量简洁，解释部分可以引用多个 [Sx]；\n"
        "3）如资料存在冲突，请指出冲突点，并给出在当前资料下最稳妥的解释。"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
