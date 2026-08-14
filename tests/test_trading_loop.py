"""Basic import test for the TradingLoop engine."""

import sys
from pathlib import Path

# Ensure src is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_trading_loop_import():
    from src.trading_loop.engine import TradingLoop
    # Instantiate without running the infinite loop
    tl = TradingLoop()
    assert tl.market_state is not None
    assert tl.opportunity is not None
    assert tl.execution is not None
    # Verify that the EventBus is started
    assert tl.bus._router_process.is_alive()
    # Clean up
    tl.bus.stop()
