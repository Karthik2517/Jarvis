from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..schemas import Side


@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str
    average_price: float | None
    filled_quantity: int = 0


@dataclass(frozen=True)
class BrokerOrderStatus:
    status: str
    filled_quantity: int
    average_price: float | None
    rejection_reason: str | None = None


class BrokerAdapter(ABC):
    name: str

    @abstractmethod
    def place_market_order(self, symbol: str, side: Side, quantity: int) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def quote(self, symbol: str) -> float:
        raise NotImplementedError

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        raise RuntimeError(f"Order reconciliation is not supported by {self.name}")
