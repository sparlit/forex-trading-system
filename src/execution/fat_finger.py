"""
Fat-Finger Protection Engine — EAQTS V2.3 N0999–N1011.

Validates outgoing orders against maximum quantity, notional, price
deviation, position increase, and stop-distance boundary rules to prevent
accidental large / mispriced orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from loguru import logger


class FatFingerResult(str, Enum):
    ACCEPTED = "accepted"
    REJECTED_QUANTITY = "rejected_quantity"
    REJECTED_NOTIONAL = "rejected_notional"
    REJECTED_PRICE_DEVIATION = "rejected_price_deviation"
    REJECTED_POSITION_INCREASE = "rejected_position_increase"
    REJECTED_STOP_DISTANCE = "rejected_stop_distance"


@dataclass
class FatFingerLimits:
    max_order_quantity: float = 100.0
    max_order_notional: float = 1_000_000.0
    max_price_deviation_pct: float = 5.0          # % from reference
    max_position_increase_pct: float = 50.0        # % of current position
    min_stop_distance_pct: float = 0.05            # % from entry
    max_stop_distance_pct: float = 20.0            # % from entry
    account_max_notional: float = 5_000_000.0
    broker_max_notional: float = 10_000_000.0


@dataclass
class FatFingerOrder:
    symbol: str
    side: str          # "buy" / "sell"
    order_type: str    # "market" / "limit" / "stop"
    quantity: float
    price: float       # limit price or current market for market orders
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_id: str = ""
    venue: str = ""
    current_position_qty: float = 0.0
    reference_price: float = 0.0


class FatFingerEngine:
    """
    Checks each outgoing order against configurable fat-finger limits
    at multiple levels: strategy → symbol → account → broker → system.
    """

    def __init__(self, limits: FatFingerLimits | None = None) -> None:
        self.limits = limits or FatFingerLimits()
        self.violations: list[dict[str, Any]] = []

    def validate(
        self,
        order: FatFingerOrder,
        account_notional_used: float = 0.0,
        broker_notional_used: float = 0.0,
    ) -> tuple[FatFingerResult, str]:
        """Validate an order; returns (result, reason)."""
        # N1007 — Validate order size
        if order.quantity > self.limits.max_order_quantity:
            reason = (
                f"Quantity {order.quantity} exceeds max "
                f"{self.limits.max_order_quantity}"
            )
            self._reject(order, FatFingerResult.REJECTED_QUANTITY, reason)
            return FatFingerResult.REJECTED_QUANTITY, reason

        # N1008 — Validate order notional
        notional = order.quantity * order.price
        if notional > self.limits.max_order_notional:
            reason = (
                f"Notional {notional:.2f} exceeds max "
                f"{self.limits.max_order_notional}"
            )
            self._reject(order, FatFingerResult.REJECTED_NOTIONAL, reason)
            return FatFingerResult.REJECTED_NOTIONAL, reason

        # Account-level checks
        if account_notional_used + notional > self.limits.account_max_notional:
            reason = (
                f"Account notional {account_notional_used + notional:.2f} "
                f"exceeds account max {self.limits.account_max_notional}"
            )
            self._reject(order, FatFingerResult.REJECTED_NOTIONAL, reason)
            return FatFingerResult.REJECTED_NOTIONAL, reason

        # Broker-level checks
        if broker_notional_used + notional > self.limits.broker_max_notional:
            reason = (
                f"Broker notional {broker_notional_used + notional:.2f} "
                f"exceeds broker max {self.limits.broker_max_notional}"
            )
            self._reject(order, FatFingerResult.REJECTED_NOTIONAL, reason)
            return FatFingerResult.REJECTED_NOTIONAL, reason

        # N1009 — Validate price deviation from reference
        ref = order.reference_price or order.price
        if ref > 0:
            deviation_pct = abs(order.price - ref) / ref * 100
            if deviation_pct > self.limits.max_price_deviation_pct:
                reason = (
                    f"Price deviation {deviation_pct:.2f}% exceeds max "
                    f"{self.limits.max_price_deviation_pct}%"
                )
                self._reject(order, FatFingerResult.REJECTED_PRICE_DEVIATION, reason)
                return FatFingerResult.REJECTED_PRICE_DEVIATION, reason

        # N1002 — Validate maximum position increase
        if order.current_position_qty > 0:
            increase_pct = (
                order.quantity / order.current_position_qty * 100
                if order.current_position_qty > 0
                else 0
            )
            if increase_pct > self.limits.max_position_increase_pct:
                reason = (
                    f"Position increase {increase_pct:.1f}% exceeds max "
                    f"{self.limits.max_position_increase_pct}%"
                )
                self._reject(
                    order, FatFingerResult.REJECTED_POSITION_INCREASE, reason
                )
                return FatFingerResult.REJECTED_POSITION_INCREASE, reason

        # N1003–N1004 — Validate stop distance
        if order.stop_loss > 0 and order.price > 0:
            stop_dist_pct = abs(order.stop_loss - order.price) / order.price * 100
            if stop_dist_pct < self.limits.min_stop_distance_pct:
                reason = (
                    f"Stop distance {stop_dist_pct:.4f}% below min "
                    f"{self.limits.min_stop_distance_pct}%"
                )
                self._reject(order, FatFingerResult.REJECTED_STOP_DISTANCE, reason)
                return FatFingerResult.REJECTED_STOP_DISTANCE, reason
            if stop_dist_pct > self.limits.max_stop_distance_pct:
                reason = (
                    f"Stop distance {stop_dist_pct:.2f}% exceeds max "
                    f"{self.limits.max_stop_distance_pct}%"
                )
                self._reject(order, FatFingerResult.REJECTED_STOP_DISTANCE, reason)
                return FatFingerResult.REJECTED_STOP_DISTANCE, reason

        logger.debug(
            f"Fat-finger check passed: {order.symbol} qty={order.quantity} "
            f"px={order.price} notional={notional:.2f}"
        )
        return FatFingerResult.ACCEPTED, ""

    def _reject(
        self,
        order: FatFingerOrder,
        result: FatFingerResult,
        reason: str,
    ) -> None:
        self.violations.append({
            "symbol": order.symbol,
            "result": result.value,
            "reason": reason,
            "quantity": order.quantity,
            "price": order.price,
        })
        logger.warning(f"Fat-finger REJECT: {result.value} — {reason}")

    def test_extreme_order(self) -> bool:
        """N1011 — Test that an extreme outlier order is rejected."""
        bad = FatFingerOrder(
            symbol="EURUSD",
            side="buy",
            order_type="market",
            quantity=9999.0,
            price=1.10,
            reference_price=1.10,
        )
        accepted, _ = self.validate(bad)
        return not accepted


# Singleton
fat_finger_engine = FatFingerEngine()
