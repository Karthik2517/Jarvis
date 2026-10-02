"""Configurable Wilder RSI(14) scanner definition."""

import math

from ..conditions import (
    ComparisonOperator,
    Condition,
    ConditionField,
    ConditionOperand,
    ConditionValidationError,
)
from .base import RankDirection, ScannerDefinition

_SUPPORTED_RSI_OPERATORS = {
    ComparisonOperator.GREATER_THAN,
    ComparisonOperator.GREATER_THAN_OR_EQUAL,
    ComparisonOperator.LESS_THAN,
    ComparisonOperator.LESS_THAN_OR_EQUAL,
}


def rsi_scanner(
    threshold: float = 55.0,
    comparison: ComparisonOperator | str = ComparisonOperator.GREATER_THAN_OR_EQUAL,
) -> ScannerDefinition:
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ConditionValidationError("RSI threshold must be a number")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ConditionValidationError("RSI threshold must be between 0 and 100")
    try:
        comparison = ComparisonOperator(comparison)
    except ValueError as exc:
        raise ConditionValidationError(f"Unsupported RSI comparison: {comparison}") from exc
    if comparison not in _SUPPORTED_RSI_OPERATORS:
        raise ConditionValidationError("RSI scanner supports only >, >=, <, and <=")

    ascending = comparison in {
        ComparisonOperator.LESS_THAN,
        ComparisonOperator.LESS_THAN_OR_EQUAL,
    }
    return ScannerDefinition(
        key="rsi",
        name="RSI",
        description=f"Wilder RSI(14) {comparison.value} {threshold:g}.",
        conditions=(
            Condition(
                left=ConditionField.RSI14,
                operator=comparison,
                right=ConditionOperand.literal(threshold),
            ),
        ),
        minimum_history=15,
        rank_field=ConditionField.RSI14,
        rank_direction=(
            RankDirection.ASCENDING if ascending else RankDirection.DESCENDING
        ),
    )
