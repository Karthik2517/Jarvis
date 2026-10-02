"""Canonical market-data models shared by providers and scanners."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int = 0


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_key: str
    trading_symbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str
    isin: str | None = None
    security_type: str | None = None
