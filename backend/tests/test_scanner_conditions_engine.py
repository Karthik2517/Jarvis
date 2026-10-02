import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.market_data.base import HistoricalDataProvider, MarketDataProviderError
from app.market_data.cache import InMemoryCandleCache
from app.market_data.models import Candle, Instrument
from app.market_data.service import HistoricalDataService
from app.scanner.conditions import (
    ComparisonOperator,
    Condition,
    ConditionEvaluator,
    ConditionField,
    ConditionOperand,
    ConditionValidationError,
    MissingIndicatorError,
)
from app.scanner.indicators import IndicatorSnapshot
from app.scanner.scanner_engine import ScannerEngine

IST = timezone(timedelta(hours=5, minutes=30))


def snapshot(**overrides) -> IndicatorSnapshot:
    values = {
        "price": 150.0,
        "volume": 3000,
        "sma20": 140.0,
        "sma50": 130.0,
        "sma200": 100.0,
        "avg_volume_20": 1000.0,
        "volume_ratio": 3.0,
        "rsi14": 60.0,
        "prior_52w_high": 145.0,
        "prior_52w_low": 80.0,
        "breakout_percent": 3.45,
        "breakdown_percent": -46.67,
    }
    values.update(overrides)
    return IndicatorSnapshot(**values)


def condition(left, comparison, *, value=None, field=None, multiplier=1.0):
    operand = (
        ConditionOperand.literal(value)
        if value is not None
        else ConditionOperand.indicator(field, multiplier)
    )
    return Condition(ConditionField(left), ComparisonOperator(comparison), operand)


def test_condition_evaluator_supports_field_literal_and_multiplier_operands():
    conditions = [
        condition("price", ">", field="sma50"),
        condition("sma50", ">", field="sma200"),
        condition("volume", ">", field="avg_volume_20", multiplier=2),
        condition("rsi14", ">", value=55),
    ]

    result = ConditionEvaluator(conditions).evaluate(snapshot())

    assert result.matched is True
    assert len(result.checks) == 4
    assert result.checks[2].right_value == 2000


def test_condition_evaluator_uses_and_semantics_without_short_circuiting_details():
    conditions = [
        condition("price", ">", field="sma50"),
        condition("rsi14", ">=", value=70),
    ]
    result = ConditionEvaluator(conditions).evaluate(snapshot())
    assert result.matched is False
    assert [check.matched for check in result.checks] == [True, False]


def test_conditions_reject_unsafe_or_ambiguous_inputs():
    with pytest.raises(ConditionValidationError, match="exactly one"):
        ConditionOperand()
    with pytest.raises(ConditionValidationError, match="finite"):
        ConditionOperand.literal(float("inf"))
    with pytest.raises(ConditionValidationError, match="Unsupported condition field"):
        ConditionOperand.indicator("__import__('os').system('echo unsafe')")
    with pytest.raises(ConditionValidationError, match="At least one"):
        ConditionEvaluator([])


def test_condition_evaluator_reports_missing_indicator():
    evaluator = ConditionEvaluator([condition("price", ">", field="sma200")])
    with pytest.raises(MissingIndicatorError, match="sma200"):
        evaluator.evaluate(snapshot(sma200=None))


class UniverseHistoryProvider(HistoricalDataProvider):
    def __init__(self, history):
        self.history = history
        self.active = 0
        self.peak_active = 0

    async def get_daily_candles(self, instrument_key, from_date, to_date):
        del from_date, to_date
        if instrument_key == "NSE_EQ|BROKEN":
            raise MarketDataProviderError("provider unavailable")
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        return self.history[instrument_key]


def make_history(start: float, daily_change: float, count: int = 60):
    candles = []
    for index in range(count):
        close = start + (index * daily_change)
        candles.append(
            Candle(
                timestamp=datetime(2025, 1, 1, tzinfo=IST) + timedelta(days=index),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000 + index,
            )
        )
    return candles


def instrument(symbol: str, key: str) -> Instrument:
    return Instrument(
        instrument_key=key,
        trading_symbol=symbol,
        name=symbol,
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        security_type="NORMAL",
    )


def test_scanner_engine_returns_matches_nonmatches_and_skip_statistics():
    rising = make_history(100, 1)
    falling = make_history(200, -1)
    provider = UniverseHistoryProvider(
        {"NSE_EQ|RISING": rising, "NSE_EQ|FALLING": falling}
    )
    engine = ScannerEngine(
        HistoricalDataService(provider, InMemoryCandleCache(), provider_name="TEST"),
        max_concurrency=2,
    )
    instruments = [
        instrument("RISING", "NSE_EQ|RISING"),
        instrument("FALLING", "NSE_EQ|FALLING"),
        instrument("BROKEN", "NSE_EQ|BROKEN"),
    ]
    conditions = [
        condition("price", ">", field="sma50"),
        condition("rsi14", ">", value=55),
    ]

    result = asyncio.run(
        engine.scan(
            instruments,
            conditions,
            from_date=date(2025, 1, 1),
            to_date=date(2025, 3, 31),
        )
    )

    assert result.total_instruments == 3
    assert result.evaluated == 2
    assert result.matched == 1
    assert result.matches[0].instrument.trading_symbol == "RISING"
    assert result.skipped_count == 1
    assert result.skip_reasons == {"market_data_error": 1}
    assert provider.peak_active == 2


def test_scanner_engine_records_unavailable_indicator_as_skip():
    short_history = make_history(100, 1, count=15)
    provider = UniverseHistoryProvider({"NSE_EQ|SHORT": short_history})
    engine = ScannerEngine(
        HistoricalDataService(provider, InMemoryCandleCache(), provider_name="TEST")
    )
    result = asyncio.run(
        engine.scan(
            [instrument("SHORT", "NSE_EQ|SHORT")],
            [condition("price", ">", field="sma200")],
            from_date=date(2025, 1, 1),
            to_date=date(2025, 2, 1),
        )
    )
    assert result.evaluated == 0
    assert result.skip_reasons == {"missing_indicator": 1}
