import secrets
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from .brokers import BrokerFactory
from .config import get_settings
from .database import db
from .dependencies import get_current_user, get_strategy_user
from .instruments import find_instrument, register_instruments
from .schemas import (
    AuthResponse,
    BrokerRequest,
    LoginRequest,
    OrderRequest,
    OrderResponse,
    OrderSource,
    PositionResponse,
    RegisterRequest,
    SignalRequest,
    StrategyCreate,
    StrategyKeyResponse,
    StrategyResponse,
    StrategyUpdate,
)
from .security import create_token, hash_secret, verify_secret
from .services.execution import ExecutionEngine
from .services.market_data import refresh_instrument_prices, search_equities
from .services.reconciliation import reconcile_orders


def seed_jarvis_user() -> None:
    settings = get_settings()
    with db.transaction() as connection:
        existing = connection.execute("SELECT id FROM users WHERE email = ?", ("jarvis@example.com",)).fetchone()
        if existing:
            return
        legacy = connection.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@example.com",)
        ).fetchone()
        if legacy:
            connection.execute(
                "UPDATE users SET email = ?, password_hash = ? WHERE id = ?",
                ("jarvis@example.com", hash_secret("jarvis1234"), legacy["id"]),
            )
            return
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash, strategy_api_key_hash) VALUES (?, ?, ?)",
            ("jarvis@example.com", hash_secret("jarvis1234"), hash_secret(settings.demo_strategy_key)),
        )
        connection.execute(
            "INSERT INTO broker_connections (user_id, broker, status) VALUES (?, 'PAPER', 'CONNECTED')",
            (cursor.lastrowid,),
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    seed_jarvis_user()
    yield


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "paper"}


