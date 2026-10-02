"""Historical candle cache implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from threading import RLock
from typing import Iterable

from ..database import Database, db
from .models import Candle


class CandleCache(ABC):
    """Storage boundary for normalized daily candles."""

    @abstractmethod
    def get(self, instrument_key: str, from_date: date, to_date: date) -> list[Candle]:
        """Return cached candles in ascending date order."""

    @abstractmethod
    def upsert(
        self,
        instrument_key: str,
        candles: Iterable[Candle],
        *,
        provider: str,
    ) -> None:
        """Insert candles and replace corrected values for an existing date."""


class InMemoryCandleCache(CandleCache):
    """Process-local cache useful for tests and short-lived scanner jobs."""

    def __init__(self):
        self._candles: dict[tuple[str, date], Candle] = {}
        self._lock = RLock()

    def get(self, instrument_key: str, from_date: date, to_date: date) -> list[Candle]:
        with self._lock:
            return sorted(
                (
                    candle
                    for (key, candle_date), candle in self._candles.items()
                    if key == instrument_key and from_date <= candle_date <= to_date
                ),
                key=lambda candle: candle.timestamp,
            )

    def upsert(
        self,
        instrument_key: str,
        candles: Iterable[Candle],
        *,
        provider: str,
    ) -> None:
        del provider
        with self._lock:
            for candle in candles:
                self._candles[(instrument_key, candle.timestamp.date())] = candle


class DatabaseCandleCache(CandleCache):
    """Persistent candle cache backed by JARVIS SQLite or PostgreSQL."""

    def __init__(self, database: Database = db):
        self.database = database

    def get(self, instrument_key: str, from_date: date, to_date: date) -> list[Candle]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT candle_timestamp, open, high, low, close, volume, open_interest
                   FROM market_candles
                   WHERE instrument_key = ? AND candle_date BETWEEN ? AND ?
                   ORDER BY candle_date ASC""",
                (instrument_key, from_date.isoformat(), to_date.isoformat()),
            ).fetchall()
        return [
            Candle(
                timestamp=datetime.fromisoformat(str(row["candle_timestamp"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                open_interest=int(row["open_interest"]),
            )
            for row in rows
        ]

    def upsert(
        self,
        instrument_key: str,
        candles: Iterable[Candle],
        *,
        provider: str,
    ) -> None:
        rows = list(candles)
        if not rows:
            return
        with self.database.transaction() as connection:
            for candle in rows:
                connection.execute(
                    """INSERT INTO market_candles
                       (instrument_key, candle_date, candle_timestamp, open, high, low,
                        close, volume, open_interest, provider)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(instrument_key, candle_date) DO UPDATE SET
                         candle_timestamp = excluded.candle_timestamp,
                         open = excluded.open,
                         high = excluded.high,
                         low = excluded.low,
                         close = excluded.close,
                         volume = excluded.volume,
                         open_interest = excluded.open_interest,
                         provider = excluded.provider,
                         updated_at = CURRENT_TIMESTAMP""",
                    (
                        instrument_key,
                        candle.timestamp.date().isoformat(),
                        candle.timestamp.isoformat(),
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                        candle.open_interest,
                        provider,
                    ),
                )
