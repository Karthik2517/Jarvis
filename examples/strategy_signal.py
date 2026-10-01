"""Minimal example of sending a strategy signal into JARVIS."""

import os
import uuid

import httpx


def send_signal(symbol: str, side: str, quantity: int) -> dict:
    response = httpx.post(
        os.getenv("JARVIS_URL", "http://localhost:8000") + "/api/signals",
        headers={"X-Strategy-Key": os.getenv("JARVIS_STRATEGY_KEY", "demo-strategy-key")},
        json={
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "strategy_name": "example-strategy",
            "signal_id": str(uuid.uuid4()),
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print(send_signal("RELIANCE", "BUY", 10))
