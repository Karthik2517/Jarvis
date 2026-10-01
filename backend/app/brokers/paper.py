import uuid

from ..instruments import find_instrument
from ..schemas import Side
from .base import BrokerAdapter, BrokerOrderResult


class PaperBroker(BrokerAdapter):
    name = "PAPER"

    def quote(self, symbol: str) -> float:
        instrument = find_instrument(symbol)
        if not instrument:
            raise ValueError(f"Unknown instrument: {symbol}")
        return float(instrument["price"])

    def place_market_order(self, symbol: str, side: Side, quantity: int) -> BrokerOrderResult:
        price = self.quote(symbol)
        return BrokerOrderResult(
            broker_order_id=f"PAPER-{uuid.uuid4().hex[:12].upper()}",
            status="FILLED",
            average_price=price,
            filled_quantity=quantity,
        )
