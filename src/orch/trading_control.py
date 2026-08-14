"""Canonical, fail-closed trade-admission control chain.

This module is deliberately independent of models, brokers, and optimisers.  It
implements the final authority boundary described in EAQTS 2.4 sections 16,
20--23 and 59: a prediction can create an intent, but only an explicitly
complete and independently verified admission can authorise execution.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.orch.event_bus import Event, EventBus, EventStore


class SystemState(StrEnum):
    """Safety states ordered by the authority they permit."""

    NORMAL = "NORMAL"
    UNKNOWN = "UNKNOWN"
    INFORMATION_DEGRADED = "INFORMATION_DEGRADED"
    RESTRICTED = "RESTRICTED"
    DEFENSIVE = "DEFENSIVE"
    HALTED = "HALTED"
    RECOVERY = "RECOVERY"


class AdmissionDecision(StrEnum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    DEFER = "DEFER"
    EXPIRE = "EXPIRE"


@dataclass(frozen=True, slots=True)
class CanonicalTradingIntent:
    """The immutable execution candidate consumed by every downstream gate."""

    intent_id: str
    symbol: str
    direction: str
    strategy_id: str
    style: str
    timeframe: str
    probability: float
    expected_value: float
    entry_price: float
    stop_price: float
    target_price: float
    position_size: float
    risk_amount: float
    capital_allocation: float
    decision_snapshot_id: str
    created_at: datetime
    expires_at: datetime
    model_versions: tuple[str, ...] = ()
    strategy_version: str = ""
    feature_version: str = ""

    def validate(self, now: datetime) -> tuple[str, ...]:
        """Return deterministic validation failures; an empty tuple is valid."""
        reasons: list[str] = []
        if not self.intent_id or not self.decision_snapshot_id:
            reasons.append("intent and decision snapshot identifiers are required")
        if self.direction not in {"long", "short"}:
            reasons.append("direction must be long or short")
        if not 0.0 <= self.probability <= 1.0:
            reasons.append("probability is outside [0, 1]")
        if self.expected_value <= 0:
            reasons.append("expected value is not positive")
        if min(self.entry_price, self.stop_price, self.target_price, self.position_size) <= 0:
            reasons.append("prices and position size must be positive")
        if self.risk_amount <= 0 or self.capital_allocation <= 0:
            reasons.append("risk and capital allocation must be positive")
        if self.direction == "long" and not self.stop_price < self.entry_price < self.target_price:
            reasons.append("long stop/entry/target ordering is invalid")
        if self.direction == "short" and not self.target_price < self.entry_price < self.stop_price:
            reasons.append("short target/entry/stop ordering is invalid")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            reasons.append("intent timestamps must be timezone-aware")
        elif now >= self.expires_at:
            reasons.append("intent has expired")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    """Authoritative gate results supplied by the owning planes.

    ``None`` means unavailable/unknown and is intentionally rejected.  This
    prevents accidental permission being inferred from omitted integrations.
    """

    system_state: SystemState
    legal_permitted: bool | None
    broker_permitted: bool | None
    data_valid: bool | None
    data_fresh: bool | None
    strategy_licensed: bool | None
    model_eligible: bool | None
    liquidity_adequate: bool | None
    capacity_available: bool | None
    capital_reserved: bool | None
    risk_approved: bool | None
    safety_approved: bool | None
    compliance_approved: bool | None
    rate_limit_available: bool | None
    order_valid: bool | None
    market_state: Mapping[str, Any] = field(default_factory=dict)
    invariant_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdmissionOutcome:
    intent_id: str
    decision: AdmissionDecision
    reasons: tuple[str, ...]
    correlation_id: str
    decided_at: datetime


RiskVerifier = Callable[[CanonicalTradingIntent, AdmissionContext], tuple[bool, str]]
InvariantVerifier = Callable[[Mapping[str, Any]], list[Any]]


class TradeControlChain:
    """The sole final authorisation boundary for new risk.

    The chain emits durable events synchronously.  It never submits an order;
    callers may invoke execution only after receiving ``ADMIT``.
    """

    _REQUIRED_GATES = (
        "legal_permitted",
        "broker_permitted",
        "data_valid",
        "data_fresh",
        "strategy_licensed",
        "model_eligible",
        "liquidity_adequate",
        "capacity_available",
        "capital_reserved",
        "risk_approved",
        "safety_approved",
        "compliance_approved",
        "rate_limit_available",
        "order_valid",
    )

    def __init__(
        self,
        *,
        event_store: EventStore,
        event_bus: EventBus | None = None,
        invariant_verifier: InvariantVerifier | None = None,
        risk_verifier: RiskVerifier | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._invariant_verifier = invariant_verifier
        self._risk_verifier = risk_verifier
        self._clock = clock or (lambda: datetime.now(UTC))

    def evaluate(self, intent: CanonicalTradingIntent, context: AdmissionContext) -> AdmissionOutcome:
        now = self._clock()
        correlation_id = intent.intent_id or str(uuid4())
        reasons = list(intent.validate(now))

        if context.system_state is not SystemState.NORMAL:
            reasons.append(f"system state {context.system_state.value} blocks new risk")
        for gate in self._REQUIRED_GATES:
            value = getattr(context, gate)
            if value is not True:
                reasons.append(f"{gate} is {'unknown' if value is None else 'not approved'}")

        if not reasons and self._invariant_verifier is not None:
            results = self._invariant_verifier(context.invariant_context)
            failures = [result for result in results if not getattr(result, "passed", False)]
            reasons.extend(
                f"safety invariant {getattr(result, 'invariant_id', 'unknown')} failed: "
                f"{getattr(result, 'violation_reason', 'no reason')}"
                for result in failures
            )

        if not reasons:
            if self._risk_verifier is None:
                reasons.append("independent risk verifier is unavailable")
            else:
                approved, reason = self._risk_verifier(intent, context)
                if not approved:
                    reasons.append(f"independent risk verification rejected: {reason}")

        decision = self._decision_for(reasons)
        outcome = AdmissionOutcome(
            intent_id=intent.intent_id,
            decision=decision,
            reasons=tuple(reasons),
            correlation_id=correlation_id,
            decided_at=now,
        )
        self._record(intent, outcome)
        return outcome

    @staticmethod
    def _decision_for(reasons: list[str]) -> AdmissionDecision:
        if not reasons:
            return AdmissionDecision.ADMIT
        if any("expired" in reason for reason in reasons):
            return AdmissionDecision.EXPIRE
        if any("unknown" in reason or "unavailable" in reason for reason in reasons):
            return AdmissionDecision.DEFER
        return AdmissionDecision.REJECT

    def _record(self, intent: CanonicalTradingIntent, outcome: AdmissionOutcome) -> None:
        intent_event = Event(
            source="trade_control_chain",
            event_type="TradingIntentCreated",
            correlation_id=outcome.correlation_id,
            payload={"intent_id": intent.intent_id, "decision_snapshot_id": intent.decision_snapshot_id},
        )
        result_event = Event(
            source="trade_control_chain",
            event_type=("TradeAdmissionApproved" if outcome.decision is AdmissionDecision.ADMIT else "TradeAdmissionRejected"),
            correlation_id=outcome.correlation_id,
            causation_id=str(intent_event.event_id),
            payload={
                "intent_id": outcome.intent_id,
                "decision": outcome.decision.value,
                "reasons": list(outcome.reasons),
            },
        )
        for event in (intent_event, result_event):
            self._event_store.append(event)
            if self._event_bus is not None:
                self._event_bus.publish(event)
