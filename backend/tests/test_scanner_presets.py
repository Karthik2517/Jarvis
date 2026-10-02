import pytest

from app.scanner.conditions import (
    ComparisonOperator,
    ConditionEvaluator,
    ConditionValidationError,
)
from app.scanner.indicators import IndicatorSnapshot
from app.scanner.scanners import (
    RankDirection,
    RankTransform,
    default_scanners,
    fifty_two_week_high_breakout,
    fifty_two_week_low,
    price_above_smas,
    rsi_scanner,
    volume_breakout,
)


def snapshot(**overrides) -> IndicatorSnapshot:
    values = {
        "price": 150.0,
        "volume": 2000,
        "sma20": 140.0,
        "sma50": 130.0,
        "sma200": 100.0,
        "avg_volume_20": 1000.0,
        "volume_ratio": 2.0,
        "rsi14": 55.0,
        "prior_52w_high": 149.0,
        "prior_52w_low": 90.0,
        "breakout_percent": 0.671,
        "breakdown_percent": -40.0,
    }
    values.update(overrides)
    return IndicatorSnapshot(**values)


def matches(scanner, data):
    return ConditionEvaluator(scanner.conditions).evaluate(data).matched


def test_default_registry_contains_exactly_the_five_v1_scanners():
    scanners = default_scanners()
    assert set(scanners) == {
        "52_week_high_breakout",
        "52_week_low",
        "volume_breakout",
        "price_above_sma_20_50_200",
        "rsi",
    }


def test_52_week_high_breakout_is_strict_and_ranked_by_breakout_percent():
    scanner = fifty_two_week_high_breakout()
    assert matches(scanner, snapshot(price=150, prior_52w_high=149)) is True
    assert matches(scanner, snapshot(price=150, prior_52w_high=150)) is False
    assert scanner.minimum_history == 253
    assert scanner.rank_value(snapshot()) == pytest.approx(0.671)


def test_52_week_low_is_strict_and_ranked_by_breakdown_percent():
    scanner = fifty_two_week_low()
    assert matches(scanner, snapshot(price=89, prior_52w_low=90)) is True
    assert matches(scanner, snapshot(price=90, prior_52w_low=90)) is False
    assert scanner.minimum_history == 253
    assert scanner.rank_direction is RankDirection.DESCENDING


def test_volume_breakout_matches_exact_default_boundary_and_is_configurable():
    scanner = volume_breakout()
    assert matches(scanner, snapshot(volume=2000, avg_volume_20=1000)) is True
    assert matches(scanner, snapshot(volume=1999, avg_volume_20=1000)) is False
    assert matches(scanner, snapshot(volume=2000, avg_volume_20=0)) is False
    assert scanner.minimum_history == 21

    stricter = volume_breakout(3)
    assert matches(stricter, snapshot(volume=2999, avg_volume_20=1000)) is False
    assert matches(stricter, snapshot(volume=3000, avg_volume_20=1000)) is True
    with pytest.raises(ConditionValidationError, match="greater than zero"):
        volume_breakout(0)


def test_trend_scanner_requires_price_above_every_selected_sma():
    scanner = price_above_smas()
    assert matches(scanner, snapshot()) is True
    assert matches(scanner, snapshot(sma200=150)) is False
    assert scanner.minimum_history == 200
    assert len(scanner.conditions) == 3
    assert scanner.rank_transform is RankTransform.PERCENT_ABOVE
    assert scanner.rank_value(snapshot()) == pytest.approx(50.0)

    short = price_above_smas((20, 50))
    assert short.minimum_history == 50
    assert len(short.conditions) == 2
    with pytest.raises(ConditionValidationError, match="Unsupported SMA"):
        price_above_smas((10,))


def test_rsi_scanner_default_boundary_and_oversold_mode():
    bullish = rsi_scanner()
    assert matches(bullish, snapshot(rsi14=55)) is True
    assert matches(bullish, snapshot(rsi14=54.99)) is False
    assert bullish.rank_direction is RankDirection.DESCENDING

    oversold = rsi_scanner(30, ComparisonOperator.LESS_THAN_OR_EQUAL)
    assert matches(oversold, snapshot(rsi14=30)) is True
    assert matches(oversold, snapshot(rsi14=30.01)) is False
    assert oversold.rank_direction is RankDirection.ASCENDING

    with pytest.raises(ConditionValidationError, match="between 0 and 100"):
        rsi_scanner(101)
    with pytest.raises(ConditionValidationError, match="only"):
        rsi_scanner(50, ComparisonOperator.EQUAL)
