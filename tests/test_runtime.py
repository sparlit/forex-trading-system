from __future__ import annotations

from src.application.runtime import EAQTSRuntime, RuntimeConfig
from src.orch.trading_control import AdmissionDecision


def test_paper_runtime_admits_and_executes_after_quote(tmp_path):
    runtime = EAQTSRuntime(RuntimeConfig(max_spread_bps=20), event_db=tmp_path / "events.db")
    runtime.ingest_quote("EURUSD", 1.1000, 1.1001)

    _, decision, reasons = runtime.submit_intent(
        symbol="EURUSD",
        direction="long",
        strategy_id="trend",
        entry_price=1.1001,
        stop_price=1.0990,
        target_price=1.1020,
        quantity=10_000,
        risk_amount=100,
        capital_allocation=1_000,
        expected_value=10,
        probability=0.6,
        decision_snapshot_id="snapshot-1",
    )

    assert decision is AdmissionDecision.ADMIT, reasons
    assert len(runtime.snapshot()["positions"]) == 1


def test_runtime_defers_without_a_quote(tmp_path):
    runtime = EAQTSRuntime(event_db=tmp_path / "events.db")
    _, decision, reasons = runtime.submit_intent(
        symbol="EURUSD",
        direction="long",
        strategy_id="trend",
        entry_price=1.1,
        stop_price=1.09,
        target_price=1.12,
        quantity=1_000,
        risk_amount=100,
        capital_allocation=1_000,
        expected_value=10,
        probability=0.6,
        decision_snapshot_id="snapshot-1",
    )

    assert decision is AdmissionDecision.DEFER
    assert any("unknown" in reason for reason in reasons)
