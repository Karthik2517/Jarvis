"""Stable ranking and pagination for scanner results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .conditions import ConditionField
from .scanners.base import RankDirection, RankTransform, ScannerDefinition, rank_value

if TYPE_CHECKING:
    from .scanner_engine import ScanMatch, ScanResult


class PaginationError(ValueError):
    """Raised when page settings do not describe a valid result page."""


@dataclass(frozen=True, slots=True)
class RankedScanMatch:
    rank: int
    rank_value: float
    match: ScanMatch


@dataclass(frozen=True, slots=True)
class ScanPage:
    page: int
    page_size: int
    total_pages: int
    total_matches: int
    total_instruments: int
    evaluated: int
    skipped_count: int
    skip_reasons: dict[str, int]
    items: tuple[RankedScanMatch, ...]

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def rank_and_paginate(
    result: ScanResult,
    *,
    rank_field: ConditionField,
    rank_direction: RankDirection = RankDirection.DESCENDING,
    rank_transform: RankTransform = RankTransform.RAW,
    page: int = 1,
    page_size: int = 50,
) -> ScanPage:
    """Rank all matches deterministically, then return one bounded page."""

    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise PaginationError("page must be a positive integer")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= 100
    ):
        raise PaginationError("page_size must be an integer between 1 and 100")
    try:
        direction = RankDirection(rank_direction)
    except ValueError as exc:
        raise PaginationError(f"Unsupported rank direction: {rank_direction}") from exc

    valued = [
        (
            rank_value(
                match.indicators,
                field=rank_field,
                transform=rank_transform,
            ),
            match,
        )
        for match in result.matches
    ]
    # Symbol is always the deterministic tie-breaker. Two stable sorts preserve
    # alphabetical order when the primary rank values are equal.
    valued.sort(
        key=lambda item: (
            item[1].instrument.trading_symbol,
            item[1].instrument.instrument_key,
        )
    )
    valued.sort(
        key=lambda item: item[0],
        reverse=direction is RankDirection.DESCENDING,
    )

    total_matches = len(valued)
    total_pages = max(1, math.ceil(total_matches / page_size))
    if page > total_pages:
        raise PaginationError(
            f"page {page} is out of range; the result has {total_pages} page(s)"
        )
    start = (page - 1) * page_size
    page_values = valued[start : start + page_size]
    items = tuple(
        RankedScanMatch(rank=start + offset + 1, rank_value=value, match=match)
        for offset, (value, match) in enumerate(page_values)
    )
    return ScanPage(
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_matches=total_matches,
        total_instruments=result.total_instruments,
        evaluated=result.evaluated,
        skipped_count=result.skipped_count,
        skip_reasons=dict(result.skip_reasons),
        items=items,
    )


def paginate_preset_result(
    result: ScanResult,
    scanner: ScannerDefinition,
    *,
    page: int = 1,
    page_size: int = 50,
) -> ScanPage:
    return rank_and_paginate(
        result,
        rank_field=scanner.rank_field,
        rank_direction=scanner.rank_direction,
        rank_transform=scanner.rank_transform,
        page=page,
        page_size=page_size,
    )
