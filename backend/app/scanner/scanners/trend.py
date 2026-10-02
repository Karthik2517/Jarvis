"""Price-above-SMA trend scanner definition."""

from collections.abc import Iterable

from ..conditions import (
    ComparisonOperator,
    Condition,
    ConditionField,
    ConditionOperand,
    ConditionValidationError,
)
from .base import RankDirection, RankTransform, ScannerDefinition

_SMA_FIELDS = {
    20: ConditionField.SMA20,
    50: ConditionField.SMA50,
    200: ConditionField.SMA200,
}


def price_above_smas(periods: Iterable[int] = (20, 50, 200)) -> ScannerDefinition:
    selected = tuple(dict.fromkeys(periods))
    if not selected:
        raise ConditionValidationError("At least one SMA period is required")
    unsupported = [period for period in selected if period not in _SMA_FIELDS]
    if unsupported:
        raise ConditionValidationError(
            f"Unsupported SMA periods: {', '.join(map(str, unsupported))}"
        )
    conditions = tuple(
        Condition(
            left=ConditionField.PRICE,
            operator=ComparisonOperator.GREATER_THAN,
            right=ConditionOperand.indicator(_SMA_FIELDS[period]),
        )
        for period in selected
    )
    period_label = "/".join(map(str, selected))
    longest_period = max(selected)
    return ScannerDefinition(
        key=(
            "price_above_sma_20_50_200"
            if selected == (20, 50, 200)
            else f"price_above_sma_{'_'.join(map(str, selected))}"
        ),
        name=f"Price Above SMA {period_label}",
        description=f"Closing price is strictly above every selected SMA: {period_label}.",
        conditions=conditions,
        minimum_history=longest_period,
        rank_field=_SMA_FIELDS[longest_period],
        rank_direction=RankDirection.DESCENDING,
        rank_transform=RankTransform.PERCENT_ABOVE,
    )
