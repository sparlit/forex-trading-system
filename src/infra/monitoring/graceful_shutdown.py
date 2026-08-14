"""
Graceful Shutdown Manager
==========================

Provides graceful shutdown handling for all services with SIGTERM/SIGINT support.
Manages orderly shutdown of connections, workers, and resources.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from loguru import logger


class ShutdownPhase(Enum):
    """Shutdown phases in order."""
    INIT = "init"
    STOP_ACCEPTING = "stop_accepting"  # Stop accepting new requests
    DRAIN = "drain"                    # Drain in-flight requests
    CLOSE_CONNECTIONS = "close_connections"  # Close DB, Redis, NATS connections
    FLUSH_BUFFERS = "flush_buffers"    # Flush logs, metrics, caches
    FINALIZE = "finalize"              # Final cleanup


@dataclass
class ShutdownHook:
    """A registered shutdown hook."""
    name: str
    callback: Callable[[], Any]
    async_callback: bool = False
    phase: ShutdownPhase = ShutdownPhase.CLOSE_CONNECTIONS
    priority: int = 0  # Higher priority runs first within phase
    timeout: float = 30.0  # Max time to wait for this hook
    critical: bool = True  # If True, failure blocks shutdown


@dataclass
class ShutdownResult:
    """Result of a shutdown hook execution."""
    hook_name: str
    phase: ShutdownPhase
    success: bool
    duration_seconds: float
    error: str | None = None


class GracefulShutdownManager:
    """
    Manages graceful shutdown for all services.
    
    Features:
    - SIGTERM/SIGINT signal handling
    - Phase-based shutdown with configurable hooks
    - Async/sync callback support with timeouts
    - Phase ordering and priority within phase
    - Graceful degradation on hook failures
    - Shutdown progress tracking
    """
    
    def __init__(
        self,
        shutdown_timeout: float = 60.0,
        phase_timeouts: dict[ShutdownPhase, float] | None = None,
    ):
        self.shutdown_timeout = shutdown_timeout
        self.phase_timeouts = phase_timeouts or {
            ShutdownPhase.INIT: 5.0,
            ShutdownPhase.STOP_ACCEPTING: 5.0,
            ShutdownPhase.DRAIN: 30.0,
            ShutdownPhase.CLOSE_CONNECTIONS: 20.0,
            ShutdownPhase.FLUSH_BUFFERS: 10.0,
            ShutdownPhase.FINALIZE: 5.0,
        }
        
        self._hooks: dict[ShutdownPhase, list[ShutdownHook]] = {
            phase: [] for phase in ShutdownPhase
        }
        self._shutdown_event = asyncio.Event()
        self._shutdown_started = False
        self._shutdown_complete = False
        self._shutdown_start_time: datetime | None = None
        self._results: list[ShutdownResult] = []
        self._shutdown_lock = asyncio.Lock()
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        logger.info("Graceful shutdown manager initialized")
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            if hasattr(signal, sig):
                try:
                    # Store original handler
                    original = signal.getsignal(sig)
                    if original != signal.SIG_DFL and original != signal.SIG_IGN:
                        # Chain with existing handler
                        def chained_handler(sig_num, frame):
                            self._signal_handler(sig_num, frame)
                            if callable(original):
                                original(sig_num, frame)
                        signal.signal(sig, chained_handler)
                    else:
                        signal.signal(sig, self._signal_handler)
                except Exception as e:
                    logger.warning(f"Could not set signal handler for {sig}: {e}")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name}, initiating graceful shutdown")
        
        # Schedule shutdown in event loop
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._shutdown_event.set)
        except RuntimeError:
            # No running loop, schedule for later
            self._shutdown_event.set()
    
    def register_hook(
        self,
        name: str,
        callback: Callable[[], Any],
        async_callback: bool = False,
        phase: ShutdownPhase = ShutdownPhase.CLOSE_CONNECTIONS,
        priority: int = 0,
        timeout: float = 30.0,
        critical: bool = True,
    ) -> None:
        """
        Register a shutdown hook.
        
        Args:
            name: Unique name for the hook
            callback: Function to call during shutdown
            async_callback: Whether callback is async
            phase: Shutdown phase to run in
            priority: Higher priority runs first within phase
            timeout: Max time to wait for this hook
            critical: If True, failure blocks/halts shutdown
        """
        hook = ShutdownHook(
            name=name,
            callback=callback,
            async_callback=async_callback,
            phase=phase,
            priority=priority,
            timeout=timeout,
            critical=critical,
        )
        
        self._hooks[phase].append(hook)
        # Sort by priority (highest first)
        self._hooks[phase].sort(key=lambda h: h.priority, reverse=True)
        
        logger.debug(f"Registered shutdown hook: {name} (phase={phase.value}, priority={priority})")
    
    def unregister_hook(self, name: str) -> bool:
        """Unregister a hook by name."""
        for phase in ShutdownPhase:
            for i, hook in enumerate(self._hooks[phase]):
                if hook.name == name:
                    self._hooks[phase].pop(i)
                    logger.debug(f"Unregistered shutdown hook: {name}")
                    return True
        return False
    
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()
        await self.shutdown()
    
    async def shutdown(self) -> list[ShutdownResult]:
        """
        Execute graceful shutdown.
        
        Returns:
            List of ShutdownResult for each hook executed
        """
        async with self._shutdown_lock:
            if self._shutdown_started:
                return self._results
            
            self._shutdown_started = True
            self._shutdown_start_time = datetime.now(UTC)
            
            logger.info("=" * 60)
            logger.info("GRACEFUL SHUTDOWN INITIATED")
            logger.info("=" * 60)
            
            try:
                # Execute each phase in order
                for phase in ShutdownPhase:
                    await self._execute_phase(phase)
                
                self._shutdown_complete = True
                total_duration = (datetime.now(UTC) - self._shutdown_start_time).total_seconds()
                
                logger.info("=" * 60)
                logger.info(f"GRACEFUL SHUTDOWN COMPLETED in {total_duration:.1f}s")
                logger.info("=" * 60)
                
                return self._results
                
            except Exception as e:
                logger.error(f"Shutdown error: {e}")
                self._results.append(ShutdownResult(
                    hook_name="shutdown_manager",
                    phase=ShutdownPhase.FINALIZE,
                    success=False,
                    duration_seconds=0,
                    error=str(e),
                ))
                return self._results
    
    async def _execute_phase(self, phase: ShutdownPhase) -> None:
        """Execute all hooks for a phase."""
        hooks = self._hooks[phase]
        if not hooks:
            logger.debug(f"Phase {phase.value}: no hooks registered")
            return
        
        phase_start = datetime.now(UTC)
        phase_timeout = self.phase_timeouts.get(phase, 30.0)
        
        logger.info(f"Phase {phase.value}: executing {len(hooks)} hooks (timeout: {phase_timeout}s)")
        
        # Execute hooks with timeout
        for hook in hooks:
            hook_start = datetime.now(UTC)
            
            try:
                # Execute with timeout
                if hook.async_callback:
                    await asyncio.wait_for(hook.callback(), timeout=hook.timeout)
                else:
                    # Run sync callback in executor
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: asyncio.run(hook.callback()) if asyncio.iscoroutinefunction(hook.callback) else hook.callback()
                    )
                
                duration = (datetime.now(UTC) - hook_start).total_seconds()
                self._results.append(ShutdownResult(
                    hook_name=hook.name,
                    phase=phase,
                    success=True,
                    duration_seconds=duration,
                ))
                logger.debug(f"Hook '{hook.name}' completed in {duration:.2f}s")
                
            except asyncio.TimeoutError:
                duration = (datetime.now(UTC) - hook_start).total_seconds()
                error = f"Hook timed out after {hook.timeout}s"
                self._results.append(ShutdownResult(
                    hook_name=hook.name,
                    phase=phase,
                    success=False,
                    duration_seconds=duration,
                    error=error,
                ))
                logger.error(f"Hook '{hook.name}' timed out")
                
                if hook.critical:
                    raise RuntimeError(f"Critical hook '{hook.name}' timed out")
                    
            except Exception as e:
                duration = (datetime.now(UTC) - hook_start).total_seconds()
                self._results.append(ShutdownResult(
                    hook_name=hook.name,
                    phase=phase,
                    success=False,
                    duration_seconds=duration,
                    error=str(e),
                ))
                logger.error(f"Hook '{hook.name}' failed: {e}")
                
                if hook.critical:
                    raise RuntimeError(f"Critical hook '{hook.name}' failed: {e}")
        
        phase_duration = (datetime.now(UTC) - phase_start).total_seconds()
        logger.info(f"Phase {phase.value} completed in {phase_duration:.1f}s")
    
    def get_shutdown_status(self) -> dict[str, Any]:
        """Get current shutdown status."""
        return {
            "shutdown_started": self._shutdown_started,
            "shutdown_complete": self._shutdown_complete,
            "start_time": self._shutdown_start_time.isoformat() if self._shutdown_start_time else None,
            "duration_seconds": (
                (datetime.now(UTC) - self._shutdown_start_time).total_seconds()
                if self._shutdown_start_time else None
            ),
            "hooks_registered": {
                phase.value: len(hooks) for phase, hooks in self._hooks.items()
            },
            "results": [
                {
                    "hook": r.hook_name,
                    "phase": r.phase.value,
                    "success": r.success,
                    "duration": r.duration_seconds,
                    "error": r.error,
                }
                for r in self._results
            ],
        }


# Global instance
_shutdown_manager: GracefulShutdownManager | None = None


def get_shutdown_manager() -> GracefulShutdownManager:
    """Get or create global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdownManager()
    return _shutdown_manager


