import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.market_data.base import HistoricalDataProvider, MarketDataProviderError
from app.database import Database
from app.market_data.cache import DatabaseCandleCache, InMemoryCandleCache
from app.market_data.models import Candle
from app.market_data.service import HistoricalDataService
from app.scanner.indicators import (
    InsufficientHistoryError,
    build_indicator_snapshot,
    previous_average_volume,
    prior_52_week_range,
    simple_moving_average,
    volume_ratio,
    wilder_rsi,
)

IST = timezone(timedelta(hours=5, minutes=30))


def candle(day: int, close: float, *, volume: int = 100, high=None, low=None) -> Candle:
    return Candle(
        timestamp=datetime(2025, 1, 1, tzinfo=IST) + timedelta(days=day),
        open=close,
        high=float(high if high is not None else close),
        low=float(low if low is not None else close),
        close=close,
        volume=volume,
    )


class RecordingProvider(HistoricalDataProvider):
    def __init__(self, candles_by_date: dict[date, Candle]):
        self.candles_by_date = candles_by_date
        self.requests: list[tuple[date, date]] = []

    async def get_daily_candles(self, instrument_key, from_date, to_date):
        del instrument_key
        self.requests.append((from_date, to_date))
        return [
            item
            for candle_date, item in sorted(self.candles_by_date.items())
            if from_date <= candle_date <= to_date
        ]


def test_history_service_caches_and_incrementally_refreshes_latest_edge():
    candles = {candle(index, 100 + index).timestamp.date(): candle(index, 100 + index) for index in range(5)}
    provider = RecordingProvider(candles)
    cache = InMemoryCandleCache()
    service = HistoricalDataService(provider, cache, provider_name="TEST")
    start, initial_end = min(candles), sorted(candles)[2]

    first = asyncio.run(service.get_daily_candles("NSE_EQ|TEST", start, initial_end))
    assert len(first) == 3
    assert provider.requests == [(start, initial_end)]

    final_end = max(candles)
    second = asyncio.run(service.get_daily_candles("NSE_EQ|TEST", start, final_end))
    assert len(second) == 5
    assert provider.requests[-1] == (initial_end, final_end)

    cached_only = asyncio.run(
        service.get_daily_candles("NSE_EQ|TEST", start, final_end, refresh=False)
    )
    assert len(cached_only) == 5
    assert len(provider.requests) == 2


def test_history_service_replaces_provider_corrections():
    original = candle(0, 100)
    provider = RecordingProvider({original.timestamp.date(): original})
    cache = InMemoryCandleCache()
    service = HistoricalDataService(provider, cache, provider_name="TEST")
    day = original.timestamp.date()
    asyncio.run(service.get_daily_candles("NSE_EQ|TEST", day, day))

    corrected = candle(0, 105)
    provider.candles_by_date[day] = corrected
    result = asyncio.run(service.get_daily_candles("NSE_EQ|TEST", day, day))
    assert result[0].close == 105


def test_database_candle_cache_persists_and_upserts_sqlite(tmp_path):
    database = Database(str(tmp_path / "scanner-cache.db"))
    database.url = ""
    database.initialize()
    cache = DatabaseCandleCache(database)
    first = candle(0, 100)
    corrected = candle(0, 104)
    second = candle(1, 106)

    cache.upsert("NSE_EQ|TEST", [first, second], provider="TEST")
    cache.upsert("NSE_EQ|TEST", [corrected], provider="TEST")
    result = cache.get(
        "NSE_EQ|TEST", first.timestamp.date(), second.timestamp.date()
    )

    assert [item.close for item in result] == [104, 106]


def test_history_service_rejects_invalid_provider_candles():
    invalid = Candle(
        timestamp=datetime(2025, 1, 1),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=10,
    )
    provider = RecordingProvider({invalid.timestamp.date(): invalid})
    service = HistoricalDataService(provider, InMemoryCandleCache(), provider_name="TEST")
    with pytest.raises(MarketDataProviderError, match="timezone"):
        asyncio.run(
            service.get_daily_candles(
                "NSE_EQ|TEST", invalid.timestamp.date(), invalid.timestamp.date()
            )
        )


def test_sma_volume_and_volume_ratio_follow_v1_boundaries():
    candles = [candle(index, float(index + 1), volume=(index + 1) * 100) for index in range(21)]
    assert simple_moving_average(candles, 20) == pytest.approx(11.5)
    assert previous_average_volume(candles) == pytest.approx(1050)
    assert volume_ratio(candles) == pytest.approx(2.0)


def test_wilder_rsi_edge_cases():
    rising = [candle(index, 100 + index) for index in range(15)]
    falling = [candle(index, 100 - index) for index in range(15)]
    flat = [candle(index, 100) for index in range(15)]
    assert wilder_rsi(rising) == 100
    assert wilder_rsi(falling) == 0
    assert wilder_rsi(flat) == 50


def test_prior_52_week_range_excludes_evaluation_candle():
    candles = [candle(index, 100, high=110, low=90) for index in range(252)]
    candles.append(candle(252, 200, high=210, low=80))
    assert prior_52_week_range(candles) == (110, 90)

    snapshot = build_indicator_snapshot(candles)
    assert snapshot.prior_52w_high == 110
    assert snapshot.prior_52w_low == 90
    assert snapshot.breakout_percent == pytest.approx(81.8181818)


def test_indicators_report_insufficient_history():
    with pytest.raises(InsufficientHistoryError, match="20 candles"):
        simple_moving_average([candle(0, 100)], 20)
