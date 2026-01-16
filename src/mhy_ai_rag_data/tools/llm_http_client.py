#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.llm_http_client

统一的 OpenAI-compatible HTTP Client（requests 版），用于本项目所有脚本访问本地/远端 LLM 服务。

设计目标：
- 统一代理策略：默认对回环地址（localhost/127.0.0.1/::1）不信任环境代理（trust_env=False），避免被 127.0.0.1:7890 等劫持。
- 统一超时语义：拆分 connect_timeout / read_timeout（requests 的 timeout=(connect, read)）。
- 统一错误可观测性：异常信息包含 url/base_url/trust_env/timeout，便于落盘报告与排查。

依据（Primary）：
- LM Studio OpenAI compatibility 端点：/v1/models, /v1/chat/completions 等。参见 LM Studio 文档。\n
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import ipaddress

import requests


@dataclass
class LLMHTTPError(Exception):
    message: str
    base_url: str
    url: str
    trust_env: bool
    timeout: Tuple[float, float]
    status_code: Optional[int] = None
    response_content_type: Optional[str] = None
    response_snippet: Optional[str] = None
    cause: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover
        extra = f" cause={self.cause}" if self.cause else ""
        sc = f" status={self.status_code}" if self.status_code is not None else ""
        ct = f" content_type={self.response_content_type}" if self.response_content_type else ""
        snip = ""
        if self.response_snippet:
            # 避免打印过长内容污染日志；这里只显示长度与前缀
            sn = self.response_snippet
            snip = f" response_snippet_len={len(sn)} response_snippet_head={sn[:160]!r}"
        return (
            f"{self.message} url={self.url} base_url={self.base_url} "
            f"trust_env={self.trust_env} timeout={self.timeout}{sc}{ct}{snip}{extra}"
        )

    def as_dict(self) -> Dict[str, Any]:
        """结构化输出，便于评测报告落盘（避免只保留 '400 Bad Request' 的不透明字符串）。"""
        return {
            "message": self.message,
            "base_url": self.base_url,
            "url": self.url,
            "trust_env": self.trust_env,
            "timeout": list(self.timeout),
            "status_code": self.status_code,
            "response_content_type": self.response_content_type,
            "response_snippet": self.response_snippet,
            "cause": self.cause,
        }


_SESSIONS: Dict[bool, requests.Session] = {}


def _safe_truncate_text(text: Optional[str], limit: int = 2000) -> Optional[str]:
    if text is None:
        return None
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "\n...<truncated>"


def _is_loopback_base_url(base_url: str) -> bool:
    try:
        u = urlparse(base_url)
        host = (u.hostname or "").strip().lower()
        if not host:
            return False
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    except Exception:
        return False


def resolve_trust_env(base_url: str, trust_env_mode: str) -> bool:
    """trust_env_mode: auto/true/false"""
    mode = (trust_env_mode or "auto").strip().lower()
    if mode not in ("auto", "true", "false"):
        raise ValueError(f"invalid trust_env_mode={trust_env_mode!r} (expected auto/true/false)")
    if mode == "true":
        return True
    if mode == "false":
        return False
    # auto
    return not _is_loopback_base_url(base_url)


def get_session(trust_env: bool) -> requests.Session:
    s = _SESSIONS.get(bool(trust_env))
    if s is not None:
        return s
    s = requests.Session()
    # requests Session 默认会信任环境变量代理；这里显式控制
    s.trust_env = bool(trust_env)
    _SESSIONS[bool(trust_env)] = s
    return s


