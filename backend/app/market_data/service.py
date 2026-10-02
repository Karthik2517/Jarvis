"""Cached, incremental access to historical daily candles."""

from __future__ import annotations

from datetime import date, timedelta

from .base import HistoricalDataProvider, MarketDataProviderError
from .cache import CandleCache
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

        cached = self.cache.get(instrument_key, from_date, to_date)
        ranges = self._refresh_ranges(cached, from_date, to_date, refresh=refresh)
        for range_start, range_end in ranges:
            fetched = await self.provider.get_daily_candles(
                instrument_key, range_start, range_end
            )
            self._validate_provider_candles(fetched, range_start, range_end)
            self.cache.upsert(instrument_key, fetched, provider=self.provider_name)

        return self.cache.get(instrument_key, from_date, to_date)

    @staticmethod
    def _refresh_ranges(
        cached: list[Candle],
        from_date: date,
        to_date: date,
        *,
        refresh: bool,
    ) -> list[tuple[date, date]]:
        if not cached:
            return [(from_date, to_date)] if refresh else []
        if not refresh:
            return []

        first_date = cached[0].timestamp.date()
        last_date = cached[-1].timestamp.date()
        ranges: list[tuple[date, date]] = []

        if from_date < first_date:
            ranges.append((from_date, first_date - timedelta(days=1)))

        # Re-fetch the newest cached date so provider corrections overwrite the
        # cached value, and extend through the requested end date incrementally.
        right_start = max(from_date, min(last_date, to_date))
        ranges.append((right_start, to_date))
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
