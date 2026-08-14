"""
Self-Trade Prevention Engine — EAQTS V2.3 N1012–N1020.

Detects situations where EAQTS orders on opposite sides of the same
instrument / venue / account could match against each other, and applies
the configured policy (BLOCK / NET / ROUTE_DIFFERENTLY / DEFER).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class SelfTradePolicy(str, Enum):
    BLOCK = "block"
    NET = "net"
    ROUTE_DIFFERENTLY = "route_differently"
    DEFER = "defer"


class SelfTradeResult(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    ROUTED = "routed"


@dataclass
class ActiveEAQTSOrder:
    """Track active EAQTS orders for cross-match detection."""
    order_id: str
    strategy_id: str
    account: str
    venue: str
    symbol: str
    side: str          # "buy" / "sell"
    order_type: str
    price: float
    quantity: float
    timestamp: float = field(default_factory=time.time)


class SelfTradeRegistry:
    """N1012 — Maintain a registry of active EAQTS orders."""

    def __init__(self) -> None:
        self._orders: dict[str, ActiveEAQTSOrder] = {}

    def add(self, order: ActiveEAQTSOrder) -> None:
        self._orders[order.order_id] = order

    def remove(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

    def all(self) -> list[ActiveEAQTSOrder]:
        return list(self._orders.values())


class SelfTradePrevention:
    """
    Detects potential self-match conditions between a new order and
    existing EAQTS orders sharing venue/account/symbol/opposite-side.
    """

    def __init__(self, policy: SelfTradePolicy = SelfTradePolicy.BLOCK) -> None:
        self.policy = policy
        self.registry = SelfTradeRegistry()
        self.detected_count = 0

    def check_new_order(self, order: ActiveEAQTSOrder) -> tuple[SelfTradeResult, str]:
        """
        Evaluate whether the new order could self-trade with any existing
        active EAQTS order. Returns (result, reason).
        """
        # N1013–N1017 — Compare side, price, venue, account, strategy
        for existing in self.registry.all():
            if existing.order_id == order.order_id:
                continue
            # Same venue + account + symbol
            if (existing.venue != order.venue
                    or existing.account != order.account
                    or existing.symbol != order.symbol):
                continue
            # Opposite sides
            if existing.side == order.side:
                continue
            # Price overlap for limit orders
            if order.order_type == "limit" and existing.order_type == "limit":
                if order.side == "buy" and order.price >= existing.price or order.side == "sell" and order.price <= existing.price:
                    match = True
                else:
                    match = False
            else:
                # Market orders or one side market — always potential match
                match = True

            if not match:
                continue

            # Different strategy owned by same account — possible self-match
            self.detected_count += 1
            reason = (
                f"Potential self-match: {order.symbol} {order.side} "
                f"(strategy {order.strategy_id}) vs existing "
                f"{existing.side} (strategy {existing.strategy_id})"
            )

            if self.policy == SelfTradePolicy.BLOCK:
                logger.warning(f"Self-trade BLOCK: {reason}")
                return SelfTradeResult.BLOCKED, reason
            elif self.policy == SelfTradePolicy.DEFER:
                logger.info(f"Self-trade DEFER: {reason}")
                return SelfTradeResult.DEFERRED, reason
            elif self.policy == SelfTradePolicy.ROUTE_DIFFERENTLY:
                logger.info(f"Self-trade REROUTE: {reason}")
                return SelfTradeResult.ROUTED, reason
            elif self.policy == SelfTradePolicy.NET:
                logger.info(f"Self-trade NET: {reason}")
                # Allow but flag for netting logic
                break

        return SelfTradeResult.ALLOWED, ""

    def test_self_match(self) -> bool:
        """N1020 — Simulate a self-match condition and verify detection."""
        buy = ActiveEAQTSOrder(
            order_id="test-buy",
            strategy_id="strat-a",
            account="acct-1",
            venue="mt5",
            symbol="EURUSD",
            side="buy",
            order_type="limit",
            price=1.0850,
            quantity=1.0,
        )
        sell = ActiveEAQTSOrder(
            order_id="test-sell",
            strategy_id="strat-b",
            account="acct-1",
            venue="mt5",
            symbol="EURUSD",
            side="sell",
            order_type="limit",
            price=1.0850,
            quantity=1.0,
        )
        self.registry.add(buy)
        result, reason = self.check_new_order(sell)
        self.registry.remove(buy.order_id)
        self.registry.remove(sell.order_id)
        return result == SelfTradeResult.BLOCKED


# Singleton
self_trade_prevention = SelfTradePrevention()
