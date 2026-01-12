#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_llm_http.py
用途：
- 快速判断你的 answer_cli 所指向的 LLM HTTP 后端是否可用，并输出可定位的失败点。
- 同时支持两类常见后端探测：
  A) OpenAI-compatible（如 LM Studio / vLLM / one-api 等）：GET /v1/models, POST /v1/chat/completions
  B) Ollama：GET /api/tags(或 /), POST /api/chat 或 /api/generate

运行示例（PowerShell）：
  python check_llm_http.py --base-url http://127.0.0.1:1234 --mode openai --model "qwen2.5-7b-instruct"
  python check_llm_http.py --base-url http://127.0.0.1:11434 --mode ollama --model "qwen2.5:7b" --endpoint chat

注意：
- 该脚本以“人工阅读输出”为主，不输出统一的 JSON 报告契约；若你要做 OpenAI-compatible 的回归探测与固定落盘，优先使用 `python -m tools.probe_llm_server ... --json-out ...`。
- 如果你使用了代理/中转（Nginx/one-api等），base-url 就填代理地址。
- 若你的后端需要 API Key，可用 --api-key 设置（OpenAI-compatible 常见）。
"""

from __future__ import annotations

import argparse
import time

from mhy_ai_rag_data.tools.llm_http_client import resolve_trust_env, get_session
from urllib.parse import urljoin

import requests


def _print_kv(title: str, kv: dict):
    print(f"\n[{title}]")
    for k, v in kv.items():
        print(f"- {k}: {v}")


def _try_get(sess, url: str, connect_timeout: float, read_timeout: float):
    t0 = time.time()
    try:
        r = sess.get(url, timeout=(connect_timeout, read_timeout))
        dt = time.time() - t0
        return {"ok": True, "status": r.status_code, "ms": int(dt * 1000), "text_head": r.text[:300]}
    except Exception as e:
        dt = time.time() - t0
        return {"ok": False, "error": repr(e), "ms": int(dt * 1000)}


def _try_post(sess, url: str, payload: dict, headers: dict, connect_timeout: float, read_timeout: float):
    t0 = time.time()
    try:
        r = sess.post(url, json=payload, headers=headers, timeout=(connect_timeout, read_timeout))
        dt = time.time() - t0
        head = r.text[:800]
        return {"ok": True, "status": r.status_code, "ms": int(dt * 1000), "text_head": head}
    except Exception as e:
        dt = time.time() - t0
        return {"ok": False, "error": repr(e), "ms": int(dt * 1000)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="例如 http://127.0.0.1:1234 或 http://127.0.0.1:11434")
    ap.add_argument("--mode", choices=["openai", "ollama"], required=True)
    ap.add_argument("--model", default="", help="openai: 模型名；ollama: model:tag")
    ap.add_argument("--api-key", default="", help="OpenAI-compatible 的 key（如需要）")
    ap.add_argument("--connect-timeout", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument(
        "--trust-env", default="auto", choices=["auto", "true", "false"], help="auto(loopback->false) / true / false"
    )
    ap.add_argument(
        "--endpoint", choices=["chat", "generate"], default="chat", help="ollama 使用 /api/chat 或 /api/generate"
    )
    args = ap.parse_args()

    base = args.base_url.rstrip("/") + "/"
    trust_env = resolve_trust_env(args.base_url, args.trust_env)
    sess = get_session(trust_env=trust_env)

    if args.mode == "openai":
        url_models = urljoin(base, "v1/models")
        _print_kv("OpenAI-compatible: GET /v1/models", {"url": url_models})
        res = _try_get(sess, url_models, args.connect_timeout, args.timeout)
        _print_kv("result", res)

        url_chat = urljoin(base, "v1/chat/completions")
        headers = {"Content-Type": "application/json"}
        if args.api_key:
            headers["Authorization"] = f"Bearer {args.api_key}"

        model = args.model or "gpt-3.5-turbo"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping：请只回复 pong"}],
            "temperature": 0.0,
            "stream": False,
            "max_tokens": 16,
        }
        _print_kv("OpenAI-compatible: POST /v1/chat/completions", {"url": url_chat, "model": model})
        res2 = _try_post(
            sess, url_chat, payload, headers=headers, connect_timeout=args.connect_timeout, read_timeout=args.timeout
        )
        _print_kv("result", res2)

        if res2.get("ok") and res2.get("status") == 200:
            try:
                data = sess.post(
                    url_chat, json=payload, headers=headers, timeout=(args.connect_timeout, args.timeout)
                ).json()
                _print_kv("parsed.choice0", {"content": data["choices"][0]["message"]["content"]})
            except Exception as e:
                _print_kv("parse_warning", {"error": repr(e)})

    else:
        # ollama
        url_root = base
        url_tags = urljoin(base, "api/tags")
        _print_kv("Ollama: GET / (or base)", {"url": url_root})
        res0 = _try_get(url_root, timeout=min(args.timeout, 10.0))
        _print_kv("result", res0)

        _print_kv("Ollama: GET /api/tags", {"url": url_tags})
        res1 = _try_get(url_tags, timeout=min(args.timeout, 10.0))
        _print_kv("result", res1)

        model = args.model or "qwen2.5:7b"
        if args.endpoint == "chat":
            url_chat = urljoin(base, "api/chat")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping：请只回复 pong"}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 16},
            }
            _print_kv("Ollama: POST /api/chat", {"url": url_chat, "model": model})
            res2 = _try_post(url_chat, payload, headers={"Content-Type": "application/json"}, timeout=args.timeout)
            _print_kv("result", res2)
        else:
            url_gen = urljoin(base, "api/generate")
            payload = {
                "model": model,
                "prompt": "ping：请只回复 pong",
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 16},
            }
            _print_kv("Ollama: POST /api/generate", {"url": url_gen, "model": model})
            res2 = _try_post(
                sess,
                url_gen,
                payload,
                headers={"Content-Type": "application/json"},
                connect_timeout=args.connect_timeout,
                read_timeout=args.timeout,
            )
            _print_kv("result", res2)

    print("\nDONE")


if __name__ == "__main__":
    try:
        import requests  # noqa
    except Exception:
        print("缺少 requests：请先 pip install requests")
        raise
    main()
