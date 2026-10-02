"""Authenticated, read-only HTTP API for preset and custom stock scans."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings, resolve_upstox_market_data_token
from ..database import db
from ..dependencies import get_current_user
from ..market_data import (
    DatabaseCandleCache,
    HistoricalDataService,
    MarketDataProviderError,
    UpstoxHistoricalDataProvider,
    UpstoxInstrumentMasterProvider,
)
from ..schemas import (
    SavedScannerCreate,
    ScannerAlertCreate,
    ScannerAlertUpdate,
    ScannerRunRequest,
)
from .conditions import Condition, ConditionField, ConditionOperand, ConditionValidationError
from .results import PaginationError, ScanPage, rank_and_paginate
from .scanner_engine import ScannerEngine
from .scanners import ScannerDefinition, default_scanners
from .universe import Nifty50Universe

router = APIRouter(prefix="/api/scanners", tags=["scanners"])
IST = ZoneInfo("Asia/Kolkata")


def _completed_through(now: datetime | None = None) -> date:
    current = now or datetime.now(IST)
    candidate = current.date() if current.time() >= time(16, 0) else current.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _condition_payload(condition: Condition) -> dict:
    right = condition.right
    return {
        "left": condition.left.value,
        "operator": condition.operator.value,
        "right": (
            {"field": right.field.value, "multiplier": right.multiplier}
            if right.field is not None
            else {"value": right.value}
        ),
    }


def _definition_payload(scanner: ScannerDefinition) -> dict:
    return {
        "key": scanner.key,
        "name": scanner.name,
        "description": scanner.description,
        "minimum_history": scanner.minimum_history,
        "rank_field": scanner.rank_field.value,
        "rank_direction": scanner.rank_direction.value,
        "conditions": [_condition_payload(condition) for condition in scanner.conditions],
    }


def _page_payload(page: ScanPage, scanner_key: str) -> dict:
    return {
        "scanner_key": scanner_key,
        "page": page.page,
        "page_size": page.page_size,
        "total_pages": page.total_pages,
        "total_matches": page.total_matches,
        "total_instruments": page.total_instruments,
        "evaluated": page.evaluated,
        "skipped_count": page.skipped_count,
        "skip_reasons": page.skip_reasons,
        "has_previous": page.has_previous,
        "has_next": page.has_next,
        "items": [
            {
                "rank": item.rank,
                "rank_value": round(item.rank_value, 6),
                "instrument_key": item.match.instrument.instrument_key,
                "symbol": item.match.instrument.trading_symbol,
                "name": item.match.instrument.name,
                "exchange": item.match.instrument.exchange,
                "data_as_of": item.match.data_as_of.isoformat(),
                "indicators": asdict(item.match.indicators),
            }
            for item in page.items
        ],
    }


def _saved_scanner_payload(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "preset_key": row["preset_key"],
        "conditions": json.loads(row["conditions_json"]),
        "rank_field": row["rank_field"],
        "rank_direction": row["rank_direction"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _alert_payload(row) -> dict:
    return {
        "id": row["id"],
        "saved_scanner_id": row["saved_scanner_id"],
        "saved_scanner_name": row["saved_scanner_name"],
        "name": row["name"],
        "minimum_matches": row["minimum_matches"],
        "enabled": bool(row["enabled"]),
        "last_checked_at": row["last_checked_at"],
        "last_triggered_at": row["last_triggered_at"],
        "created_at": row["created_at"],
    }


def _event_payload(row) -> dict:
    return {
        "id": row["id"],
        "alert_id": row["alert_id"],
        "alert_name": row["alert_name"],
        "match_count": row["match_count"],
        "symbols": json.loads(row["symbols_json"]),
        "data_as_of": row["data_as_of"],
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
    }


async def _execute_scan(payload: ScannerRunRequest) -> tuple[ScanPage, str]:
    """Evaluate one validated scan without crossing into signal or execution code."""
    settings = get_settings()
    market_data_token = resolve_upstox_market_data_token(settings)
    if not market_data_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "UPSTOX_MARKET_DATA_TOKEN or UPSTOX_ACCESS_TOKEN is required "
                "to run NIFTY 50 scanners"
            ),
        )

    # Reuse one connection pool for both instrument files and all 50 history
    # requests. Creating a new TLS client per stock made local preset scans take
    # minutes and could exhaust a serverless invocation window.
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        universe = await Nifty50Universe().load(UpstoxInstrumentMasterProvider(client))
        if not universe:
            raise MarketDataProviderError(
                "Upstox returned no eligible NIFTY 50 equities; the scanner universe could not be loaded"
            )
        if payload.symbols:
            requested = {symbol.strip().upper() for symbol in payload.symbols if symbol.strip()}
            universe = [item for item in universe if item.trading_symbol in requested]
            if not universe:
                raise HTTPException(status_code=404, detail="None of the requested NSE symbols were found")

        history = HistoricalDataService(
            UpstoxHistoricalDataProvider(
                market_data_token,
                settings.upstox_api_base_url,
                client,
            ),
            DatabaseCandleCache(db),
            provider_name="UPSTOX",
        )
        engine = ScannerEngine(history)
        to_date = _completed_through()
        from_date = to_date - timedelta(days=430)

        if payload.preset_key:
            scanner = default_scanners().get(payload.preset_key)
            if not scanner:
                raise HTTPException(status_code=404, detail="Scanner preset not found")
            page = await engine.scan_definition(
                universe,
                scanner,
                from_date=from_date,
                to_date=to_date,
                refresh=payload.refresh,
                page=payload.page,
                page_size=payload.page_size,
            )
            return page, scanner.key

        conditions = [
            Condition(
                left=item.left,
                operator=item.operator,
                right=(
                    ConditionOperand.indicator(item.right.field, item.right.multiplier)
                    if item.right.field is not None
                    else ConditionOperand.literal(item.right.value)
                ),
            )
            for item in payload.conditions
        ]
        result = await engine.scan(
            universe,
            conditions,
            from_date=from_date,
            to_date=to_date,
            refresh=payload.refresh,
        )
        page = rank_and_paginate(
            result,
            rank_field=payload.rank_field,
            rank_direction=payload.rank_direction,
            page=payload.page,
            page_size=payload.page_size,
        )
        return page, "custom"


@router.get("")
def list_scanners(_=Depends(get_current_user)):
    return {
        "presets": [_definition_payload(scanner) for scanner in default_scanners().values()],
        "fields": [field.value for field in ConditionField],
        "operators": [">", ">=", "<", "<=", "=="],
    }


@router.post("/run")
async def run_scanner(payload: ScannerRunRequest, _=Depends(get_current_user)):
    try:
        page, scanner_key = await _execute_scan(payload)
    except HTTPException:
        raise
    except (ConditionValidationError, PaginationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _page_payload(page, scanner_key)


@router.get("/saved")
def list_saved_scanners(user=Depends(get_current_user)):
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM saved_scanners WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user["id"],),
        ).fetchall()
    return [_saved_scanner_payload(row) for row in rows]


@router.post("/saved", status_code=201)
def save_scanner(payload: SavedScannerCreate, user=Depends(get_current_user)):
    if payload.preset_key and payload.preset_key not in default_scanners():
        raise HTTPException(status_code=404, detail="Scanner preset not found")
    conditions_json = json.dumps(
        [condition.model_dump(mode="json") for condition in payload.conditions],
        separators=(",", ":"),
    )
    with db.transaction() as connection:
        duplicate = connection.execute(
            "SELECT id FROM saved_scanners WHERE user_id = ? AND name = ?",
            (user["id"], payload.name),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="A saved scanner with this name already exists")
        cursor = connection.execute(
            """INSERT INTO saved_scanners
               (user_id, name, preset_key, conditions_json, rank_field, rank_direction)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user["id"], payload.name, payload.preset_key, conditions_json,
                payload.rank_field.value, payload.rank_direction.value,
            ),
        )
        row = connection.execute(
            "SELECT * FROM saved_scanners WHERE id = ? AND user_id = ?",
            (cursor.lastrowid, user["id"]),
        ).fetchone()
    return _saved_scanner_payload(row)


