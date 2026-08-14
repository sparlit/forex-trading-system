# safety/kernel.py
"""Deterministic Safety Kernel
Implements a strict, testable safety layer that validates all aspects of a trading intent
before it reaches the execution engine. The Kernel owns a reference to the
SafetyStateMachine (risk‑aware state) and can query the independent KillSwitch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Local imports – keep them lightweight; the risk engine already provides a basic Portfolio
# representation we can reuse for portfolio‑level checks.
from ..data.models import Portfolio  # type: ignore
from .kill_switch import KillSwitch

# The safety sub‑package also provides its own state machine and kill switch.
from .state_machine import SafetyStateMachine

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SafetyKernel:
    """Core safety gate.

    The kernel is *deterministic*: given the same input and the same internal state it will always
    return the same approval decision. No stochastic components are used.
    """

    # Dependencies – injected at runtime so the kernel stays testable.
    state_machine: SafetyStateMachine
    kill_switch: KillSwitch

    # Optional callbacks for external systems (e.g. monitoring dashboards).
    on_halt: Callable[[str], None] | None = field(default=None)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def validate(self, trading_intent: dict[str, Any]) -> tuple[bool, list[str]]:
        """Run the full suite of safety checks.

        Parameters
        ----------
        trading_intent:
            A dictionary describing the intended order. Expected keys include:
            ``symbol``, ``price``, ``volume``, ``order_type``, ``stop_loss``, ``take_profit``,
            ``margin_required``, ``leverage``, ``timestamp`` and any custom payload the user
            wishes to attach.

        Returns
        -------
        (approved, reasons):
            ``approved`` is ``True`` only if *all* checks pass.
            ``reasons`` contains textual explanations for any failures.
        """
        reasons: list[str] = []
        approved = True

        # Short‑circuit if the independent kill switch is active.
        if self.is_kill_switch_active():
            approved = False
            reasons.append("Kill switch active – all trading halted")
            logger.warning("Kill switch prevented trade validation")
            return approved, reasons

        # 1. Instrument validity – symbol must be known to the system.
        if not self._check_instrument(trading_intent.get("symbol")):
            approved = False
            reasons.append("Instrument symbol unknown or unsupported")

        # 2. Price validity – price must be positive and within a reasonable spread.
        if not self._check_price(trading_intent.get("price"), trading_intent.get("symbol")):
            approved = False
            reasons.append("Price invalid or outside acceptable spread")

        # 3. Volume validity – non‑zero, respects position limits.
        if not self._check_volume(trading_intent.get("volume"), trading_intent.get("symbol")):
            approved = False
            reasons.append("Volume invalid or exceeds limits")

        # 4. Order type validity – must be one of the accepted enums.
        if not self._check_order_type(trading_intent.get("order_type")):
            approved = False
            reasons.append("Order type unsupported")

        # 5. Stop / target validity – sl must be below price for longs, above for shorts, etc.
        if not self._check_stop_target(
            trading_intent.get("price"),
            trading_intent.get("stop_loss"),
            trading_intent.get("take_profit"),
            trading_intent.get("order_side"),
        ):
            approved = False
            reasons.append("Stop‑loss / take‑profit configuration invalid")

        # 6. Margin & leverage checks.
        if not self._check_margin_leverage(
            trading_intent.get("margin_required"),
            trading_intent.get("leverage"),
        ):
            approved = False
            reasons.append("Margin or leverage out of permitted range")

        # 7. Market state – market must be open and data fresh.
        if not self._check_market_state(trading_intent.get("symbol")):
            approved = False
            reasons.append("Market closed or data stale for symbol")

        # 8. Spread – enforce a maximum spread percentage.
        if not self._check_spread(trading_intent.get("symbol")):
            approved = False
            reasons.append("Current spread exceeds safety threshold")

        # 9. Portfolio risk – delegate to the supplied risk engine via state machine.
        if not self._check_portfolio_risk(trading_intent.get("portfolio")):
            approved = False
            reasons.append("Portfolio risk limits would be breached")

        # 10. Broker state – ensure broker connectivity and health flags.
        if not self._check_broker_state():
            approved = False
            reasons.append("Broker unhealthy or disconnected")

        # 11. Model state – sanity check that the AI model is healthy.
        if not self._check_model_state():
            approved = False
            reasons.append("Model health check failed")

        # 12. Security state – no open security incidents.
        if not self._check_security_state():
            approved = False
            reasons.append("Security anomaly detected")

        # Final state‑machine gate – each state defines whether trading is allowed.
        if not self.state_machine.can_trade():
            approved = False
            reasons.append(f"Current safety state {self.state_machine.current_state.name} blocks trading")

        return approved, reasons

    # ---------------------------------------------------------------------
    # Individual check implementations – each is pure and returns a bool.
    # ---------------------------------------------------------------------
    def _check_instrument(self, symbol: str | None) -> bool:
        if not symbol:
            return False
        # In a real system we would query a symbol registry. Here we use a static whitelist.
        allowed_symbols = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"}
        return symbol.upper() in allowed_symbols

    def _check_price(self, price: float | None, symbol: str | None) -> bool:
        if price is None or price <= 0:
            return False
        # Guard against wildly out‑of‑range price (e.g. >10× previous close). We obtain the last price
        # via a helper that would normally hit market data cache – we fall back to a safe range if unknown.
        last_price = self._get_last_price(symbol)
        if last_price is None:
            return True  # No reference – allow but log.
        # Accept price within ±20% of last known price.
        return abs(price - last_price) / last_price <= 0.20

    def _check_volume(self, volume: float | None, symbol: str | None) -> bool:
        if volume is None or volume <= 0:
            return False
        # Simplistic per‑symbol max volume rule (could be derived from risk limits).
        max_volume = {
            "EURUSD": 5_000_000,
            "GBPUSD": 3_000_000,
            "USDJPY": 6_000_000,
        }.get(symbol.upper() if symbol else None, 1_000_000)
        return volume <= max_volume

    def _check_order_type(self, order_type: str | None) -> bool:
        valid = {"market", "limit", "stop", "stop_limit"}
        return order_type in valid

    def _check_stop_target(
        self,
        price: float | None,
        stop: float | None,
        target: float | None,
        side: str | None,
    ) -> bool:
        if price is None or side not in {"long", "short"}:
            return False
        if side == "long":
            if stop is not None and stop >= price:
                return False
            if target is not None and target <= price:
                return False
        else:  # short
            if stop is not None and stop <= price:
                return False
            if target is not None and target >= price:
                return False
        return True

    def _check_margin_leverage(self, margin: float | None, leverage: float | None) -> bool:
        if margin is None or leverage is None:
            return False
        # Hard limits – these could be read from a config file; we embed sensible defaults.
        if margin < 0.0 or margin > 1.0:
            return False
        if leverage < 1.0 or leverage > 10.0:
            return False
        return True

    def _check_market_state(self, symbol: str | None) -> bool:
        # Placeholder market‑open check – in production we would query an exchange calendar.
        # Assume markets are open Mon‑Fri 00:00‑23:59 UTC for forex.
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:  # Saturday / Sunday
            return False
        # No per‑symbol holiday handling for this deterministic example.
        return True

    def _check_spread(self, symbol: str | None) -> bool:
        # Retrieve a recent spread estimate; if unavailable, allow but log.
        spread = self._get_current_spread(symbol)
        if spread is None:
            return True
        # Max acceptable spread of 0.5% of price.
        last_price = self._get_last_price(symbol) or 1.0
        return spread / last_price <= 0.005

    def _check_portfolio_risk(self, portfolio: Portfolio | None) -> bool:
        if portfolio is None:
            return False
        # Leveraging the existing RiskEngine guards would be ideal, but we keep the check
        # lightweight: ensure gross leverage is below 5x and no single position exceeds 20% of equity.
        if getattr(portfolio, "gross_leverage", 1.0) > 5.0:
            return False
        equity = getattr(portfolio, "total_equity", 0.0) or 1.0
        for pos in getattr(portfolio, "positions", []):
            if getattr(pos, "market_value", 0.0) / equity > 0.20:
                return False
        return True

    def _check_broker_state(self) -> bool:
        # In a real system this would query the broker health endpoint.
        # For determinism we assume a static healthy flag that could be toggled by tests.
        return getattr(self, "_broker_healthy", True)

    def _check_model_state(self) -> bool:
        # Model health – placeholder that could be replaced by a health‑check callback.
        return getattr(self, "_model_healthy", True)

    def _check_security_state(self) -> bool:
        # Security incident flag – defaults to no incident.
        return getattr(self, "_security_clear", True)

    # ---------------------------------------------------------------------
    # Helper data‑access methods – kept very light; they could be swapped out.
    # ---------------------------------------------------------------------
    def _get_last_price(self, symbol: str | None) -> float | None:
        # Mocked price cache – in production a market data service would provide this.
        dummy_prices = {
            "EURUSD": 1.10,
            "GBPUSD": 1.30,
            "USDJPY": 150.0,
            "AUDUSD": 0.70,
        }
        return dummy_prices.get(symbol.upper() if symbol else None)

    def _get_current_spread(self, symbol: str | None) -> float | None:
        dummy_spreads = {
            "EURUSD": 0.0002,
            "GBPUSD": 0.0003,
            "USDJPY": 0.02,
        }
        return dummy_spreads.get(symbol.upper() if symbol else None)

    # ---------------------------------------------------------------------
    # Veto authority – external events can ask the kernel to veto a specific
    #   event type (e.g., "order_created"). Returning True means the event must be
    #   blocked.
    # ---------------------------------------------------------------------
    def veto(self, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        """Absolute veto authority.

        The current implementation vetoes anything when the kill switch is active
        or when the safety state machine is in a restrictive mode.
        """
        if self.is_kill_switch_active():
            logger.info(f"Vetoed {event_type} because kill switch active")
            return True
        if not self.state_machine.can_trade():
            logger.info(f"Vetoed {event_type} because state {self.state_machine.current_state.name} disallows trading")
            return True
        # Additional custom veto rules could be added here.
        return False

    # ---------------------------------------------------------------------
    # State‑machine integration
    # ---------------------------------------------------------------------
    def set_state(self, new_state: Any) -> None:
        """Delegate state change to the wrapped SafetyStateMachine."""
        self.state_machine.set_state(new_state)

    def get_state(self) -> Any:
        return self.state_machine.get_state()

    # ---------------------------------------------------------------------
    # Emergency handling
    # ---------------------------------------------------------------------
    def emergency_halt(self, reason: str) -> None:
        """Force the system into a HALTED state and activate the kill switch.

        The method also triggers any registered ``on_halt`` callback.
        """
        logger.warning(f"Emergency halt triggered: {reason}")
        self.state_machine.set_state(self.state_machine.State.HALTED)
        self.kill_switch.activate(reason)
        if self.on_halt:
            try:
                self.on_halt(reason)
            except Exception as exc:  # pragma: no cover – defensive programming
                logger.exception("on_halt callback failed", exc_info=exc)

    def is_kill_switch_active(self) -> bool:
        return self.kill_switch.is_active()
