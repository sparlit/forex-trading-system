"""Import tests for real data feed adapters (MT5 and CCXT)."""
import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_mt5_feed_import():
    from src.data_ingestion.mt5_feed import get_latest_tick
    # Call with a dummy symbol – should return a dict (real or synthetic)
    tick = get_latest_tick("EURUSD")
    assert isinstance(tick, dict)
    assert "symbol" in tick and tick["symbol"] == "EURUSD"

def test_ccxt_feed_import():
    from src.data_ingestion.ccxt_feed import get_latest_ticker
    # Use first exchange from settings (fallback to "binance")
    ticker = get_latest_ticker("binance", "BTC/USDT")
    assert isinstance(ticker, dict)
    assert ticker["symbol"] == "BTC/USDT"
    assert "exchange" in ticker and ticker["exchange"] == "binance"
