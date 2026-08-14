"""
Loss Velocity Engine — EAQTS V2.3 N0876–N0883.

Measures loss *rate* and *acceleration* across short, medium and long
windows. Abnormally rapid degradation triggers restriction before
absolute hard limits are reached.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

from loguru import logger


class VelocityState(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    RESTRICTED = "restricted"


@dataclass
class PnLPoint:
    timestamp: float
    pnl: float


@dataclass
class VelocityResult:
    short_slope: float
    medium_slope: float
    long_slope: float
    drawdown_acceleration: float
    state: VelocityState
    triggered: bool = False
    reason: str = ""


class LossVelocityEngine:
    """
    N0876–N0883: Tracks PnL time-series and computes slopes across
    three time windows plus drawdown acceleration.
    """

    def __init__(
        self,
        short_window_s: float = 300,      # 5 minutes
        medium_window_s: float = 3600,    # 1 hour
        long_window_s: float = 86400,     # 1 day
        abnormal_velocity: float = -0.5,  # PnL units per second
        critical_velocity: float = -2.0,
    ) -> None:
        self.short_window_s = short_window_s
        self.medium_window_s = medium_window_s
        self.long_window_s = long_window_s
        self.abnormal_velocity = abnormal_velocity
        self.critical_velocity = critical_velocity
        self._pnl_history: deque[PnLPoint] = deque(maxlen=10000)
        self._max_drawdown_seen: float = 0.0
        self._last_drawdown: float = 0.0
        self.state = VelocityState.NORMAL

    def record_pnl(self, pnl: float) -> None:
        """Record current cumulative PnL."""
        self._pnl_history.append(PnLPoint(timestamp=time.time(), pnl=pnl))

    def _slope(self, window_s: float) -> float:
        """Calculate PnL slope (change per second) over the given window."""
        now = time.time()
        cutoff = now - window_s
        points = [p for p in self._pnl_history if p.timestamp >= cutoff]
        if len(points) < 2:
            return 0.0
        dt = points[-1].timestamp - points[0].timestamp
        if dt < 1e-9:
            return 0.0
        return (points[-1].pnl - points[0].pnl) / dt

    def _drawdown_acceleration(self) -> float:
        """Second derivative of the drawdown curve."""
        now = time.time()
        window = 600  # 10 minutes
        cutoff = now - window
        points = [p for p in self._pnl_history if p.timestamp >= cutoff]
        if len(points) < 3:
            return 0.0
        # Simple: compare recent half slope vs first half slope
        mid = len(points) // 2
        first_half = points[:mid]
        second_half = points[mid:]
        if len(first_half) < 2 or len(second_half) < 2:
            return 0.0
        dt1 = first_half[-1].timestamp - first_half[0].timestamp
        dt2 = second_half[-1].timestamp - second_half[0].timestamp
        if dt1 < 1e-9 or dt2 < 1e-9:
            return 0.0
        slope1 = (first_half[-1].pnl - first_half[0].pnl) / dt1
        slope2 = (second_half[-1].pnl - second_half[0].pnl) / dt2
        return slope2 - slope1

    def evaluate(self) -> VelocityResult:
        """N0880–N0882: Calculate and classify velocity."""
        short = self._slope(self.short_window_s)
        medium = self._slope(self.medium_window_s)
        long = self._slope(self.long_window_s)
        dd_accel = self._drawdown_acceleration()

        triggered = False
        reason = ""

        # N0881 — Critical velocity
        if short < self.critical_velocity:
            self.state = VelocityState.CRITICAL
            triggered = True
            reason = f"short-term loss rate {short:.4f}/s below critical {self.critical_velocity}"
        # N0880 — Abnormal velocity
        elif short < self.abnormal_velocity or medium < self.abnormal_velocity:
            self.state = VelocityState.ELEVATED
            triggered = True
            reason = f"loss rate excessive (short={short:.4f}/s, medium={medium:.4f}/s)"
        # Drawdown acceleration
        elif dd_accel < self.critical_velocity:
            self.state = VelocityState.CRITICAL
            triggered = True
            reason = f"drawdown acceleration {dd_accel:.4f} indicates accelerating loss"
        else:
            if self.state != VelocityState.NORMAL:
                logger.info("Loss velocity: → NORMAL")
            self.state = VelocityState.NORMAL

        if triggered:
            logger.warning(f"Loss velocity {self.state.value}: {reason}")

        return VelocityResult(
            short_slope=short,
            medium_slope=medium,
            long_slope=long,
            drawdown_acceleration=dd_accel,
            state=self.state,
            triggered=triggered,
            reason=reason,
        )

    def should_restrict(self) -> tuple[bool, str]:
        """N0882 — Should new risk be restricted due to loss velocity?"""
        result = self.evaluate()
        if result.state == VelocityState.CRITICAL:
            self.state = VelocityState.RESTRICTED
            return True, f"CRITICAL velocity: {result.reason}"
        if result.state == VelocityState.ELEVATED:
            return True, f"ELEVATED velocity: {result.reason}"
        return False, ""

    def test_rapid_loss(self) -> bool:
        """N0883 — Simulate rapid losses and verify restriction triggers."""
        self._pnl_history.clear()
        base_t = time.time() - 100
        for i in range(100):
            self._pnl_history.append(
                PnLPoint(
                    timestamp=base_t + i,
                    pnl=10000 - i * 50,  # rapid linear loss
                )
            )
        restricted, reason = self.should_restrict()
        return restricted


# Singleton
loss_velocity_engine = LossVelocityEngine()
