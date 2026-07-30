"""Cliente del endpoint oficial GET /user/balance de DeepSeek.

Documentación: https://api-docs.deepseek.com/  (sección "Get User Balance")
Respuesta:
{
  "is_available": true,
  "balance_infos": [
    {"currency": "USD", "total_balance": "1.88",
     "granted_balance": "0.00", "topped_up_balance": "1.88"}
  ]
}
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from . import config


class BalanceError(RuntimeError):
    """Error al consultar el balance (red, auth, formato inesperado...)."""


@dataclass
class BalanceInfo:
    is_available: bool
    currency: str
    total: float
    granted: float
    topped_up: float
    raw: dict = field(default_factory=dict)

    @property
    def low(self) -> bool:
        return self.total < config.low_balance_threshold()


def fetch_balance(api_key: str | None = None, timeout: int = 10,
                  prefer_currency: str = "USD") -> BalanceInfo:
    """Consulta el balance actual de la cuenta.

    Devuelve BalanceInfo. Lanza BalanceError si algo falla.
    """
    key = api_key or config.get_api_key()
    try:
        resp = requests.get(
            config.BALANCE_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise BalanceError(f"Error de red consultando balance: {exc}") from exc

    if resp.status_code == 401:
        raise BalanceError("401 no autorizado: revisa tu DEEPSEEK_API_KEY.")
    if resp.status_code != 200:
        raise BalanceError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        payload = resp.json()
        infos = payload["balance_infos"]
    except Exception as exc:  # JSON malformado o sin balance_infos
        raise BalanceError(f"Respuesta inesperada de la API: {resp.text[:200]}") from exc

    if not infos:
        raise BalanceError("La API devolvió balance_infos vacío.")

    # Preferimos USD; si no está, usamos la primera moneda disponible.
    info = next((i for i in infos if i.get("currency") == prefer_currency), infos[0])

    def _f(name: str) -> float:
        try:
            return float(info.get(name) or 0.0)  # llegan como strings
        except (TypeError, ValueError):
            return 0.0

    return BalanceInfo(
        is_available=bool(payload.get("is_available", False)),
        currency=str(info.get("currency", "?")),
        total=_f("total_balance"),
        granted=_f("granted_balance"),
        topped_up=_f("topped_up_balance"),
        raw=payload,
    )
