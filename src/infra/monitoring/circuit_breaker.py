"""
Circuit Breaker Pattern for External APIs
==========================================

Provides circuit breaker pattern implementation for external API protection.
Prevents cascade failures when external services are unavailable.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    # Failure thresholds
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 2          # Successes in half-open before closing
    
    # Timeouts
    timeout_seconds: float = 30.0       # Request timeout
    recovery_timeout_seconds: float = 60.0  # Time in open before half-open
    
    # Exceptions to count as failures
    expected_exceptions: tuple = (Exception,)
    
    # Monitoring
    window_seconds: float = 60.0        # Rolling window for failure counting
    minimum_requests: int = 10          # Minimum requests before evaluating


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    total_requests: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None
    last_state_change: datetime = field(default_factory=datetime.now)
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    # Rolling window
    recent_requests: list[tuple[datetime, bool]] = field(default_factory=list)
    
    @property
    def failure_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failure_count / self.total_requests
    
    @property
    def recent_failure_rate(self) -> float:
        if not self.recent_requests:
            return 0.0
        failures = sum(1 for _, success in self.recent_requests if not success)
        return failures / len(self.recent_requests)


class CircuitBreaker:
    """
    Circuit breaker implementation for external API protection.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests blocked immediately
    - HALF_OPEN: Testing recovery, limited requests allowed
    
    Features:
    - Configurable failure/success thresholds
    - Rolling window for failure rate calculation
    - Automatic state transitions
    - Metrics and monitoring
    - Async/sync support
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        
        logger.info(f"Circuit breaker '{name}' initialized: {self.config}")
    
    @property
    def state(self) -> CircuitState:
        return self.stats.state
    
    @property
    def is_available(self) -> bool:
        """Check if circuit allows requests."""
        return self.stats.state != CircuitState.OPEN
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        async with self._lock:
            if not await self._can_execute():
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
            
            self.stats.total_requests += 1
            _start_time = time.time()
        
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout_seconds)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: func(*args, **kwargs)
                )
            
            await self._on_success()
            return result
            
        except asyncio.TimeoutError:
            await self._on_failure(TimeoutError(f"Request timed out after {self.config.timeout_seconds}s"))
            raise
        except self.config.expected_exceptions as e:
            await self._on_failure(e)
            raise
    
    async def _can_execute(self) -> bool:
        """Check if request can execute based on circuit state."""
        if self.stats.state == CircuitState.CLOSED:
            return True
        
        if self.stats.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            elapsed = (datetime.now(UTC) - self.stats.last_state_change).total_seconds()
            if elapsed >= self.config.recovery_timeout_seconds:
                await self._transition_to_half_open()
                return True
            return False
        
        return self.stats.state == CircuitState.HALF_OPEN
    
    async def _on_success(self) -> None:
        """Handle successful request."""
        async with self._lock:
            self.stats.success_count += 1
            self.stats.total_requests += 1
            self.stats.last_success_time = datetime.now(UTC)
            self.stats.consecutive_failures = 0
            self.stats.consecutive_successes += 1
            
            # Add to recent requests
            now = datetime.now(UTC)
            self.stats.recent_requests.append((now, True))
            self._clean_recent_requests(now)
            
            # Handle state transitions
            if self.stats.state == CircuitState.HALF_OPEN:
                if self.stats.consecutive_successes >= self.config.success_threshold:
                    await self._transition_to_closed()
    
    async def _on_failure(self, exception: Exception) -> None:
        """Handle failed request."""
        async with self._lock:
            self.stats.failure_count += 1
            self.stats.total_requests += 1
            self.stats.last_failure_time = datetime.now(UTC)
            self.stats.consecutive_failures += 1
            self.stats.consecutive_successes = 0
            
            # Add to recent requests
            now = datetime.now(UTC)
            self.stats.recent_requests.append((now, False))
            self._clean_recent_requests(now)
            
            # Handle state transitions
            if self.stats.state == CircuitState.CLOSED:
                # Check if failure threshold reached
                if (self.stats.consecutive_failures >= self.config.failure_threshold or
                    (len(self.stats.recent_requests) >= self.config.minimum_requests and
                     self.stats.recent_failure_rate >= 0.5)):
                    await self._transition_to_open()
            
            elif self.stats.state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                await self._transition_to_open()
    
    def _clean_recent_requests(self, now: datetime) -> None:
        """Remove requests outside the window."""
        cutoff = now - timedelta(seconds=self.config.window_seconds)
        self.stats.recent_requests = [
            (ts, success) for ts, success in self.stats.recent_requests
            if ts >= cutoff
        ]
    
    async def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        if self.stats.state != CircuitState.OPEN:
            logger.warning(f"Circuit breaker '{self.name}' OPENED after {self.stats.consecutive_failures} failures")
            self.stats.state = CircuitState.OPEN
            self.stats.last_state_change = datetime.now(UTC)
    
    async def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
        self.stats.state = CircuitState.HALF_OPEN
        self.stats.last_state_change = datetime.now(UTC)
        self.stats.consecutive_successes = 0
    
    async def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        logger.info(f"Circuit breaker '{self.name}' CLOSED after recovery")
        self.stats.state = CircuitState.CLOSED
        self.stats.last_state_change = datetime.now(UTC)
        self.stats.consecutive_failures = 0
        self.stats.consecutive_successes = 0
    
    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "failure_rate": self.stats.failure_rate,
            "recent_failure_rate": self.stats.recent_failure_rate,
            "consecutive_failures": self.stats.consecutive_failures,
            "consecutive_successes": self.stats.consecutive_successes,
            "last_failure_time": self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None,
            "last_success_time": self.stats.last_success_time.isoformat() if self.stats.last_success_time else None,
            "state_duration_seconds": (datetime.now(UTC) - self.stats.last_state_change).total_seconds(),
        }
    
    async def reset(self) -> None:
        """Manually reset circuit breaker to closed."""
        async with self._lock:
            self.stats = CircuitBreakerStats()
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get or create circuit breaker."""
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    async def get_breaker_stats(self, name: str) -> dict[str, Any] | None:
        """Get stats for a circuit breaker."""
        async with self._lock:
            breaker = self._breakers.get(name)
            if breaker:
                return breaker.get_stats()
            return None
    
    async def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get stats for all circuit breakers."""
        async with self._lock:
            return {name: breaker.get_stats() for name, breaker in self._breakers.items()}
    
    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        async with self._lock:
            for breaker in self._breakers.values():
                await breaker.reset()
    
    async def reset_breaker(self, name: str) -> bool:
        """Reset specific circuit breaker."""
        async with self._lock:
            breaker = self._breakers.get(name)
            if breaker:
                await breaker.reset()
                return True
            return False


