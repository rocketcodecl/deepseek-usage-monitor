"""Dashboard web local (FastAPI): réplica del panel Usage de DeepSeek.

Arrancar:  dseek serve   →  http://127.0.0.1:8000
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from . import db, report

app = FastAPI(title="deepseek-usage-monitor", docs_url=None, redoc_url=None)
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/summary")
def api_summary(days: int = Query(30, ge=1, le=365)):
    """Las tarjetas del panel: balance ($1.88), costo total, costo 30d,
    requests y tokens — en JSON."""
    return JSONResponse(report.summary(days=days, live=True))


@app.get("/api/series")
def api_series(days: int = Query(30, ge=1, le=365)):
    """Serie diaria del tracker para el gráfico."""
    return JSONResponse({"days": days, "series": db.daily_series(days)})


@app.get("/api/export.csv", response_class=PlainTextResponse)
def api_export(days: int = Query(30, ge=0, le=365)):
    """Equivalente al botón Export de la web oficial."""
    from_ts = 0 if days == 0 else time.time() - days * 86400
    tmp = Path("/tmp/deepseek_usage_export.csv")
    db.export_usage_csv(tmp, from_ts)
    return PlainTextResponse(tmp.read_text(), media_type="text/csv",
                             headers={"Content-Disposition":
                                      "attachment; filename=deepseek_usage.csv"})
