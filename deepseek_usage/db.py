"""Persistencia en SQLite: snapshots de balance + eventos de uso.

- balance_snapshots: cada consulta al balance (para deducir gasto por deltas).
- usage_events: cada request registrado por el tracker (métricas exactas).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    currency TEXT,
    total REAL,
    granted REAL,
    topped_up REAL,
    is_available INTEGER,
    raw TEXT
);
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cache_hit_tokens INTEGER DEFAULT 0,
    cache_miss_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    source TEXT DEFAULT 'tracker',
    meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON balance_snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_evt_ts ON usage_events(ts);
"""


def connect(db_file: Path | None = None) -> sqlite3.Connection:
    path = db_file or config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------- snapshots

def insert_snapshot(balance, conn: sqlite3.Connection | None = None,
                    ts: float | None = None) -> None:
    """Guarda un snapshot a partir de un BalanceInfo (o de un dict equivalente)."""
    own = conn is None
    conn = conn or connect()
    ts = ts or time.time()
    get = (lambda k: getattr(balance, k, None)) if not isinstance(balance, dict) \
        else (lambda k: balance.get(k))
    raw = get("raw") or {}
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    conn.execute(
        "INSERT INTO balance_snapshots (ts, currency, total, granted, topped_up,"
        " is_available, raw) VALUES (?,?,?,?,?,?,?)",
        (ts, get("currency"), float(get("total") or 0), float(get("granted") or 0),
         float(get("topped_up") or 0), int(bool(get("is_available"))), raw),
    )
    conn.commit()
    if own:
        conn.close()


def latest_snapshot(conn: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    own = conn is None
    conn = conn or connect()
    row = conn.execute(
        "SELECT * FROM balance_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
    if own:
        conn.close()
    return row


def snapshots_between(from_ts: float, to_ts: float,
                      conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    """Snapshots del rango + el anterior al inicio (baseline para deltas)."""
    own = conn is None
    conn = conn or connect()
    baseline = conn.execute(
        "SELECT * FROM balance_snapshots WHERE ts < ? ORDER BY ts DESC LIMIT 1",
        (from_ts,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM balance_snapshots WHERE ts BETWEEN ? AND ? ORDER BY ts",
        (from_ts, to_ts)).fetchall()
    if own:
        conn.close()
    return ([baseline] if baseline else []) + rows


def spend_between(from_ts: float, to_ts: float,
                  conn: sqlite3.Connection | None = None) -> float:
    """Gasto inferido: suma de *bajadas* de balance total en el rango.

    Las subidas (recargas, granted nuevo) se ignoran, así top-ups no cuentan
    como gasto negativo. Funciona aunque el gasto venga de otras herramientas.
    """
    rows = snapshots_between(from_ts, to_ts, conn)
    spend = 0.0
    prev = None
    for row in rows:
        total = row["total"] or 0.0
        if prev is not None and total < prev:
            spend += prev - total
        prev = total
    return spend


# ------------------------------------------------------------- usage events

def insert_usage_event(event: dict, conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    meta = event.get("meta") or {}
    if not isinstance(meta, str):
        meta = json.dumps(meta, ensure_ascii=False)
    conn.execute(
        "INSERT INTO usage_events (ts, model, prompt_tokens, completion_tokens,"
        " cache_hit_tokens, cache_miss_tokens, cost_usd, source, meta)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (event.get("ts") or time.time(), event.get("model"),
         int(event.get("prompt_tokens") or 0), int(event.get("completion_tokens") or 0),
         int(event.get("cache_hit_tokens") or 0), int(event.get("cache_miss_tokens") or 0),
         event.get("cost_usd"), event.get("source", "tracker"), meta),
    )
    conn.commit()
    if own:
        conn.close()


def usage_between(from_ts: float, to_ts: float,
                  conn: sqlite3.Connection | None = None) -> dict:
    """Agregados del tracker en el rango: requests, tokens y costo."""
    own = conn is None
    conn = conn or connect()
    row = conn.execute(
        "SELECT COUNT(*) AS requests,"
        " COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,"
        " COALESCE(SUM(completion_tokens),0) AS completion_tokens,"
        " COALESCE(SUM(prompt_tokens)+SUM(completion_tokens),0) AS tokens,"
        " COALESCE(SUM(cost_usd),0) AS cost_usd"
        " FROM usage_events WHERE ts BETWEEN ? AND ?",
        (from_ts, to_ts)).fetchone()
    if own:
        conn.close()
    return dict(row)


def daily_series(days: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Serie diaria (UTC) de costo/tokens/requests del tracker, últimos N días."""
    own = conn is None
    conn = conn or connect()
    from_ts = time.time() - days * 86400
    rows = conn.execute(
        "SELECT strftime('%Y-%m-%d', ts, 'unixepoch') AS day,"
        " COUNT(*) AS requests,"
        " COALESCE(SUM(prompt_tokens)+SUM(completion_tokens),0) AS tokens,"
        " COALESCE(SUM(cost_usd),0) AS cost_usd"
        " FROM usage_events WHERE ts >= ? GROUP BY day ORDER BY day",
        (from_ts,)).fetchall()
    if own:
        conn.close()
    return [dict(r) for r in rows]


def export_usage_csv(path: Path, from_ts: float = 0,
                     conn: sqlite3.Connection | None = None) -> int:
    own = conn is None
    conn = conn or connect()
    rows = conn.execute(
        "SELECT ts, model, prompt_tokens, completion_tokens, cache_hit_tokens,"
        " cache_miss_tokens, cost_usd, source FROM usage_events"
        " WHERE ts >= ? ORDER BY ts", (from_ts,)).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        f.write("ts,iso_utc,model,prompt_tokens,completion_tokens,"
                "cache_hit_tokens,cache_miss_tokens,cost_usd,source\n")
        for r in rows:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["ts"]))
            f.write(f"{r['ts']:.0f},{iso},{r['model']},{r['prompt_tokens']},"
                    f"{r['completion_tokens']},{r['cache_hit_tokens']},"
                    f"{r['cache_miss_tokens']},{r['cost_usd'] or 0},{r['source']}\n")
    if own:
        conn.close()
    return len(rows)


def append_balance_csv(path: Path, snap: dict) -> None:
    """Añade una fila al CSV de historial de balance (para GitHub Actions)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a") as f:
        if new:
            f.write("iso_utc,currency,total,granted,topped_up,is_available\n")
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(snap.get("ts") or time.time()))
        f.write(f"{iso},{snap.get('currency')},{snap.get('total')},"
                f"{snap.get('granted')},{snap.get('topped_up')},"
                f"{int(bool(snap.get('is_available')))}\n")
