# safety/state_machine.py
"""Safety State Machine
Implements deterministic state transitions for the trading system based on a small set of health metrics.
The implementation is deliberately lightweight – it does not depend on external services and can be unit‑tested in isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class SafetyState(Enum):
    NORMAL = auto()
    CAUTION = auto()
    RESTRICTED = auto()
    DEFENSIVE = auto()
    HALTED = auto()
    RECOVERY = auto()


@dataclass(slots=True)
class SafetyStateMachine:
    """Manage safety state transitions.

    The machine tracks a set of health metrics (drawdown, liquidity, model health, broker health,
    data health, execution quality, security state). External callers should invoke ``evaluate``
    with the latest metric snapshot; the method updates the internal state according to the guard
    conditions defined in the spec.
    """

    # Current state – defaults to NORMAL.
    current_state: SafetyState = SafetyState.NORMAL

    # The last observed metrics – stored to allow transition logic that depends on historical values.
    metrics: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------------------
    # Public interface
    # ---------------------------------------------------------------------
    def get_state(self) -> SafetyState:
        return self.current_state

    def set_state(self, new_state: SafetyState) -> None:
        if not isinstance(new_state, SafetyState):
            raise ValueError("new_state must be a SafetyState enum value")
        logger.info(f"SafetyStateMachine transitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state

    def can_trade(self) -> bool:
        """Return ``True`` if trading is permitted in the current state.
        HALTED, DEFENSIVE and RECOVERY block trading entirely.
        """
        return self.current_state not in {SafetyState.HALTED, SafetyState.DEFENSIVE, SafetyState.RECOVERY}

    def risk_multiplier(self) -> float:
        """Position‑size multiplier according to the current state.
        """
        mapping = {
            SafetyState.NORMAL: 1.0,
            SafetyState.CAUTION: 0.5,
            SafetyState.RESTRICTED: 0.25,
            SafetyState.DEFENSIVE: 0.0,
            SafetyState.HALTED: 0.0,
            SafetyState.RECOVERY: 0.0,
        }
        return mapping[self.current_state]

    # ---------------------------------------------------------------------
    # Evaluation logic – feed a fresh metric snapshot and the machine will decide on
    # a possibly new state. This is deterministic: identical input produces identical
    # output.
    # ---------------------------------------------------------------------
    def evaluate(self, new_metrics: dict[str, Any]) -> None:
        """Update internal metrics and transition to a new state if guard conditions fire.

        Expected keys in ``new_metrics`` (all optional, missing values are ignored):
        - ``drawdown`` (float, absolute % e.g. 0.06 for 6%)
        - ``liquidity_score`` (float 0..1)
        - ``model_health`` (bool)
        - ``broker_health`` (bool)
        - ``data_freshness_seconds`` (int)
        - ``execution_quality`` (float 0..1)
        - ``security_state_ok`` (bool)
        """
        self.metrics.update(new_metrics)
        d = self.metrics

        # Helper predicates – we only evaluate a guard if the required metric is present.
        def drawdown_gt(pct: float) -> bool:
            return isinstance(d.get("drawdown"), (int, float)) and d["drawdown"] > pct

        def liquidity_lt(threshold: float) -> bool:
            return isinstance(d.get("liquidity_score"), (int, float)) and d["liquidity_score"] < threshold

        # Guard conditions – ordered from most severe to least.
        # 1. Immediate HALTED if catastrophic drawdown > 20% or data older than 30 seconds.
        if drawdown_gt(0.20) or (
            isinstance(d.get("data_freshness_seconds"), int)
            and d["data_freshness_seconds"] > 30
        ):
            self.set_state(SafetyState.HALTED)
            return

        # 2. DEFENSIVE if model or broker health is bad.
        if d.get("model_health") is False or d.get("broker_health") is False:
            self.set_state(SafetyState.DEFENSIVE)
            return

        # 3. RESTRICTED if drawdown > 5% OR liquidity < 0.3.
        if drawdown_gt(0.05) or liquidity_lt(0.30):
            self.set_state(SafetyState.RESTRICTED)
            return

        # 4. CAUTION if drawdown > 2% OR liquidity < 0.5.
        if drawdown_gt(0.02) or liquidity_lt(0.50):
            self.set_state(SafetyState.CAUTION)
            return

        # 5. RECOVERY – enters after being in HALTED/DEFENSIVE/RESTRICTED and metrics have
        #    improved for a configurable number of consecutive evaluations. For simplicity we
        #    detect a clear positive trend: drawdown < 1% and liquidity > 0.8.
        if (
            self.current_state in {SafetyState.HALTED, SafetyState.DEFENSIVE, SafetyState.RESTRICTED}
            and d.get("drawdown", 0) < 0.01
            and d.get("liquidity_score", 1) > 0.80
        ):
            self.set_state(SafetyState.RECOVERY)
            return

        # Default: NORMAL.
        self.set_state(SafetyState.NORMAL)

    # ---------------------------------------------------------------------
    # Convenience aliases for clearer external calls.
    # ---------------------------------------------------------------------
    # expose State enum for callers that want ``SafetyStateMachine.State`` similar to spec
    class State:
        NORMAL = SafetyState.NORMAL
        CAUTION = SafetyState.CAUTION
        RESTRICTED = SafetyState.RESTRICTED
        DEFENSIVE = SafetyState.DEFENSIVE
        HALTED = SafetyState.HALTED
        RECOVERY = SafetyState.RECOVERY