# Global registry
_circuit_breaker_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get or create global circuit breaker registry."""
    global _circuit_breaker_registry
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry()
    return _circuit_breaker_registry


async def get_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
    """Get or create circuit breaker."""
    registry = get_circuit_breaker_registry()
    return await registry.get_breaker(name, config)


# Pre-configured breakers for common services
async def get_mt5_circuit_breaker() -> CircuitBreaker:
    """Get MT5 circuit breaker."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=10.0,
        recovery_timeout_seconds=30.0,
        expected_exceptions=(ConnectionError, TimeoutError, OSError),
    )
    return await get_circuit_breaker("mt5", config)


async def get_ccxt_circuit_breaker(exchange: str) -> CircuitBreaker:
    """Get CCXT exchange circuit breaker."""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=3,
        timeout_seconds=30.0,
        recovery_timeout_seconds=60.0,
        expected_exceptions=(ConnectionError, TimeoutError, OSError),
    )
    return await get_circuit_breaker(f"ccxt_{exchange}", config)


async def get_rest_circuit_breaker(provider: str) -> CircuitBreaker:
    """Get REST API circuit breaker."""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=10.0,
        recovery_timeout_seconds=30.0,
        expected_exceptions=(ConnectionError, TimeoutError, OSError),
    )
    return await get_circuit_breaker(f"rest_{provider}", config)


