from dataclasses import dataclass

from ..config import get_settings
from ..schemas import Side


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str | None = None


class RiskEngine:
    def check(self, *, side: Side, quantity: int, price: float, current_quantity: int) -> RiskDecision:
        settings = get_settings()
        if quantity <= 0:
            return RiskDecision(False, "Quantity must be positive")
        if price <= 0:
            return RiskDecision(False, "A valid market price is unavailable")
        if quantity > settings.max_order_quantity:
            return RiskDecision(False, f"Quantity exceeds limit of {settings.max_order_quantity}")
        if quantity * price > settings.max_order_notional:
            return RiskDecision(False, f"Order notional exceeds limit of INR {settings.max_order_notional:,.0f}")
        if side == Side.SELL and not settings.allow_short_selling and quantity > current_quantity:
            return RiskDecision(False, "Short selling is disabled")
        return RiskDecision(True)
