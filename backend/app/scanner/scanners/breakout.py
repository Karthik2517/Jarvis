"""52-week high-breakout and low-breakdown scanner definitions."""

from ..conditions import ComparisonOperator, Condition, ConditionField, ConditionOperand
from .base import RankDirection, ScannerDefinition


def fifty_two_week_high_breakout() -> ScannerDefinition:
    return ScannerDefinition(
        key="52_week_high_breakout",
        name="52-Week High Breakout",
        description="Closing price is above the highest high of the prior 252 sessions.",
        conditions=(
            Condition(
                left=ConditionField.PRICE,
                operator=ComparisonOperator.GREATER_THAN,
                right=ConditionOperand.indicator(ConditionField.PRIOR_52W_HIGH),
            ),
        ),
        minimum_history=253,
        rank_field=ConditionField.BREAKOUT_PERCENT,
        rank_direction=RankDirection.DESCENDING,
    )


def fifty_two_week_low() -> ScannerDefinition:
    return ScannerDefinition(
        key="52_week_low",
        name="52-Week Low",
        description="Closing price is below the lowest low of the prior 252 sessions.",
        conditions=(
            Condition(
                left=ConditionField.PRICE,
                operator=ComparisonOperator.LESS_THAN,
                right=ConditionOperand.indicator(ConditionField.PRIOR_52W_LOW),
            ),
        ),
        minimum_history=253,
        rank_field=ConditionField.BREAKDOWN_PERCENT,
        rank_direction=RankDirection.DESCENDING,
    )
