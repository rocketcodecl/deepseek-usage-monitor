"""App de barra de menú de macOS (requiere rumps: pip install rumps).

Muestra el balance junto al reloj, p. ej.:  🟢 $1.88
Menú: gasto de hoy, métricas de 30 días, abrir dashboard, recargar saldo.

Lanzar:      dseek menubar
Autoarranque: instala el plist de macos/ (ver README) o empaqueta con py2app.
"""

from __future__ import annotations

import webbrowser

from . import config, report

import rumps  # noqa: E402  (solo existe en macOS)

REFRESH_LABEL = "Actualizar ahora"
STATE = {"low_notified": False}


class DeepSeekMenuBar(rumps.App):
    def __init__(self):
        super().__init__("DeepSeek", title="⚡…", quit_button=None)
        self.menu = [
            rumps.MenuItem("Balance: —"),
            rumps.MenuItem("Hoy (UTC): —"),
            rumps.MenuItem("Últimos 30 días: —"),
            None,
            rumps.MenuItem(REFRESH_LABEL, callback=self.refresh_clicked),
            rumps.MenuItem("Abrir dashboard…", callback=self.open_dashboard),
            rumps.MenuItem("Recargar saldo…", callback=self.open_topup),
            None,
            rumps.MenuItem("Salir", callback=rumps.quit_application),
        ]
        self._timer = rumps.Timer(self._tick, config.menubar_interval())
        self._timer.start()
        self._tick(None)  # primera pintada inmediata

    # ------------------------------------------------------------------
    def _tick(self, _sender):
        try:
            s = report.summary(days=30, live=True)
            self._paint(s)
        except Exception as exc:
            self.title = "⚡?"
            self.menu["Balance: —"].title = f"Error: {exc}"[:60]

    def _paint(self, s: dict):
        b = s["balance"]
        total = b.get("total")
        low = config.low_balance_threshold()
        if total is None:
            self.title = "⚡?"
        else:
            dot = "🔴" if total < low * 0.5 else ("🟡" if total < low else "🟢")
            self.title = f"{dot} ${total:,.2f}"

        self.menu["Balance: —"].title = (
            f"Balance: ${total:,.2f} {b.get('currency','')}"
            f"  (top-up ${b.get('topped_up') or 0:,.2f})" if total is not None
            else "Balance: —")
        self.menu["Hoy (UTC): —"].title = (
            f"Hoy (UTC): ${s['today']['cost']:,.4f} · "
            f"{s['today']['requests']} reqs · {s['today']['tokens']:,} tok")
        w = s["window"]
        self.menu["Últimos 30 días: —"].title = (
            f"30 días: ${w['cost']:,.2f} · {w['requests']} reqs · "
            f"{w['tokens']:,} tok")

        if total is not None and total < low and not STATE["low_notified"]:
            STATE["low_notified"] = True
            rumps.notification(
                title="DeepSeek: saldo bajo",
                subtitle=f"Quedan ${total:,.2f}",
                message=f"Umbral configurado: ${low:.2f}. Toca para recargar.",
                action_url="https://platform.deepseek.com/top_up")
        elif total is not None and total >= low:
            STATE["low_notified"] = False  # se reactiva si vuelve a bajar

    # ------------------------------------------------------------- menú
    @rumps.clicked(REFRESH_LABEL)
    def refresh_clicked(self, _sender):
        self._tick(None)

    def open_dashboard(self, _sender):
        webbrowser.open(config.dashboard_url())

    def open_topup(self, _sender):
        webbrowser.open("https://platform.deepseek.com/top_up")


def main():
    DeepSeekMenuBar().run()


if __name__ == "__main__":
    main()
