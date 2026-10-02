"""Authenticated, read-only HTTP API for preset and custom stock scans."""

from __future__ import annotations

import asyncio
import json
import math
import time as monotonic_time
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..config import get_settings, resolve_upstox_market_data_token
from ..database import db
from ..dependencies import get_current_user
from ..market_data import (
    DatabaseCandleCache,
    HistoricalDataService,
    MarketDataProviderError,
    PrefetchedCandleCache,
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
from .scanner_engine import ScanMatch, ScanResult, ScanSkip, ScannerEngine
from .scanners import RankTransform, ScannerDefinition, default_scanners
from .scanners.base import rank_value
from .universe import Nifty50Universe

router = APIRouter(prefix="/api/scanners", tags=["scanners"])
IST = ZoneInfo("Asia/Kolkata")
SCAN_CANDLE_MEMORY_TTL_SECONDS = 5 * 60
_scan_candle_memory: dict[tuple, tuple[float, dict, dict]] = {}


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


def _page_payload(page: ScanPage, scanner_key: str, *, scan_id: str | None = None) -> dict:
    payload = {
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
    if scan_id:
        payload["scan_id"] = scan_id
    return payload


def _match_payload(match: ScanMatch, *, rank: int, rank_value_: float) -> dict:
    """Serialize a live match using the same shape as a finalized page item."""

    return {
        "rank": rank,
        "rank_value": round(rank_value_, 6),
        "instrument_key": match.instrument.instrument_key,
        "symbol": match.instrument.trading_symbol,
        "name": match.instrument.name,
        "exchange": match.instrument.exchange,
        "data_as_of": match.data_as_of.isoformat(),
        "indicators": asdict(match.indicators),
    }


def _custom_conditions(payload: ScannerRunRequest) -> list[Condition]:
    return [
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


def _scan_plan(payload: ScannerRunRequest):
    if payload.preset_key:
        scanner = default_scanners().get(payload.preset_key)
        if not scanner:
            raise HTTPException(status_code=404, detail="Scanner preset not found")
        return (
            scanner.conditions,
            scanner.key,
            scanner.rank_field,
            scanner.rank_direction,
            scanner.rank_transform,
        )
    return (
        _custom_conditions(payload),
        "custom",
        payload.rank_field,
        payload.rank_direction,
        RankTransform.RAW,
    )


async def _load_scan_universe(
    payload: ScannerRunRequest,
    client: httpx.AsyncClient,
):
    """Load and optionally restrict the universe consistently for all scan APIs."""

    universe = await Nifty50Universe().load(UpstoxInstrumentMasterProvider(client))
    if not universe:
        raise MarketDataProviderError(
            "Upstox returned no eligible NIFTY 50 equities; the scanner universe could not be loaded"
        )
    if payload.symbols:
        requested = {symbol.strip().upper() for symbol in payload.symbols if symbol.strip()}
        universe = [item for item in universe if item.trading_symbol in requested]
        if not universe:
            raise HTTPException(
                status_code=404,
                detail="None of the requested NSE symbols were found",
            )
    return universe


async def _build_scan_history(
    universe,
    *,
    market_data_token: str,
    api_base_url: str,
    client: httpx.AsyncClient,
    from_date: date,
    to_date: date,
) -> tuple[HistoricalDataService, PrefetchedCandleCache, tuple]:
    """Bulk-load cached candles once instead of opening a DB connection per stock."""

    persistent_cache = DatabaseCandleCache(db)
    instrument_keys = tuple(instrument.instrument_key for instrument in universe)
    cache_key = (
        db.url or db.path,
        from_date.isoformat(),
        to_date.isoformat(),
        instrument_keys,
    )
    memory_entry = _scan_candle_memory.get(cache_key)
    if (
        memory_entry
        and monotonic_time.monotonic() - memory_entry[0]
        < SCAN_CANDLE_MEMORY_TTL_SECONDS
    ):
        cached = {key: list(rows) for key, rows in memory_entry[1].items()}
        checked_through = dict(memory_entry[2])
    else:
        cached, checked_through = await asyncio.to_thread(
            persistent_cache.prefetch,
            instrument_keys,
            from_date,
            to_date,
        )
    scan_cache = PrefetchedCandleCache(persistent_cache, cached, checked_through)
    history = HistoricalDataService(
        UpstoxHistoricalDataProvider(
            market_data_token,
            api_base_url,
            client,
        ),
        scan_cache,
        provider_name="UPSTOX",
    )
    return history, scan_cache, cache_key


def _remember_scan_cache(
    cache_key: tuple,
    scan_cache: PrefetchedCandleCache,
    universe,
    from_date: date,
    to_date: date,
) -> None:
    candles, checked = scan_cache.snapshot(
        [instrument.instrument_key for instrument in universe],
        from_date,
        to_date,
    )
    _scan_candle_memory[cache_key] = (monotonic_time.monotonic(), candles, checked)


def _ndjson(payload: dict) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def _save_scan_snapshot(
    *,
    user_id: int,
    scanner_key: str,
    result: ScanResult,
    rank_field: ConditionField,
    rank_direction,
    rank_transform: RankTransform,
) -> str:
    """Persist one user's latest ranked result for cheap page reads."""

    first_page = rank_and_paginate(
        result,
        rank_field=rank_field,
        rank_direction=rank_direction,
        rank_transform=rank_transform,
        page=1,
        page_size=100,
    )
    ranked_items = list(first_page.items)
    for page_number in range(2, first_page.total_pages + 1):
        ranked_items.extend(
            rank_and_paginate(
                result,
                rank_field=rank_field,
                rank_direction=rank_direction,
                rank_transform=rank_transform,
                page=page_number,
                page_size=100,
            ).items
        )
    scan_id = uuid4().hex
    item_rows = [
        (
            scan_id,
            item.rank,
            json.dumps(
                _match_payload(
                    item.match,
                    rank=item.rank,
                    rank_value_=item.rank_value,
                ),
                separators=(",", ":"),
            ),
        )
        for item in ranked_items
    ]
    with db.transaction() as connection:
        # One bounded snapshot per user avoids unbounded candle-scan history.
        connection.execute("DELETE FROM scanner_runs WHERE user_id = ?", (user_id,))
        connection.execute(
            """INSERT INTO scanner_runs
               (id, user_id, scanner_key, total_matches, total_instruments,
                evaluated, skipped_count, skip_reasons_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id,
                user_id,
                scanner_key,
                result.matched,
                result.total_instruments,
                result.evaluated,
                result.skipped_count,
                json.dumps(result.skip_reasons, separators=(",", ":")),
            ),
        )
        if item_rows:
            connection.executemany(
                "INSERT INTO scanner_run_results (scan_id, rank, item_json) VALUES (?, ?, ?)",
                item_rows,
            )
    return scan_id


def _snapshot_page(scan_id: str, user_id: int, page: int, page_size: int) -> dict:
    with db.connect() as connection:
        run = connection.execute(
            "SELECT * FROM scanner_runs WHERE id = ? AND user_id = ?",
            (scan_id, user_id),
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Scanner result has expired; run it again")
        total_pages = max(1, math.ceil(int(run["total_matches"]) / page_size))
        if page > total_pages:
            raise HTTPException(
                status_code=400,
                detail=f"page {page} is out of range; the result has {total_pages} page(s)",
            )
        rows = connection.execute(
            """SELECT item_json FROM scanner_run_results
               WHERE scan_id = ? ORDER BY rank LIMIT ? OFFSET ?""",
            (scan_id, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "scan_id": scan_id,
        "scanner_key": run["scanner_key"],
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_matches": int(run["total_matches"]),
        "total_instruments": int(run["total_instruments"]),
        "evaluated": int(run["evaluated"]),
        "skipped_count": int(run["skipped_count"]),
        "skip_reasons": json.loads(run["skip_reasons_json"]),
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "items": [json.loads(row["item_json"]) for row in rows],
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
        universe = await _load_scan_universe(payload, client)
        to_date = _completed_through()
        from_date = to_date - timedelta(days=430)
        history, scan_cache, cache_key = await _build_scan_history(
            universe,
            market_data_token=market_data_token,
            api_base_url=settings.upstox_api_base_url,
            client=client,
            from_date=from_date,
            to_date=to_date,
        )
        engine = ScannerEngine(history)

        conditions, scanner_key, rank_field, rank_direction, rank_transform = _scan_plan(payload)
        try:
            result = await engine.scan(
                universe,
                conditions,
                from_date=from_date,
                to_date=to_date,
                refresh=payload.refresh,
            )
        finally:
            await asyncio.to_thread(scan_cache.flush, provider="UPSTOX")
            _remember_scan_cache(cache_key, scan_cache, universe, from_date, to_date)
        page = rank_and_paginate(
            result,
            rank_field=rank_field,
            rank_direction=rank_direction,
            rank_transform=rank_transform,
            page=payload.page,
            page_size=payload.page_size,
        )
        return page, scanner_key


async def _stream_scan(
    payload: ScannerRunRequest,
    *,
    user_id: int,
    market_data_token: str,
    api_base_url: str,
) -> AsyncIterator[bytes]:
    """Stream scan progress and matches, then emit one ranked page."""

    conditions, scanner_key, rank_field, rank_direction, rank_transform = _scan_plan(payload)
    yield _ndjson({"type": "state", "stage": "loading_universe"})

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            universe = await _load_scan_universe(payload, client)

            yield _ndjson(
                {
                    "type": "started",
                    "scanner_key": scanner_key,
                    "total_instruments": len(universe),
                    "page": payload.page,
                    "page_size": payload.page_size,
                }
            )

            to_date = _completed_through()
            from_date = to_date - timedelta(days=430)
            history, scan_cache, cache_key = await _build_scan_history(
                universe,
                market_data_token=market_data_token,
                api_base_url=api_base_url,
                client=client,
                from_date=from_date,
                to_date=to_date,
            )
            engine = ScannerEngine(history)
            outcomes: list[ScanMatch | ScanSkip | None] = []
            match_count = 0
            skipped_count = 0

            try:
                async for instrument, outcome in engine.scan_outcomes(
                    universe,
                    conditions,
                    from_date=from_date,
                    to_date=to_date,
                    refresh=payload.refresh,
                ):
                    outcomes.append(outcome)
                    event = {
                        "type": "progress",
                        "symbol": instrument.trading_symbol,
                        "completed": len(outcomes),
                        "total_instruments": len(universe),
                        "evaluated": len(outcomes) - skipped_count,
                        "match_count": match_count,
                        "skipped_count": skipped_count,
                        "status": "no_match",
                    }
                    if isinstance(outcome, ScanSkip):
                        skipped_count += 1
                        event.update(
                            {
                                "evaluated": len(outcomes) - skipped_count,
                                "skipped_count": skipped_count,
                                "status": "skipped",
                            }
                        )
                    elif isinstance(outcome, ScanMatch):
                        match_count += 1
                        event.update(
                            {
                                "match_count": match_count,
                                "status": "match",
                                "item": _match_payload(
                                    outcome,
                                    rank=match_count,
                                    rank_value_=rank_value(
                                        outcome.indicators,
                                        field=rank_field,
                                        transform=rank_transform,
                                    ),
                                ),
                            }
                        )
                    yield _ndjson(event)
            finally:
                await asyncio.to_thread(scan_cache.flush, provider="UPSTOX")
                _remember_scan_cache(cache_key, scan_cache, universe, from_date, to_date)

            result = engine.build_result(universe, outcomes)
            scan_id = await asyncio.to_thread(
                _save_scan_snapshot,
                user_id=user_id,
                scanner_key=scanner_key,
                result=result,
                rank_field=rank_field,
                rank_direction=rank_direction,
                rank_transform=rank_transform,
            )
            page = rank_and_paginate(
                result,
                rank_field=rank_field,
                rank_direction=rank_direction,
                rank_transform=rank_transform,
                page=payload.page,
                page_size=payload.page_size,
            )
            yield _ndjson(
                {
                    "type": "complete",
                    "result": _page_payload(page, scanner_key, scan_id=scan_id),
                }
            )
    except asyncio.CancelledError:
        raise
    except HTTPException as exc:
        yield _ndjson({"type": "error", "detail": str(exc.detail)})
    except (ConditionValidationError, PaginationError, ValueError) as exc:
        yield _ndjson({"type": "error", "detail": str(exc)})
    except MarketDataProviderError as exc:
        yield _ndjson({"type": "error", "detail": str(exc)})
    except Exception:
        yield _ndjson(
            {"type": "error", "detail": "Scanner stream failed unexpectedly"}
        )


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


@router.post("/run/stream")
async def stream_scanner(payload: ScannerRunRequest, user=Depends(get_current_user)):
    """Return newline-delimited scan events as each NIFTY 50 stock completes."""

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
    # Validate the selected preset/custom conditions before response headers are
    # sent; runtime provider errors are delivered as terminal stream events.
    _scan_plan(payload)
    return StreamingResponse(
        _stream_scan(
            payload,
            user_id=user["id"],
            market_data_token=market_data_token,
            api_base_url=settings.upstox_api_base_url,
        ),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{scan_id}")
async def scanner_result_page(
    scan_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=25),
    user=Depends(get_current_user),
):
    """Read one ranked page without recomputing market indicators."""

    return await asyncio.to_thread(
        _snapshot_page, scan_id, user["id"], page, page_size
    )


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
        refresh=False,
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
