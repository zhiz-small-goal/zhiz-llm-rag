"""RAG 闭环最小可用 CLI。

用法示例：

    python answer_cli.py --q "存档导入与导出怎么做"
    python answer_cli.py --q "如何自定义资产" --k 8

默认行为：
1）从 Chroma 中检索 top-k 证据块
2）打印每个证据块的概览
3）构造 RAG prompt 调用 LLM
4）打印最终回答
"""

from __future__ import annotations

import argparse
import textwrap

from mhy_ai_rag_data.rag_config import RAG_TOP_K
from mhy_ai_rag_data.retriever_chroma import retrieve
from mhy_ai_rag_data.prompt_rag import build_messages
from mhy_ai_rag_data.llm_client_http import call_llm, LLMError


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 闭环最小可用 CLI")
    parser.add_argument("--q", required=True, help="问题文本")
    parser.add_argument("--k", type=int, default=None, help="检索 top-k，默认使用 RAG_TOP_K")
    parser.add_argument(
        "--only-sources",
        action="store_true",
        help="仅打印检索结果，不调用 LLM（用于调试检索）",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="LLM temperature，默认 0.2",
    )
    args = parser.parse_args()

    k = args.k or RAG_TOP_K
    print(f"Q: {args.q}")
    print(f"k={k}")
    print()

    # 1) 检索
    sources = retrieve(args.q, k)
    print(f"=== RETRIEVED SOURCES ({len(sources)}) ===")
    for s in sources:
        preview = (s.text or "").replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "..."
        header = f"{s.sid}: doc_id={s.doc_id} source_uri={s.source_uri} locator={s.locator}"
        print(header)
        print(textwrap.indent(preview, prefix="    "))
        print()

    if args.only_sources:
        return

    # 2) 构造 prompt
    messages = build_messages(args.q, sources)

    # 3) 调用 LLM
    print("=== ANSWER ===")
    try:
        answer = call_llm(messages, temperature=args.temperature)
    except LLMError as exc:
        print(f"[LLM ERROR] {exc}")
        return

    print(answer)


if __name__ == "__main__":
    main()