@router.delete("/saved/{scanner_id}")
def delete_saved_scanner(scanner_id: int, user=Depends(get_current_user)):
    with db.transaction() as connection:
        row = connection.execute(
            "SELECT id FROM saved_scanners WHERE id = ? AND user_id = ?",
            (scanner_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Saved scanner not found")
        connection.execute(
            "DELETE FROM saved_scanners WHERE id = ? AND user_id = ?",
            (scanner_id, user["id"]),
        )
    return {"message": "Saved scanner deleted"}


@router.get("/alerts")
def list_alerts(user=Depends(get_current_user)):
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT a.*, s.name AS saved_scanner_name
               FROM scanner_alerts a JOIN saved_scanners s ON s.id = a.saved_scanner_id
               WHERE a.user_id = ? ORDER BY a.updated_at DESC, a.id DESC""",
            (user["id"],),
        ).fetchall()
    return [_alert_payload(row) for row in rows]


@router.post("/alerts", status_code=201)
def create_alert(payload: ScannerAlertCreate, user=Depends(get_current_user)):
    with db.transaction() as connection:
        scanner = connection.execute(
            "SELECT id FROM saved_scanners WHERE id = ? AND user_id = ?",
            (payload.saved_scanner_id, user["id"]),
        ).fetchone()
        if not scanner:
            raise HTTPException(status_code=404, detail="Saved scanner not found")
        duplicate = connection.execute(
            "SELECT id FROM scanner_alerts WHERE user_id = ? AND name = ?",
            (user["id"], payload.name),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="An alert with this name already exists")
        cursor = connection.execute(
            """INSERT INTO scanner_alerts
               (user_id, saved_scanner_id, name, minimum_matches)
               VALUES (?, ?, ?, ?)""",
            (user["id"], payload.saved_scanner_id, payload.name, payload.minimum_matches),
        )
        row = connection.execute(
            """SELECT a.*, s.name AS saved_scanner_name
               FROM scanner_alerts a JOIN saved_scanners s ON s.id = a.saved_scanner_id
               WHERE a.id = ? AND a.user_id = ?""",
            (cursor.lastrowid, user["id"]),
        ).fetchone()
    return _alert_payload(row)


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: int, payload: ScannerAlertUpdate, user=Depends(get_current_user)):
    with db.transaction() as connection:
        existing = connection.execute(
            "SELECT id, enabled, minimum_matches FROM scanner_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user["id"]),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Scanner alert not found")
        enabled = existing["enabled"] if payload.enabled is None else int(payload.enabled)
        minimum_matches = payload.minimum_matches or existing["minimum_matches"]
        connection.execute(
            """UPDATE scanner_alerts SET enabled = ?, minimum_matches = ?,
               updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?""",
            (enabled, minimum_matches, alert_id, user["id"]),
        )
        row = connection.execute(
            """SELECT a.*, s.name AS saved_scanner_name
               FROM scanner_alerts a JOIN saved_scanners s ON s.id = a.saved_scanner_id
               WHERE a.id = ? AND a.user_id = ?""",
            (alert_id, user["id"]),
        ).fetchone()
    return _alert_payload(row)


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, user=Depends(get_current_user)):
    with db.transaction() as connection:
        existing = connection.execute(
            "SELECT id FROM scanner_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user["id"]),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Scanner alert not found")
        connection.execute(
            "DELETE FROM scanner_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user["id"]),
        )
    return {"message": "Scanner alert deleted"}


@router.post("/alerts/{alert_id}/evaluate")
async def evaluate_alert(alert_id: int, user=Depends(get_current_user)):
    with db.connect() as connection:
        row = connection.execute(
            """SELECT a.*, s.name AS saved_scanner_name, s.preset_key,
                      s.conditions_json, s.rank_field, s.rank_direction
               FROM scanner_alerts a JOIN saved_scanners s ON s.id = a.saved_scanner_id
               WHERE a.id = ? AND a.user_id = ?""",
            (alert_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Scanner alert not found")
    if not bool(row["enabled"]):
        raise HTTPException(status_code=409, detail="Enable this alert before checking it")

    scan = ScannerRunRequest(
        preset_key=row["preset_key"],
        conditions=json.loads(row["conditions_json"]),
        rank_field=row["rank_field"],
        rank_direction=row["rank_direction"],
        page=1,
        page_size=100,
        refresh=True,
    )
    try:
        page, scanner_key = await _execute_scan(scan)
    except HTTPException:
        raise
    except (ConditionValidationError, PaginationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = datetime.now(IST).isoformat()
    triggered = page.total_matches >= row["minimum_matches"]
    symbols = [item.match.instrument.trading_symbol for item in page.items]
    data_as_of = page.items[0].match.data_as_of.isoformat() if page.items else None
    event = None
    with db.transaction() as connection:
        connection.execute(
            """UPDATE scanner_alerts SET last_checked_at = ?,
               last_triggered_at = CASE WHEN ? = 1 THEN ? ELSE last_triggered_at END,
               updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?""",
            (now, int(triggered), now, alert_id, user["id"]),
        )
        if triggered:
            cursor = connection.execute(
                """INSERT INTO scanner_alert_events
                   (user_id, alert_id, match_count, symbols_json, data_as_of)
                   VALUES (?, ?, ?, ?, ?)""",
                (user["id"], alert_id, page.total_matches, json.dumps(symbols), data_as_of),
            )
            event = connection.execute(
                """SELECT e.*, a.name AS alert_name FROM scanner_alert_events e
                   JOIN scanner_alerts a ON a.id = e.alert_id
                   WHERE e.id = ? AND e.user_id = ?""",
                (cursor.lastrowid, user["id"]),
            ).fetchone()
    return {
        "triggered": triggered,
        "scanner_key": scanner_key,
        "match_count": page.total_matches,
        "event": _event_payload(event) if event else None,
    }


@router.get("/alert-events")
def list_alert_events(user=Depends(get_current_user)):
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT e.*, a.name AS alert_name FROM scanner_alert_events e
               JOIN scanner_alerts a ON a.id = e.alert_id
               WHERE e.user_id = ? ORDER BY e.created_at DESC, e.id DESC LIMIT 100""",
            (user["id"],),
        ).fetchall()
    return [_event_payload(row) for row in rows]


@router.patch("/alert-events/{event_id}/read")
def mark_alert_event_read(event_id: int, user=Depends(get_current_user)):
    with db.transaction() as connection:
        row = connection.execute(
            "SELECT id FROM scanner_alert_events WHERE id = ? AND user_id = ?",
            (event_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scanner alert event not found")
        connection.execute(
            "UPDATE scanner_alert_events SET is_read = 1 WHERE id = ? AND user_id = ?",
            (event_id, user["id"]),
        )
    return {"message": "Alert marked as read"}
