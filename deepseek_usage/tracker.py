"""Tracker de uso: registra cada respuesta de la API en la base local.

Uso directo (línea única tras cada llamada):

    from openai import OpenAI
    from deepseek_usage import tracker

    client = OpenAI(api_key=..., base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(model="deepseek-chat", messages=[...])
    tracker.log_response(resp)

O con el wrapper (registra automáticamente, incluye streaming si activas
stream_options={"include_usage": True}):

    client = tracker.wrap_client(OpenAI(api_key=..., base_url="https://api.deepseek.com"))
    resp = client.chat.completions.create(...)
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Iterator

from . import db, pricing


def _get(obj: Any, key: str) -> Any:
    """Lee obj.key o obj[key] (compatible con SDK de OpenAI y dicts)."""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def log_usage(usage: Any, model: str | None = None,
              source: str = "tracker") -> dict:
    """Registra un objeto `usage` (tenga la forma que tenga) y devuelve el evento."""
    prompt = int(_get(usage, "prompt_tokens") or 0)
    completion = int(_get(usage, "completion_tokens") or 0)
    # Campos de caché propios de DeepSeek (pueden no existir):
    hit = int(_get(usage, "prompt_cache_hit_tokens") or 0)
    miss = int(_get(usage, "prompt_cache_miss_tokens") or 0)
    cost = pricing.estimate_cost(model, prompt, completion, hit, miss)

    event = {
        "ts": time.time(),
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_hit_tokens": hit or max(0, prompt - miss) if hit or miss else 0,
        "cache_miss_tokens": miss or (prompt - hit if hit else 0),
        "cost_usd": cost,
        "source": source,
    }
    db.insert_usage_event(event)
    return event


def log_response(response: Any, model: str | None = None,
                 source: str = "tracker") -> dict | None:
    """Registra una respuesta completa de chat.completions. None si no trae usage."""
    usage = _get(response, "usage")
    if usage is None:
        return None
    model = model or _get(response, "model")
    return log_usage(usage, model=model, source=source)


def _tracked_stream(stream: Iterator, model: str | None) -> Iterator:
    """Envuelve un stream: registra el usage final (include_usage=True)."""
    final_usage = None
    for chunk in stream:
        usage = _get(chunk, "usage")
        if usage:
            final_usage = usage
        yield chunk
    if final_usage is not None:
        try:
            log_usage(final_usage, model=model)
        except Exception:
            pass  # el tracking nunca debe romper la app del usuario


class _TrackedCompletions:
    def __init__(self, completions):
        self._c = completions

    def create(self, *args, **kwargs):
        model = kwargs.get("model")
        stream = kwargs.get("stream", False)
        resp = self._c.create(*args, **kwargs)
        try:
            if stream:
                return _tracked_stream(resp, model)
            log_response(resp, model=model)
        except Exception:
            pass
        return resp

    def __getattr__(self, name):
        return getattr(self._c, name)


class _TrackedChat:
    def __init__(self, chat):
        self._chat = chat
        self.completions = _TrackedCompletions(chat.completions)

    def __getattr__(self, name):
        return getattr(self._chat, name)


class _TrackedClient:
    def __init__(self, client):
        self._client = client
        self.chat = _TrackedChat(client.chat)

    def __getattr__(self, name):
        return getattr(self._client, name)


def wrap_client(client: Any) -> _TrackedClient:
    """Devuelve un cliente OpenAI idéntico, pero que registra cada request."""
    return _TrackedClient(client)
