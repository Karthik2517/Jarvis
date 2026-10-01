import json

import httpx

from app.brokers.upstox import UpstoxBroker
from app.instruments import register_instruments
from app.schemas import Side


def test_upstox_sandbox_submission_and_fill_status():
    register_instruments([{
        "symbol": "RELIANCE",
        "name": "Reliance Industries",
        "exchange": "NSE",
        "price": 1167.70,
        "instrument_key": "NSE_EQ|INE002A01018",
        "source": "UPSTOX",
    }])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sandbox-test-token"
        if request.method == "POST" and request.url.path == "/v3/order/place":
            payload = json.loads(request.content)
            assert payload["instrument_token"] == "NSE_EQ|INE002A01018"
            assert payload["transaction_type"] == "BUY"
            assert payload["quantity"] == 1
            assert payload["market_protection"] == -1
            return httpx.Response(200, json={
                "status": "success", "data": {"order_ids": ["sandbox-order-1"]}
            })
        if request.method == "GET" and request.url.path == "/v2/order/details":
            assert request.url.params["order_id"] == "sandbox-order-1"
            return httpx.Response(200, json={
                "status": "success",
                "data": {
                    "status": "complete",
                    "quantity": 1,
                    "filled_quantity": 1,
                    "average_price": 1168.25,
                },
            })
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        broker = UpstoxBroker("UPSTOX_SANDBOX", client)
        broker.access_token = "sandbox-test-token"
        broker.order_base_url = "https://sandbox.test"
        broker.api_base_url = "https://sandbox.test"

        submitted = broker.place_market_order("RELIANCE", Side.BUY, 1)
        assert submitted.status == "SUBMITTED"
        assert submitted.filled_quantity == 0
        assert submitted.broker_order_id == "sandbox-order-1"

        reconciled = broker.get_order_status(submitted.broker_order_id)
        assert reconciled.status == "FILLED"
        assert reconciled.filled_quantity == 1
        assert reconciled.average_price == 1168.25

