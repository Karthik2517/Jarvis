import asyncio

import httpx

from app.instruments import find_instrument
from app.services.market_data import UpstoxMarketData


def test_upstox_search_combines_instruments_and_ltp():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path == "/v2/instruments/search":
            assert request.url.params["exchanges"] == "NSE"
            assert request.url.params["segments"] == "EQ"
            return httpx.Response(200, json={
                "status": "success",
                "data": [{
                    "name": "RELIANCE INDUSTRIES LTD",
                    "exchange": "NSE",
                    "instrument_key": "NSE_EQ|INE002A01018",
                    "trading_symbol": "RELIANCE",
                }],
            })
        if request.url.path == "/v3/market-quote/ltp":
            return httpx.Response(200, json={
                "status": "success",
                "data": {"NSE_EQ:RELIANCE": {
                    "instrument_token": "NSE_EQ|INE002A01018",
                    "last_price": 3010.5,
                    "cp": 2995.0,
                }},
            })
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = UpstoxMarketData("test-token", "https://api.upstox.test", client)
            return await provider.search_equities("Reliance")

    results = asyncio.run(run())
    assert results[0]["symbol"] == "RELIANCE"
    assert results[0]["price"] == 3010.5
    assert results[0]["source"] == "UPSTOX"
    assert results[0]["change_percent"] == 0.52
    assert find_instrument("RELIANCE")["price"] == 3010.5

