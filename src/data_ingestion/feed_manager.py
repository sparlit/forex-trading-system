"""Data ingestion feed manager.
Selects appropriate feed implementation (MT5 or CCXT) based on configuration.
Provides a unified `get_latest(symbol)` that returns a dict with `bid`, `ask`, `last`, `time`, `volume`.
If a feed is disabled, returns a synthetic placeholder.
"""

from typing import Any

from src.data_ingestion.ccxt_feed import get_latest_ticker as ccxt_get_latest

# Import concrete feed implementations (may be dummy if dependencies missing)
from src.data_ingestion.mt5_feed import get_latest_tick as mt5_get_latest
from src.infra.config.settings import Settings

_settings = Settings()

def get_latest(symbol: str) -> dict[str, Any]:
    """Return latest market data for *symbol*.
    Preference order:
    1. MT5 if enabled
    2. CCXT if enabled
    3. Synthetic fallback (mt5_get_latest will already fallback)
    """
    if _settings.mt5_enabled:
        # MT5 feed expects symbol only
        try:
            return mt5_get_latest(symbol)
        except Exception:
            # Log suppressed for brevity; fall back to next source
            pass
    if _settings.ccxt_enabled:
        # Choose first enabled exchange for the symbol (simple heuristic)
        exchange = _settings.ccxt_exchanges[0] if _settings.ccxt_exchanges else "binance"
        try:
            return ccxt_get_latest(exchange, symbol)
        except Exception:
            pass
    # Final fallback – synthetic stub via MT5 function
    return mt5_get_latest(symbol)