def init_shutdown_manager(
    shutdown_timeout: float = 60.0,
    phase_timeouts: dict[ShutdownPhase, float] | None = None,
) -> GracefulShutdownManager:
    """Initialize global shutdown manager."""
    global _shutdown_manager
    _shutdown_manager = GracefulShutdownManager(
        shutdown_timeout=shutdown_timeout,
        phase_timeouts=phase_timeouts,
    )
    return _shutdown_manager


async def wait_for_shutdown() -> None:
    """Wait for shutdown signal and execute graceful shutdown."""
    manager = get_shutdown_manager()
    await manager.wait_for_shutdown()


def register_shutdown_hook(
    name: str,
    callback: Callable[[], Any],
    async_callback: bool = False,
    phase: ShutdownPhase = ShutdownPhase.CLOSE_CONNECTIONS,
    priority: int = 0,
    timeout: float = 30.0,
    critical: bool = True,
) -> None:
    """Register a shutdown hook on the global manager."""
    manager = get_shutdown_manager()
    manager.register_hook(
        name=name,
        callback=callback,
        async_callback=async_callback,
        phase=phase,
        priority=priority,
        timeout=timeout,
        critical=critical,
    )


# Common shutdown hooks for services
class DatabaseShutdownHooks:
    """Common database shutdown hooks."""
    
    @staticmethod
    def register_postgres_shutdown(pool: Any) -> None:
        """Register PostgreSQL pool shutdown."""
        async def close_pool():
            if pool:
                await pool.close()
                logger.info("PostgreSQL pool closed")
        
        register_shutdown_hook(
            name="postgres_pool",
            callback=close_pool,
            async_callback=True,
            phase=ShutdownPhase.CLOSE_CONNECTIONS,
            priority=10,
            timeout=10.0,
        )
    
    @staticmethod
    def register_redis_shutdown(redis: Any) -> None:
        """Register Redis connection shutdown."""
        async def close_redis():
            if redis:
                await redis.close()
                logger.info("Redis connection closed")
        
        register_shutdown_hook(
            name="redis_connection",
            callback=close_redis,
            async_callback=True,
            phase=ShutdownPhase.CLOSE_CONNECTIONS,
            priority=10,
            timeout=5.0,
        )
    
    @staticmethod
    def register_nats_shutdown(nats: Any) -> None:
        """Register NATS connection shutdown."""
        async def close_nats():
            if nats:
                await nats.close()
                logger.info("NATS connection closed")
        
        register_shutdown_hook(
            name="nats_connection",
            callback=close_nats,
            async_callback=True,
            phase=ShutdownPhase.CLOSE_CONNECTIONS,
            priority=10,
            timeout=5.0,
        )
    
    @staticmethod
    def register_influxdb_shutdown(influx: Any) -> None:
        """Register InfluxDB connection shutdown."""
        async def close_influx():
            if influx:
                await influx.close()
                logger.info("InfluxDB connection closed")
        
        register_shutdown_hook(
            name="influxdb_connection",
            callback=close_influx,
            async_callback=True,
            phase=ShutdownPhase.CLOSE_CONNECTIONS,
            priority=10,
            timeout=5.0,
        )


