"""Cached, incremental access to historical daily candles."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from .base import HistoricalDataProvider, MarketDataProviderError
from .cache import CandleCache, DatabaseCandleCache
from .models import Candle


class HistoricalDataService:
    """Combine a remote history provider with a replaceable candle cache."""

    def __init__(
        self,
        provider: HistoricalDataProvider,
        cache: CandleCache,
        *,
        provider_name: str,
    ):
        self.provider = provider
        self.cache = cache
        self.provider_name = provider_name

    async def get_daily_candles(
        self,
        instrument_key: str,
        from_date: date,
        to_date: date,
        *,
        refresh: bool = True,
    ) -> list[Candle]:
        if not instrument_key.strip():
            raise ValueError("instrument_key is required")
        if from_date > to_date:
            raise ValueError("from_date must not be after to_date")

        # SQLite/psycopg are synchronous. Run cache I/O in worker threads so a
        # NIFTY 50 scan can actually fetch several instruments concurrently and
        # does not freeze unrelated FastAPI requests while Neon responds.
        cached = await self._cache_get(instrument_key, from_date, to_date)
        checked_through = self.cache.checked_through(instrument_key)
        ranges = self._refresh_ranges(
            cached,
            from_date,
            to_date,
            refresh=refresh,
            checked_through=checked_through,
        )
        for range_start, range_end in ranges:
            fetched = await self.provider.get_daily_candles(
                instrument_key, range_start, range_end
            )
            self._validate_provider_candles(fetched, range_start, range_end)
            await self._cache_upsert(instrument_key, fetched)
            await self._cache_mark_checked(instrument_key, range_end)

        return await self._cache_get(instrument_key, from_date, to_date)

    async def _cache_get(
        self, instrument_key: str, from_date: date, to_date: date
    ) -> list[Candle]:
        if isinstance(self.cache, DatabaseCandleCache):
            return await asyncio.to_thread(
                self.cache.get, instrument_key, from_date, to_date
            )
        return self.cache.get(instrument_key, from_date, to_date)

    async def _cache_upsert(self, instrument_key: str, candles: list[Candle]) -> None:
        if isinstance(self.cache, DatabaseCandleCache):
            await asyncio.to_thread(
                self.cache.upsert,
                instrument_key,
                candles,
                provider=self.provider_name,
            )
            return
        self.cache.upsert(instrument_key, candles, provider=self.provider_name)

    async def _cache_mark_checked(self, instrument_key: str, checked_through: date) -> None:
        if isinstance(self.cache, DatabaseCandleCache):
            await asyncio.to_thread(
                self.cache.mark_checked_through, instrument_key, checked_through
            )
            return
        self.cache.mark_checked_through(instrument_key, checked_through)

    @staticmethod
    def _refresh_ranges(
        cached: list[Candle],
        from_date: date,
        to_date: date,
        *,
        refresh: bool,
        checked_through: date | None = None,
    ) -> list[tuple[date, date]]:
        # `refresh=False` means cache-first, not cache-only: missing coverage
        # must still be downloaded or a cold deployment could never scan.
        if not cached:
            return [(from_date, to_date)]

        first_date = cached[0].timestamp.date()
        last_date = cached[-1].timestamp.date()
        ranges: list[tuple[date, date]] = []

        if from_date < first_date:
            ranges.append((from_date, first_date - timedelta(days=1)))

        coverage_end = max(last_date, checked_through) if checked_through else last_date
        if coverage_end < to_date:
            # A normal scan fetches only dates not already cached. A forced
            # refresh overlaps the newest candle so provider corrections win.
            right_start = last_date if refresh else coverage_end + timedelta(days=1)
            ranges.append((max(from_date, right_start), to_date))
        elif refresh:
            # Explicit refresh of a fully covered range rechecks only its edge.
            ranges.append((max(from_date, min(last_date, to_date)), to_date))
        return ranges

    @staticmethod
    def _validate_provider_candles(
        candles: list[Candle],
        from_date: date,
        to_date: date,
    ) -> None:
        seen_dates: set[date] = set()
        previous_timestamp = None
        for candle in candles:
            candle_date = candle.timestamp.date()
            if candle.timestamp.tzinfo is None:
                raise MarketDataProviderError("Candle timestamp must include a timezone")
            if not from_date <= candle_date <= to_date:
                raise MarketDataProviderError("Provider returned a candle outside the requested range")
            if candle_date in seen_dates:
                raise MarketDataProviderError("Provider returned duplicate daily candles")
            if previous_timestamp and candle.timestamp <= previous_timestamp:
                raise MarketDataProviderError("Provider candles are not in ascending order")
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                raise MarketDataProviderError("Candle prices must be positive")
            if candle.high < max(candle.open, candle.close) or candle.low > min(
                candle.open, candle.close
            ):
                raise MarketDataProviderError("Candle OHLC values are inconsistent")
            if candle.volume < 0 or candle.open_interest < 0:
                raise MarketDataProviderError("Candle volume and open interest cannot be negative")
            seen_dates.add(candle_date)
            previous_timestamp = candle.timestamp
