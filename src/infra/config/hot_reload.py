"""
Config Hot-Reload Manager
=========================

Provides SIGHUP-based configuration hot-reloading for all services.
Watches configuration files and triggers reload callbacks.
"""

from __future__ import annotations

import asyncio
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.infra.config.settings import settings


@dataclass
class ReloadCallback:
    """A registered reload callback."""
    name: str
    callback: Callable[[], Any]
    async_callback: bool = False
    priority: int = 0  # Higher priority runs first


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for config files."""
    
    def __init__(self, reload_manager: ConfigReloader):
        self.reload_manager = reload_manager
        self._last_modified = {}
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path).resolve()
        
        # Debounce rapid modifications
        now = time.time()
        last = self._last_modified.get(str(file_path), 0)
        if now - last < 0.5:  # 500ms debounce
            return
        self._last_modified[str(file_path)] = now
        
        # Check if it's a watched file
        for watched in self.reload_manager.watched_files:
            if file_path.match(watched) or file_path == watched:
                logger.info(f"Config file changed: {file_path}")
                self.reload_manager.trigger_reload(f"file_change:{file_path}")
                break


class ConfigReloader:
    """
    Configuration hot-reload manager with SIGHUP and file watching support.
    
    Features:
    - SIGHUP signal handling (Unix)
    - File system watching for config files
    - Async/sync callback support
    - Priority-based callback execution
    - Reload debouncing
    - Graceful error handling
    """
    
    def __init__(
        self,
        watched_paths: list[str] | None = None,
        reload_interval: float = 1.0,
    ):
        self.watched_files = [Path(p).resolve() for p in (watched_paths or [".env", "config/"])]
        self.reload_interval = reload_interval
        
        self._callbacks: list[ReloadCallback] = []
        self._observer: Observer | None = None
        self._handler: ConfigFileHandler | None = None
        self._running = False
        self._shutdown_event = threading.Event()
        self._last_reload = 0.0
        self._reload_lock = threading.Lock()
        
        # Register signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for SIGHUP."""
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._signal_handler)
            logger.info("SIGHUP handler registered")
        
        # Also handle SIGTERM/SIGINT for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            if hasattr(signal, sig):
                signal.signal(sig, self._shutdown_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle SIGHUP signal."""
        logger.info("Received SIGHUP, triggering config reload")
        self.trigger_reload("signal:SIGHUP")
    
    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down")
        self.shutdown()
    
    def register_callback(
        self,
        name: str,
        callback: Callable[[], Any],
        async_callback: bool = False,
        priority: int = 0,
    ) -> None:
        """
        Register a reload callback.
        
        Args:
            name: Unique name for the callback
            callback: Function to call on reload
            async_callback: Whether callback is async
            priority: Higher priority runs first
        """
        callback_obj = ReloadCallback(
            name=name,
            callback=callback,
            async_callback=async_callback,
            priority=priority,
        )
        self._callbacks.append(callback_obj)
        # Sort by priority (highest first)
        self._callbacks.sort(key=lambda c: c.priority, reverse=True)
        logger.debug(f"Registered reload callback: {name} (priority={priority})")
    
    def unregister_callback(self, name: str) -> bool:
        """Unregister a callback by name."""
        for i, cb in enumerate(self._callbacks):
            if cb.name == name:
                self._callbacks.pop(i)
                logger.debug(f"Unregistered reload callback: {name}")
                return True
        return False
    
    def trigger_reload(self, reason: str = "manual") -> None:
        """
        Trigger a configuration reload.
        
        Args:
            reason: Reason for the reload (for logging)
        """
        with self._reload_lock:
            now = time.time()
            if now - self._last_reload < self.reload_interval:
                logger.debug(f"Reload skipped (debounced): {reason}")
                return
            self._last_reload = now
        
        logger.info(f"Config reload triggered: {reason}")
        
        # Execute callbacks
        for callback in self._callbacks:
            try:
                if callback.async_callback:
                    # Schedule async callback
                    asyncio.run_coroutine_threadsafe(
                        self._run_async_callback(callback),
                        asyncio.get_event_loop(),
                    )
                else:
                    # Run sync callback
                    callback.callback()
            except Exception as e:
                logger.error(f"Reload callback '{callback.name}' failed: {e}")
    
    async def _run_async_callback(self, callback: ReloadCallback) -> None:
        """Run async callback."""
        try:
            await callback.callback()
        except Exception as e:
            logger.error(f"Async reload callback '{callback.name}' failed: {e}")
    
    def start(self) -> None:
        """Start the config reloader."""
        if self._running:
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        # Start file watcher
        self._observer = Observer()
        self._handler = ConfigFileHandler(self)
        
        for watched in self.watched_files:
            path = Path(watched)
            if path.is_dir():
                self._observer.schedule(self._handler, str(path), recursive=True)
            elif path.is_file():
                self._observer.schedule(self._handler, str(path.parent), recursive=False)
        
        self._observer.start()
        logger.info(f"Config reloader started, watching: {[str(p) for p in self.watched_files]}")
    
    def shutdown(self) -> None:
        """Shutdown the config reloader."""
        if not self._running:
            return
        
        self._running = False
        self._shutdown_event.set()
        
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        
        logger.info("Config reloader stopped")
    
    def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        """Wait for shutdown signal."""
        return self._shutdown_event.wait(timeout)


# Global instance
_config_reloader: ConfigReloader | None = None


def get_config_reloader() -> ConfigReloader:
    """Get or create global config reloader."""
    global _config_reloader
    if _config_reloader is None:
        _config_reloader = ConfigReloader()
    return _config_reloader


def init_config_reloader(
    watched_paths: list[str] | None = None,
    reload_interval: float = 1.0,
) -> ConfigReloader:
    """Initialize global config reloader."""
    global _config_reloader
    _config_reloader = ConfigReloader(
        watched_paths=watched_paths,
        reload_interval=reload_interval,
    )
    return _config_reloader


# Convenience decorator for registering reload callbacks
def on_config_reload(
    name: str | None = None,
    priority: int = 0,
    async_callback: bool = False,
):
    """
    Decorator to register a function as a config reload callback.
    
    Usage:
        @on_config_reload("my_service", priority=10)
        async def reload_my_service():
            await my_service.reload_config()
    """
    def decorator(func):
        callback_name = name or func.__name__
        reloader = get_config_reloader()
        reloader.register_callback(
            name=callback_name,
            callback=func,
            async_callback=async_callback,
            priority=priority,
        )
        return func
    return decorator


# Example usage and integration
class ServiceBase:
    """Base class for services with config reload support."""
    
    def __init__(self, name: str):
        self.name = name
        self._reloader = get_config_reloader()
        self._register_reload()
    
    def _register_reload(self) -> None:
        self._reloader.register_callback(
            name=f"{self.name}_reload",
            callback=self.reload_config,
            async_callback=asyncio.iscoroutinefunction(self.reload_config),
            priority=10,
        )
    
    async def reload_config(self) -> None:
        """Override in subclass to implement config reload logic."""
        logger.info(f"{self.name}: Reloading configuration")
    
    def shutdown(self) -> None:
        """Cleanup on shutdown."""
        self._reloader.unregister_callback(f"{self.name}_reload")


# Integration with settings
def setup_settings_reload() -> None:
    """Set up automatic settings reload on config change."""
    reloader = get_config_reloader()
    
    @reloader.register_callback(
        name="settings_reload",
        priority=100,  # High priority - settings reload first
    )
    def reload_settings():
        # Re-read .env file
        settings.__init__()  # Re-initialize settings
        logger.info("Settings reloaded from .env")


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize
        reloader = init_config_reloader(
            watched_paths=[".env", "config/"],
            reload_interval=1.0,
        )
        
        # Register some callbacks
        @on_config_reload("database", priority=10)
        async def reload_database():
            logger.info("Reloading database connections...")
            # Recreate connection pools
        
        @on_config_reload("redis", priority=10)
        def reload_redis():
            print("Reloading Redis connections...")
        
        @on_config_reload("brokers", priority=5)
        async def reload_brokers():
            print("Reconnecting brokers...")
        
        # Start
        reloader.start()
        print("Config reloader started. Send SIGHUP or modify .env to trigger reload.")
        
        # Wait for shutdown
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            reloader.shutdown()
            print("Shutdown complete")
    
    asyncio.run(example())