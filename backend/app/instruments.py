INSTRUMENTS = [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "exchange": "NSE", "price": 2984.40},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "exchange": "NSE", "price": 4216.75},
    {"symbol": "INFY", "name": "Infosys", "exchange": "NSE", "price": 1886.20},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "exchange": "NSE", "price": 1732.55},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "exchange": "NSE", "price": 1298.80},
    {"symbol": "SBIN", "name": "State Bank of India", "exchange": "NSE", "price": 812.35},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "exchange": "NSE", "price": 1684.10},
    {"symbol": "ITC", "name": "ITC", "exchange": "NSE", "price": 474.65},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India", "exchange": "NSE", "price": 12360.00},
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "exchange": "NSE", "price": 781.25},
]

_DYNAMIC_INSTRUMENTS: dict[str, dict] = {}


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("NSE:", "")


def find_instrument(symbol: str) -> dict | None:
    normalized = normalize_symbol(symbol)
    return _DYNAMIC_INSTRUMENTS.get(normalized) or next(
        (item for item in INSTRUMENTS if item["symbol"] == normalized), None
    )


def register_instruments(instruments: list[dict]) -> None:
    """Cache searched instruments so the paper broker can execute them at the fetched LTP."""
    for instrument in instruments:
        if instrument.get("symbol") and instrument.get("price") is not None:
            _DYNAMIC_INSTRUMENTS[normalize_symbol(instrument["symbol"])] = instrument


def search_local_instruments(query: str, limit: int = 10) -> list[dict]:
    term = query.strip().lower()
    matches = [
        {**item, "instrument_key": None, "source": "PAPER", "previous_close": item["price"], "change_percent": 0.0}
        for item in INSTRUMENTS
        if not term or term in item["symbol"].lower() or term in item["name"].lower()
    ]
    return matches[:limit]
