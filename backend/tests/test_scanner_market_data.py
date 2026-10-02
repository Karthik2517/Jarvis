import asyncio
import gzip
import json
from datetime import date

import httpx
import pytest

from app.market_data import (
    MarketDataProviderError,
    UpstoxHistoricalDataProvider,
    UpstoxInstrumentMasterProvider,
)
from app.scanner.universe import NSEEquityUniverse


def equity_record(symbol: str, key: str, **overrides):
    record = {
        "segment": "NSE_EQ",
        "name": f"{symbol} LIMITED",
        "exchange": "NSE",
        "isin": key.split("|", 1)[-1],
        "instrument_type": "EQ",
        "instrument_key": key,
        "trading_symbol": symbol,
        "security_type": "NORMAL",
    }
    record.update(overrides)
    return record


def test_nse_equity_universe_filters_and_sorts_provider_records():
    reliance = equity_record("RELIANCE", "NSE_EQ|INE002A01018")
    records = [
        reliance,
        equity_record("TCS", "NSE_EQ|INE467B01029"),
        equity_record("SMECO", "NSE_EQ|INESME000001", security_type="SME"),
        equity_record("NIFTYBEES", "NSE_EQ|INF204KB14I2", instrument_type="ETF"),
        equity_record("BSEONLY", "BSE_EQ|INE000000001", exchange="BSE", segment="BSE_EQ"),
        {**reliance, "name": "DUPLICATE RECORD"},
        {"segment": "NSE_EQ", "instrument_type": "EQ", "security_type": "NORMAL"},
    ]

    universe = NSEEquityUniverse().build(records, {"NSE_EQ|INE467B01029"})

    assert [item.trading_symbol for item in universe] == ["RELIANCE"]
    assert universe[0].instrument_key == "NSE_EQ|INE002A01018"
    assert universe[0].name == "DUPLICATE RECORD"


def test_upstox_instrument_provider_reads_gzip_and_suspended_files():
    nse_payload = [equity_record("RELIANCE", "NSE_EQ|INE002A01018")]
    suspended_payload = {"data": [{"instrument_key": "NSE_EQ|INESUSPENDED1"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = suspended_payload if "suspended" in request.url.path else nse_payload
        return httpx.Response(200, content=gzip.compress(json.dumps(payload).encode()))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = UpstoxInstrumentMasterProvider(client)
            return (
                await provider.get_nse_instruments(),
                await provider.get_suspended_instrument_keys(),
            )

    instruments, suspended = asyncio.run(run())
    assert instruments == nse_payload
    assert suspended == {"NSE_EQ|INESUSPENDED1"}


def test_upstox_daily_history_encodes_key_and_orders_candles():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert b"NSE_EQ%7CINE002A01018" in request.url.raw_path
        assert request.url.path.endswith("/days/1/2026-09-30/2026-09-01")
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "candles": [
                        ["2026-09-02T00:00:00+05:30", 101, 105, 100, 104, 1200, 0],
                        ["2026-09-01T00:00:00+05:30", 100, 103, 99, 101, 1000, 0],
                    ]
                },
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = UpstoxHistoricalDataProvider(
                "test-token", "https://api.upstox.test", client
            )
            return await provider.get_daily_candles(
                "NSE_EQ|INE002A01018", date(2026, 9, 1), date(2026, 9, 30)
            )

    candles = asyncio.run(run())
    assert [candle.close for candle in candles] == [101.0, 104.0]
    assert candles[0].timestamp.utcoffset() is not None
    assert candles[1].volume == 1200


def test_upstox_daily_history_validates_requests_and_payloads():
    provider = UpstoxHistoricalDataProvider("")
    with pytest.raises(MarketDataProviderError, match="UPSTOX_ACCESS_TOKEN"):
        asyncio.run(
            provider.get_daily_candles(
                "NSE_EQ|INE002A01018", date(2026, 9, 1), date(2026, 9, 30)
            )
        )

    provider = UpstoxHistoricalDataProvider("token")
    with pytest.raises(ValueError, match="from_date"):
        asyncio.run(
            provider.get_daily_candles(
                "NSE_EQ|INE002A01018", date(2026, 9, 30), date(2026, 9, 1)
            )
        )
