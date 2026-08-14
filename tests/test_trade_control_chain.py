from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from src.orch.event_bus import EventStore
from src.orch.trading_control import (
    AdmissionContext,
    AdmissionDecision,
    CanonicalTradingIntent,
    SystemState,
    TradeControlChain,
)


def _intent(now: datetime) -> CanonicalTradingIntent:
    return CanonicalTradingIntent(
        intent_id="intent-1", symbol="EURUSD", direction="long", strategy_id="s-1",
        style="swing", timeframe="H1", probability=0.6, expected_value=1.0,
        entry_price=1.1, stop_price=1.09, target_price=1.12, position_size=1.0,
        risk_amount=10.0, capital_allocation=100.0, decision_snapshot_id="snapshot-1",
        created_at=now, expires_at=now + timedelta(seconds=30), model_versions=("m-1",),
    )


def _context(**overrides: object) -> AdmissionContext:
    values: dict[str, object] = {
        "system_state": SystemState.NORMAL,
        "legal_permitted": True, "broker_permitted": True, "data_valid": True,
        "data_fresh": True, "strategy_licensed": True, "model_eligible": True,
        "liquidity_adequate": True, "capacity_available": True, "capital_reserved": True,
        "risk_approved": True, "safety_approved": True, "compliance_approved": True,
        "rate_limit_available": True, "order_valid": True,
    }
    values.update(overrides)
    return AdmissionContext(**values)  # type: ignore[arg-type]


def test_control_chain_admits_only_after_independent_verification(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = EventStore(tmp_path / "events.db")
    chain = TradeControlChain(
        event_store=store, clock=lambda: now, risk_verifier=lambda intent, context: (True, "ok")
    )

    outcome = chain.evaluate(_intent(now), _context())

    assert outcome.decision is AdmissionDecision.ADMIT
    assert [event.event_type for event in store.get_events_by_correlation_id("intent-1")] == [
        "TradingIntentCreated", "TradeAdmissionApproved"
    ]


def test_control_chain_fails_closed_for_unknown_or_missing_verifier(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    chain = TradeControlChain(event_store=EventStore(tmp_path / "events.db"), clock=lambda: now)

    outcome = chain.evaluate(_intent(now), _context(data_fresh=None))

    assert outcome.decision is AdmissionDecision.DEFER
    assert "data_fresh is unknown" in outcome.reasons
    assert "independent risk verifier is unavailable" not in outcome.reasons


def test_control_chain_expires_old_intents(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    expired = replace(_intent(now - timedelta(minutes=2)), expires_at=now - timedelta(seconds=1))
    chain = TradeControlChain(
        event_store=EventStore(tmp_path / "events.db"), clock=lambda: now,
        risk_verifier=lambda intent, context: (True, "ok"),
    )

    assert chain.evaluate(expired, _context()).decision is AdmissionDecision.EXPIRE
