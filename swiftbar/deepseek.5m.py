#!/usr/bin/env python3
# <swiftbar.title>DeepSeek Balance</swiftbar.title>
# <swiftbar.version>v0.1</swiftbar.version>
# <swiftbar.author>deepseek-usage-monitor</swiftbar.author>
# <swiftbar.desc>Muestra el balance de la API de DeepSeek en la barra de menú. El intervalo se define por el nombre del archivo (deepseek.5m.py = cada 5 min).</swiftbar.desc>
#
# Plugin de SwiftBar/xbar (también funciona con BitBar).
# Instalación:
#   brew install swiftbar
#   cp deepseek.5m.py ~/swiftbar-plugins/   (o la carpeta que elijas en SwiftBar)
#   chmod +x ~/swiftbar-plugins/deepseek.5m.py
# Config:  ~/.config/deepseek-usage-monitor/.env  con  DEEPSEEK_API_KEY=sk-...
# Opcional: DSU_LOW_BALANCE=1.0   DSU_DASHBOARD_URL=http://127.0.0.1:8000

import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("DSU_CONFIG_DIR",
                                 Path.home() / ".config/deepseek-usage-monitor"))
DATA_DIR = Path(os.environ.get("DSU_DATA_DIR",
                               Path.home() / ".local/share/deepseek-usage-monitor"))
DB = Path(os.environ.get("DSU_DB_PATH", DATA_DIR / "usage.db"))


def load_env():
    env = CONFIG_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fetch_balance(key):
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        payload = json.loads(r.read().decode())
    infos = payload.get("balance_infos") or [{}]
    info = next((i for i in infos if i.get("currency") == "USD"), infos[0])
    return {
        "is_available": bool(payload.get("is_available")),
        "currency": info.get("currency", "USD"),
        "total": float(info.get("total_balance") or 0),
        "granted": float(info.get("granted_balance") or 0),
        "topped_up": float(info.get("topped_up_balance") or 0),
    }


def save_snapshot(b):
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS balance_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, currency TEXT,
        total REAL, granted REAL, topped_up REAL, is_available INTEGER, raw TEXT)""")
    conn.execute(
        "INSERT INTO balance_snapshots (ts,currency,total,granted,topped_up,"
        "is_available,raw) VALUES (?,?,?,?,?,?,?)",
        (time.time(), b["currency"], b["total"], b["granted"], b["topped_up"],
         int(b["is_available"]), ""))
    conn.commit()
    conn.close()


def local_stats():
    if not DB.exists():
        return {}
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    try:
        day = time.time() - (time.time() % 86400)
        row = conn.execute(
            "SELECT COUNT(*) r, COALESCE(SUM(cost_usd),0) c, "
            "COALESCE(SUM(prompt_tokens)+SUM(completion_tokens),0) t "
            "FROM usage_events WHERE ts >= ?", (day,)).fetchone()
        return {"req": row["r"], "cost": row["c"], "tok": row["t"]}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def main():
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    low = float(os.environ.get("DSU_LOW_BALANCE", "1.0"))
    dash = os.environ.get("DSU_DASHBOARD_URL", "http://127.0.0.1:8000")

    if not key:
        print("⚡ sin clave | color=orange")
        print("---")
        print(f"Crear {CONFIG_DIR}/.env con DEEPSEEK_API_KEY | color=gray")
        return

    try:
        b = fetch_balance(key)
        save_snapshot(b)
    except Exception as exc:
        print("⚡ -- | color=gray")
        print("---")
        print(f"Sin conexión / error: {str(exc)[:60]} | color=red")
        print(f"Reintentar | refresh=true")
        return

    total = b["total"]
    dot = "🔴" if total < low * 0.5 else ("🟡" if total < low else "🟢")
    print(f"{dot} ${total:,.2f}")
    print("---")
    print(f"Balance total: ${total:,.4f} {b['currency']}")
    print(f"-- Top-up: ${b['topped_up']:,.4f}")
    print(f"-- Granted: ${b['granted']:,.4f}")
    st = local_stats()
    if st:
        print("---")
        print(f"Hoy (tracker): ${st['cost']:,.4f} · {st['req']} reqs · "
              f"{st['tok']:,} tokens")
        print(f"Gastos por día (SQLite local): dseek series | color=gray")
    print("---")
    print(f"Abrir dashboard | href={dash}")
    print("Recargar saldo… | href=https://platform.deepseek.com/top_up")
    print("Actualizar ahora | refresh=true")
    if total < low:
        print(f"⚠ SALDO BAJO (umbral ${low:.2f}) | color=red")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # nunca rompas la barra de menú
        print(f"⚡ err | color=red\n---\n{str(e)[:80]}")
        sys.exit(0)
