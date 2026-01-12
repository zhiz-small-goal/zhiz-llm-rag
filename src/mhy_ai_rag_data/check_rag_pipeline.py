"""RAG 管线自检脚本（不调用 LLM）。

说明：该脚本以交互式自检为主，不输出统一的 JSON 报告契约；若你要做回归/CI，请改用各“步骤验收脚本”的 `--json-out`。

作用：
- 对给定问题执行检索
- 检查拼接后的上下文长度是否在 RAG_MAX_CONTEXT_CHARS 以内
- 打印 messages 结构，确认能被 ChatCompletion 接口接受

用法示例：

    python check_rag_pipeline.py --q "存档导入与导出怎么做"
"""

from __future__ import annotations

import argparse

from mhy_ai_rag_data.rag_config import RAG_TOP_K, RAG_MAX_CONTEXT_CHARS
from mhy_ai_rag_data.retriever_chroma import retrieve
from mhy_ai_rag_data.prompt_rag import build_context, build_messages


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 管线快速自检（检索 + prompt 构造）")
    parser.add_argument("--q", required=True, help="问题文本")
    parser.add_argument("--k", type=int, default=None, help="检索 top-k，默认使用 RAG_TOP_K")
    args = parser.parse_args()

    k = args.k or RAG_TOP_K
    print(f"Q={args.q!r}")
    print(f"k={k}")
    print()

    # 1) 检索
    sources = retrieve(args.q, k)
    print(f"retrieved={len(sources)}")

    # 2) 拼接上下文
    ctx = build_context(sources)
    ctx_len = len(ctx)
    print(f"context_length={ctx_len} (limit={RAG_MAX_CONTEXT_CHARS})")
    if ctx_len > RAG_MAX_CONTEXT_CHARS:
        print("STATUS: WARN (context exceeds limit, consider reducing k or 调整切块策略)")
    else:
        print("STATUS: OK  (context within limit)")

    # 3) 构造 messages（不调用 LLM）
    messages = build_messages(args.q, sources)
    print(f"messages_count={len(messages)}")
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content", "")
        print(f"[message {i}] role={role}, content_length={len(content)}")

    print("\nRAG pipeline check finished.")


if __name__ == "__main__":
    main()
