"""MT5 data feed implementation.
Uses the MetaTrader5 Python package to fetch the latest tick for a symbol.
If MT5 cannot be initialized (e.g., library missing, terminal not running),
falls back to a deterministic synthetic tick based on the symbol name.
"""

import datetime
import hashlib
from typing import Any

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover
    mt5 = None

# Simple deterministic synthetic data – used when MT5 is unavailable
def _synthetic_tick(symbol: str) -> dict[str, Any]:
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    # Deterministic base price from symbol hash
    base_int = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
    base = 1.0 + (base_int % 1000) / 1000.0
    return {
        "symbol": symbol,
        "bid": round(base, 5),
        "ask": round(base + 0.0001, 5),
        "last": round(base + 0.00005, 5),
        "time": now,
        "volume": 1000,
    }


def get_latest_tick(symbol: str) -> dict[str, Any]:
    """Return the latest tick for *symbol* using MT5.
    Initializes MT5 on first call; shuts down after the request to avoid
    lingering connections in short‑lived processes.
    """
    if not mt5:
        return _synthetic_tick(symbol)

    # Attempt to initialize MT5 – reuse if already initialized
    if not mt5.initialize():
        # Initialization failed; fallback to synthetic
        return _synthetic_tick(symbol)
    try:
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return _synthetic_tick(symbol)
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "time": datetime.datetime.fromtimestamp(tick.time, tz=datetime.timezone.utc),
            "volume": tick.volume,
        }
    finally:
        # Clean shutdown to keep the process tidy
        mt5.shutdown()
