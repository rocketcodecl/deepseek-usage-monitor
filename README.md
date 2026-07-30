# deepseek-usage-monitor

Monitor del **balance, uso y gasto** de tu cuenta de la API de DeepSeek: en la **terminal**, en un **dashboard web local** (réplica del panel Usage oficial) y en la **barra de menú de macOS** 🟢 `$1.88`, junto al reloj.

Además: historial en SQLite, export a CSV, alertas de saldo bajo, y un **GitHub Action** que vigila tu saldo gratis cada 6 horas.

## Cómo obtiene los datos (lo importante)

DeepSeek solo expone **un endpoint oficial** de cuenta: `GET /user/balance` → te dice cuánto saldo tienes ahora. **No existe API oficial pública** para el historial de uso (la propia plataforma solo ofrece el botón *Export* en la web). Por eso este monitor combina **dos fuentes**:

| Fuente | Qué da | Cobertura |
|---|---|---|
| 💰 **Balance oficial** (polling cada N min) | Saldo actual exacto | Los *deltas* (bajadas de saldo) = **todo** tu gasto, venga de donde venga |
| 📒 **Tracker local** (`tracker.wrap_client`) | Requests, tokens y costo por llamada | Exacto, pero solo mide lo que pasa por el wrapper |

Una foto como la del panel oficial sale de cruzar las dos: las recargas se detectan y no se confunden con gasto.

## Instalación

```bash
git clone https://github.com/USUARIO/deepseek-usage-monitor.git
cd deepseek-usage-monitor
pip install -e ".[all]"        # núcleo + dashboard + menubar (macOS)

# Configura tu clave (de https://platform.deepseek.com/api_keys)
mkdir -p ~/.config/deepseek-usage-monitor
cp .env.example ~/.config/deepseek-usage-monitor/.env
# edita el archivo y pon tu DEEPSEEK_API_KEY=sk-...
```

## Uso rápido

```bash
dseek status            # balance en vivo + gasto hoy + métricas 30 días
dseek series            # gasto día a día
dseek export            # CSV con todo el historial del tracker
dseek serve             # dashboard en http://127.0.0.1:8000 (auto-refresh 60 s)
dseek demo              # datos de ejemplo para probar sin gastar tu API
```

## 📊 Dashboard web local

`dseek serve` levanta una copia fiel del panel oficial (tema oscuro): *Topped-up balance*, *Total cost*, *Cost / API requests / Tokens* a 7/30/90 días, gráfico diario y botón **Export**. Se actualiza solo cada 60 segundos.

## 🍎 Barra de menú de macOS (dos opciones)

### Opción 1 — Plugin SwiftBar (recomendada, cero dependencias)

```bash
brew install --cask swiftbar
mkdir -p ~/swiftbar-plugins
cp swiftbar/deepseek.5m.py ~/swiftbar-plugins/   # el "5m" del nombre = refresco cada 5 min
chmod +x ~/swiftbar-plugins/deepseek.5m.py
```

Abre SwiftBar, elige `~/swiftbar-plugins` como carpeta de plugins y listo: verás `🟢 $1.88` en la barra. Amarillo si baja de `DSU_LOW_BALANCE`, rojo si baja de la mitad. Menú: gasto de hoy, abrir dashboard, recargar saldo, refrescar.

### Opción 2 — App nativa (rumps + autoarranque)

```bash
pip install -e ".[menubar]"
dseek menubar
```

Para que arranque sola al iniciar sesión:

```bash
cp macos/cl.deepseek.usage-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/cl.deepseek.usage-monitor.plist
```

## 📒 Medir tu uso exacto por request

En el código que llama a DeepSeek, envuelve el cliente una sola línea:

```python
from openai import OpenAI
from deepseek_usage import tracker

client = tracker.wrap_client(OpenAI(api_key="sk-...", base_url="https://api.deepseek.com"))
resp = client.chat.completions.create(model="deepseek-chat",
                                      messages=[...])   # se registra solo ✔
```

También funciona con streaming (`stream_options={"include_usage": True}`) y sin wrapper: `tracker.log_response(resp)`. Los precios están en `deepseek_usage/pricing.json` (USD por 1M tokens) — **revísalos y edítalos** según la [página oficial de precios](https://api-docs.deepseek.com/quick_start/pricing), porque DeepSeek los cambia.

## 🤖 Monitor automático en GitHub (gratis)

El workflow `.github/workflows/monitor.yml` corre cada 6 h: guarda el saldo en `data/balance_history.csv` (historial commiteado al repo), y si baja del umbral **falla el run** (GitHub te manda email) y/o avisa por Telegram.

1. En tu repo: *Settings → Secrets → Actions* → `DEEPSEEK_API_KEY`.
2. Opcional: *Variables* → `DSU_LOW_BALANCE` (defecto `1.0`), secrets `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

## Estructura

```
deepseek_usage/        núcleo Python (balance, db SQLite, pricing, tracker, report, cli)
  static/index.html    dashboard oscuro
  menubar_app.py       app rumps (macOS)
swiftbar/              plugin SwiftBar/xbar (solo stdlib)
macos/                 LaunchAgent para autoarranque
.github/workflows/     monitor programado en GitHub Actions
tests/                 pytest: 9 tests de lógica de costo y deltas
```

## Límites honestos

- Los **requests/tokens** solo se ven si pasan por el tracker (DeepSeek no publica ese dato por API). El **costo** por deltas sí cubre todo, con la precisión de tu frecuencia de polling.
- El balance que devuelve la API puede ir ~5 min retrasado (como avisa la propia web).
- El panel web de DeepSeek tiene endpoints internos usados por proyectos como `shajanjp/deepseek-usage`; este repo **no los usa** a propósito: son oficiosos, requieren tu token de sesión del navegador y pueden romperse sin aviso.

## Licencia

MIT — haz lo que quieras con ella.
