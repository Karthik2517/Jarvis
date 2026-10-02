"""Pure technical-indicator calculations for completed daily candles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..market_data.models import Candle


class InsufficientHistoryError(ValueError):
    """Raised when an indicator does not have its required lookback."""


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    price: float
    volume: int
    sma20: float | None
    sma50: float | None
    sma200: float | None
    avg_volume_20: float | None
    volume_ratio: float | None
    rsi14: float | None
    prior_52w_high: float | None
    prior_52w_low: float | None
    breakout_percent: float | None
    breakdown_percent: float | None


def _require_history(candles: Sequence[Candle], required: int, indicator: str) -> None:
    if len(candles) < required:
        raise InsufficientHistoryError(
            f"{indicator} requires {required} candles; received {len(candles)}"
        )


def simple_moving_average(candles: Sequence[Candle], period: int) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    _require_history(candles, period, f"SMA({period})")
    return sum(candle.close for candle in candles[-period:]) / period


def previous_average_volume(candles: Sequence[Candle], period: int = 20) -> float:
    """Average prior volume, intentionally excluding the evaluation candle."""

    if period <= 0:
        raise ValueError("period must be positive")
    _require_history(candles, period + 1, f"average volume ({period})")
    return sum(candle.volume for candle in candles[-(period + 1) : -1]) / period


def volume_ratio(candles: Sequence[Candle], period: int = 20) -> float:
    average = previous_average_volume(candles, period)
    if average <= 0:
        raise ValueError("average volume must be greater than zero")
    return candles[-1].volume / average


def wilder_rsi(candles: Sequence[Candle], period: int = 14) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    _require_history(candles, period + 1, f"RSI({period})")

    closes = [candle.close for candle in candles]
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period

    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def prior_52_week_range(
    candles: Sequence[Candle], sessions: int = 252
) -> tuple[float, float]:
    """Return prior high/low, excluding the latest evaluation candle."""

    if sessions <= 0:
        raise ValueError("sessions must be positive")
    _require_history(candles, sessions + 1, "prior 52-week range")
    prior = candles[-(sessions + 1) : -1]
    return max(candle.high for candle in prior), min(candle.low for candle in prior)


def build_indicator_snapshot(candles: Sequence[Candle]) -> IndicatorSnapshot:
    if not candles:
        raise InsufficientHistoryError("Indicator snapshot requires at least one candle")

    price = candles[-1].close
    average_volume = (
        previous_average_volume(candles, 20) if len(candles) >= 21 else None
    )
    ratio = (
        candles[-1].volume / average_volume
        if average_volume is not None and average_volume > 0
        else None
    )
    prior_high = prior_low = None
    if len(candles) >= 253:
        prior_high, prior_low = prior_52_week_range(candles)

    return IndicatorSnapshot(
        price=price,
        volume=candles[-1].volume,
        sma20=simple_moving_average(candles, 20) if len(candles) >= 20 else None,
        sma50=simple_moving_average(candles, 50) if len(candles) >= 50 else None,
        sma200=simple_moving_average(candles, 200) if len(candles) >= 200 else None,
        avg_volume_20=average_volume,
        volume_ratio=ratio,
        rsi14=wilder_rsi(candles, 14) if len(candles) >= 15 else None,
        prior_52w_high=prior_high,
        prior_52w_low=prior_low,
        breakout_percent=(
            ((price / prior_high) - 1) * 100 if prior_high is not None else None
        ),
        breakdown_percent=(
            ((prior_low / price) - 1) * 100 if prior_low is not None else None
        ),
    )
