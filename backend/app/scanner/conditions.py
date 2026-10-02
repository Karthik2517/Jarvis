"""Safe, structured custom-condition models and evaluation."""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .indicators import IndicatorSnapshot


class ConditionValidationError(ValueError):
    """Raised when a condition is unsupported or structurally invalid."""


class MissingIndicatorError(ValueError):
    """Raised when a condition needs an indicator that could not be calculated."""


class ConditionField(str, Enum):
    PRICE = "price"
    VOLUME = "volume"
    AVG_VOLUME_20 = "avg_volume_20"
    VOLUME_RATIO = "volume_ratio"
    SMA20 = "sma20"
    SMA50 = "sma50"
    SMA200 = "sma200"
    RSI14 = "rsi14"
    PRIOR_52W_HIGH = "prior_52w_high"
    PRIOR_52W_LOW = "prior_52w_low"
    BREAKOUT_PERCENT = "breakout_percent"
    BREAKDOWN_PERCENT = "breakdown_percent"


class ComparisonOperator(str, Enum):
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "=="


_COMPARATORS = {
    ComparisonOperator.GREATER_THAN: operator.gt,
    ComparisonOperator.GREATER_THAN_OR_EQUAL: operator.ge,
    ComparisonOperator.LESS_THAN: operator.lt,
    ComparisonOperator.LESS_THAN_OR_EQUAL: operator.le,
    ComparisonOperator.EQUAL: operator.eq,
}


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConditionValidationError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ConditionValidationError(f"{name} must be finite")
    return number


@dataclass(frozen=True, slots=True)
class ConditionOperand:
    """A literal number or a permitted field multiplied by a finite number."""

    value: float | None = None
    field: ConditionField | None = None
    multiplier: float = 1.0

    def __post_init__(self) -> None:
        if (self.value is None) == (self.field is None):
            raise ConditionValidationError(
                "An operand must contain exactly one of value or field"
            )
        multiplier = _finite_number(self.multiplier, "multiplier")
        if self.field is None and multiplier != 1.0:
            raise ConditionValidationError("A literal operand cannot have a multiplier")
        if self.value is not None:
            object.__setattr__(self, "value", _finite_number(self.value, "value"))
        object.__setattr__(self, "multiplier", multiplier)

    @classmethod
    def literal(cls, value: float) -> "ConditionOperand":
        return cls(value=value)

    @classmethod
    def indicator(
        cls, field: ConditionField | str, multiplier: float = 1.0
    ) -> "ConditionOperand":
        try:
            resolved_field = ConditionField(field)
        except ValueError as exc:
            raise ConditionValidationError(f"Unsupported condition field: {field}") from exc
        return cls(field=resolved_field, multiplier=multiplier)


@dataclass(frozen=True, slots=True)
class Condition:
    left: ConditionField
    operator: ComparisonOperator
    right: ConditionOperand

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "left", ConditionField(self.left))
        except ValueError as exc:
            raise ConditionValidationError(f"Unsupported condition field: {self.left}") from exc
        try:
            object.__setattr__(self, "operator", ComparisonOperator(self.operator))
        except ValueError as exc:
            raise ConditionValidationError(
                f"Unsupported comparison operator: {self.operator}"
            ) from exc
        if not isinstance(self.right, ConditionOperand):
            raise ConditionValidationError("right must be a ConditionOperand")


@dataclass(frozen=True, slots=True)
class ConditionCheck:
    condition: Condition
    left_value: float
    right_value: float
    matched: bool


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    matched: bool
    checks: tuple[ConditionCheck, ...]


class ConditionEvaluator:
    """Evaluate validated conditions with AND semantics."""

    def __init__(self, conditions: tuple[Condition, ...] | list[Condition]):
        if not conditions:
            raise ConditionValidationError("At least one condition is required")
        if not all(isinstance(condition, Condition) for condition in conditions):
            raise ConditionValidationError("All conditions must be Condition instances")
        self.conditions = tuple(conditions)

    def evaluate(self, snapshot: IndicatorSnapshot) -> ConditionEvaluation:
        values = self._snapshot_values(snapshot)
        checks: list[ConditionCheck] = []
        for condition in self.conditions:
            left_value = self._required_value(values, condition.left)
            if condition.right.field is not None:
                right_value = (
                    self._required_value(values, condition.right.field)
                    * condition.right.multiplier
                )
            else:
                right_value = float(condition.right.value)
            matched = bool(_COMPARATORS[condition.operator](left_value, right_value))
            checks.append(
                ConditionCheck(
                    condition=condition,
                    left_value=left_value,
                    right_value=right_value,
                    matched=matched,
                )
            )
        return ConditionEvaluation(
            matched=all(check.matched for check in checks), checks=tuple(checks)
        )

    @staticmethod
    def _snapshot_values(snapshot: IndicatorSnapshot) -> Mapping[ConditionField, float | None]:
        return {
            field: float(getattr(snapshot, field.value))
            if getattr(snapshot, field.value) is not None
            else None
            for field in ConditionField
        }

    @staticmethod
    def _required_value(
        values: Mapping[ConditionField, float | None], field: ConditionField
    ) -> float:
        value = values[field]
        if value is None:
            raise MissingIndicatorError(f"{field.value} is unavailable")
        if not math.isfinite(value):
            raise MissingIndicatorError(f"{field.value} is not finite")
        return value
