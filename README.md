# JARVIS MVP

A deliberately small equity trading platform with one complete vertical slice:

`BUY RELIANCE 10 -> FastAPI -> risk checks -> execution engine -> paper broker -> order -> position -> P&L`

Both the React order ticket and external Python strategies enter through the backend and share exactly the same risk and execution code.

## Equity scanner

The Scanner tab evaluates the NIFTY 50 universe with five daily-candle scans:
52-week high breakout, 52-week low, volume breakout, price above SMA 20/50/200,
and RSI momentum. Users can also combine validated custom conditions, rank and
paginate results, save scanner setups, and create in-app alerts with a
minimum-match threshold. The universe boundary is modular so broader NSE index
groups can be added later without changing the scanner engine.

Scanner alerts are evaluated with **Check now** and remain research-only. The
scanner does not generate strategy signals or place orders. Scheduled checks and
email/SMS/push delivery require a separate durable background worker and are not
part of this Vercel-first version.

## Architecture

```text
React dashboard ---- POST /api/orders ---------+
                                                  |
Python strategy --- POST /api/signals ---------+--> RiskEngine --> ExecutionEngine --> BrokerAdapter
                                                                                         |-- PaperBroker (active)
                                                                                         `-- UpstoxAdapter (connection boundary)
```

SQLite stores users, broker connections, orders, and positions. The browser never receives broker credentials and never calls a broker API.

## Run locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with `jarvis@example.com` / `jarvis1234`, or create an account.

## Deploy with Vercel

Deploy the `frontend` directory as one Vercel project using the default Vite build settings. Set `VITE_API_URL` to the public URL of the deployed FastAPI service, including `/api`.

Deploy the `backend` directory as a separate Vercel project. The included `pyproject.toml` points Vercel to `app.main:app`, and `vercel.json` configures the function runtime.

Before deploying the backend, move the database from local SQLite to a hosted PostgreSQL provider such as Neon or Supabase. Vercel function filesystems are not persistent, so `jarvis.db` must remain local development storage only. Configure `APP_SECRET`, `DATABASE_URL` (after the PostgreSQL migration), `FRONTEND_ORIGIN`, and the Upstox settings as backend environment variables. Never commit `.env` or broker tokens.

### Migrate the local database to Neon

Set `DATABASE_URL` in `backend/.env` to the pooled Neon connection string, then run:

```bash
cd backend
pip install -r requirements.txt
python -m scripts.migrate_sqlite_to_postgres --source ./jarvis.db
```

The migration creates the PostgreSQL schema and copies users, broker connections, orders, positions, and strategies. When `DATABASE_URL` is empty, the API continues using `DATABASE_PATH` and SQLite for local development.

### Enable live Upstox market data

Generate a one-year read-only Analytics Token from your Upstox developer app for
stock search, quotes, and scanners. Keep the daily OAuth token separate for live
account and order operations:

```env
UPSTOX_MARKET_DATA_TOKEN=your_analytics_token
UPSTOX_ACCESS_TOKEN=your_daily_trading_token
```

The FastAPI backend uses `UPSTOX_MARKET_DATA_TOKEN` for Instrument Search, V3
LTP quotes, position price refreshes, and historical scanner candles. It never
uses this read-only token for order placement. If it is empty, the backend falls
back to `UPSTOX_ACCESS_TOKEN` for backward compatibility. Without either token—or
if Upstox is temporarily unavailable—the search uses the seeded paper list.

Verify the token without displaying it or your personal profile details:

```bash
cd backend
../.venv/bin/python -m scripts.verify_upstox
```

### Upstox order execution modes

Execution is explicitly separated from market data:

```env
UPSTOX_SANDBOX_ACCESS_TOKEN=your_sandbox_token
UPSTOX_SANDBOX_BASE_URL=https://api-sandbox.upstox.com
UPSTOX_ORDER_BASE_URL=https://api-hft.upstox.com
LIVE_TRADING_ENABLED=false
ALLOW_LIVE_STRATEGIES=false
```

Choose `Upstox Sandbox` in the dashboard to test broker order submission and reconciliation without real funds. Upstox orders remain pending until the broker confirms filled quantity and average price; only confirmed fills update positions and P&L. `Upstox Live` stays backend-locked until `LIVE_TRADING_ENABLED=true`, and automated live strategies have their own separate gate.

Every automated signal should provide a unique `signal_id`. Reusing the same ID returns the original order instead of placing a duplicate.

## Strategy signal example

The seeded JARVIS user's development strategy key is `demo-strategy-key`. Change it outside local development.

```bash
curl -X POST http://localhost:8000/api/signals \
  -H 'Content-Type: application/json' \
  -H 'X-Strategy-Key: demo-strategy-key' \
  -d '{"symbol":"RELIANCE","side":"BUY","quantity":10,"strategy_name":"momentum-v1"}'
```

See [`examples/strategy_signal.py`](examples/strategy_signal.py) for a reusable Python example.

## Safety boundary

This version is paper-only. Selecting Upstox records the intended connection, but order placement stays disabled and returns a clear error. Before live trading, add OAuth token encryption, instrument-master synchronization, WebSocket quotes, idempotency, audit logs, reconciliation, rate limiting, exchange/product/order types, and broker-specific sandbox tests.
