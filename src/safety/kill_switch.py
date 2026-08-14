# safety/kill_switch.py
"""Independent Kill Switch.
A lightweight watchdog that can be instantiated at module import time. It runs a daemon
thread that remains alive even if the primary AI logic crashes because the thread is
marked as ``daemon=True``. The switch monitors a set of critical health signals and
activates when any exceed its threshold.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class KillSwitch:
    """Independent kill switch monitoring catastrophic conditions.

    The class spawns a background daemon thread on construction. The thread periodically
    calls the registered ``monitor_functions`` – callables returning ``(bool, str)`` where
    the boolean indicates a fatal condition and the string provides a reason.
    If any monitor reports ``True`` the switch becomes active and records the first
    observed reason.
    """

    def __init__(self, poll_interval: float = 1.0):
        self._active: bool = False
        self._reason: str | None = None
        self._lock = threading.Lock()
        self._monitor_functions: list[Callable[[], tuple[bool, str]]] = []
        self._poll_interval = poll_interval
        self._thread = threading.Thread(target=self._run, daemon=True, name="KillSwitchWatcher")
        self._thread.start()
        logger.debug("KillSwitch background thread started (daemon=%s)", self._thread.daemon)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def register_monitor(self, fn: Callable[[], tuple[bool, str]]) -> None:
        """Register a callable that returns ``(is_fatal, reason)``.
        The function is invoked from the watchdog thread.
        """
        self._monitor_functions.append(fn)
        logger.debug("KillSwitch monitor registered: %s", fn)

    def activate(self, reason: str) -> None:
        """Manually activate the kill switch.
        This is used by components such as ``SafetyKernel.emergency_halt``.
        """
        with self._lock:
            if not self._active:
                self._active = True
                self._reason = reason
                logger.warning("KillSwitch activated manually: %s", reason)

    def deactivate(self) -> None:
        """Reset the kill switch; typically after a manual investigation.
        ``deactivate`` does *not* stop the background thread – it continues monitoring.
        """
        with self._lock:
            if self._active:
                logger.info("KillSwitch deactivated (previous reason: %s)", self._reason)
            self._active = False
            self._reason = None

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def get_reason(self) -> str | None:
        with self._lock:
            return self._reason

    # ---------------------------------------------------------------------
    # Internal watchdog loop
    # ---------------------------------------------------------------------
    def _run(self) -> None:
        while True:
            # Evaluate monitors; short‑circuit on first fatal condition.
            for fn in self._monitor_functions:
                try:
                    fatal, reason = fn()
                except Exception as exc:  # pragma: no cover – defensive
                    logger.exception("KillSwitch monitor raised exception", exc_info=exc)
                    continue
                if fatal:
                    self.activate(reason)
                    # Once active we keep the reason of the first fatal event.
                    break
            time.sleep(self._poll_interval)

    # ---------------------------------------------------------------------
    # Helper: built‑in monitors for common catastrophic failures.
    # ---------------------------------------------------------------------
    @staticmethod
    def monitor_data_freshness(get_freshness: Callable[[], int]) -> Callable[[], tuple[bool, str]]:
        """Factory for a data‑freshness monitor.

        ``get_freshness`` should return the age of the latest data in seconds.
        The monitor triggers if the age exceeds 30 seconds.
        """

        def _monitor() -> tuple[bool, str]:
            age = get_freshness()
            if age > 30:
                return True, f"Data freshness exceeded threshold (age={age}s)"
            return False, ""

        return _monitor

    @staticmethod
    def monitor_drawdown(get_drawdown: Callable[[], float]) -> Callable[[], tuple[bool, str]]:
        """Factory for drawdown monitor; triggers on >20% drawdown.
        ``get_drawdown`` returns absolute drawdown as a float (e.g., 0.22 for 22%).
        """

        def _monitor() -> tuple[bool, str]:
            dd = get_drawdown()
            if dd > 0.20:
                return True, f"Excessive drawdown detected ({dd:.2%})"
            return False, ""

        return _monitor

    @staticmethod
    def monitor_broker_health(is_healthy: Callable[[], bool]) -> Callable[[], tuple[bool, str]]:
        def _monitor() -> tuple[bool, str]:
            if not is_healthy():
                return True, "Broker health degraded"
            return False, ""
        return _monitor

    @staticmethod
    def monitor_model_health(is_healthy: Callable[[], bool]) -> Callable[[], tuple[bool, str]]:
        def _monitor() -> tuple[bool, str]:
            if not is_healthy():
                return True, "Model health failure"
            return False, ""
        return _monitor

    @staticmethod
    def monitor_security(anomaly_detected: Callable[[], bool]) -> Callable[[], tuple[bool, str]]:
        def _monitor() -> tuple[bool, str]:
            if anomaly_detected():
                return True, "Security breach detected"
            return False, ""
        return _monitor

    # Additional monitors can be added following the same pattern.

# Convenience singleton that can be imported throughout the codebase.
kill_switch = KillSwitch()
