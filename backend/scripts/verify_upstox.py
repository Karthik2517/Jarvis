"""Verify the configured Upstox token without printing the token or personal details."""

import asyncio

import httpx

from app.config import get_settings
from app.services.market_data import UpstoxMarketData


async def main() -> int:
    settings = get_settings()
    if not settings.upstox_access_token:
        print("UPSTOX_ACCESS_TOKEN is not set in backend/.env")
        return 1

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.upstox_api_base_url.rstrip('/')}/v2/user/profile",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {settings.upstox_access_token}",
                },
            )
            response.raise_for_status()
            instruments = await UpstoxMarketData(
                settings.upstox_access_token,
                settings.upstox_api_base_url,
                client,
            ).search_equities("RELIANCE", limit=5)
        profile = response.json().get("data", {})
        exchanges = ", ".join(profile.get("exchanges", [])) or "none reported"
        print(f"Upstox connection verified: broker={profile.get('broker', 'UPSTOX')}")
        print(f"Account active: {bool(profile.get('is_active'))}")
        print(f"Enabled exchanges: {exchanges}")
        live_results = [item for item in instruments if item.get("source") == "UPSTOX"]
        quoted_results = [item for item in live_results if item.get("price", 0) > 0]
        print(f"Instrument search: {len(live_results)} Upstox result(s)")
        if quoted_results:
            sample = quoted_results[0]
            print(f"Live quote verified: {sample['symbol']} at INR {sample['price']:,.2f}")
        else:
            print("Live quote unavailable for the returned search results")
            return 4
        return 0
    except httpx.HTTPStatusError as exc:
        print(f"Upstox rejected the token (HTTP {exc.response.status_code}).")
        return 2
    except httpx.HTTPError as exc:
        print(f"Could not reach Upstox: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
