"""Shared metadata contract for built-in scanner definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ..conditions import Condition, ConditionField, ConditionValidationError
from ..indicators import IndicatorSnapshot


class RankDirection(str, Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"


class RankTransform(str, Enum):
    RAW = "raw"
    PERCENT_ABOVE = "percent_above"


@dataclass(frozen=True, slots=True)
class ScannerDefinition:
    """A named condition set plus metadata needed by API and ranking layers."""

    key: str
    name: str
    description: str
    conditions: tuple[Condition, ...]
    minimum_history: int
    rank_field: ConditionField
    rank_direction: RankDirection
    rank_transform: RankTransform = RankTransform.RAW

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.key):
            raise ConditionValidationError(
                "Scanner key may contain only lowercase letters, numbers, and underscores"
            )
        if not self.name.strip() or not self.description.strip():
            raise ConditionValidationError("Scanner name and description are required")
        if not self.conditions:
            raise ConditionValidationError("A scanner requires at least one condition")
        if not all(isinstance(condition, Condition) for condition in self.conditions):
            raise ConditionValidationError("Scanner conditions must be Condition instances")
        if self.minimum_history <= 0:
            raise ConditionValidationError("minimum_history must be positive")
        try:
            object.__setattr__(self, "rank_field", ConditionField(self.rank_field))
            object.__setattr__(self, "rank_direction", RankDirection(self.rank_direction))
            object.__setattr__(self, "rank_transform", RankTransform(self.rank_transform))
        except ValueError as exc:
            raise ConditionValidationError("Invalid scanner ranking metadata") from exc

    def rank_value(self, snapshot: IndicatorSnapshot) -> float:
        return rank_value(
            snapshot,
            field=self.rank_field,
            transform=self.rank_transform,
        )


def rank_value(
    snapshot: IndicatorSnapshot,
    *,
    field: ConditionField,
    transform: RankTransform = RankTransform.RAW,
) -> float:
    """Resolve a validated rank value for preset or custom scan results."""

    try:
        field = ConditionField(field)
        transform = RankTransform(transform)
    except ValueError as exc:
        raise ConditionValidationError("Invalid ranking configuration") from exc
    value = getattr(snapshot, field.value)
    if value is None:
        raise ValueError(f"{field.value} is unavailable for ranking")
    value = float(value)
    if transform is RankTransform.PERCENT_ABOVE:
        if value == 0:
            raise ValueError(f"{field.value} cannot be zero for ranking")
        return ((snapshot.price / value) - 1) * 100
    return value
