"""Cálculo de costo por request usando pricing.json (USD por 1M tokens)."""

from __future__ import annotations

import json

from . import config


def load_pricing() -> dict:
    path = config.pricing_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def estimate_cost(model: str | None, prompt_tokens: int = 0,
                  completion_tokens: int = 0, cache_hit_tokens: int = 0,
                  cache_miss_tokens: int = 0) -> float | None:
    """Costo estimado en USD. None si el modelo no existe en pricing.json.

    Si no llega desglose de caché, todo el prompt se cobra como cache-miss
    (escenario conservador, igual que antes de la caché de DeepSeek).
    """
    pricing = load_pricing()
    rate = pricing.get(model or "")
    if rate is None:
        return None

    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    cache_hit_tokens = int(cache_hit_tokens or 0)
    cache_miss_tokens = int(cache_miss_tokens or 0)
    if cache_hit_tokens == 0 and cache_miss_tokens == 0:
        cache_miss_tokens = prompt_tokens

    cost = (
        cache_hit_tokens * rate.get("input_cache_hit", 0.0)
        + cache_miss_tokens * rate.get("input_cache_miss", 0.0)
        + completion_tokens * rate.get("output", 0.0)
    ) / 1_000_000
    return round(cost, 8)
