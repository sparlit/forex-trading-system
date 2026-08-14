"""Tests for TCA analysis utilities."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.tca.analysis import log_order, compute_metrics, reset, record_metrics


def test_compute_metrics_basic():
    reset()
    log_order({"price": 100.0, "mid_price": 100.5, "filled": True})
    log_order({"price": 101.0, "mid_price": 100.5, "filled": False})
    slippage, fill_rate = compute_metrics()
    assert abs(slippage - 0.5) < 1e-6
    assert abs(fill_rate - 0.5) < 1e-6


def test_record_metrics_calls_prometheus(monkeypatch):
    # Prepare known orders
    reset()
    log_order({"price": 100.0, "mid_price": 100.5, "filled": True})
    log_order({"price": 101.0, "mid_price": 100.5, "filled": False})
    # Mock the Prometheus client function
    called = {}
    def fake_record(slippage, fill_rate):
        called["slippage"] = slippage
        called["fill_rate"] = fill_rate
    monkeypatch.setattr('src.monitoring.prometheus_client.record_tca_metrics', fake_record)
    record_metrics()
    assert "slippage" in called and "fill_rate" in called
    assert abs(called["slippage"] - 0.5) < 1e-6
    assert abs(called["fill_rate"] - 0.5) < 1e-6
