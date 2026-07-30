"""Reportes: las métricas de la pantalla Usage de DeepSeek, pero propias.

- Balance: endpoint oficial (o último snapshot si no hay red).
- Costo total / últimos N días: deltas de balance (cubre TODO el gasto,
  incluso el de herramientas ajenas a este script).
- Requests y tokens: eventos del tracker local (métricas exactas por request).
"""

from __future__ import annotations

import time

from . import balance as balance_mod
from . import db


def _window(days: int) -> tuple[float, float]:
    now = time.time()
    return now - days * 86400, now


def summary(days: int = 30, live: bool = True) -> dict:
    """Resumen completo tipo panel Usage. live=True intenta refrescar el balance."""
    now = time.time()
    day_start = now - (now % 86400)  # inicio del día UTC

    # ---- balance (tarjeta superior izquierda de la captura)
    bal_block: dict = {"stale": True}
    snap = None
    if live:
        try:
            b = balance_mod.fetch_balance()
            db.insert_snapshot(b)
            snap = {
                "ts": now, "currency": b.currency, "total": b.total,
                "granted": b.granted, "topped_up": b.topped_up,
                "is_available": b.is_available,
            }
            bal_block["stale"] = False
        except Exception as exc:  # sin red / sin clave → fallback al histórico
            bal_block["error"] = str(exc)
    if snap is None:
        row = db.latest_snapshot()
        if row:
            snap = dict(row)
        else:
            snap = {"ts": None, "currency": "USD", "total": None, "granted": None,
                    "topped_up": None, "is_available": None}
    bal_block.update(snap)

    # ---- costos por deltas de balance (tarjetas "Total cost" y "Cost")
    f30, t30 = _window(days)
    spend_30d = round(db.spend_between(f30, t30), 4)
    spend_all = round(db.spend_between(0, now), 4)

    # ---- métricas del tracker (tarjetas "API requests" y "Tokens")
    w30 = db.usage_between(f30, t30)
    today = db.usage_between(day_start, now)

    return {
        "generated_at": now,
        "balance": bal_block,
        "total_cost_alltime": spend_all,
        "window": {
            "days": days,
            "cost": min(spend_30d, 10**9),
            "requests": int(w30["requests"]),
            "tokens": int(w30["tokens"]),
            "prompt_tokens": int(w30["prompt_tokens"]),
            "completion_tokens": int(w30["completion_tokens"]),
            "tracked_cost": round(float(w30["cost_usd"]), 4),
        },
        "today": {
            "cost": round(db.spend_between(day_start, now), 4),
            "tracked_cost": round(float(today["cost_usd"]), 4),
            "requests": int(today["requests"]),
            "tokens": int(today["tokens"]),
        },
    }


def render_text(s: dict) -> str:
    """Formato terminal del resumen."""
    b = s["balance"]

    def money(v) -> str:
        return "—" if v is None else f"${v:.2f}"

    stale = " (dato en caché, sin conexión)" if b.get("stale") else ""
    avail = {True: "✔ disponible", False: "✘ sin fondos"}.get(
        b.get("is_available"), "?")
    lines = [
        f"⚡ Balance   : {money(b.get('total'))} {b.get('currency')}"
        f"  (recargado {money(b.get('topped_up'))} · regalado"
        f" {money(b.get('granted'))})  {avail}{stale}",
        f"💸 Total     : {money(s['total_cost_alltime'])} gastados"
        f" (inferido del balance)",
        f"📅 Hoy (UTC) : {money(s['today']['cost'])} · "
        f"{s['today']['requests']} requests · {s['today']['tokens']:,} tokens",
        f"🗓  {s['window']['days']} días    : {money(s['window']['cost'])} · "
        f"{s['window']['requests']} requests · {s['window']['tokens']:,} tokens",
    ]
    if b.get("error"):
        lines.append(f"⚠  Balance en vivo falló: {b['error']}")
    note = ("   · requests/tokens los registra el tracker local; el costo se "
            "infiere de bajadas de balance y cubre todo el gasto.")
    lines.append(note)
    return "\n".join(lines)
