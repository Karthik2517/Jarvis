"""Interfaces that keep scanner data acquisition independent of any broker."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from .models import Candle


class MarketDataProviderError(RuntimeError):
    """Raised when a provider response cannot supply valid market data."""


class HistoricalDataProvider(ABC):
    """Provider contract for completed or historical daily OHLCV candles."""

    @abstractmethod
    async def get_daily_candles(
        self,
        instrument_key: str,
        from_date: date,
        to_date: date,
    ) -> list[Candle]:
        """Return daily candles ordered from oldest to newest."""


class InstrumentMasterProvider(ABC):
    """Provider contract for instrument-master and suspension records."""

    @abstractmethod
    async def get_nse_instruments(self) -> list[dict[str, Any]]:
        """Return raw NSE instrument records from the provider."""

    @abstractmethod
    async def get_suspended_instrument_keys(self) -> set[str]:
        """Return instrument keys that must be excluded from scanning."""
