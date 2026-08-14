"""
Dependency Circuit Breakers + Bulkheads + Backpressure — EAQTS V2.3 N1585–N1618.

Three independent resilience primitives in one module:
  1. DependencyCircuitBreaker — CLOSED / OPEN / HALF_OPEN per external dependency
  2. ResourceBulkhead — Isolated critical-resource pools
  3. BackpressureManager — Queue monitoring, priority-aware shedding, degraded mode
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Dependency Circuit Breaker — N1585–N1593
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    cooldown_s: float = 30.0
    half_open_probes: int = 3


class DependencyCircuitBreaker:
    """
    Per-dependency circuit breaker. When OPEN, requests fail fast.
    HALF_OPEN allows a limited number of probe requests.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._states: dict[str, CircuitState] = {}
        self._failure_counts: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}
        self._half_open_success: dict[str, int] = {}

    def get_state(self, dependency: str) -> CircuitState:
        state = self._states.get(dependency, CircuitState.CLOSED)
        if state == CircuitState.OPEN:
            # Check if cooldown elapsed
            if time.time() - self._last_failure.get(dependency, 0) >= self.config.cooldown_s:
                self._states[dependency] = CircuitState.HALF_OPEN
                self._half_open_success[dependency] = 0
                logger.info(f"Circuit breaker {dependency}: OPEN → HALF_OPEN (cooldown elapsed)")
                return CircuitState.HALF_OPEN
        return state

    def record_success(self, dependency: str) -> None:
        state = self.get_state(dependency)
        if state == CircuitState.HALF_OPEN:
            self._half_open_success[dependency] += 1
            if self._half_open_success[dependency] >= self.config.half_open_probes:
                self._states[dependency] = CircuitState.CLOSED
                self._failure_counts[dependency] = 0
                logger.info(f"Circuit breaker {dependency}: HALF_OPEN → CLOSED")
        else:
            self._failure_counts[dependency] = 0

    def record_failure(self, dependency: str) -> None:
        state = self.get_state(dependency)
        self._failure_counts[dependency] = self._failure_counts.get(dependency, 0) + 1
        self._last_failure[dependency] = time.time()

        if state == CircuitState.HALF_OPEN:
            self._states[dependency] = CircuitState.OPEN
            logger.warning(f"Circuit breaker {dependency}: HALF_OPEN → OPEN (probe failed)")
        elif self._failure_counts[dependency] >= self.config.failure_threshold:
            self._states[dependency] = CircuitState.OPEN
            logger.error(f"Circuit breaker {dependency}: CLOSED → OPEN (threshold {self.config.failure_threshold} reached)")

    def call(self, dependency: str, func: Callable[[], Any]) -> Any:
        """Execute func if circuit permits; raise if OPEN."""
        state = self.get_state(dependency)
        if state == CircuitState.OPEN:
            raise RuntimeError(f"Circuit breaker {dependency} is OPEN")
        try:
            result = func()
            self.record_success(dependency)
            return result
        except Exception:
            self.record_failure(dependency)
            raise


# ---------------------------------------------------------------------------
# Resource Bulkheads — N1602–N1608
# ---------------------------------------------------------------------------

class ResourcePool(str, Enum):
    SAFETY = "safety"
    EXECUTION = "execution"
    RISK = "risk"
    DATA = "data"
    RESEARCH = "research"


@dataclass
class BulkheadConfig:
    max_workers: dict[ResourcePool, int] = field(default_factory=lambda: {
        ResourcePool.SAFETY: 4,
        ResourcePool.EXECUTION: 8,
        ResourcePool.RISK: 4,
        ResourcePool.DATA: 6,
        ResourcePool.RESEARCH: 2,
    })
    max_queue: dict[ResourcePool, int] = field(default_factory=lambda: {
        ResourcePool.SAFETY: 100,
        ResourcePool.EXECUTION: 200,
        ResourcePool.RISK: 100,
        ResourcePool.DATA: 200,
        ResourcePool.RESEARCH: 50,
    })


