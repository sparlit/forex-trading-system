"""Self‑diagnostics recovery utilities.
Provides a simple mechanism to stop the EventBus and raise a restart signal
when a health check fails. In a production system this would trigger a
process supervisor to restart the trading loop.
"""

from typing import Any


# Custom exception used to signal an orchestrated restart.
class RestartSignal(Exception):
    """Raised when a fatal health‑check failure occurs.
    The caller should catch this and perform any necessary cleanup before
    restarting the process or exiting.
    """


def handle_failure(bus: Any, reason: str) -> None:
    """Stop the provided ``bus`` (expected to be an ``EventBus``) and raise
    ``RestartSignal`` with the given ``reason``.
    ``bus`` is typed as ``Any`` to avoid importing the heavy ``EventBus``
    module at import time – the caller passes the instance directly.
    """
    try:
        bus.stop()
    except Exception:
        # If stopping fails we still want to raise the signal – ignore errors.
        pass
    raise RestartSignal(reason)
