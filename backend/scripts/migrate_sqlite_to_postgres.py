"""Copy the local JARVIS SQLite data into the PostgreSQL database in DATABASE_URL.

Run from the backend directory after setting DATABASE_URL in .env:
    python -m scripts.migrate_sqlite_to_postgres --source ./jarvis.db
"""

import argparse
import sqlite3
from pathlib import Path

from app.database import db


TABLE_COLUMNS = {
    "users": ["id", "email", "password_hash", "strategy_api_key_hash", "created_at"],
    "broker_connections": ["id", "user_id", "broker", "status", "updated_at"],
    "orders": [
        "id", "user_id", "execution_mode", "broker_order_id", "symbol", "instrument_key",
        "side", "quantity", "filled_quantity", "order_type", "product", "source",
        "strategy_name", "signal_id", "status", "requested_price", "average_price",
        "rejection_reason", "created_at", "updated_at",
    ],
    "positions": [
        "id", "user_id", "execution_mode", "symbol", "instrument_key", "quantity",
        "average_price", "realized_pnl", "updated_at",
    ],
    "strategies": [
        "id", "user_id", "name", "description", "status", "signal_count",
        "last_signal_at", "created_at", "updated_at",
    ],
}


def copy_table(source: sqlite3.Connection, destination, table: str, columns: list[str]) -> int:
    rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    statement = (
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
        "ON CONFLICT (id) DO NOTHING"
    )
    for row in rows:
        destination.execute(statement, tuple(row[column] for column in columns))
    return len(rows)


def reset_sequences(destination) -> None:
    for table in TABLE_COLUMNS:
        destination.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), true)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="./jarvis.db", help="SQLite database path")
    args = parser.parse_args()

    if not db.is_postgres:
        raise SystemExit("DATABASE_URL must be set before running this migration")

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"SQLite database not found: {source_path}")

    db.initialize()
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        with db.transaction() as destination:
            copied = {
                table: copy_table(source, destination, table, columns)
                for table, columns in TABLE_COLUMNS.items()
            }
            reset_sequences(destination)
    finally:
        source.close()

    for table, count in copied.items():
        print(f"{table}: {count} rows copied")
    print("Migration completed successfully")


if __name__ == "__main__":
    main()
