from __future__ import annotations

import sys


def main() -> int:
    # 默认行为：提示用户使用 rag-* 或具体模块。
    print("mhy_ai_rag_data: use 'rag-...' console scripts or 'python -m mhy_ai_rag_data.<module> ...'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
