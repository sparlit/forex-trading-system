"""CCXT data feed implementation.
Wraps the CCXT library to fetch the latest ticker for a symbol on a given exchange.
If CCXT is unavailable or the exchange cannot be instantiated, falls back to a deterministic synthetic tick.
"""

import datetime
import hashlib
from typing import Any

try:
    import ccxt  # type: ignore
except Exception:  # pragma: no cover
    ccxt = None

def _synthetic_ticker(exchange_name: str, symbol: str) -> dict[str, Any]:
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    base_int = int(hashlib.sha256((exchange_name + symbol).encode()).hexdigest()[:8], 16)
    base = 10.0 + (base_int % 1000) / 1000.0
    return {
        "symbol": symbol,
        "exchange": exchange_name,
        "bid": round(base, 5),
        "ask": round(base + 0.01, 5),
        "last": round(base + 0.005, 5),
        "time": now,
        "volume": 5000,
    }


def get_latest_ticker(exchange_name: str, symbol: str) -> dict[str, Any]:
    """Return the latest ticker for *symbol* on *exchange_name* using CCXT.
    If the library or exchange cannot be used, returns a synthetic placeholder.
    """
    if not ccxt:
        return _synthetic_ticker(exchange_name, symbol)
    exchange_cls = getattr(ccxt, exchange_name, None)
    if not exchange_cls:
        return _synthetic_ticker(exchange_name, symbol)
    exch = exchange_cls()
    try:
        ticker = exch.fetch_ticker(symbol)
        if not ticker:
            return _synthetic_ticker(exchange_name, symbol)
        return {
            "symbol": symbol,
            "exchange": exchange_name,
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "last": ticker.get("last"),
            "time": datetime.datetime.fromtimestamp(ticker.get("timestamp", 0) / 1000, tz=datetime.timezone.utc) if ticker.get("timestamp") else datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc),
            "volume": ticker.get("baseVolume"),
        }
    finally:
        # Ensure any resources are cleaned up – CCXT doesn't need explicit close,
        # but we call ``close`` if present for consistency.
        close_fn = getattr(exch, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass
