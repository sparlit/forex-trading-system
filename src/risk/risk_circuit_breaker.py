from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum

import numpy as np
from loguru import logger

from src.infra.config.settings import settings


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Tripped, blocking trades
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreakerType(str, Enum):
    DAILY_LOSS = "daily_loss"
    DRAWDOWN = "drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    VOLATILITY_SPIKE = "volatility_spike"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    MARGIN_CALL = "margin_call"
    NEWS_EVENT = "news_event"
    MANUAL = "manual"


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    breaker_type: CircuitBreakerType
    threshold: float
    window_minutes: int = 60
    cooldown_minutes: int = 60
    enabled: bool = True
    auto_reset: bool = True


@dataclass
class CircuitBreaker:
    """Individual circuit breaker."""
    config: CircuitBreakerConfig
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    triggered_at: datetime | None = None
    trigger_count: int = 0
    last_reset: datetime | None = None
    metadata: dict = field(default_factory=dict)

    def check(self, value: float) -> bool:
        """Check if breaker should trip."""
        if not self.config.enabled:
            return False

        if self.state == CircuitBreakerState.OPEN:
            # Check if cooldown expired
            if self.triggered_at:
                cooldown_end = self.triggered_at + timedelta(minutes=self.config.cooldown_minutes)
                if datetime.now(UTC) >= cooldown_end:
                    if self.config.auto_reset:
                        self.reset()
                    else:
                        self.state = CircuitBreakerState.HALF_OPEN
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            # In half-open, allow one test trade
            return False

        # Check threshold
        triggered = value >= self.config.threshold

        if triggered:
            self.trip(value)

        return triggered

    def trip(self, value: float) -> None:
        """Trip the circuit breaker."""
        self.state = CircuitBreakerState.OPEN
        self.triggered_at = datetime.now(UTC)
        self.trigger_count += 1
        self.metadata["last_trigger_value"] = value
        self.metadata["last_trigger_time"] = self.triggered_at.isoformat()
        logger.warning(f"Circuit breaker {self.config.breaker_type.value} TRIPPED: value={value}, threshold={self.config.threshold}")

    def reset(self) -> None:
        """Reset the circuit breaker."""
        self.state = CircuitBreakerState.CLOSED
        self.triggered_at = None
        self.last_reset = datetime.now(UTC)
        logger.info(f"Circuit breaker {self.config.breaker_type.value} RESET")

    def force_open(self, reason: str = "Manual override") -> None:
        """Force breaker open."""
        self.state = CircuitBreakerState.OPEN
        self.triggered_at = datetime.now(UTC)
        self.metadata["force_reason"] = reason
        logger.warning(f"Circuit breaker {self.config.breaker_type.value} FORCED OPEN: {reason}")

    def force_close(self) -> None:
        """Force breaker closed."""
        self.state = CircuitBreakerState.CLOSED
        self.triggered_at = None
        logger.info(f"Circuit breaker {self.config.breaker_type.value} FORCED CLOSE")

    def is_open(self) -> bool:
        return self.state == CircuitBreakerState.OPEN

    def is_half_open(self) -> bool:
        return self.state == CircuitBreakerState.HALF_OPEN

    def allow_trading(self) -> bool:
        return self.state != CircuitBreakerState.OPEN