def _join(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _truncate_text(s: str, limit: int = 2048) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= limit:
        return s
    return s[:limit] + "\n...<truncated>"


def _extract_response_info(exc: requests.RequestException) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """从 requests 异常中尽可能提取 HTTP 响应信息（status/code/body）。

    说明：
    - 对 4xx/5xx（尤其 400）来说，服务端通常会在 body 给出明确原因（model not found / context length exceeded / invalid param）。
    - 这里仅截断保存前 2KB，避免评测报告无限膨胀。
    """
    resp = getattr(exc, "response", None)
    if resp is None:
        return (None, None, None)
    status = getattr(resp, "status_code", None)
    ctype = None
    try:
        ctype = (resp.headers or {}).get("content-type")
    except Exception:
        ctype = None

    text = None
    try:
        # requests 会基于响应头猜测编码；若失败则退化为 bytes->repr
        text = resp.text
    except Exception:
        try:
            raw = resp.content
            text = repr(raw[:512])
        except Exception:
            text = None
    if text is not None:
        text = _truncate_text(str(text), limit=2048)
    return (status, ctype, text)


def get_json(
    base_url: str,
    path: str,
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    trust_env_mode: str = "auto",
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    trust_env = resolve_trust_env(base_url, trust_env_mode)
    url = _join(base_url, path)
    timeout = (float(connect_timeout), float(read_timeout))
    sess = get_session(trust_env=trust_env)
    try:
        r = sess.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        result = r.json()
        if not isinstance(result, dict):
            raise ValueError("Expected dict response")
        return result
    except requests.RequestException as exc:
        status, ctype, snippet = _extract_response_info(exc)
        raise LLMHTTPError(
            message="LLM HTTP GET failed",
            base_url=base_url,
            url=url,
            trust_env=trust_env,
            timeout=timeout,
            status_code=status,
            response_content_type=ctype,
            response_snippet=snippet,
            cause=f"{type(exc).__name__}: {exc}",
        ) from exc
    except ValueError as exc:
        raise LLMHTTPError(
            message="LLM HTTP GET JSON decode failed",
            base_url=base_url,
            url=url,
            trust_env=trust_env,
            timeout=timeout,
            cause=f"{type(exc).__name__}: {exc}",
        ) from exc


def post_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    trust_env_mode: str = "auto",
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    trust_env = resolve_trust_env(base_url, trust_env_mode)
    url = _join(base_url, path)
    timeout = (float(connect_timeout), float(read_timeout))
    sess = get_session(trust_env=trust_env)
    try:
        r = sess.post(url, json=payload, headers=headers, timeout=timeout)
        r.raise_for_status()
        result = r.json()
        if not isinstance(result, dict):
            raise ValueError("Expected dict response")
        return result
    except requests.RequestException as exc:
        status, ctype, snippet = _extract_response_info(exc)
        raise LLMHTTPError(
            message="LLM HTTP POST failed",
            base_url=base_url,
            url=url,
            trust_env=trust_env,
            timeout=timeout,
            status_code=status,
            response_content_type=ctype,
            response_snippet=snippet,
            cause=f"{type(exc).__name__}: {exc}",
        ) from exc
    except ValueError as exc:
        raise LLMHTTPError(
            message="LLM HTTP POST JSON decode failed",
            base_url=base_url,
            url=url,
            trust_env=trust_env,
            timeout=timeout,
            cause=f"{type(exc).__name__}: {exc}",
        ) from exc


def chat_completions(
    base_url: str,
    payload: Dict[str, Any],
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 120.0,
    trust_env_mode: str = "auto",
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    return post_json(
        base_url,
        "/chat/completions",
        payload,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        trust_env_mode=trust_env_mode,
        headers=headers,
    )


def extract_chat_content(resp_json: Dict[str, Any]) -> str:
    try:
        content = resp_json["choices"][0]["message"]["content"]
        return str(content)
    except Exception as exc:
        raise ValueError(f"unexpected chat completion response format: keys={list(resp_json.keys())}") from exc


# -----------------------------
# /models helpers
# -----------------------------


def list_models(
    base_url: str,
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    trust_env_mode: str = "auto",
) -> Dict[str, Any]:
    """GET /models (base_url should typically include /v1).

    Returns the raw JSON payload.
    """
    return get_json(
        base_url,
        "/models",
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        trust_env_mode=trust_env_mode,
    )


def extract_model_ids(models_json: Dict[str, Any]) -> List[str]:
    """Extract model ids from OpenAI-compatible /models response.

    Expected format: {"data": [{"id": "...", ...}, ...], ...}
    """
    ids: List[str] = []
    data = models_json.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                mid = item.get("id")
                if isinstance(mid, str) and mid.strip():
                    ids.append(mid.strip())
    # stable de-dup preserving order
    seen = set()
    out: List[str] = []
    for mid in ids:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def select_best_model_id(ids: List[str]) -> Tuple[Optional[str], str]:
    """Select a reasonable chat model id from a list.

    Heuristic (deterministic):
    1) prefer ids containing 'instruct'
    2) then ids containing 'chat'
    3) else first
    """
    if not ids:
        return None, "no_models"
    low = [(mid, mid.lower()) for mid in ids]
    for key in ("instruct", "chat"):
        for mid, lo in low:
            if key in lo:
                return mid, f"prefer_{key}"
    return ids[0], "first"


def resolve_model_id(
    base_url: str,
    model_arg: str,
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    trust_env_mode: str = "auto",
    fallback_model: str = "gpt-3.5-turbo",
) -> Tuple[str, Dict[str, Any]]:
    """Resolve the model id to send in request payload.

    - If model_arg is an explicit non-empty string and not 'auto', return it.
    - If model_arg is '' or 'auto', fetch /models and select a best id.
    - If fetching fails, fall back to fallback_model.

    Returns: (resolved_model, info_dict)
    """
    info: Dict[str, Any] = {
        "model_arg": model_arg,
        "resolved_model": None,
        "server_models": None,
        "selection_reason": None,
        "models_fetch_error": None,
    }

    arg = (model_arg or "").strip()
    if arg and arg.lower() != "auto":
        info["resolved_model"] = arg
        info["selection_reason"] = "explicit"
        return arg, info

    try:
        mj = list_models(
            base_url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            trust_env_mode=trust_env_mode,
        )
        ids = extract_model_ids(mj)
        info["server_models"] = ids
        chosen, reason = select_best_model_id(ids)
        if chosen:
            info["resolved_model"] = chosen
            info["selection_reason"] = f"auto:{reason}"
            return chosen, info
        # empty list -> fallback
        info["resolved_model"] = fallback_model
        info["selection_reason"] = "fallback:no_models"
        return fallback_model, info
    except Exception as e:
        # Prefer rich LLMHTTPError dict if available
        if isinstance(e, LLMHTTPError):
            info["models_fetch_error"] = e.as_dict()
            info["resolved_model"] = fallback_model
            info["selection_reason"] = "fallback:models_fetch_llmhttp_error"
        else:
            info["models_fetch_error"] = {"type": type(e).__name__, "message": str(e)}
            info["resolved_model"] = fallback_model
            info["selection_reason"] = "fallback:models_fetch_error"
        return fallback_model, info
