"""Historical candle cache implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from collections import defaultdict
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

    def checked_through(self, instrument_key: str) -> date | None:
        """Return the newest date already checked with the provider, even if empty."""

        del instrument_key
        return None

    def mark_checked_through(self, instrument_key: str, checked_through: date) -> None:
        """Remember that the provider was queried through this date."""

        del instrument_key, checked_through


class InMemoryCandleCache(CandleCache):
    """Process-local cache useful for tests and short-lived scanner jobs."""

    def __init__(self):
        self._candles: dict[tuple[str, date], Candle] = {}
        self._checked_through: dict[str, date] = {}
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

    def checked_through(self, instrument_key: str) -> date | None:
        with self._lock:
            return self._checked_through.get(instrument_key)

    def mark_checked_through(self, instrument_key: str, checked_through: date) -> None:
        with self._lock:
            current = self._checked_through.get(instrument_key)
            if current is None or checked_through > current:
                self._checked_through[instrument_key] = checked_through


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

    def get_many(
        self,
        instrument_keys: Iterable[str],
        from_date: date,
        to_date: date,
    ) -> dict[str, list[Candle]]:
        """Load a scan universe with one database connection and one query."""

        candles, _ = self.prefetch(instrument_keys, from_date, to_date)
        return candles

    def prefetch(
        self,
        instrument_keys: Iterable[str],
        from_date: date,
        to_date: date,
    ) -> tuple[dict[str, list[Candle]], dict[str, date]]:
        """Bulk-load candles and provider coverage with one DB connection."""

        keys = list(dict.fromkeys(key for key in instrument_keys if key.strip()))
        if not keys:
            return {}, {}
        placeholders = ",".join("?" for _ in keys)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT instrument_key, candle_timestamp, open, high, low, close,
                           volume, open_interest
                    FROM market_candles
                    WHERE instrument_key IN ({placeholders})
                      AND candle_date BETWEEN ? AND ?
                    ORDER BY instrument_key, candle_date ASC""",
                (*keys, from_date.isoformat(), to_date.isoformat()),
            ).fetchall()
            sync_rows = connection.execute(
                f"""SELECT instrument_key, checked_through
                    FROM market_candle_sync
                    WHERE instrument_key IN ({placeholders})""",
                tuple(keys),
            ).fetchall()
        grouped: dict[str, list[Candle]] = defaultdict(list)
        for row in rows:
            grouped[str(row["instrument_key"])].append(
                Candle(
                    timestamp=datetime.fromisoformat(str(row["candle_timestamp"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    open_interest=int(row["open_interest"]),
                )
            )
        checked = {
            str(row["instrument_key"]): date.fromisoformat(str(row["checked_through"]))
            for row in sync_rows
        }
        return dict(grouped), checked

    def checked_through(self, instrument_key: str) -> date | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT checked_through FROM market_candle_sync WHERE instrument_key = ?",
                (instrument_key,),
            ).fetchone()
        return date.fromisoformat(str(row["checked_through"])) if row else None

    def mark_checked_through(self, instrument_key: str, checked_through: date) -> None:
        self.persist_scan({}, {instrument_key: checked_through}, provider="UPSTOX")

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
        self.upsert_many({instrument_key: rows}, provider=provider)

    def upsert_many(
        self,
        candles_by_instrument: dict[str, Iterable[Candle]],
        *,
        provider: str,
    ) -> None:
        """Persist all candles produced by a scan in one transaction."""
        self.persist_scan(candles_by_instrument, {}, provider=provider)

    def persist_scan(
        self,
        candles_by_instrument: dict[str, Iterable[Candle]],
        checked_by_instrument: dict[str, date],
        *,
        provider: str,
    ) -> None:
        """Persist candle changes and coverage markers in one transaction."""

        values = [
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
            )
            for instrument_key, candles in candles_by_instrument.items()
            for candle in candles
        ]
        sync_values = [
            (instrument_key, checked.isoformat(), provider)
            for instrument_key, checked in checked_by_instrument.items()
        ]
        if not values and not sync_values:
            return
        with self.database.transaction() as connection:
            if values:
                connection.executemany(
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
                    values,
                )
            if sync_values:
                connection.executemany(
                    """INSERT INTO market_candle_sync
                       (instrument_key, checked_through, provider)
                       VALUES (?, ?, ?)
                       ON CONFLICT(instrument_key) DO UPDATE SET
                         checked_through = CASE
                           WHEN excluded.checked_through > market_candle_sync.checked_through
                           THEN excluded.checked_through
                           ELSE market_candle_sync.checked_through
                         END,
                         provider = excluded.provider,
                         updated_at = CURRENT_TIMESTAMP""",
                    sync_values,
                )


class PrefetchedCandleCache(CandleCache):
    """Per-scan memory cache with one bulk read and one deferred bulk write."""

    def __init__(
        self,
        backing: DatabaseCandleCache,
        prefetched: dict[str, list[Candle]],
        checked_through: dict[str, date] | None = None,
    ):
        self.backing = backing
        self.memory = InMemoryCandleCache()
        self._pending: dict[tuple[str, date], Candle] = {}
        self._checked_through = dict(checked_through or {})
        self._pending_checked: dict[str, date] = {}
        self._lock = RLock()
        for instrument_key, candles in prefetched.items():
            self.memory.upsert(instrument_key, candles, provider="PREFETCH")

    def get(self, instrument_key: str, from_date: date, to_date: date) -> list[Candle]:
        return self.memory.get(instrument_key, from_date, to_date)

    def upsert(
        self,
        instrument_key: str,
        candles: Iterable[Candle],
        *,
        provider: str,
    ) -> None:
        del provider
        rows = list(candles)
        self.memory.upsert(instrument_key, rows, provider="SCAN")
        with self._lock:
            for candle in rows:
                self._pending[(instrument_key, candle.timestamp.date())] = candle

    def checked_through(self, instrument_key: str) -> date | None:
        with self._lock:
            return self._checked_through.get(instrument_key)

    def mark_checked_through(self, instrument_key: str, checked_through: date) -> None:
        with self._lock:
            current = self._checked_through.get(instrument_key)
            if current is None or checked_through > current:
                self._checked_through[instrument_key] = checked_through
                self._pending_checked[instrument_key] = checked_through

    def flush(self, *, provider: str) -> None:
        """Write fetched ranges after evaluation without opening per-stock connections."""

        with self._lock:
            pending = list(self._pending.items())
            pending_checked = dict(self._pending_checked)
        if not pending and not pending_checked:
            return
        grouped: dict[str, list[Candle]] = defaultdict(list)
        for (instrument_key, _), candle in pending:
            grouped[instrument_key].append(candle)
        self.backing.persist_scan(dict(grouped), pending_checked, provider=provider)
        with self._lock:
            for key, candle in pending:
                if self._pending.get(key) is candle:
                    self._pending.pop(key, None)
            for instrument_key, checked in pending_checked.items():
                if self._pending_checked.get(instrument_key) == checked:
                    self._pending_checked.pop(instrument_key, None)

    def snapshot(
        self,
        instrument_keys: Iterable[str],
        from_date: date,
        to_date: date,
    ) -> tuple[dict[str, list[Candle]], dict[str, date]]:
        """Export the updated in-memory view for reuse by a warm API process."""

        candles = {
            instrument_key: rows
            for instrument_key in instrument_keys
            if (rows := self.memory.get(instrument_key, from_date, to_date))
        }
        with self._lock:
            checked = {
                instrument_key: self._checked_through[instrument_key]
                for instrument_key in instrument_keys
                if instrument_key in self._checked_through
            }
        return candles, checked
