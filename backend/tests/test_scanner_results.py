from datetime import date

import pytest

from app.market_data.models import Instrument
from app.scanner.conditions import ConditionField
from app.scanner.indicators import IndicatorSnapshot
from app.scanner.results import PaginationError, paginate_preset_result, rank_and_paginate
from app.scanner.scanner_engine import ScanMatch, ScanResult
from app.scanner.scanners import RankDirection, price_above_smas, rsi_scanner


def instrument(symbol: str) -> Instrument:
    return Instrument(
        instrument_key=f"NSE_EQ|{symbol}",
        trading_symbol=symbol,
        name=symbol,
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        security_type="NORMAL",
    )


def snapshot(*, price=150.0, sma200=100.0, rsi14=55.0) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        price=price,
        volume=2000,
        sma20=140.0,
        sma50=130.0,
        sma200=sma200,
        avg_volume_20=1000.0,
        volume_ratio=2.0,
        rsi14=rsi14,
        prior_52w_high=149.0,
        prior_52w_low=90.0,
        breakout_percent=0.67,
        breakdown_percent=-40.0,
    )


def match(symbol: str, **snapshot_values) -> ScanMatch:
    return ScanMatch(
        instrument=instrument(symbol),
        data_as_of=date(2026, 9, 30),
        indicators=snapshot(**snapshot_values),
        checks=(),
    )


def scan_result(*matches: ScanMatch) -> ScanResult:
    return ScanResult(
        total_instruments=len(matches) + 2,
        evaluated=len(matches) + 1,
        matches=matches,
        skipped=(),
        skip_reasons={"market_data_error": 1},
    )


def test_descending_ranking_uses_symbol_as_stable_tie_breaker():
    result = scan_result(
        match("ZETA", rsi14=60),
        match("ALPHA", rsi14=60),
        match("MID", rsi14=70),
    )
    page = rank_and_paginate(
        result,
        rank_field=ConditionField.RSI14,
        rank_direction=RankDirection.DESCENDING,
    )

    assert [item.match.instrument.trading_symbol for item in page.items] == [
        "MID",
        "ALPHA",
        "ZETA",
    ]
    assert [item.rank for item in page.items] == [1, 2, 3]
    assert [item.rank_value for item in page.items] == [70, 60, 60]


def test_ascending_rsi_ranking_and_pagination_preserve_global_ranks():
    result = scan_result(
        match("FIFTY", rsi14=50),
        match("TEN", rsi14=10),
        match("THIRTY", rsi14=30),
        match("TWENTY", rsi14=20),
        match("FORTY", rsi14=40),
    )
    page = paginate_preset_result(
        result,
        rsi_scanner(55, "<="),
        page=2,
        page_size=2,
    )

    assert page.page == 2
    assert page.total_pages == 3
    assert page.total_matches == 5
    assert page.has_previous is True
    assert page.has_next is True
    assert [item.match.instrument.trading_symbol for item in page.items] == [
        "THIRTY",
        "FORTY",
    ]
    assert [item.rank for item in page.items] == [3, 4]


def test_trend_ranking_uses_percentage_above_sma_not_raw_sma():
    result = scan_result(
        match("NEAR", price=110, sma200=100),
        match("FAR", price=150, sma200=100),
    )
    page = paginate_preset_result(result, price_above_smas())
    assert [item.match.instrument.trading_symbol for item in page.items] == ["FAR", "NEAR"]
    assert page.items[0].rank_value == pytest.approx(50)
    assert page.items[1].rank_value == pytest.approx(10)


def test_empty_results_return_one_empty_page_with_summary():
    result = ScanResult(
        total_instruments=100,
        evaluated=90,
        matches=(),
        skipped=(),
        skip_reasons={"missing_indicator": 10},
    )
    page = rank_and_paginate(result, rank_field=ConditionField.RSI14)
    assert page.page == 1
    assert page.total_pages == 1
    assert page.total_matches == 0
    assert page.items == ()
    assert page.total_instruments == 100
    assert page.evaluated == 90


@pytest.mark.parametrize(
    ("page", "page_size", "message"),
    [
        (0, 10, "page must"),
        (1, 0, "page_size"),
        (1, 101, "page_size"),
        (2, 10, "out of range"),
    ],
)
def test_invalid_pagination_is_rejected(page, page_size, message):
    with pytest.raises(PaginationError, match=message):
        rank_and_paginate(
            scan_result(match("ONLY")),
            rank_field=ConditionField.RSI14,
            page=page,
            page_size=page_size,
        )
