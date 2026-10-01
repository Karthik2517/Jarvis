import logging

import httpx

from ..config import get_settings
from ..instruments import register_instruments, search_local_instruments

logger = logging.getLogger(__name__)


class UpstoxMarketData:
    def __init__(self, access_token: str, base_url: str, client: httpx.AsyncClient | None = None):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.client = client

    @property
    def headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}"}

    async def search_equities(self, query: str, limit: int = 10) -> list[dict]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=6.0)
        try:
            search_response = await client.get(
                f"{self.base_url}/v2/instruments/search",
                headers=self.headers,
                params={
                    "query": query,
                    "exchanges": "NSE",
                    "segments": "EQ",
                    "page_number": 1,
                    "records": min(limit, 30),
                },
            )
            search_response.raise_for_status()
            records = search_response.json().get("data", [])
            keys = [item.get("instrument_key") for item in records if item.get("instrument_key")]
            quotes: dict[str, dict] = {}
            if keys:
                quote_response = await client.get(
                    f"{self.base_url}/v3/market-quote/ltp",
                    headers=self.headers,
                    params={"instrument_key": ",".join(keys)},
                )
                quote_response.raise_for_status()
                for quote in quote_response.json().get("data", {}).values():
                    if quote.get("instrument_token"):
                        quotes[quote["instrument_token"]] = quote

            results = []
            for item in records:
                key = item.get("instrument_key")
                quote = quotes.get(key, {})
                last_price = float(quote.get("last_price") or 0)
                previous_close = float(quote.get("cp") or last_price)
                change_percent = (
                    ((last_price - previous_close) / previous_close) * 100 if previous_close else 0.0
                )
                results.append({
                    "symbol": item.get("trading_symbol") or item.get("short_name"),
                    "name": item.get("name") or item.get("short_name") or "",
                    "exchange": item.get("exchange", "NSE"),
                    "price": last_price,
                    "instrument_key": key,
                    "source": "UPSTOX",
                    "previous_close": previous_close,
                    "change_percent": round(change_percent, 2),
                })
            register_instruments(results)
            return results
        finally:
            if owns_client:
                await client.aclose()

    async def refresh_prices(self, symbols: list[str]) -> None:
        """Refresh cached LTPs for already-resolved symbols in one Upstox request."""
        from ..instruments import find_instrument

        keys = []
        instruments = []
        for symbol in symbols:
            instrument = find_instrument(symbol)
            if instrument and instrument.get("instrument_key"):
                keys.append(instrument["instrument_key"])
                instruments.append(instrument)
        if not keys:
            return

        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=6.0)
        try:
            response = await client.get(
                f"{self.base_url}/v3/market-quote/ltp",
                headers=self.headers,
                params={"instrument_key": ",".join(keys)},
            )
            response.raise_for_status()
            quotes = response.json().get("data", {})
            updated = []
            for instrument in instruments:
                quote = next(
                    (item for item in quotes.values()
                     if item.get("instrument_token") == instrument.get("instrument_key")),
                    None,
                )
                if not quote or quote.get("last_price") is None:
                    continue
                last_price = float(quote["last_price"])
                previous_close = float(quote.get("cp") or instrument.get("previous_close") or last_price)
                updated.append({
                    **instrument,
                    "price": last_price,
                    "previous_close": previous_close,
                    "change_percent": round(
                        ((last_price - previous_close) / previous_close) * 100 if previous_close else 0.0,
                        2,
                    ),
                })
            register_instruments(updated)
        finally:
            if owns_client:
                await client.aclose()


async def search_equities(query: str, limit: int = 10) -> list[dict]:
    settings = get_settings()
    if not query.strip() or not settings.upstox_access_token:
        return search_local_instruments(query, limit)
    try:
        return await UpstoxMarketData(
            settings.upstox_access_token, settings.upstox_api_base_url
        ).search_equities(query, limit)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Upstox instrument search failed; using paper fallback: %s", exc)
        return search_local_instruments(query, limit)


async def refresh_instrument_prices(symbols: list[str]) -> None:
    settings = get_settings()
    if not settings.upstox_access_token or not symbols:
        return
    try:
        await UpstoxMarketData(
            settings.upstox_access_token, settings.upstox_api_base_url
        ).refresh_prices(symbols)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Upstox LTP refresh failed; keeping last known prices: %s", exc)
