"""Concurrent scanner orchestration independent of execution and risk."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date

from ..market_data.base import MarketDataProviderError
from ..market_data.models import Instrument
from ..market_data.service import HistoricalDataService
from .conditions import (
    Condition,
    ConditionCheck,
    ConditionEvaluator,
    MissingIndicatorError,
)
from .indicators import IndicatorSnapshot, InsufficientHistoryError, build_indicator_snapshot
from .results import ScanPage, paginate_preset_result
from .scanners.base import ScannerDefinition


@dataclass(frozen=True, slots=True)
class ScanMatch:
    instrument: Instrument
    data_as_of: date
    indicators: IndicatorSnapshot
    checks: tuple[ConditionCheck, ...]


@dataclass(frozen=True, slots=True)
class ScanSkip:
    instrument_key: str
    trading_symbol: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    total_instruments: int
    evaluated: int
    matches: tuple[ScanMatch, ...]
    skipped: tuple[ScanSkip, ...]
    skip_reasons: dict[str, int]

    @property
    def matched(self) -> int:
        return len(self.matches)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ScannerEngine:
    """Fetch history, calculate indicators, and evaluate conditions per stock."""

    def __init__(
        self,
        historical_data: HistoricalDataService,
        *,
        max_concurrency: int = 8,
    ):
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self.historical_data = historical_data
        self.max_concurrency = max_concurrency

    async def scan(
        self,
        instruments: list[Instrument],
        conditions: tuple[Condition, ...] | list[Condition],
        *,
        from_date: date,
        to_date: date,
        refresh: bool = True,
    ) -> ScanResult:
        if from_date > to_date:
            raise ValueError("from_date must not be after to_date")
        evaluator = ConditionEvaluator(conditions)
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def evaluate_instrument(instrument: Instrument):
            async with semaphore:
                return await self._evaluate_instrument(
                    instrument,
                    evaluator,
                    from_date=from_date,
                    to_date=to_date,
                    refresh=refresh,
                )

        outcomes = await asyncio.gather(
            *(evaluate_instrument(instrument) for instrument in instruments)
        )
        matches = sorted(
            (outcome for outcome in outcomes if isinstance(outcome, ScanMatch)),
            key=lambda match: (match.instrument.trading_symbol, match.instrument.instrument_key),
        )
        skipped = sorted(
            (outcome for outcome in outcomes if isinstance(outcome, ScanSkip)),
            key=lambda skip: (skip.trading_symbol, skip.instrument_key),
        )
        evaluated = len(instruments) - len(skipped)
        return ScanResult(
            total_instruments=len(instruments),
            evaluated=evaluated,
            matches=tuple(matches),
            skipped=tuple(skipped),
            skip_reasons=dict(sorted(Counter(skip.reason for skip in skipped).items())),
        )

    async def scan_definition(
        self,
        instruments: list[Instrument],
        scanner: ScannerDefinition,
        *,
        from_date: date,
        to_date: date,
        refresh: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> ScanPage:
        """Run, rank, and paginate a validated built-in scanner."""

        result = await self.scan(
            instruments,
            scanner.conditions,
            from_date=from_date,
            to_date=to_date,
            refresh=refresh,
        )
        return paginate_preset_result(
            result,
            scanner,
            page=page,
            page_size=page_size,
        )

    async def _evaluate_instrument(
        self,
        instrument: Instrument,
        evaluator: ConditionEvaluator,
        *,
        from_date: date,
        to_date: date,
        refresh: bool,
    ) -> ScanMatch | ScanSkip | None:
        try:
            candles = await self.historical_data.get_daily_candles(
                instrument.instrument_key,
                from_date,
                to_date,
                refresh=refresh,
            )
            snapshot = build_indicator_snapshot(candles)
            evaluation = evaluator.evaluate(snapshot)
        except MarketDataProviderError as exc:
            return self._skip(instrument, "market_data_error", exc)
        except InsufficientHistoryError as exc:
            return self._skip(instrument, "insufficient_history", exc)
        except MissingIndicatorError as exc:
            return self._skip(instrument, "missing_indicator", exc)

        if not evaluation.matched:
            return None
        return ScanMatch(
            instrument=instrument,
            data_as_of=candles[-1].timestamp.date(),
            indicators=snapshot,
            checks=evaluation.checks,
        )

    @staticmethod
    def _skip(instrument: Instrument, reason: str, exc: Exception) -> ScanSkip:
        return ScanSkip(
            instrument_key=instrument.instrument_key,
            trading_symbol=instrument.trading_symbol,
            reason=reason,
            detail=str(exc),
        )