class APIShutdownHooks:
    """Common API server shutdown hooks."""

    @staticmethod
    def register_fastapi_shutdown(app: Any) -> None:
        """Register FastAPI shutdown."""
        @app.on_event("shutdown")
        async def shutdown() -> None:
            # Trigger the global shutdown manager
            try:
                from src.infra.monitoring.graceful_shutdown import get_shutdown_manager
                manager = get_shutdown_manager()
                await manager.shutdown()
            except Exception as e:
                logger.warning(f"Shutdown manager not available: {e}")

    @staticmethod
    def register_uvicorn_shutdown(server: Any) -> None:
        """Register Uvicorn server shutdown."""
        async def stop_server():
            if server:
                server.should_exit = True
                await server.shutdown()
                logger.info("Uvicorn server stopped")
        
        register_shutdown_hook(
            name="uvicorn_server",
            callback=stop_server,
            async_callback=True,
            phase=ShutdownPhase.STOP_ACCEPTING,
            priority=10,
            timeout=10.0,
        )


class WorkerShutdownHooks:
    """Common worker shutdown hooks."""
    
    @staticmethod
    def register_task_shutdown(tasks: list[asyncio.Task]) -> None:
        """Register task cancellation."""
        async def cancel_tasks():
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Cancelled {len(tasks)} tasks")
        
        register_shutdown_hook(
            name="async_tasks",
            callback=cancel_tasks,
            async_callback=True,
            phase=ShutdownPhase.DRAIN,
            priority=10,
            timeout=15.0,
        )
    
    @staticmethod
    def register_thread_pool_shutdown(executor: Any) -> None:
        """Register thread pool shutdown."""
        def shutdown_executor():
            if executor:
                executor.shutdown(wait=True)
                logger.info("Thread pool shutdown")
        
        register_shutdown_hook(
            name="thread_pool",
            callback=shutdown_executor,
            async_callback=False,
            phase=ShutdownPhase.FINALIZE,
            priority=5,
            timeout=5.0,
        )


