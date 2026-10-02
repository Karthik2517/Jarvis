import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.market_data.models import Candle, Instrument
from app.scanner import api as scanner_api

IST = timezone(timedelta(hours=5, minutes=30))


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "jarvis@example.com", "password": "jarvis1234"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_scanner_catalog_is_authenticated_and_lists_five_presets():
    with TestClient(app) as client:
        assert client.get("/api/scanners").status_code == 401
        response = client.get("/api/scanners", headers=auth_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["presets"]) == 5
    assert {item["key"] for item in payload["presets"]} == {
        "52_week_high_breakout",
        "52_week_low",
        "volume_breakout",
        "price_above_sma_20_50_200",
        "rsi",
    }
    assert "sma200" in payload["fields"]


def test_scanner_run_returns_ranked_paginated_api_response(monkeypatch):
    instrument = Instrument(
        instrument_key="NSE_EQ|SCANAPITEST",
        trading_symbol="SCANAPITEST",
        name="Scanner API Test",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        security_type="NORMAL",
    )

    async def load_universe(_self, _provider):
        return [instrument]

    async def get_history(_self, _instrument_key, from_date, to_date):
        del from_date
        end = datetime.combine(to_date, datetime.min.time(), tzinfo=IST)
        return [
            Candle(
                timestamp=end - timedelta(days=252 - index),
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100 + index,
                volume=1000 + index,
            )
            for index in range(253)
        ]

    monkeypatch.setattr(scanner_api.Nifty50Universe, "load", load_universe)
    monkeypatch.setattr(
        scanner_api.UpstoxHistoricalDataProvider,
        "get_daily_candles",
        get_history,
    )
    monkeypatch.setattr(
        scanner_api,
        "get_settings",
        lambda: SimpleNamespace(
            upstox_access_token="test-token",
            upstox_api_base_url="https://api.upstox.test",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scanners/run",
            headers=auth_headers(client),
            json={
                "conditions": [
                    {
                        "left": "price",
                        "operator": ">",
                        "right": {"field": "sma50", "multiplier": 1},
                    },
                    {
                        "left": "rsi14",
                        "operator": ">=",
                        "right": {"value": 55},
                    },
                ],
                "rank_field": "rsi14",
                "rank_direction": "desc",
                "page": 1,
                "page_size": 25,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scanner_key"] == "custom"
    assert payload["total_matches"] == 1
    assert payload["items"][0]["rank"] == 1
    assert payload["items"][0]["symbol"] == "SCANAPITEST"
    assert payload["items"][0]["indicators"]["rsi14"] == 100


def test_scanner_stream_emits_incremental_match_and_paginated_completion(monkeypatch):
    instrument = Instrument(
        instrument_key="NSE_EQ|STREAMTEST",
        trading_symbol="STREAMTEST",
        name="Scanner Stream Test",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        security_type="NORMAL",
    )

    async def load_universe(_self, _provider):
        return [instrument]

    async def get_history(_self, _instrument_key, from_date, to_date):
        del from_date
        end = datetime.combine(to_date, datetime.min.time(), tzinfo=IST)
        return [
            Candle(
                timestamp=end - timedelta(days=252 - index),
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100 + index,
                volume=1000 + index,
            )
            for index in range(253)
        ]

    monkeypatch.setattr(scanner_api.Nifty50Universe, "load", load_universe)
    monkeypatch.setattr(
        scanner_api.UpstoxHistoricalDataProvider,
        "get_daily_candles",
        get_history,
    )
    monkeypatch.setattr(
        scanner_api,
        "get_settings",
        lambda: SimpleNamespace(
            upstox_market_data_token="stream-token",
            upstox_access_token="execution-token",
            upstox_api_base_url="https://api.upstox.test",
        ),
    )

    with TestClient(app) as client:
        headers = auth_headers(client)
        with client.stream(
            "POST",
            "/api/scanners/run/stream",
            headers=headers,
            json={"preset_key": "rsi", "page": 1, "page_size": 10},
        ) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]
        scan_id = events[-1]["result"]["scan_id"]
        snapshot_page = client.get(
            f"/api/scanners/runs/{scan_id}?page=1&page_size=5",
            headers=headers,
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [event["type"] for event in events] == [
        "state", "started", "progress", "complete"
    ]
    assert events[2]["status"] == "match"
    assert events[2]["item"]["symbol"] == "STREAMTEST"
    assert events[3]["result"]["page_size"] == 10
    assert events[3]["result"]["total_matches"] == 1
    assert snapshot_page.status_code == 200
    assert snapshot_page.json()["scan_id"] == scan_id
    assert snapshot_page.json()["page_size"] == 5
    assert snapshot_page.json()["items"][0]["symbol"] == "STREAMTEST"


def test_scanner_run_rejects_ambiguous_selection():
    with TestClient(app) as client:
        response = client.post(
            "/api/scanners/run",
            headers=auth_headers(client),
            json={"preset_key": "rsi", "conditions": [
                {"left": "price", "operator": ">", "right": {"value": 100}}
            ]},
        )
    assert response.status_code == 422


def test_scanner_run_reports_empty_provider_universe(monkeypatch):
    async def load_empty_universe(_self, _provider):
        return []

    monkeypatch.setattr(scanner_api.Nifty50Universe, "load", load_empty_universe)
    monkeypatch.setattr(
        scanner_api,
        "get_settings",
        lambda: SimpleNamespace(
            upstox_access_token="test-token",
            upstox_api_base_url="https://api.upstox.test",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scanners/run",
            headers=auth_headers(client),
            json={"preset_key": "volume_breakout"},
        )

    assert response.status_code == 502
    assert "no eligible NIFTY 50 equities" in response.json()["detail"]


def test_saved_scanner_and_in_app_alert_lifecycle(monkeypatch):
    suffix = uuid4().hex[:8]
    scanner_name = f"Momentum {suffix}"
    alert_name = f"Momentum Alert {suffix}"

    async def execute_scan(_payload):
        match = SimpleNamespace(
            instrument=SimpleNamespace(trading_symbol="RELIANCE"),
            data_as_of=date(2026, 10, 1),
        )
        return SimpleNamespace(total_matches=2, items=[SimpleNamespace(match=match)]), "rsi"

    monkeypatch.setattr(scanner_api, "_execute_scan", execute_scan)

    with TestClient(app) as client:
        headers = auth_headers(client)
        saved = client.post(
            "/api/scanners/saved",
            headers=headers,
            json={
                "name": scanner_name,
                "preset_key": "rsi",
                "rank_field": "rsi14",
                "rank_direction": "desc",
            },
        )
        assert saved.status_code == 201
        saved_id = saved.json()["id"]
        assert saved.json()["preset_key"] == "rsi"
        assert any(item["id"] == saved_id for item in client.get(
            "/api/scanners/saved", headers=headers
        ).json())

        created_alert = client.post(
            "/api/scanners/alerts",
            headers=headers,
            json={
                "saved_scanner_id": saved_id,
                "name": alert_name,
                "minimum_matches": 2,
            },
        )
        assert created_alert.status_code == 201
        alert_id = created_alert.json()["id"]

        evaluation = client.post(
            f"/api/scanners/alerts/{alert_id}/evaluate", headers=headers
        )
        assert evaluation.status_code == 200
        assert evaluation.json()["triggered"] is True
        assert evaluation.json()["event"]["symbols"] == ["RELIANCE"]

        events = client.get("/api/scanners/alert-events", headers=headers).json()
        assert events[0]["alert_name"] == alert_name
        assert events[0]["match_count"] == 2

        disabled = client.patch(
            f"/api/scanners/alerts/{alert_id}",
            headers=headers,
            json={"enabled": False},
        )
        assert disabled.json()["enabled"] is False

        deleted = client.delete(f"/api/scanners/saved/{saved_id}", headers=headers)
        assert deleted.status_code == 200
        assert all(item["id"] != alert_id for item in client.get(
            "/api/scanners/alerts", headers=headers
        ).json())
