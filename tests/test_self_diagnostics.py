"""Tests for self‑diagnostics health checks and recovery handling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.self_diagnostics.health import run_checks
from src.self_diagnostics.recovery import handle_failure, RestartSignal


def test_run_checks_healthy():
    class MockBus:
        def publish(self, *_, **__):
            pass
    class MockMarketState:
        def get_state(self):
            return {}
    bus = MockBus()
    market_state = MockMarketState()
    result = run_checks(bus, market_state)
    assert result["bus"] is True
    assert result["market_state"] is True


def test_handle_failure_raises_and_stops_bus():
    class MockBus:
        def __init__(self):
            self.stopped = False
        def stop(self):
            self.stopped = True
    bus = MockBus()
    try:
        handle_failure(bus, "test failure")
    except RestartSignal as e:
        assert str(e) == "test failure"
    else:
        assert False, "RestartSignal not raised"
    assert bus.stopped is True