class CircuitBreakerManager:
    """Manages all circuit breakers."""

    def __init__(self):
        self._breakers: dict[CircuitBreakerType, CircuitBreaker] = {}
        self._callbacks: list[Callable] = []
        self._initialize_default_breakers()

    def _initialize_default_breakers(self) -> None:
        """Initialize default circuit breakers from settings."""
        configs = [
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.DAILY_LOSS,
                threshold=settings.risk_daily_loss_limit,
                window_minutes=1440,  # 24 hours
                cooldown_minutes=1440,
            ),
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.DRAWDOWN,
                threshold=settings.risk_max_drawdown,
                window_minutes=10080,  # 7 days
                cooldown_minutes=10080,
            ),
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.CONSECUTIVE_LOSSES,
                threshold=5,  # 5 consecutive losses
                window_minutes=60,
                cooldown_minutes=30,
            ),
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.VOLATILITY_SPIKE,
                threshold=3.0,  # 3x normal volatility
                window_minutes=60,
                cooldown_minutes=60,
            ),
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.CORRELATION_BREAKDOWN,
                threshold=0.9,  # Correlation > 0.9
                window_minutes=60,
                cooldown_minutes=60,
            ),
            CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.MARGIN_CALL,
                threshold=settings.risk_margin_call_level * 100,  # Margin level %
                window_minutes=5,
                cooldown_minutes=30,
            ),
        ]

        for config in configs:
            self._breakers[config.breaker_type] = CircuitBreaker(config)

    def register_breaker(self, config: CircuitBreakerConfig) -> None:
        """Register a custom circuit breaker."""
        self._breakers[config.breaker_type] = CircuitBreaker(config)

    def register_callback(self, callback: Callable[[CircuitBreakerType, CircuitBreaker], None]) -> None:
        """Register callback for breaker events."""
        self._callbacks.append(callback)

    def check_all(self, metrics: dict[str, float]) -> list[CircuitBreakerType]:
        """Check all breakers against current metrics."""
        triggered = []

        for breaker_type, breaker in self._breakers.items():
            metric_key = breaker_type.value
            if metric_key in metrics and breaker.check(metrics[metric_key]):
                triggered.append(breaker_type)
                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(breaker_type, breaker)
                    except Exception as e:
                        logger.error(f"Circuit breaker callback error: {e}")

        return triggered

    def check_breaker(self, breaker_type: CircuitBreakerType, value: float) -> bool:
        """Check specific breaker."""
        if breaker_type in self._breakers:
            return self._breakers[breaker_type].check(value)
        return False

    def get_breaker(self, breaker_type: CircuitBreakerType) -> CircuitBreaker | None:
        """Get breaker by type."""
        return self._breakers.get(breaker_type)

    def get_all_breakers(self) -> dict[CircuitBreakerType, CircuitBreaker]:
        """Get all breakers."""
        return self._breakers.copy()

    def is_any_open(self) -> bool:
        """Check if any breaker is open."""
        return any(b.is_open() for b in self._breakers.values())

    def get_open_breakers(self) -> list[CircuitBreakerType]:
        """Get list of open breakers."""
        return [bt for bt, b in self._breakers.items() if b.is_open()]

    def force_open(self, breaker_type: CircuitBreakerType, reason: str = "Manual override") -> None:
        """Force a breaker open."""
        if breaker_type in self._breakers:
            self._breakers[breaker_type].force_open(reason)

    def force_close(self, breaker_type: CircuitBreakerType) -> None:
        """Force a breaker closed."""
        if breaker_type in self._breakers:
            self._breakers[breaker_type].force_close()

    def reset_all(self) -> None:
        """Reset all breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def get_status(self) -> dict:
        """Get status of all breakers."""
        return {
            bt.value: {
                "state": b.state.value,
                "threshold": b.config.threshold,
                "triggered_at": b.triggered_at.isoformat() if b.triggered_at else None,
                "trigger_count": b.trigger_count,
                "enabled": b.config.enabled,
            }
            for bt, b in self._breakers.items()
        }


class DrawdownGuard:
    """Monitors and protects against excessive drawdown."""

    def __init__(
        self,
        max_drawdown: float = 0.10,
        warning_drawdown: float = 0.05,
        reduce_at_drawdown: float = 0.07,
        stop_at_drawdown: float = 0.10,
    ):
        self.max_drawdown = max_drawdown
        self.warning_drawdown = warning_drawdown
        self.reduce_at_drawdown = reduce_at_drawdown
        self.stop_at_drawdown = stop_at_drawdown

        self._peak_equity: Decimal = Decimal(0)
        self._current_drawdown: float = 0.0
        self._drawdown_history: deque = deque(maxlen=1000)
        self._warning_issued = False
        self._reduction_active = False
        self._trading_stopped = False

    def update(self, equity: Decimal) -> dict[str, any]:
        """Update drawdown tracking."""
        # Update peak
        if equity > self._peak_equity:
            self._peak_equity = equity
            self._warning_issued = False
            self._reduction_active = False
            self._trading_stopped = False

        # Calculate current drawdown
        if self._peak_equity > 0:
            self._current_drawdown = float((self._peak_equity - equity) / self._peak_equity)
        else:
            self._current_drawdown = 0.0

        self._drawdown_history.append({
            "timestamp": datetime.now(UTC),
            "equity": equity,
            "peak": self._peak_equity,
            "drawdown": self._current_drawdown,
        })

        # Check thresholds
        status = {
            "current_drawdown": self._current_drawdown,
            "max_drawdown": self.max_drawdown,
            "warning": False,
            "reduce_position": False,
            "stop_trading": False,
            "position_multiplier": 1.0,
        }

        if self._current_drawdown >= self.stop_at_drawdown:
            status["stop_trading"] = True
            status["position_multiplier"] = 0.0
            if not self._trading_stopped:
                logger.critical(f"DRAWDOWN GUARD: Trading STOPPED. Drawdown: {self._current_drawdown:.2%}")
                self._trading_stopped = True

        elif self._current_drawdown >= self.reduce_at_drawdown:
            status["reduce_position"] = True
            # Linear reduction from 1.0 to 0.0
            reduction_range = self.stop_at_drawdown - self.reduce_at_drawdown
            progress = (self._current_drawdown - self.reduce_at_drawdown) / reduction_range
            status["position_multiplier"] = max(0.0, 1.0 - progress)
            if not self._reduction_active:
                logger.warning(f"DRAWDOWN GUARD: Reducing positions. Multiplier: {status['position_multiplier']:.2f}")
                self._reduction_active = True

        elif self._current_drawdown >= self.warning_drawdown:
            status["warning"] = True
            status["position_multiplier"] = 1.0
            if not self._warning_issued:
                logger.warning(f"DRAWDOWN GUARD: Warning - Drawdown at {self._current_drawdown:.2%}")
                self._warning_issued = True

        return status

    def get_status(self) -> dict:
        """Get current drawdown status."""
        return {
            "peak_equity": float(self._peak_equity),
            "current_drawdown": self._current_drawdown,
            "max_drawdown": self.max_drawdown,
            "warning_drawdown": self.warning_drawdown,
            "reduce_at_drawdown": self.reduce_at_drawdown,
            "stop_at_drawdown": self.stop_at_drawdown,
            "warning_issued": self._warning_issued,
            "reduction_active": self._reduction_active,
            "trading_stopped": self._trading_stopped,
        }

    def reset(self, new_peak: Decimal | None = None) -> None:
        """Reset drawdown guard."""
        if new_peak:
            self._peak_equity = new_peak
        else:
            self._peak_equity = Decimal(0)
        self._current_drawdown = 0.0
        self._warning_issued = False
        self._reduction_active = False
        self._trading_stopped = False
        self._drawdown_history.clear()
        logger.info("Drawdown guard reset")


class VolatilityMonitor:
    """Monitors for volatility spikes."""

    def __init__(self, window: int = 20, spike_threshold: float = 3.0):
        self.window = window
        self.spike_threshold = spike_threshold
        self._returns: deque = deque(maxlen=window * 5)
        self._volatility_history: deque = deque(maxlen=1000)
        self._baseline_volatility: float | None = None

    def update(self, price: Decimal) -> dict:
        """Update with new price."""
        if len(self._returns) > 0:
            last_price = self._returns[-1]
            ret = float((price - last_price) / last_price)
            self._returns.append(ret)

            # Calculate rolling volatility
            if len(self._returns) >= self.window:
                recent_returns = list(self._returns)[-self.window:]
                current_vol = np.std(recent_returns) * np.sqrt(252)  # Annualized

                self._volatility_history.append({
                    "timestamp": datetime.now(UTC),
                    "volatility": current_vol,
                })

                # Update baseline (median of last 100)
                if len(self._volatility_history) >= 100:
                    vols = [v["volatility"] for v in list(self._volatility_history)[-100:]]
                    self._baseline_volatility = np.median(vols)

                # Check for spike
                is_spike = False
                spike_ratio = 1.0
                if self._baseline_volatility and self._baseline_volatility > 0:
                    spike_ratio = current_vol / self._baseline_volatility
                    is_spike = spike_ratio >= self.spike_threshold

                return {
                    "current_volatility": current_vol,
                    "baseline_volatility": self._baseline_volatility,
                    "spike_ratio": spike_ratio,
                    "is_spike": is_spike,
                }

        return {
            "current_volatility": 0.0,
            "baseline_volatility": self._baseline_volatility,
            "spike_ratio": 1.0,
            "is_spike": False,
        }

    def get_status(self) -> dict:
        return {
            "baseline_volatility": self._baseline_volatility,
            "current_volatility": self._volatility_history[-1]["volatility"] if self._volatility_history else 0.0,
            "spike_threshold": self.spike_threshold,
        }


# Global instances
circuit_breaker_manager = CircuitBreakerManager()
drawdown_guard = DrawdownGuard(
    max_drawdown=settings.risk_max_drawdown,
    warning_drawdown=settings.risk_max_drawdown * 0.5,
    reduce_at_drawdown=settings.risk_max_drawdown * 0.7,
    stop_at_drawdown=settings.risk_max_drawdown,
)
volatility_monitor = VolatilityMonitor()