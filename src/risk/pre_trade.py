"""
Pre‑Trade Risk Checks
=====================

Provides a lightweight, stateless validator that can be invoked by the
order management layer before an order is sent to a broker.

The validator checks:

* **Margin** – the required margin must not exceed the account free
  margin.
* **Position limits** – the resulting position size must stay below the
  configured maximum (per symbol and globally).
* **Symbol allow‑list** – only symbols present in the configured list
  may be traded.
* **Daily loss limit** – cumulative realised P&L must not exceed the
  configured daily loss limit.

All limits are read from the global :mod:`src.infra.config` ``settings``
object and may be overridden via the constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from loguru import logger

from src.data.models import Order


@dataclass
class PreTradeLimits:
    """Container for the configurable risk limits."""

    max_position_size: Decimal = Decimal(100)
    max_global_position_size: Decimal = Decimal(1000)
    max_daily_loss: Decimal = Decimal(5000)
    allowed_symbols: list[str] = field(default_factory=list)
    margin_buffer: Decimal = Decimal("0.10")  # 10% safety margin


class PreTradeValidationError(Exception):
    """Raised when an order violates one of the pre‑trade checks."""


class PreTradeValidator:
    """Stateless validator; instances are safe to share."""

    def __init__(self, limits: PreTradeLimits | None = None) -> None:
        self.limits = limits or PreTradeLimits()

    def validate(
        self,
        order: Order,
        account_balance: Decimal,
        account_free_margin: Decimal,
        current_position_size: Decimal = Decimal(0),
        current_global_exposure: Decimal = Decimal(0),
        daily_pnl: Decimal = Decimal(0),
    ) -> None:
        """Validate ``order`` against the configured limits.

        Args:
            order: The order to be placed.
            account_balance: Account equity used for margin calculations.
            account_free_margin: Free margin currently available.
            current_position_size: Current position size for the same
                symbol.
            current_global_exposure: Current global exposure (all
                symbols combined).
            daily_pnl: Realised P&L for the current trading day.

        Raises:
            PreTradeValidationError: When any limit is exceeded.
        """
        limits = self.limits

        # Symbol allow‑list
        if limits.allowed_symbols and order.symbol not in limits.allowed_symbols:
            raise PreTradeValidationError(
                f"Symbol {order.symbol!r} not in allowed list"
            )

        # Position size (per symbol)
        projected_symbol_pos = current_position_size + order.volume
        if projected_symbol_pos > limits.max_position_size:
            raise PreTradeValidationError(
                f"Projected position {projected_symbol_pos} exceeds per‑symbol "
                f"limit {limits.max_position_size}"
            )

        # Global exposure
        projected_global = current_global_exposure + order.volume
        if projected_global > limits.max_global_position_size:
            raise PreTradeValidationError(
                f"Projected global exposure {projected_global} exceeds limit "
                f"{limits.max_global_position_size}"
            )

        # Daily loss limit
        if daily_pnl < -limits.max_daily_loss:
            raise PreTradeValidationError(
                f"Daily loss {abs(daily_pnl)} exceeds limit {limits.max_daily_loss}"
            )

        # Margin check – assume a 1% margin requirement per unit
        required_margin = order.volume * Decimal("0.01") * (1 + limits.margin_buffer)
        if required_margin > account_free_margin:
            raise PreTradeValidationError(
                f"Insufficient free margin: required {required_margin}, "
                f"available {account_free_margin}"
            )

        logger.debug(
            "Pre‑trade validation passed",
            order_id=str(order.order_id),
            symbol=order.symbol,
            volume=str(order.volume),
        )


# Convenience singleton accessor -------------------------------------------------
_default_validator: PreTradeValidator | None = None


def get_pre_trade_validator() -> PreTradeValidator:
    """Return a process‑wide :class:`PreTradeValidator`."""
    global _default_validator
    if _default_validator is None:
        # Use app_config for any future dynamic settings
        _default_validator = PreTradeValidator()
    return _default_validator
