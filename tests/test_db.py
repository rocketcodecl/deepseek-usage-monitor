import pytest

from deepseek_usage import db


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DSU_DB_PATH", str(tmp_path / "test.db"))
    c = db.connect()
    yield c
    c.close()


def snap(total, ts, granted=0.0):
    return {"ts": ts, "currency": "USD", "total": total, "granted": granted,
            "topped_up": total - granted, "is_available": True}


def test_spend_por_deltas_ignora_recargas(conn):
    # 10 → 9.5 (gasto 0.5) → 12 (recarga, ignorar) → 11.8 (gasto 0.2)
    for ts, total in [(100, 10.0), (200, 9.5), (300, 12.0), (400, 11.8)]:
        db.insert_snapshot(snap(total, ts), conn=conn, ts=ts)
    assert db.spend_between(0, 500, conn=conn) == pytest.approx(0.7)


def test_spend_respeta_la_ventana(conn):
    for ts, total in [(100, 10.0), (200, 9.0), (300, 8.0)]:
        db.insert_snapshot(snap(total, ts), conn=conn, ts=ts)
    # con baseline en ts=100, la ventana 150→250 solo ve la bajada 10→9
    assert db.spend_between(150, 250, conn=conn) == pytest.approx(1.0)


def test_usage_between_agrega(conn):
    db.insert_usage_event({"ts": 100, "model": "deepseek-chat",
                           "prompt_tokens": 100, "completion_tokens": 50,
                           "cost_usd": 0.001}, conn=conn)
    db.insert_usage_event({"ts": 200, "model": "deepseek-chat",
                           "prompt_tokens": 300, "completion_tokens": 150,
                           "cost_usd": 0.002}, conn=conn)
    agg = db.usage_between(0, 1000, conn=conn)
    assert agg["requests"] == 2
    assert agg["tokens"] == 600
    assert agg["cost_usd"] == pytest.approx(0.003)


def test_daily_series(conn):
    import time
    now = time.time()
    for i in range(3):
        db.insert_usage_event({"ts": now - i * 60, "model": "deepseek-chat",
                               "prompt_tokens": 10, "completion_tokens": 5,
                               "cost_usd": 0.0001}, conn=conn)
    series = db.daily_series(30, conn=conn)
    assert len(series) == 1
    assert series[0]["requests"] == 3


def test_export_csv(tmp_path, conn):
    db.insert_usage_event({"ts": 100, "model": "deepseek-chat",
                           "prompt_tokens": 10, "completion_tokens": 5,
                           "cost_usd": 0.0001}, conn=conn)
    out = tmp_path / "exp.csv"
    n = db.export_usage_csv(out, 0, conn=conn)
    assert n == 1
    assert "deepseek-chat" in out.read_text()
