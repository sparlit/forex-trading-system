"""
Security & Audit Logging
========================

Provides a simple audit logger that records security‑relevant events such
as login attempts, order rejections, kill‑switch triggers and configuration
changes.

The module uses :mod:`loguru` to write structured JSON entries to a
dedicated audit channel.  In production the channel would forward to a
SIEM system.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger


@dataclass
class AuditEvent:
    """A single audit log entry."""

    event_type: str
    actor: str
    resource: str
    action: str
    outcome: str  # "success" | "failure"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


class AuditLogger:
    """Records audit events in memory and forwards to loguru."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        """Persist an audit event."""
        self._events.append(event)
        logger.bind(audit=True).info(json.dumps(event.to_dict()))

    def events(self) -> list[AuditEvent]:
        """Return a copy of the recorded events."""
        return list(self._events)

    def clear(self) -> None:
        """Remove all stored events – useful for tests."""
        self._events.clear()


# Singleton accessor ---------------------------------------------------------
_default_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Return a process‑wide :class:`AuditLogger`."""
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger


# Convenience helpers --------------------------------------------------------
def log_login(actor: str, success: bool, ip: str = "") -> None:
    get_audit_logger().record(
        AuditEvent(
            event_type="login",
            actor=actor,
            resource="auth",
            action="authenticate",
            outcome="success" if success else "failure",
            metadata={"ip": ip},
        )
    )


def log_order_rejected(actor: str, order_id: str, reason: str) -> None:
    get_audit_logger().record(
        AuditEvent(
            event_type="order_rejected",
            actor=actor,
            resource="order",
            action="place",
            outcome="failure",
            metadata={"order_id": order_id, "reason": reason},
        )
    )
