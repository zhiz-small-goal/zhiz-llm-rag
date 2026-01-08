#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.probe_llm_server

目的：
  快速探测一个 LLM HTTP 服务是否为 OpenAI-compatible 接口，并验证其端点可用性。
  重点用于回答：base_url/端口/路径是否可达；最小 chat/completions 是否能在超时内返回。

关键规则（与本项目 JSON 契约一致）：
- 当提供 --json-out 时，只写该路径，不再额外生成默认时间戳报告文件。

推荐运行方式（避免 import 路径问题）：
  python -m tools.probe_llm_server --base http://localhost:8000/v1 --timeout 10 --json-out data_processed/build_reports/llm_probe.json
"""

from __future__ import annotations

import argparse
import json
import time
from urllib.parse import urljoin

try:
    # 兼容两种运行方式：python -m tools.probe_llm_server 以及 python tools/probe_llm_server.py
    from mhy_ai_rag_data.tools.llm_http_client import resolve_trust_env, get_session, resolve_model_id
except Exception:  # noqa: BLE001
    from llm_http_client import resolve_trust_env, get_session, resolve_model_id  # type: ignore

from mhy_ai_rag_data.tools.reporting import build_base, add_error, write_report, status_to_rc


GET_CANDIDATES = [
    "/", "/v1/models", "/models", "/docs", "/openapi.json", "/v1", "/api/tags",
]

POST_CANDIDATES = [
    "/v1/chat/completions", "/chat/completions", "/v1/completions",
]


def _get(url: str, connect_timeout: float, read_timeout: float, trust_env: bool) -> dict:
    t0 = time.time()
    try:
        sess = get_session(trust_env=trust_env)
        r = sess.get(url, timeout=(connect_timeout, read_timeout))
        dt = time.time() - t0
        return {"ok": True, "status": r.status_code, "seconds": round(dt, 4), "text_head": r.text[:600]}
    except Exception as e:
        dt = time.time() - t0
        return {"ok": False, "error": repr(e), "seconds": round(dt, 4)}


def _post(url: str, payload: dict, connect_timeout: float, read_timeout: float, trust_env: bool) -> dict:
    t0 = time.time()
    try:
        sess = get_session(trust_env=trust_env)
        r = sess.post(url, json=payload, timeout=(connect_timeout, read_timeout))
        dt = time.time() - t0
        return {"ok": True, "status": r.status_code, "seconds": round(dt, 4), "text_head": r.text[:800]}
    except Exception as e:
        dt = time.time() - t0
        return {"ok": False, "error": repr(e), "seconds": round(dt, 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="例如 http://localhost:8000 或 http://localhost:8000/v1")
    ap.add_argument("--connect-timeout", type=float, default=5.0, help="连接超时秒（requests connect timeout）")
    ap.add_argument("--timeout", type=float, default=10.0, help="读取超时秒（requests read timeout；legacy 名称 --timeout）")
    ap.add_argument("--trust-env", default="auto", choices=["auto","true","false"], help="是否信任环境代理：auto(loopback->false), true, false")
    ap.add_argument("--json-out", default=None, help="JSON 报告输出路径（提供则只写这一份）")
    ap.add_argument("--json-stdout", action="store_true", help="将 JSON 报告打印到 stdout（可与 --json-out 同时使用）")
    args = ap.parse_args()

    base = args.base.rstrip("/") + "/"
    trust_env = resolve_trust_env(args.base, args.trust_env)

    # Choose a real model id when possible (avoid placeholder values)
    base_for_client = args.base.rstrip('/')
    if not base_for_client.endswith('/v1'):
        base_for_client = base_for_client + '/v1'
    resolved_model, model_resolve = resolve_model_id(
        base_for_client,
        'auto',
        connect_timeout=args.connect_timeout,
        read_timeout=args.timeout,
        trust_env_mode=args.trust_env,
        fallback_model='gpt-3.5-turbo',
    )
    report = build_base("llm_probe", inputs={"base": args.base, "connect_timeout": args.connect_timeout, "read_timeout": args.timeout, "trust_env": args.trust_env})
    report['resolved_model'] = resolved_model
    report['model_resolve'] = model_resolve

    # payloads
    chat_payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    comp_payload = {
        "model": resolved_model,
        "prompt": "ping",
        "max_tokens": 16,
        "temperature": 0,
    }

    print("== GET probes ==")
    report["get"] = []
    for path in GET_CANDIDATES:
        url = urljoin(base, path.lstrip("/"))
        res = _get(url, args.connect_timeout, args.timeout, trust_env)
        report["get"].append({"path": path, "url": url, **res})
        ok = "OK" if res.get("ok") and res.get("status") == 200 else "FAIL"
        code = res.get("status", "")
        print(f"{ok:<4} {str(code):<4} {path:<16} {res.get('seconds',0):>6.2f}s")

    print("\n== POST probes ==")
    report["post"] = []
    for path in POST_CANDIDATES:
        url = urljoin(base, path.lstrip("/"))
        payload = chat_payload if "chat" in path else comp_payload
        res = _post(url, payload, args.connect_timeout, args.timeout, trust_env)
        report["post"].append({"path": path, "url": url, "payload": payload, **res})
        ok = "OK" if res.get("ok") and res.get("status") == 200 else "FAIL"
        code = res.get("status", "")
        print(f"{ok:<4} {str(code):<4} {path:<22} {res.get('seconds',0):>6.2f}s")

    post_ok = any(x.get("ok") and x.get("status") == 200 for x in report["post"])
    report["status"] = "PASS" if post_ok else "FAIL"
    if not post_ok:
        add_error(report, "NO_POST_200", "No POST probe returned HTTP 200")

    default_name = f"llm_probe_report_{int(time.time())}.json"
    if args.json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    out_path = write_report(report, json_out=args.json_out, default_name=default_name)
    print(f"\nWrote report: {out_path}")

    return status_to_rc(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
