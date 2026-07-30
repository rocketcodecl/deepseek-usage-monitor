"""CLI `dseek`: status, snapshot, report, export, serve, menubar, demo."""

from __future__ import annotations

import random
import time
from pathlib import Path

import typer

from . import balance as balance_mod
from . import config, db, report

app = typer.Typer(
    name="dseek",
    help="Monitor de balance, uso y gasto de la API de DeepSeek.",
    no_args_is_help=True,
)


@app.command()
def status(days: int = typer.Option(30, help="Ventana en días para el reporte."),
           no_live: bool = typer.Option(False, "--no-live",
                                        help="No consultar la API; usar la base local.")):
    """Muestra balance, gasto de hoy y métricas de los últimos N días."""
    s = report.summary(days=days, live=not no_live)
    typer.echo(report.render_text(s))


@app.command()
def snapshot(csv: Path | None = typer.Option(
        None, "--csv", help="Además de guardar en SQLite, añade fila a este CSV (CI).")):
    """Consulta el balance una vez y lo guarda en el historial (uso con cron)."""
    b = balance_mod.fetch_balance()
    db.insert_snapshot(b)
    snap = {"ts": time.time(), "currency": b.currency, "total": b.total,
            "granted": b.granted, "topped_up": b.topped_up,
            "is_available": b.is_available}
    if csv:
        db.append_balance_csv(csv, snap)
        typer.echo(f"Fila añadida a {csv}")
    typer.echo(f"Balance: ${b.total:.2f} {b.currency} "
               f"(top-up ${b.topped_up:.2f}, granted ${b.granted:.2f}) "
               f"{'✔' if b.is_available else '✘'}")
    if b.low:
        typer.echo("⚠  Balance por debajo del umbral "
                   f"(DSU_LOW_BALANCE={config.low_balance_threshold()})", err=True)
        raise typer.Exit(code=2)  # útil para alertas en CI


@app.command()
def report_cmd(days: int = 30):
    """Alias de `dseek status --days N` (solo datos locales)."""
    s = report.summary(days=days, live=False)
    typer.echo(report.render_text(s))


@app.command(name="export")
def export(out: Path = typer.Argument(Path("usage_export.csv")),
           days: int = typer.Option(0, help="0 = todo el historial")):
    """Exporta los eventos del tracker a CSV (igual que el botón Export web)."""
    from_ts = 0 if days <= 0 else time.time() - days * 86400
    n = db.export_usage_csv(out, from_ts)
    typer.echo(f"{n} eventos exportados a {out}")


@app.command()
def series(days: int = 30):
    """Costo diario (tracker) de los últimos N días, en texto."""
    for row in db.daily_series(days):
        typer.echo(f"{row['day']}  ${row['cost_usd']:.4f}  "
                   f"{row['requests']:>4} reqs  {row['tokens']:>10,} tokens")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Levanta el dashboard web local (réplica del panel Usage)."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("Instala las dependencias del dashboard: "
                   "pip install 'deepseek-usage-monitor[server]'", err=True)
        raise typer.Exit(code=1)
    from .server import app as fastapi_app
    typer.echo(f"Dashboard en http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")


@app.command()
def menubar():
    """Lanza la app de barra de menú de macOS (requiere: pip install rumps)."""
    try:
        from .menubar_app import main
    except ImportError:
        typer.echo("rumps no está instalado o no estás en macOS.\n"
                   "Instala: pip install 'deepseek-usage-monitor[menubar]'\n"
                   "Alternativa sin dependencias: usa el plugin de SwiftBar "
                   "(carpeta swiftbar/ del repo).", err=True)
        raise typer.Exit(code=1)
    main()


@app.command()
def demo():
    """Inserta datos de ejemplo para ver el dashboard sin gastar tu API."""
    conn = db.connect()
    now = time.time()
    models = ["deepseek-chat", "deepseek-reasoner"]
    bal = 2.10
    for i in range(14, -1, -1):  # 15 días de historial
        day = now - i * 86400
        cost = round(random.uniform(0.002, 0.03), 4)
        bal = round(bal - cost, 4)
        db.insert_snapshot(
            {"ts": day, "currency": "USD", "total": bal, "granted": 0.0,
             "topped_up": bal, "is_available": True}, conn=conn, ts=day)
        for _ in range(random.randint(2, 10)):
            prompt = random.randint(500, 80_000)
            completion = random.randint(100, 4_000)
            model = random.choice(models)
            from . import pricing
            db.insert_usage_event({
                "ts": day + random.uniform(0, 80_000), "model": model,
                "prompt_tokens": prompt, "completion_tokens": completion,
                "cache_hit_tokens": 0, "cache_miss_tokens": prompt,
                "cost_usd": pricing.estimate_cost(model, prompt, completion),
                "source": "demo",
            }, conn=conn)
    conn.close()
    typer.echo("✔ Datos demo insertados. Prueba:  dseek status --no-live  "
               "o  dseek serve")


def main():
    app()


if __name__ == "__main__":
    main()
