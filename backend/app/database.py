import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    strategy_api_key_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broker_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    broker TEXT NOT NULL DEFAULT 'PAPER',
    status TEXT NOT NULL DEFAULT 'CONNECTED',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    execution_mode TEXT NOT NULL DEFAULT 'PAPER',
    broker_order_id TEXT,
    symbol TEXT NOT NULL,
    instrument_key TEXT,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    filled_quantity INTEGER NOT NULL DEFAULT 0,
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    product TEXT NOT NULL DEFAULT 'D',
    source TEXT NOT NULL CHECK(source IN ('MANUAL', 'STRATEGY')),
    strategy_name TEXT,
    signal_id TEXT,
    status TEXT NOT NULL,
    requested_price REAL,
    average_price REAL,
    rejection_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    execution_mode TEXT NOT NULL DEFAULT 'PAPER',
    symbol TEXT NOT NULL,
    instrument_key TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    average_price REAL NOT NULL DEFAULT 0,
    realized_pnl REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, execution_mode, symbol)
);

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'PAUSED')),
    signal_count INTEGER NOT NULL DEFAULT 0,
    last_signal_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);
"""


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or get_settings().database_path

    def connect(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._add_missing_columns(connection, "orders", {
                "execution_mode": "TEXT NOT NULL DEFAULT 'PAPER'",
                "instrument_key": "TEXT",
                "filled_quantity": "INTEGER NOT NULL DEFAULT 0",
                "product": "TEXT NOT NULL DEFAULT 'D'",
                "signal_id": "TEXT",
            })
            self._add_missing_columns(connection, "positions", {"instrument_key": "TEXT"})
            self._migrate_positions_scope(connection)
            connection.execute("DROP INDEX IF EXISTS idx_orders_user_signal")
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_user_signal
                   ON orders(user_id, execution_mode, signal_id) WHERE signal_id IS NOT NULL"""
            )
            connection.execute(
                """UPDATE broker_connections SET broker = 'UPSTOX_LIVE', status = 'LOCKED'
                   WHERE broker = 'UPSTOX'"""
            )

    @staticmethod
    def _add_missing_columns(
        connection: sqlite3.Connection, table: str, columns: dict[str, str]
    ) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_positions_scope(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(positions)")}
        if "execution_mode" in columns:
            return
        connection.executescript(
            """
            ALTER TABLE positions RENAME TO positions_legacy;
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                execution_mode TEXT NOT NULL DEFAULT 'PAPER',
                symbol TEXT NOT NULL,
                instrument_key TEXT,
                quantity INTEGER NOT NULL DEFAULT 0,
                average_price REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, execution_mode, symbol)
            );
            INSERT INTO positions
                (id, user_id, execution_mode, symbol, instrument_key, quantity,
                 average_price, realized_pnl, updated_at)
            SELECT id, user_id, 'PAPER', symbol, instrument_key, quantity,
                   average_price, realized_pnl, updated_at
            FROM positions_legacy;
            DROP TABLE positions_legacy;
            """
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


db = Database()