@app.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    api_key = secrets.token_urlsafe(32)
    try:
        with db.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, password_hash, strategy_api_key_hash) VALUES (?, ?, ?)",
                (payload.email.lower(), hash_secret(payload.password), hash_secret(api_key)),
            )
            user_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO broker_connections (user_id, broker, status) VALUES (?, 'PAPER', 'CONNECTED')",
                (user_id,),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return AuthResponse(access_token=create_token(user_id), email=payload.email.lower(), strategy_api_key=api_key)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    with db.connect() as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (payload.email.lower(),)).fetchone()
    if not user or not verify_secret(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return AuthResponse(access_token=create_token(user["id"]), email=user["email"])


@app.post("/api/auth/strategy-key", response_model=StrategyKeyResponse)
def rotate_strategy_key(user=Depends(get_current_user)):
    api_key = secrets.token_urlsafe(32)
    with db.transaction() as connection:
        connection.execute(
            "UPDATE users SET strategy_api_key_hash = ? WHERE id = ?",
            (hash_secret(api_key), user["id"]),
        )
    return StrategyKeyResponse(
        strategy_api_key=api_key,
        message="Save this key now. It will not be shown again.",
    )


@app.get("/api/instruments")
async def instruments(q: str = Query(default="", max_length=50), _=Depends(get_current_user)):
    if q and len(q.strip()) < 2:
        return []
    return await search_equities(q, limit=10)


def selected_broker(connection, user_id: int):
    broker = connection.execute(
        "SELECT broker FROM broker_connections WHERE user_id = ?", (user_id,)
    ).fetchone()
    return BrokerFactory.create(broker["broker"] if broker else "PAPER")


def selected_broker_name(user_id: int) -> str:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT broker FROM broker_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["broker"] if row else "PAPER"


@app.post("/api/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(payload: OrderRequest, user=Depends(get_current_user)):
    broker_name = selected_broker_name(user["id"])
    if broker_name in {"UPSTOX", "UPSTOX_LIVE"} and not payload.confirm_live:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required for a live order")
    instrument = find_instrument(payload.symbol)
    # Vercel may route the search request and the order request to different
    # function instances. Resolve an unknown symbol again in this request so a
    # paper order never depends on an in-memory search cache from a prior call.
    if not instrument or (broker_name != "PAPER" and not instrument.get("instrument_key")):
        await search_equities(payload.symbol, limit=10)
    with db.transaction() as connection:
        order = ExecutionEngine(selected_broker(connection, user["id"])).execute(
            connection,
            user_id=user["id"],
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            source=OrderSource.MANUAL,
        )
    return dict(order)


@app.post("/api/signals", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def receive_signal(payload: SignalRequest, user=Depends(get_strategy_user)):
    broker_name = selected_broker_name(user["id"])
    if broker_name in {"UPSTOX", "UPSTOX_LIVE"} and not get_settings().allow_live_strategies:
        raise HTTPException(status_code=403, detail="Automated live strategy execution is disabled")
    instrument = find_instrument(payload.symbol)
    if not instrument or (broker_name != "PAPER" and not instrument.get("instrument_key")):
        await search_equities(payload.symbol, limit=10)
    with db.transaction() as connection:
        if payload.signal_id:
            existing_order = connection.execute(
                """SELECT * FROM orders
                   WHERE user_id = ? AND execution_mode = ? AND signal_id = ?""",
                (user["id"], broker_name, payload.signal_id),
            ).fetchone()
            if existing_order:
                return dict(existing_order)
        strategy = connection.execute(
            "SELECT * FROM strategies WHERE user_id = ? AND name = ?",
            (user["id"], payload.strategy_name),
        ).fetchone()
        if strategy and strategy["status"] == "PAUSED":
            raise HTTPException(status_code=409, detail=f"Strategy '{payload.strategy_name}' is paused")
        if not strategy:
            connection.execute(
                "INSERT INTO strategies (user_id, name, description) VALUES (?, ?, ?)",
                (user["id"], payload.strategy_name, "Auto-registered from Signal API"),
            )
        order = ExecutionEngine(selected_broker(connection, user["id"])).execute(
            connection,
            user_id=user["id"],
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            source=OrderSource.STRATEGY,
            strategy_name=payload.strategy_name,
            signal_id=payload.signal_id,
        )
        connection.execute(
            """UPDATE strategies SET signal_count = signal_count + 1,
               last_signal_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ? AND name = ?""",
            (user["id"], payload.strategy_name),
        )
    return dict(order)


@app.get("/api/strategies", response_model=list[StrategyResponse])
def list_strategies(user=Depends(get_current_user)):
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM strategies WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/strategies", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(payload: StrategyCreate, user=Depends(get_current_user)):
    name = " ".join(payload.name.strip().split())
    try:
        with db.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO strategies (user_id, name, description) VALUES (?, ?, ?)",
                (user["id"], name, payload.description.strip()),
            )
            row = connection.execute("SELECT * FROM strategies WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A strategy with this name already exists")
    return dict(row)


@app.patch("/api/strategies/{strategy_id}", response_model=StrategyResponse)
def update_strategy(strategy_id: int, payload: StrategyUpdate, user=Depends(get_current_user)):
    with db.transaction() as connection:
        cursor = connection.execute(
            "UPDATE strategies SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (payload.status, strategy_id, user["id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Strategy not found")
        row = connection.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return dict(row)


@app.get("/api/orders", response_model=list[OrderResponse])
def list_orders(user=Depends(get_current_user)):
    reconcile_orders(user["id"])
    execution_mode = selected_broker_name(user["id"])
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT * FROM orders WHERE user_id = ? AND execution_mode = ?
               ORDER BY id DESC LIMIT 100""",
            (user["id"], execution_mode),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/positions", response_model=list[PositionResponse])
async def list_positions(include_closed: bool = False, user=Depends(get_current_user)):
    execution_mode = selected_broker_name(user["id"])
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT * FROM positions WHERE user_id = ? AND execution_mode = ?
               AND (? OR quantity != 0) ORDER BY symbol""",
            (user["id"], execution_mode, include_closed),
        ).fetchall()
    register_instruments([
        {
            "symbol": row["symbol"],
            "name": row["symbol"],
            "exchange": "NSE",
            "price": float(row["average_price"]),
            "instrument_key": row["instrument_key"],
            "source": "UPSTOX",
        }
        for row in rows if row["instrument_key"]
    ])
    # Market data can be live while execution remains safely in paper mode.
    if get_settings().upstox_access_token:
        await refresh_instrument_prices([row["symbol"] for row in rows if row["quantity"] != 0])
    positions = []
    for row in rows:
        instrument = find_instrument(row["symbol"])
        last_price = float(instrument["price"]) if instrument else float(row["average_price"])
        unrealized = (last_price - row["average_price"]) * row["quantity"]
        positions.append({
            "execution_mode": row["execution_mode"],
            "symbol": row["symbol"],
            "quantity": row["quantity"],
            "average_price": round(row["average_price"], 2),
            "last_price": round(last_price, 2),
            "market_value": round(last_price * row["quantity"], 2),
            "realized_pnl": round(row["realized_pnl"], 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(row["realized_pnl"] + unrealized, 2),
        })
    return positions


@app.post("/api/portfolio/paper/reset")
def reset_paper_portfolio(user=Depends(get_current_user)):
    """Clear this user's paper orders and positions without touching other modes."""
    with db.transaction() as connection:
        orders_removed = connection.execute(
            "DELETE FROM orders WHERE user_id = ? AND execution_mode = 'PAPER'",
            (user["id"],),
        ).rowcount
        positions_removed = connection.execute(
            "DELETE FROM positions WHERE user_id = ? AND execution_mode = 'PAPER'",
            (user["id"],),
        ).rowcount
    return {
        "message": "Paper portfolio reset successfully",
        "orders_removed": orders_removed,
        "positions_removed": positions_removed,
    }


@app.get("/api/broker")
def broker_status(user=Depends(get_current_user)):
    with db.connect() as connection:
        row = connection.execute(
            "SELECT broker, status, updated_at FROM broker_connections WHERE user_id = ?", (user["id"],)
        ).fetchone()
    result = dict(row) if row else {"broker": "PAPER", "status": "CONNECTED"}
    result["market_data_source"] = "UPSTOX" if get_settings().upstox_access_token else "PAPER"
    return result


@app.put("/api/broker")
def connect_broker(payload: BrokerRequest, user=Depends(get_current_user)):
    broker = payload.broker.strip().upper()
    if broker not in {"PAPER", "UPSTOX_SANDBOX", "UPSTOX_LIVE"}:
        raise HTTPException(
            status_code=400,
            detail="Supported execution modes: PAPER, UPSTOX_SANDBOX, UPSTOX_LIVE",
        )
    settings = get_settings()
    if broker == "PAPER":
        connection_status = "CONNECTED"
        message = "Paper broker ready"
    elif broker == "UPSTOX_SANDBOX":
        connection_status = "CONNECTED" if settings.upstox_sandbox_access_token else "SETUP_REQUIRED"
        message = (
            "Upstox sandbox execution ready" if settings.upstox_sandbox_access_token
            else "Add UPSTOX_SANDBOX_ACCESS_TOKEN to enable sandbox orders"
        )
    else:
        connection_status = (
            "CONNECTED" if settings.upstox_access_token and settings.live_trading_enabled else "LOCKED"
        )
        message = (
            "Upstox live execution enabled" if connection_status == "CONNECTED"
            else "Live trading remains locked until sandbox verification and LIVE_TRADING_ENABLED=true"
        )
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO broker_connections (user_id, broker, status)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET broker=excluded.broker,
                 status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
            (user["id"], broker, connection_status),
        )
    return {
        "broker": broker,
        "status": connection_status,
        "market_data_source": "UPSTOX" if settings.upstox_access_token else "PAPER",
        "message": message,
    }
