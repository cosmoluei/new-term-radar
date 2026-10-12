"""OpenAI-compatible chat for the name judge, without requiring AIsa.

Keys, tried in order:

- ``LLM_API_KEY`` (+ optional ``LLM_API_BASE``, default OpenAI)
- ``OPENAI_API_KEY``
- ``DEEPSEEK_API_KEY`` (base https://api.deepseek.com)
- ``AISA_API_KEY`` (legacy AIsa chat endpoint)

Without a key the judge falls back to a local heuristic (see ``judge.heuristic``).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import UA, aisa

TIMEOUT = 90
DEFAULT_OPENAI = "https://api.openai.com/v1"
DEFAULT_DEEPSEEK = "https://api.deepseek.com"


class LLMError(RuntimeError):
    pass


def _endpoint() -> tuple[str, str] | None:
    """(base_url_without_trailing_slash, api_key) or None."""
    if k := os.environ.get("LLM_API_KEY", "").strip():
        base = os.environ.get("LLM_API_BASE", DEFAULT_OPENAI).rstrip("/")
        return base, k
    if k := os.environ.get("OPENAI_API_KEY", "").strip():
        return DEFAULT_OPENAI, k
    if k := os.environ.get("DEEPSEEK_API_KEY", "").strip():
        return DEFAULT_DEEPSEEK, k
    if aisa.available():
        return "aisa", ""
    return None


def available() -> bool:
    return _endpoint() is not None


def chat(model: str, system: str, user: str, max_tokens: int = 1500) -> str:
    ep = _endpoint()
    if ep is None:
        raise LLMError("no LLM key: set LLM_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, or AISA_API_KEY")
    base, key = ep
    if base == "aisa":
        return aisa.chat(model, system, user, max_tokens=max_tokens)
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            data = json.load(res)
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code}: {' '.join(exc.read().decode('utf-8', 'replace').split())[:200]}") from exc
    except (OSError, ValueError) as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected chat answer: {str(data)[:160]}") from exc