class ResourceBulkhead:
    """
    Isolates critical resource pools. A failure in research pool
    cannot consume workers needed by safety/execution.
    """

    def __init__(self, config: BulkheadConfig | None = None) -> None:
        self.config = config or BulkheadConfig()
        self._active_workers: dict[ResourcePool, int] = {p: 0 for p in ResourcePool}
        self._queued_tasks: dict[ResourcePool, int] = {p: 0 for p in ResourcePool}

    def acquire(self, pool: ResourcePool) -> bool:
        """Try to reserve a worker slot; return False if pool exhausted."""
        if self._active_workers[pool] < self.config.max_workers[pool]:
            self._active_workers[pool] += 1
            return True
        if self._queued_tasks[pool] < self.config.max_queue[pool]:
            self._queued_tasks[pool] += 1
            return True
        return False

    def release(self, pool: ResourcePool, was_queued: bool = False) -> None:
        """Release a worker slot."""
        if was_queued:
            self._queued_tasks[pool] = max(0, self._queued_tasks[pool] - 1)
        else:
            self._active_workers[pool] = max(0, self._active_workers[pool] - 1)

    def pool_status(self, pool: ResourcePool) -> dict[str, Any]:
        return {
            "pool": pool.value,
            "active": self._active_workers[pool],
            "max_workers": self.config.max_workers[pool],
            "queued": self._queued_tasks[pool],
            "max_queue": self.config.max_queue[pool],
            "utilization": self._active_workers[pool] / self.config.max_workers[pool],
        }

    def test_isolation(self) -> bool:
        """N1608 — Verify pool crossover is prevented."""
        # Fill research pool
        for _ in range(self.config.max_workers[ResourcePool.RESEARCH] + self.config.max_queue[ResourcePool.RESEARCH]):
            assert self.acquire(ResourcePool.RESEARCH)
        # Safety pool should still be available
        ok = self.acquire(ResourcePool.SAFETY)
        # Cleanup
        for _ in range(self.config.max_workers[ResourcePool.RESEARCH]):
            self.release(ResourcePool.RESEARCH)
        self._queued_tasks[ResourcePool.RESEARCH] = 0
        if ok:
            self.release(ResourcePool.SAFETY)
        return ok


# ---------------------------------------------------------------------------
# Backpressure Manager — N1609–N1618
# ---------------------------------------------------------------------------

class BackpressureLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    DEGRADED = "degraded"
    SAFE_MODE = "safe_mode"


class Priority(str, Enum):
    CRITICAL = 0    # Safety, Execution, Current Market Data, Reconciliation
    HIGH = 1        # Risk
    NORMAL = 2      # Data ingestion, Compliance
    LOW = 3         # Dashboard detail, Historical analysis
    DEFERRED = 4    # Research, Training


@dataclass
class BackpressureConfig:
    warning_threshold: float = 0.7
    critical_threshold: float = 0.9
    max_queue_size: int = 10000


class BackpressureManager:
    """
    Monitors queue depth and implements priority-aware data shedding.
    Critical data (safety, execution, risk) is preserved; research/training deferred.
    """

    def __init__(self, config: BackpressureConfig | None = None) -> None:
        self.config = config or BackpressureConfig()
        self._queue: deque[tuple[Priority, Any]] = deque(maxlen=self.config.max_queue_size)
        self._dropped: dict[Priority, int] = {p: 0 for p in Priority}
        self.level = BackpressureLevel.NORMAL

    def enqueue(self, priority: Priority, item: Any) -> bool:
        """Add item to queue; return False if dropped due to backpressure."""
        self._evaluate_level()
        if self.level in (BackpressureLevel.CRITICAL, BackpressureLevel.SAFE_MODE):
            if priority.value >= Priority.LOW.value:
                self._dropped[priority] += 1
                logger.debug(f"Backpressure: dropped {priority.value} item (level={self.level.value})")
                return False
        self._queue.append((priority, item))
        return True

    def dequeue(self) -> tuple[Priority, Any] | None:
        """Pop highest-priority item."""
        if not self._queue:
            return None
        # Sort by priority (lower value = higher priority)
        self._queue = deque(sorted(self._queue, key=lambda x: x[0].value))
        return self._queue.popleft()

    def _evaluate_level(self) -> None:
        util = len(self._queue) / self.config.max_queue_size
        if util >= self.config.critical_threshold:
            self.level = BackpressureLevel.CRITICAL
        elif util >= self.config.warning_threshold:
            self.level = BackpressureLevel.WARNING
        elif self.level == BackpressureLevel.CRITICAL and util < self.config.warning_threshold:
            self.level = BackpressureLevel.NORMAL

    def shed(self, amount: int = 1) -> list[Any]:
        """N1614–N1616 — Shed lowest-priority items."""
        if not self._queue:
            return []
        # Drop from lowest priority first
        self._queue = deque(sorted(self._queue, key=lambda x: -x[0].value))
        dropped = []
        for _ in range(min(amount, len(self._queue))):
            if self._queue:
                dropped.append(self._queue.pop())
        for p, _ in dropped:
            self._dropped[p] += 1
        logger.warning(f"Backpressure: shed {len(dropped)} items (level={self.level.value})")
        return dropped

    def enter_degraded(self) -> None:
        """N1617–N1618 — Enter degraded mode."""
        self.level = BackpressureLevel.DEGRADED
        logger.warning("Backpressure: entered DEGRADED mode — dashboard detail reduced")

    def enter_safe_mode(self) -> None:
        self.level = BackpressureLevel.SAFE_MODE
        logger.error("Backpressure: entered SAFE_MODE — only safety/execution preserved")

    def status(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "queue_size": len(self._queue),
            "utilization": len(self._queue) / self.config.max_queue_size,
            "dropped": {p.value: c for p, c in self._dropped.items()},
        }


# Singletons
dependency_circuit_breaker = DependencyCircuitBreaker()
resource_bulkhead = ResourceBulkhead()
backpressure_manager = BackpressureManager()
