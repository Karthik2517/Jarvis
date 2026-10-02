"""Upstox market-data adapters for scanner inputs.

These adapters only read instrument and historical data. They do not share the
order-execution adapter and cannot place an order.
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from .base import HistoricalDataProvider, InstrumentMasterProvider, MarketDataProviderError
from .models import Candle

UPSTOX_NSE_INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)
UPSTOX_SUSPENDED_INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/"
    "suspended-instrument.json.gz"
)
INSTRUMENT_MASTER_CACHE_TTL_SECONDS = 6 * 60 * 60
_instrument_master_cache: dict[str, tuple[float, Any]] = {}


def _json_from_response(response: httpx.Response) -> Any:
    """Read plain JSON or a gzip payload whose server omits content encoding."""

    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            return json.loads(gzip.decompress(response.content))
        except (gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MarketDataProviderError("Upstox returned an invalid instrument file") from exc


def _extract_instrument_keys(payload: Any) -> set[str]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("data", payload.get("instruments", []))
    else:
        records = []
    if not isinstance(records, list):
        return set()
    return {
        str(record["instrument_key"])
        for record in records
        if isinstance(record, dict) and record.get("instrument_key")
    }


def _extract_suspended_nse_equity_keys(payload: Any) -> set[str]:
    """Return only suspended NSE instruments from the ordinary EQ series.

    Upstox's suspended file contains records from several NSE series (BE, BL,
    RL, and others). Those records can share an ISIN-based instrument key with
    an active EQ-series security. Treating every key in that file as a suspended
    ordinary equity therefore removes valid stocks from the scanner universe.
    """

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("data", payload.get("instruments", []))
    else:
        records = []
    if not isinstance(records, list):
        return set()
    return {
        str(record["instrument_key"])
        for record in records
        if (
            isinstance(record, dict)
            and record.get("instrument_key")
            and str(record.get("segment") or "").upper() == "NSE_EQ"
            and str(record.get("instrument_type") or "").upper() == "EQ"
        )
    }


class UpstoxInstrumentMasterProvider(InstrumentMasterProvider):
    """Download Upstox's daily NSE and suspended-instrument master files."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        nse_url: str = UPSTOX_NSE_INSTRUMENTS_URL,
        suspended_url: str = UPSTOX_SUSPENDED_INSTRUMENTS_URL,
    ):
        self.client = client
        self.nse_url = nse_url
        self.suspended_url = suspended_url

    async def _get_json(self, url: str) -> Any:
        cached = _instrument_master_cache.get(url)
        if cached and time.monotonic() - cached[0] < INSTRUMENT_MASTER_CACHE_TTL_SECONDS:
            return cached[1]
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        try:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = _json_from_response(response)
            _instrument_master_cache[url] = (time.monotonic(), payload)
            return payload
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Could not download Upstox instruments: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def get_nse_instruments(self) -> list[dict[str, Any]]:
        payload = await self._get_json(self.nse_url)
        if not isinstance(payload, list):
            raise MarketDataProviderError("Upstox NSE instrument file is not a JSON list")
        return [record for record in payload if isinstance(record, dict)]

    async def get_suspended_instrument_keys(self) -> set[str]:
        return _extract_suspended_nse_equity_keys(
            await self._get_json(self.suspended_url)
        )


class UpstoxHistoricalDataProvider(HistoricalDataProvider):
    """Read daily candles through the Upstox Historical Candle Data V3 API."""

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.upstox.com",
        client: httpx.AsyncClient | None = None,
    ):
        self.access_token = access_token.strip()
        self.base_url = base_url.rstrip("/")
        self.client = client

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    async def get_daily_candles(
        self,
        instrument_key: str,
        from_date: date,
        to_date: date,
    ) -> list[Candle]:
        if not self.access_token:
            raise MarketDataProviderError("Upstox market-data token is not configured")
        if not instrument_key.strip():
            raise ValueError("instrument_key is required")
        if from_date > to_date:
            raise ValueError("from_date must not be after to_date")

        encoded_key = quote(instrument_key.strip(), safe="")
        url = (
            f"{self.base_url}/v3/historical-candle/{encoded_key}/days/1/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise MarketDataProviderError(f"Could not fetch Upstox daily candles: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            raw_candles = payload["data"]["candles"]
        except (KeyError, TypeError) as exc:
            raise MarketDataProviderError("Upstox candle response is missing data.candles") from exc
        if not isinstance(raw_candles, list):
            raise MarketDataProviderError("Upstox data.candles is not a list")

        candles: list[Candle] = []
        for row in raw_candles:
            try:
                if not isinstance(row, list) or len(row) < 6:
                    raise ValueError("a candle must contain at least six values")
                timestamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("candle timestamp must include a timezone")
                candles.append(
                    Candle(
                        timestamp=timestamp,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=int(row[5]),
                        open_interest=int(row[6]) if len(row) > 6 and row[6] is not None else 0,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise MarketDataProviderError("Upstox returned a malformed candle") from exc

        return sorted(candles, key=lambda candle: candle.timestamp)
