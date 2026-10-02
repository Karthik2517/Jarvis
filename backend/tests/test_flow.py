import os
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path(__file__).parent / "test_jarvis.db")
os.environ["DATABASE_URL"] = ""
os.environ["APP_SECRET"] = "test-secret"
os.environ["DEMO_STRATEGY_KEY"] = "demo-strategy-key"
os.environ["UPSTOX_ACCESS_TOKEN"] = ""

from fastapi.testclient import TestClient

from app.database import db
from app.instruments import register_instruments
from app.main import app


def test_complete_buy_sell_and_signal_flow():
    test_db = Path(os.environ["DATABASE_PATH"])
    test_db.unlink(missing_ok=True)
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "jarvis@example.com", "password": "jarvis1234"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        buy = client.post("/api/orders", headers=headers, json={"symbol": "RELIANCE", "side": "BUY", "quantity": 10})
        assert buy.status_code == 201
        assert buy.json()["status"] == "FILLED"

        positions = client.get("/api/positions", headers=headers).json()
        assert positions[0]["symbol"] == "RELIANCE"
        assert positions[0]["quantity"] == 10

        client.put("/api/broker", headers=headers, json={"broker": "UPSTOX_SANDBOX"})
        assert client.get("/api/positions", headers=headers).json() == []
        assert client.get("/api/orders", headers=headers).json() == []
        client.put("/api/broker", headers=headers, json={"broker": "PAPER"})
        assert client.get("/api/positions", headers=headers).json()[0]["quantity"] == 10

        signal = client.post(
            "/api/signals",
            headers={"X-Strategy-Key": "demo-strategy-key"},
            json={"symbol": "RELIANCE", "side": "SELL", "quantity": 4, "strategy_name": "test"},
        )
        assert signal.status_code == 201
        assert signal.json()["source"] == "STRATEGY"
        assert client.get("/api/positions", headers=headers).json()[0]["quantity"] == 6

        close = client.post(
            "/api/orders", headers=headers,
            json={"symbol": "RELIANCE", "side": "SELL", "quantity": 6},
        )
        assert close.json()["status"] == "FILLED"
        assert client.get("/api/positions", headers=headers).json() == []
        closed = client.get("/api/positions?include_closed=true", headers=headers).json()
        assert closed[0]["symbol"] == "RELIANCE"
        assert closed[0]["quantity"] == 0

        strategies = client.get("/api/strategies", headers=headers).json()
        assert strategies[0]["name"] == "test"
        assert strategies[0]["signal_count"] == 1
        paused = client.patch(
            f"/api/strategies/{strategies[0]['id']}", headers=headers, json={"status": "PAUSED"}
        )
        assert paused.json()["status"] == "PAUSED"
        blocked = client.post(
            "/api/signals",
            headers={"X-Strategy-Key": "demo-strategy-key"},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "strategy_name": "test"},
        )
        assert blocked.status_code == 409

        rotated = client.post("/api/auth/strategy-key", headers=headers).json()["strategy_api_key"]
        assert rotated != "demo-strategy-key"
        assert client.post(
            "/api/signals",
            headers={"X-Strategy-Key": "demo-strategy-key"},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "strategy_name": "new"},
        ).status_code == 401
        assert client.post(
            "/api/signals",
            headers={"X-Strategy-Key": rotated},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "strategy_name": "new"},
        ).status_code == 201
    test_db.unlink(missing_ok=True)


def test_risk_rejection_is_audited():
    test_db = Path(os.environ["DATABASE_PATH"])
    test_db.unlink(missing_ok=True)


def test_paper_order_resolves_a_stock_not_in_the_default_list(monkeypatch):
    """Orders must not rely on a prior serverless search request's memory."""
    test_db = Path(os.environ["DATABASE_PATH"])
    test_db.unlink(missing_ok=True)

    async def resolve_hindalco(*_args, **_kwargs):
        instrument = {
            "symbol": "HINDALCO",
            "name": "Hindalco Industries",
            "exchange": "NSE",
            "price": 941.85,
            "instrument_key": "NSE_EQ|INE038A01020",
            "source": "UPSTOX",
            "previous_close": 940.90,
            "change_percent": 0.10,
        }
        register_instruments([instrument])
        return [instrument]

    monkeypatch.setattr("app.main.search_equities", resolve_hindalco)
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "jarvis@example.com", "password": "jarvis1234"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        order = client.post(
            "/api/orders", headers=headers,
            json={"symbol": "HINDALCO", "side": "BUY", "quantity": 1},
        )
        assert order.status_code == 201
        assert order.json()["status"] == "FILLED"
        assert order.json()["symbol"] == "HINDALCO"
    test_db.unlink(missing_ok=True)
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"email": "jarvis@example.com", "password": "jarvis1234"}).json()["access_token"]
        response = client.post(
            "/api/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1001},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "REJECTED"
        assert "limit" in response.json()["rejection_reason"].lower()
    test_db.unlink(missing_ok=True)
