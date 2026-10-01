from .base import BrokerAdapter
from .paper import PaperBroker
from .upstox import UpstoxBroker


class BrokerFactory:
    @classmethod
    def create(cls, name: str) -> BrokerAdapter:
        normalized = name.upper()
        if normalized == "PAPER":
            return PaperBroker()
        if normalized in {"UPSTOX", "UPSTOX_SANDBOX", "UPSTOX_LIVE"}:
            mode = "UPSTOX_LIVE" if normalized in {"UPSTOX", "UPSTOX_LIVE"} else normalized
            return UpstoxBroker(mode)
        raise ValueError(f"Unsupported broker: {name}")
