from deepseek_usage import pricing


def test_cost_chat_cache_miss_y_output():
    # 1M tokens de entrada (sin caché) + 1M de salida con deepseek-chat
    cost = pricing.estimate_cost(
        "deepseek-chat", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 1.37  # 0.27 + 1.10


def test_cost_hirez_de_cache():
    # si viene desglose de caché, se usan esos precios
    cost = pricing.estimate_cost(
        "deepseek-chat", prompt_tokens=1_000_000, completion_tokens=0,
        cache_hit_tokens=1_000_000, cache_miss_tokens=0)
    assert cost == round(0.07, 8)


def test_modelo_desconocido_devuelve_none():
    assert pricing.estimate_cost("modelo-que-no-existe", 100, 100) is None


def test_none_y_ceros_no_rompen():
    assert pricing.estimate_cost("deepseek-chat", None, None) == 0
