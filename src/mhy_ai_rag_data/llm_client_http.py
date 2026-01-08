#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_client_http.py

通过 HTTP 调用 **OpenAI-compatible** Chat Completions 接口。

本文件是 answer_cli.py 的 LLM 客户端实现（同步 requests）。

关键改动（替代方案 B）：
- 统一走 tools/llm_http_client.py，默认对回环地址禁用环境代理（trust_env=False），避免 127.0.0.1:7890 代理劫持。
- timeout 拆分 connect/read：requests 支持 timeout=(connect, read)。

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from mhy_ai_rag_data.rag_config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_MAX_TOKENS

try:
    # answer_cli 在项目根目录运行时可用
    from mhy_ai_rag_data.tools.llm_http_client import chat_completions, extract_chat_content, LLMHTTPError
except Exception:  # noqa: BLE001
    # 极端情况下（例如被复制到 tools 目录单独运行）兜底
    from llm_http_client import chat_completions, extract_chat_content, LLMHTTPError  # type: ignore


@dataclass
class LLMError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


def call_llm(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    base_url: str = LLM_BASE_URL,
    api_key: str = LLM_API_KEY,
    model: str = LLM_MODEL,
    max_tokens: int = LLM_MAX_TOKENS,
    connect_timeout: float = 10.0,
    read_timeout: float = 300.0,
    trust_env: str = "auto",
) -> str:
    """调用 OpenAI-compatible 的 /chat/completions 并返回文本内容。"""
    headers: Optional[Dict[str, str]] = None
    if api_key and api_key.upper() != "EMPTY":
        headers = {"Authorization": f"Bearer {api_key}"}

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    try:
        resp = chat_completions(
            base_url,
            payload,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            trust_env_mode=trust_env,
            headers=headers,
        )
        return extract_chat_content(resp)
    except LLMHTTPError as exc:
        raise LLMError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