# Decorator for easy hook registration
def shutdown_hook(
    name: str,
    phase: ShutdownPhase = ShutdownPhase.CLOSE_CONNECTIONS,
    priority: int = 0,
    timeout: float = 30.0,
    critical: bool = True,
):
    """Decorator to register a function as a shutdown hook."""
    def decorator(func: Callable) -> Callable:
        register_shutdown_hook(
            name=name,
            callback=func,
            async_callback=asyncio.iscoroutinefunction(func),
            phase=phase,
            priority=priority,
            timeout=timeout,
            critical=critical,
        )
        return func
    return decorator


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize
        manager = init_shutdown_manager(shutdown_timeout=60.0)
        
        # Register some hooks
        @shutdown_hook("database", phase=ShutdownPhase.CLOSE_CONNECTIONS, priority=10)
        async def close_db():
            print("Closing database connections...")
            await asyncio.sleep(0.5)
        
        @shutdown_hook("redis", phase=ShutdownPhase.CLOSE_CONNECTIONS, priority=10)
        def close_redis():
            print("Closing Redis...")
        
        @shutdown_hook("api", phase=ShutdownPhase.STOP_ACCEPTING, priority=10)
        async def stop_api():
            print("Stopping API server...")
            await asyncio.sleep(0.2)
        
        @shutdown_hook("flush_logs", phase=ShutdownPhase.FLUSH_BUFFERS, priority=5)
        def flush_logs():
            print("Flushing logs...")
        
        # Start
        manager.start()
        print("Shutdown manager started. Send SIGTERM or press Ctrl+C to test.")
        
        try:
            await manager.wait_for_shutdown()
        except KeyboardInterrupt:
            await manager.shutdown()
        
        print("Shutdown complete")
    
    asyncio.run(example())