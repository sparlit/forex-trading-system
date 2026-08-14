"""
Order and Message Rate Governor — EAQTS V2.3 N0985–N0098.

Independent rate-limit subsystem for orders, cancellations, modifications,
messages-per-second, executions-per-minute, with per-strategy, per-symbol
and per-venue sub-limits.

States: NORMAL → ELEVATED → THROTTLED → RESTRICTED → HALTED
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class RateState(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    THROTTLED = "throttled"
    RESTRICTED = "restricted"
    HALTED = "halted"


@dataclass
class RateLimits:
    orders_per_second: float = 10.0
    cancellations_per_second: float = 20.0
    modifications_per_second: float = 15.0
    messages_per_second: float = 50.0
    executions_per_minute: float = 30.0
    strategy_specific: dict[str, float] = field(default_factory=dict)
    symbol_specific: dict[str, float] = field(default_factory=dict)
    venue_specific: dict[str, float] = field(default_factory=dict)


class _SlidingWindow:
    """Simple sliding-window counter for rate enforcement."""

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._events: deque[float] = deque()

    def count(self, now: float) -> int:
        cutoff = now - self._window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
        return len(self._events)

    def add(self, now: float) -> None:
        self._events.append(now)


class RateGovernor:
    """
    Tracks outgoing order-flow events and enforces independent rate limits.
    Rate limits are monetary-risk-independent — they protect infrastructure
    and avoid exchange throttling, not capital.
    """

    def __init__(self, limits: RateLimits | None = None) -> None:
        self.limits = limits or RateLimits()
        self.state = RateState.NORMAL
        self._order_win = _SlidingWindow(1.0)
        self._cancel_win = _SlidingWindow(1.0)
        self._modify_win = _SlidingWindow(1.0)
        self._msg_win = _SlidingWindow(1.0)
        self._exec_win = _SlidingWindow(60.0)
        self._strategy_counters: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(1.0))
        self._symbol_counters: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(1.0))
        self._venue_counters: dict[str, _SlidingWindow] = defaultdict(lambda: _SlidingWindow(1.0))
        self._elevated_at: float | None = None
        self._halted_until: float | None = None

    def _now(self) -> float:
        return time.monotonic()

    @property
    def is_halted(self) -> bool:
        return self.state == RateState.HALTED

    @property
    def can_send(self) -> bool:
        """Whether any outgoing order traffic is permitted right now."""
        if self.state in (RateState.HALTED, RateState.RESTRICTED):
            return False
        if self.state == RateState.THROTTLED:
            return self._order_win.count(self._now()) < self.limits.orders_per_second * 0.3
        return True

    def _evaluate_state(self, now: float) -> None:
        """Promote or demote the rate state based on current counters."""
        ops = self._order_win.count(now)
        mps = self._msg_win.count(now)

        if self.state == RateState.HALTED:
            if self._halted_until and now >= self._halted_until:
                self.state = RateState.RESTRICTED
                self._halted_until = None
                logger.warning("Rate governor: HALTED → RESTRICTED (cooldown elapsed)")
            return

        if ops > self.limits.orders_per_second * 2 or mps > self.limits.messages_per_second * 2:
            self.state = RateState.HALTED
            self._halted_until = now + 30.0
            logger.error(f"Rate governor: → HALTED (ops={ops}, mps={mps}). 30s cooldown.")
        elif ops > self.limits.orders_per_second * 1.5:
            self.state = RateState.RESTRICTED
            logger.warning(f"Rate governor: → RESTRICTED (ops={ops})")
        elif ops > self.limits.orders_per_second:
            self.state = RateState.THROTTLED
            self._elevated_at = now
            logger.info(f"Rate governor: → THROTTLED (ops={ops})")
        elif ops > self.limits.orders_per_second * 0.8:
            self.state = RateState.ELEVATED
            self._elevated_at = now
            logger.debug(f"Rate governor: → ELEVATED (ops={ops})")
        else:
            if self.state != RateState.NORMAL:
                logger.info("Rate governor: → NORMAL")
            self.state = RateState.NORMAL

    def record_order(self, strategy_id: str = "", symbol: str = "", venue: str = "") -> bool:
        """
        Record an outgoing order. Returns True if accepted, False if rejected
        by a rate limit.
        """
        now = self._now()
        self._evaluate_state(now)
        if not self.can_send:
            logger.warning(f"Rate governor: order rejected (state={self.state.value})")
            return False

        self._order_win.add(now)
        self._msg_win.add(now)
        if strategy_id:
            self._strategy_counters[strategy_id].add(now)
        if symbol:
            self._symbol_counters[symbol].add(now)
        if venue:
            self._venue_counters[venue].add(now)

        # Check strategy/symbol/venue sub-limits
        if strategy_id and strategy_id in self.limits.strategy_specific:
            if self._strategy_counters[strategy_id].count(now) > self.limits.strategy_specific[strategy_id]:
                logger.warning(f"Rate governor: strategy {strategy_id} sub-limit exceeded")
                return False
        if symbol and symbol in self.limits.symbol_specific:
            if self._symbol_counters[symbol].count(now) > self.limits.symbol_specific[symbol]:
                logger.warning(f"Rate governor: symbol {symbol} sub-limit exceeded")
                return False
        if venue and venue in self.limits.venue_specific:
            if self._venue_counters[venue].count(now) > self.limits.venue_specific[venue]:
                logger.warning(f"Rate governor: venue {venue} sub-limit exceeded")
                return False

        self._evaluate_state(now)
        return True

    def record_cancellation(self) -> bool:
        now = self._now()
        self._cancel_win.add(now)
        self._msg_win.add(now)
        if self._cancel_win.count(now) > self.limits.cancellations_per_second:
            logger.warning("Rate governor: cancellation limit hit")
            return False
        return True

    def record_modification(self) -> bool:
        now = self._now()
        self._modify_win.add(now)
        self._msg_win.add(now)
        if self._modify_win.count(now) > self.limits.modifications_per_second:
            logger.warning("Rate governor: modification limit hit")
            return False
        return True

    def record_execution(self) -> None:
        now = self._now()
        self._exec_win.add(now)
        if self._exec_win.count(now) > self.limits.executions_per_minute:
            logger.warning("Rate governor: executions-per-minute limit exceeded")

    def detect_elevated_rate(self) -> bool:
        """N0994 — Detect elevated rate."""
        return self._order_win.count(self._now()) > self.limits.orders_per_second * 0.8

    def throttle(self, factor: float = 0.5) -> None:
        """N0995 — Apply throttle by reducing effective limits."""
        self.limits.orders_per_second *= factor
        self.state = RateState.THROTTLED
        logger.info(f"Rate governor: throttled to {self.limits.orders_per_second:.1f} ops/s")

    def restrict(self) -> None:
        """N0996 — Restrict: block all new orders."""
        self.state = RateState.RESTRICTED
        logger.warning("Rate governor: RESTRICTED")

    def rate_circuit_break(self, cooldown_s: float = 30.0) -> None:
        """N0997 — Rate circuit breaker: halt all traffic for cooldown."""
        self.state = RateState.HALTED
        self._halted_until = self._now() + cooldown_s
        logger.error(f"Rate governor: circuit breaker tripped ({cooldown_s}s)")

    def test_runaway_order_generator(self) -> bool:
        """N0998 — Simulate 100 orders/s and verify governor trips."""
        original_state = self.state
        original_limit = self.limits.orders_per_second
        self.limits.orders_per_second = 5
        trip_count = 0
        for _ in range(200):
            accepted = self.record_order()
            if not accepted:
                trip_count += 1
        self.limits.orders_per_second = original_limit
        self.state = original_state
        logger.info(f"Runaway test: {trip_count} orders rejected")
        return trip_count > 0

    def status(self) -> dict[str, Any]:
        now = self._now()
        return {
            "state": self.state.value,
            "orders_per_second": self._order_win.count(now),
            "messages_per_second": self._msg_win.count(now),
            "cancellations_per_second": self._cancel_win.count(now),
            "executions_per_minute": self._exec_win.count(now),
            "can_send": self.can_send,
        }


# Singleton
rate_governor = RateGovernor()