# Decorator for easy circuit breaker usage
def circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
    fallback: Callable | None = None,
):
    """
    Decorator to add circuit breaker to a function.
    
    Usage:
        @circuit_breaker("my_service")
        async def my_api_call():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            breaker = await get_circuit_breaker(name, config)
            try:
                return await breaker.call(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                if fallback:
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # For sync functions, run in event loop
            import asyncio
            loop = asyncio.get_event_loop()
            
            async def _run():
                breaker = await get_circuit_breaker(name, config)
                return await breaker.call(func, *args, **kwargs)
            
            try:
                return loop.run_until_complete(_run())
            except CircuitBreakerOpenError:
                if fallback:
                    return fallback(*args, **kwargs)
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Integration with existing services
class CircuitBreakerIntegration:
    """Helper to integrate circuit breakers with existing services."""
    
    @staticmethod
    async def wrap_mt5_connector(connector: Any) -> Any:
        """Wrap MT5 connector with circuit breaker."""
        breaker = await get_mt5_circuit_breaker()
        
        _original_connect = connector.connect
        _original_disconnect = connector.disconnect
        
        async def protected_connect():
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(connector.connect(), timeout=10)
                )
            )
        
        connector.connect = lambda: asyncio.get_event_loop().run_until_complete(
            asyncio.wait_for(breaker.call(protected_connect), timeout=10)
        )
        
        return connector
    
    @staticmethod
    async def wrap_ccxt_exchange(exchange: Any, exchange_name: str) -> Any:
        """Wrap CCXT exchange with circuit breaker."""
        breaker = await get_ccxt_circuit_breaker(exchange_name)
        
        # Wrap key methods
        original_fetch = exchange.fetch_ticker
        original_create_order = exchange.create_order
        
        async def protected_fetch_ticker(symbol):
            return await breaker.call(original_fetch, symbol)
        
        async def protected_create_order(*args, **kwargs):
            return await breaker.call(original_create_order, *args, **kwargs)
        
        exchange.fetch_ticker = protected_fetch_ticker
        exchange.create_order = protected_create_order
        
        return exchange


# Monitoring and alerting
async def get_all_circuit_breaker_stats() -> dict[str, dict[str, Any]]:
    """Get stats for all circuit breakers."""
    registry = get_circuit_breaker_registry()
    return await registry.get_all_stats()


async def check_circuit_breaker_health() -> dict[str, Any]:
    """Check health of all circuit breakers."""
    stats = await get_all_circuit_breaker_stats()
    
    unhealthy = []
    for name, stat in stats.items():
        if stat["state"] == "open":
            unhealthy.append({
                "name": name,
                "state": stat["state"],
                "failure_rate": stat["failure_rate"],
                "consecutive_failures": stat["consecutive_failures"],
            })
    
    return {
        "healthy": len(unhealthy) == 0,
        "total_breakers": len(stats),
        "open_breakers": len(unhealthy),
        "unhealthy": unhealthy,
    }


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Create circuit breaker
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=5.0,
            recovery_timeout_seconds=10.0,
        )
        
        breaker = CircuitBreaker("example_service", config)
        
        # Simulate successful calls
        async def successful_call():
            await asyncio.sleep(0.1)
            return "success"
        
        async def failing_call():
            await asyncio.sleep(0.1)
            raise ConnectionError("Service unavailable")
        
        # Test successful calls
        for i in range(5):
            try:
                result = await breaker.call(successful_call)
                print(f"Call {i+1}: {result}")
            except Exception as e:
                print(f"Call {i+1} failed: {e}")
        
        print(f"Stats: {breaker.get_stats()}")
        
        # Test failing calls
        for i in range(4):
            try:
                await breaker.call(failing_call)
            except ConnectionError:
                print(f"Call {i+1} failed as expected")
        
        print(f"Stats after failures: {breaker.get_stats()}")
        
        # Wait for recovery
        print("Waiting for recovery...")
        await asyncio.sleep(11)
        
        # Try again
        try:
            result = await breaker.call(successful_call)
            print(f"After recovery: {result}")
        except Exception as e:
            print(f"Still failing: {e}")
        
        print(f"Final stats: {breaker.get_stats()}")
    
    asyncio.run(example())