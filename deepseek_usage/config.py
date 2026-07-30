"""Configuración central: rutas, .env y clave de API."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "deepseek-usage-monitor"
BASE_URL = "https://api.deepseek.com"
BALANCE_URL = f"{BASE_URL}/user/balance"


def config_dir() -> Path:
    return Path(os.environ.get("DSU_CONFIG_DIR", Path.home() / ".config" / APP_NAME))


def data_dir() -> Path:
    return Path(os.environ.get("DSU_DATA_DIR", Path.home() / ".local" / "share" / APP_NAME))


def db_path() -> Path:
    return Path(os.environ.get("DSU_DB_PATH", data_dir() / "usage.db"))


def env_path() -> Path:
    return Path(os.environ.get("DSU_ENV_PATH", config_dir() / ".env"))


def pricing_path() -> Path:
    default = Path(__file__).parent / "pricing.json"
    return Path(os.environ.get("DSU_PRICING_PATH", default))


def load_env_file(path: Path | None = None) -> None:
    """Carga pares KEY=VALUE desde el .env (sin pisar variables ya definidas)."""
    path = path or env_path()
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_api_key() -> str:
    load_env_file()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "No se encontró DEEPSEEK_API_KEY.\n"
            f"Defínela como variable de entorno o crea el archivo: {env_path()}\n"
            "Con una línea: DEEPSEEK_API_KEY=sk-tu-clave"
        )
    return key


def low_balance_threshold() -> float:
    load_env_file()
    try:
        return float(os.environ.get("DSU_LOW_BALANCE", "1.0"))
    except ValueError:
        return 1.0


def menubar_interval() -> int:
    load_env_file()
    try:
        return max(15, int(os.environ.get("DSU_MENUBAR_INTERVAL", "120")))
    except ValueError:
        return 120


def dashboard_url() -> str:
    load_env_file()
    return os.environ.get("DSU_DASHBOARD_URL", "http://127.0.0.1:8000")
