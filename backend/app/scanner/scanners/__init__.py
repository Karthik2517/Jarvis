"""Built-in scanner definitions and their stable v1 registry."""

from .base import RankDirection, RankTransform, ScannerDefinition
from .breakout import fifty_two_week_high_breakout, fifty_two_week_low
from .momentum import rsi_scanner
from .trend import price_above_smas
from .volume import volume_breakout


def default_scanners() -> dict[str, ScannerDefinition]:
    scanners = (
        fifty_two_week_high_breakout(),
        fifty_two_week_low(),
        volume_breakout(),
        price_above_smas(),
        rsi_scanner(),
    )
    return {scanner.key: scanner for scanner in scanners}


__all__ = [
    "RankDirection",
    "RankTransform",
    "ScannerDefinition",
    "default_scanners",
    "fifty_two_week_high_breakout",
    "fifty_two_week_low",
    "price_above_smas",
    "rsi_scanner",
    "volume_breakout",
]
