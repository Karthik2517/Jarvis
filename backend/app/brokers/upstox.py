import uuid

import httpx

from ..config import get_settings
from ..instruments import find_instrument
from ..schemas import Side
from .base import BrokerAdapter, BrokerOrderResult, BrokerOrderStatus


class UpstoxBroker(BrokerAdapter):
    """Upstox V3 execution adapter with separate sandbox and live safety gates."""

    def __init__(self, mode: str = "UPSTOX_SANDBOX", client: httpx.Client | None = None):
        settings = get_settings()
        self.name = mode.upper()
        self.is_sandbox = self.name == "UPSTOX_SANDBOX"
        if self.is_sandbox:
            self.access_token = settings.upstox_sandbox_access_token
            self.order_base_url = settings.upstox_sandbox_base_url.rstrip("/")
            self.api_base_url = settings.upstox_sandbox_base_url.rstrip("/")
        else:
            self.access_token = settings.upstox_access_token
            self.order_base_url = settings.upstox_order_base_url.rstrip("/")
            self.api_base_url = settings.upstox_api_base_url.rstrip("/")
        self.live_enabled = settings.live_trading_enabled
        self.client = client

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _assert_ready(self) -> None:
        if not self.access_token:
            variable = "UPSTOX_SANDBOX_ACCESS_TOKEN" if self.is_sandbox else "UPSTOX_ACCESS_TOKEN"
            raise RuntimeError(f"{variable} is not configured")
        if not self.is_sandbox and not self.live_enabled:
            raise RuntimeError(
                "Live trading is locked. Set LIVE_TRADING_ENABLED=true only after sandbox verification"
            )

    def quote(self, symbol: str) -> float:
        instrument = find_instrument(symbol)
        if not instrument:
            raise RuntimeError(f"Search and select {symbol} before placing an Upstox order")
        if not instrument.get("instrument_key"):
            raise RuntimeError(f"Upstox instrument key is unavailable for {symbol}; search the symbol again")
        price = float(instrument.get("price") or 0)
        if price <= 0:
            raise RuntimeError(f"A valid Upstox quote is unavailable for {symbol}")
        return price

    def place_market_order(self, symbol: str, side: Side, quantity: int) -> BrokerOrderResult:
        self._assert_ready()
        instrument = find_instrument(symbol)
        if not instrument or not instrument.get("instrument_key"):
            raise RuntimeError(f"Upstox instrument key is unavailable for {symbol}; search the symbol again")
        payload = {
            "quantity": quantity,
            "product": "D",
            "validity": "DAY",
            "price": 0,
            "tag": f"JARVIS-{uuid.uuid4().hex[:12]}",
            "instrument_token": instrument["instrument_key"],
            "order_type": "MARKET",
            "transaction_type": side.value,
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
            "slice": False,
            "market_protection": -1,
        }
        response = self._request("POST", f"{self.order_base_url}/v3/order/place", json=payload)
        order_ids = response.get("data", {}).get("order_ids", [])
        if not order_ids:
            raise RuntimeError("Upstox accepted the request but returned no order ID")
        return BrokerOrderResult(
            broker_order_id=str(order_ids[0]),
            status="SUBMITTED",
            average_price=None,
            filled_quantity=0,
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        self._assert_ready()
        response = self._request(
            "GET",
            f"{self.api_base_url}/v2/order/details",
            params={"order_id": broker_order_id},
        )
        data = response.get("data", {})
        raw_status = str(data.get("status", "")).lower()
        filled = int(data.get("filled_quantity") or 0)
        quantity = int(data.get("quantity") or 0)
        if raw_status == "complete" or (quantity and filled >= quantity):
            status = "FILLED"
        elif raw_status in {"rejected", "cancelled", "canceled"}:
            status = "REJECTED" if raw_status == "rejected" else "CANCELLED"
        elif filled > 0:
            status = "PARTIAL"
        else:
            status = "OPEN"
        average_price = float(data.get("average_price") or 0) or None
        reason = data.get("status_message") or data.get("status_message_raw")
        return BrokerOrderStatus(status, filled, average_price, reason)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=10.0)
        try:
            response = client.request(method, url, headers=self.headers, **kwargs)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if response.is_error:
                errors = payload.get("errors", []) if isinstance(payload, dict) else []
                message = errors[0].get("message") if errors and isinstance(errors[0], dict) else None
                raise RuntimeError(message or f"Upstox request failed with HTTP {response.status_code}")
            return payload
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not reach Upstox: {exc}") from exc
        finally:
            if owns_client:
                client.close()
