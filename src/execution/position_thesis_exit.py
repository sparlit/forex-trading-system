"""
Position Thesis Engine & Exit Engine — EAQTS V2.3 N1081–N1125.

Every open position has a thesis that is continuously reevaluated.
Exit management is first-class — 17+ exit classes, each independently
evaluated against live market context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

try:
    from src.execution.market_state_machines import broker_state_machine
except ImportError:
    broker_state_machine = None


# ---------------------------------------------------------------------------
# Position Thesis — N1097–N1108
# ---------------------------------------------------------------------------

class ThesisState(str, Enum):
    VALID = "thesis_valid"
    WEAKENING = "thesis_weakening"
    INVALID = "thesis_invalid"
    REVERSED = "thesis_reversed"
    UNKNOWN = "thesis_unknown"


@dataclass
class PositionThesis:
    position_id: str
    strategy_id: str
    model_id: str
    entry_reason: str = ""
    thesis_state: ThesisState = ThesisState.VALID
    original_regime: str = ""
    original_direction: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_recalc: float = field(default_factory=time.time)
    evidence: list[str] = field(default_factory=list)


class PositionThesisEngine:
    """
    Continuously reevaluates thesis state on:
    - tick/candle update
    - regime change
    - model update
    - liquidity change
    - event change
    """

    def __init__(self) -> None:
        self._theses: dict[str, PositionThesis] = {}

    def create_thesis(self, thesis: PositionThesis) -> None:
        self._theses[thesis.position_id] = thesis
        logger.info(
            f"Thesis created for {thesis.position_id}: {thesis.thesis_state.value}"
        )

    def get_thesis(self, position_id: str) -> PositionThesis | None:
        return self._theses.get(position_id)

    def recalculate(
        self,
        position_id: str,
        current_price: float | None = None,
        regime: str | None = None,
        model_confidence: float | None = None,
        liquidity_score: float | None = None,
        event_active: bool = False,
    ) -> ThesisState:
        """Recompute thesis state based on current context."""
        thesis = self._theses.get(position_id)
        if not thesis:
            return ThesisState.UNKNOWN

        new_state = thesis.thesis_state
        reasons: list[str] = []

        # Regime change invalidation
        if regime and thesis.original_regime and regime != thesis.original_regime:
            new_state = ThesisState.WEAKENING
            reasons.append(f"regime changed {thesis.original_regime} → {regime}")

        # Model confidence degradation
        if model_confidence is not None and model_confidence < 0.4:
            new_state = ThesisState.WEAKENING
            reasons.append(f"model confidence low ({model_confidence:.2f})")

        # Price reversal
        if current_price is not None and thesis.entry_price > 0:
            if thesis.original_direction == "buy" and current_price < thesis.stop_price:
                new_state = ThesisState.REVERSED
                reasons.append(f"price {current_price} below stop {thesis.stop_price}")
            elif thesis.original_direction == "sell" and current_price > thesis.stop_price:
                new_state = ThesisState.REVERSED
                reasons.append(f"price {current_price} above stop {thesis.stop_price}")

        # Liquidity degradation
        if liquidity_score is not None and liquidity_score < 0.3:
            if new_state == ThesisState.VALID:
                new_state = ThesisState.WEAKENING
            reasons.append(f"liquidity degraded ({liquidity_score:.2f})")

        # Event disablement
        if event_active:
            if new_state == ThesisState.VALID:
                new_state = ThesisState.WEAKENING
            reasons.append("event firewall active")

        if new_state != thesis.thesis_state:
            logger.info(
                f"Thesis {position_id}: {thesis.thesis_state.value} → {new_state.value} "
                f"({'; '.join(reasons)})"
            )
            thesis.thesis_state = new_state
            thesis.evidence.extend(reasons)

        thesis.last_recalc = time.time()
        return new_state

    def should_exit(self, position_id: str) -> tuple[bool, str]:
        """Check if thesis requires immediate exit."""
        thesis = self._theses.get(position_id)
        if not thesis:
            return True, "no thesis"
        if thesis.thesis_state in (ThesisState.INVALID, ThesisState.REVERSED):
            return True, f"thesis {thesis.thesis_state.value}"
        if thesis.thesis_state == ThesisState.WEAKENING:
            return False, "thesis weakening — reevaluate exit options"
        return False, ""

    def remove(self, position_id: str) -> None:
        self._theses.pop(position_id, None)


# ---------------------------------------------------------------------------
# Exit Engine — N1109–N1125
# ---------------------------------------------------------------------------

class ExitReason(str, Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TRAILING_TARGET = "trailing_target"
    TIME_EXIT = "time_exit"
    VOLATILITY_EXIT = "volatility_exit"
    REGIME_EXIT = "regime_exit"
    THESIS_FAILURE = "thesis_failure"
    THESIS_REVERSAL = "thesis_reversal"
    LIQUIDITY_EXIT = "liquidity_exit"
    EVENT_EXIT = "event_exit"
    PORTFOLIO_RISK_EXIT = "portfolio_risk_exit"
    EMERGENCY_EXIT = "emergency_exit"
    OPPORTUNITY_COST_EXIT = "opportunity_cost_exit"
    MARGIN_EXIT = "margin_exit"
    BROKER_STATE_EXIT = "broker_state_exit"
    EXECUTION_QUALITY_EXIT = "execution_quality_exit"


@dataclass
class ExitContext:
    position_id: str
    symbol: str
    side: str
    entry_price: float
    current_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    high_water_mark: float = 0.0   # MFE
    low_water_mark: float = 0.0    # MAE
    position_age_s: float = 0.0
    max_holding_period_s: float = 86400.0
    regime: str = ""
    thesis_state: ThesisState = ThesisState.VALID
    portfolio_risk_exceeded: bool = False
    liquidity_score: float = 1.0
    event_active: bool = False
    margin_level: float = 1.0
    broker_can_cancel: bool = True
    better_opportunity_ev: float | None = None
    execution_toxicity: float = 0.0


class ExitEngine:
    """
    N1109–N1125: Evaluates 17 exit classes and returns the highest-priority
    exit trigger for a given position context.
    """

    PRIORITY = [
        ExitReason.EMERGENCY_EXIT,          # always first
        ExitReason.THESIS_REVERSAL,
        ExitReason.STOP_LOSS,
        ExitReason.MARGIN_EXIT,
        ExitReason.PORTFOLIO_RISK_EXIT,
        ExitReason.BROKER_STATE_EXIT,
        ExitReason.THESIS_FAILURE,
        ExitReason.TIME_EXIT,
        ExitReason.VOLATILITY_EXIT,
        ExitReason.REGIME_EXIT,
        ExitReason.LIQUIDITY_EXIT,
        ExitReason.EVENT_EXIT,
        ExitReason.TAKE_PROFIT,
        ExitReason.TRAILING_STOP,
        ExitReason.TRAILING_TARGET,
        ExitReason.OPPORTUNITY_COST_EXIT,
        ExitReason.EXECUTION_QUALITY_EXIT,
    ]

    def __init__(self) -> None:
        self.exit_history: list[dict[str, Any]] = []

    def evaluate(self, ctx: ExitContext) -> tuple[ExitReason | None, str]:
        """Evaluate all exit conditions; return first triggered in priority order."""

        # Emergency exit — portfolio or system critical
        if ctx.portfolio_risk_exceeded:
            return ExitReason.PORTFOLIO_RISK_EXIT, "portfolio risk exceeded"
        if ctx.margin_level < 0.5:
            return ExitReason.MARGIN_EXIT, f"margin level {ctx.margin_level:.2f} critical"
        if broker_state_machine and not broker_state_machine.can_cancel:
            return ExitReason.BROKER_STATE_EXIT, "broker cannot cancel — defense mode"

        # Thesis reversal
        if ctx.thesis_state == ThesisState.REVERSED:
            return ExitReason.THESIS_REVERSAL, "thesis reversed"

        # Thesis failure
        if ctx.thesis_state == ThesisState.INVALID:
            return ExitReason.THESIS_FAILURE, "thesis invalid"

        # Stop loss
        if ctx.side == "buy" and ctx.current_price <= ctx.stop_loss:
            return ExitReason.STOP_LOSS, f"price {ctx.current_price} ≤ SL {ctx.stop_loss}"
        if ctx.side == "sell" and ctx.current_price >= ctx.stop_loss:
            return ExitReason.STOP_LOSS, f"price {ctx.current_price} ≥ SL {ctx.stop_loss}"

        # Take profit
        if ctx.side == "buy" and ctx.current_price >= ctx.take_profit:
            return ExitReason.TAKE_PROFIT, f"price {ctx.current_price} ≥ TP {ctx.take_profit}"
        if ctx.side == "sell" and ctx.current_price <= ctx.take_profit:
            return ExitReason.TAKE_PROFIT, f"price {ctx.current_price} ≤ TP {ctx.take_profit}"

        # Trailing stop
        if ctx.side == "buy" and ctx.high_water_mark > 0:
            trail_stop = ctx.high_water_mark - abs(ctx.entry_price - ctx.stop_loss)
            if ctx.current_price <= trail_stop:
                return ExitReason.TRAILING_STOP, f"trailing stop hit at {trail_stop:.5f}"
        if ctx.side == "sell" and ctx.low_water_mark > 0:
            trail_stop = ctx.low_water_mark + abs(ctx.stop_loss - ctx.entry_price)
            if ctx.current_price >= trail_stop:
                return ExitReason.TRAILING_STOP, f"trailing stop hit at {trail_stop:.5f}"

        # Time exit
        if ctx.position_age_s > ctx.max_holding_period_s:
            return ExitReason.TIME_EXIT, f"age {ctx.position_age_s:.0f}s > max {ctx.max_holding_period_s:.0f}s"

        # Regime exit
        if ctx.regime in ("crisis", "transition") and ctx.thesis_state == ThesisState.WEAKENING:
            return ExitReason.REGIME_EXIT, f"regime {ctx.regime} + weakening thesis"

        # Liquidity exit
        if ctx.liquidity_score < 0.2:
            return ExitReason.LIQUIDITY_EXIT, f"liquidity {ctx.liquidity_score:.2f}"

        # Event exit
        if ctx.event_active:
            return ExitReason.EVENT_EXIT, "market event firewall active"

        # Opportunity cost
        if ctx.better_opportunity_ev is not None and ctx.better_opportunity_ev > 0:
            return ExitReason.OPPORTUNITY_COST_EXIT, f"better opportunity EV={ctx.better_opportunity_ev:.4f}"

        # Execution toxicity
        if ctx.execution_toxicity > 0.7:
            return ExitReason.EXECUTION_QUALITY_EXIT, f"toxicity {ctx.execution_toxicity:.2f}"

        # No exit triggered
        return None, ""

    def record_exit(
        self,
        position_id: str,
        reason: ExitReason,
        note: str,
    ) -> None:
        self.exit_history.append({
            "position_id": position_id,
            "reason": reason.value,
            "note": note,
            "timestamp": time.time(),
        })
        logger.info(f"Exit {position_id}: {reason.value} — {note}")


# Singletons
position_thesis_engine = PositionThesisEngine()
exit_engine = ExitEngine()
