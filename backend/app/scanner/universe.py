"""Build the eligible NSE cash-equity universe for scanner runs."""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from ..market_data.base import InstrumentMasterProvider
from ..market_data.models import Instrument


# Official NIFTY 50 constituents published by NSE Indices. Keep this boundary
# separate from scanner evaluation so the universe can later grow to NIFTY 100,
# NIFTY 200, or the full eligible NSE equity market without changing the engine.
NIFTY_50_SYMBOLS = frozenset(
    {
        "ADANIENT",
        "ADANIPORTS",
        "APOLLOHOSP",
        "ASIANPAINT",
        "AXISBANK",
        "BAJAJ-AUTO",
        "BAJAJFINSV",
        "BAJFINANCE",
        "BEL",
        "BHARTIARTL",
        "BSE",
        "CIPLA",
        "COALINDIA",
        "DRREDDY",
        "EICHERMOT",
        "ETERNAL",
        "GRASIM",
        "HCLTECH",
        "HDFCBANK",
        "HDFCLIFE",
        "HINDALCO",
        "HINDUNILVR",
        "ICICIBANK",
        "INDIGO",
        "INFY",
        "ITC",
        "JIOFIN",
        "JSWSTEEL",
        "KOTAKBANK",
        "LT",
        "M&M",
        "MARUTI",
        "MAXHEALTH",
        "NESTLEIND",
        "NTPC",
        "ONGC",
        "POWERGRID",
        "RELIANCE",
        "SBILIFE",
        "SBIN",
        "SHRIRAMFIN",
        "SUNPHARMA",
        "TATACONSUM",
        "TATASTEEL",
        "TCS",
        "TECHM",
        "TITAN",
        "TMPV",
        "TRENT",
        "ULTRACEMCO",
    }
)


class NSEEquityUniverse:
    """Filter provider records using the Scanner Rules v1 eligibility contract."""

    ELIGIBLE_SEGMENT = "NSE_EQ"
    ELIGIBLE_INSTRUMENT_TYPE = "EQ"
    ELIGIBLE_SECURITY_TYPE = "NORMAL"

    def build(
        self,
        records: Iterable[dict[str, Any]],
        suspended_instrument_keys: Iterable[str] = (),
    ) -> list[Instrument]:
        suspended = {key.strip() for key in suspended_instrument_keys if key.strip()}
        instruments: dict[str, Instrument] = {}

        for record in records:
            if not self._is_eligible(record, suspended):
                continue
            key = str(record["instrument_key"]).strip()
            instruments[key] = Instrument(
                instrument_key=key,
                trading_symbol=str(record["trading_symbol"]).strip().upper(),
                name=str(record.get("name") or record.get("short_name") or "").strip(),
                exchange="NSE",
                segment=self.ELIGIBLE_SEGMENT,
                instrument_type=self.ELIGIBLE_INSTRUMENT_TYPE,
                isin=str(record["isin"]).strip() if record.get("isin") else None,
                security_type=self.ELIGIBLE_SECURITY_TYPE,
            )

        return sorted(
            instruments.values(),
            key=lambda instrument: (instrument.trading_symbol, instrument.instrument_key),
        )

    async def load(self, provider: InstrumentMasterProvider) -> list[Instrument]:
        records, suspended = await asyncio.gather(
            provider.get_nse_instruments(),
            provider.get_suspended_instrument_keys(),
        )
        return self.build(records, suspended)

    def _is_eligible(self, record: dict[str, Any], suspended: set[str]) -> bool:
        key = str(record.get("instrument_key") or "").strip()
        symbol = str(record.get("trading_symbol") or "").strip()
        return bool(
            key
            and symbol
            and key not in suspended
            and key.startswith(f"{self.ELIGIBLE_SEGMENT}|")
            and str(record.get("exchange") or "").upper() == "NSE"
            and str(record.get("segment") or "").upper() == self.ELIGIBLE_SEGMENT
            and str(record.get("instrument_type") or "").upper()
            == self.ELIGIBLE_INSTRUMENT_TYPE
            and str(record.get("security_type") or "").upper()
            == self.ELIGIBLE_SECURITY_TYPE
        )


class Nifty50Universe(NSEEquityUniverse):
    """Restrict the eligible NSE equity master to current NIFTY 50 stocks."""

    def build(
        self,
        records: Iterable[dict[str, Any]],
        suspended_instrument_keys: Iterable[str] = (),
    ) -> list[Instrument]:
        eligible = super().build(records, suspended_instrument_keys)
        return [
            instrument
            for instrument in eligible
            if instrument.trading_symbol in NIFTY_50_SYMBOLS
        ]
