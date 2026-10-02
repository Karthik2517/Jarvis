"""Volume breakout scanner definition."""

import math

from ..conditions import (
    ComparisonOperator,
    Condition,
    ConditionField,
    ConditionOperand,
    ConditionValidationError,
)
from .base import RankDirection, ScannerDefinition


def volume_breakout(multiplier: float = 2.0) -> ScannerDefinition:
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
        raise ConditionValidationError("Volume multiplier must be a number")
    multiplier = float(multiplier)
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ConditionValidationError("Volume multiplier must be finite and greater than zero")

    return ScannerDefinition(
        key="volume_breakout",
        name="Volume Breakout",
        description=(
            f"Volume is at least {multiplier:g} times the previous 20-session average."
        ),
        conditions=(
            Condition(
                left=ConditionField.AVG_VOLUME_20,
                operator=ComparisonOperator.GREATER_THAN,
                right=ConditionOperand.literal(0),
            ),
            Condition(
                left=ConditionField.VOLUME,
                operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                right=ConditionOperand.indicator(
                    ConditionField.AVG_VOLUME_20, multiplier=multiplier
                ),
            ),
        ),
        minimum_history=21,
        rank_field=ConditionField.VOLUME_RATIO,
        rank_direction=RankDirection.DESCENDING,
    )
