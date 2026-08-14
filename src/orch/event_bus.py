"""Event Bus and persistence layer for EAQTS.

Provides:
- Event dataclass with serialization.
- EventType enum covering all spec event types (Section 8).
- EventBus for publishing/subscribing using multiprocessing.Queue.
- EventStore for SQLite event sourcing (Section 9).
- DecisionSnapshot dataclass (Section 10).

All code is pure Python, type‑hinted, and compatible with Python 3.11.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import queue
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Event definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """Immutable event representation.

    Attributes match the specification (Section 8) exactly.
    """

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    version: str = "1.0"
    correlation_id: str = ""
    causation_id: str | None = None
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""

    def __post_init__(self) -> None:  # pragma: no cover – executed automatically
        # Compute integrity hash if not supplied.
        if not self.integrity_hash:
            # Hash the JSON representation of payload (sorted keys) together with event_id.
            payload_bytes = json.dumps(self.payload, sort_keys=True).encode()
            base = f"{self.event_id}{payload_bytes.decode()}".encode()
            object.__setattr__(self, "integrity_hash", hashlib.sha256(base).hexdigest())

    # ---------------------------------------------------------------------
    # Serialisation helpers
    # ---------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert UUID and datetime to str for JSON friendliness.
        d["event_id"] = str(d["event_id"])
        d["timestamp"] = d["timestamp"].isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(',', ':'), sort_keys=True)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Event:
        # Accept both string and proper types for UUID / datetime.
        ev_id = uuid.UUID(data["event_id"]) if isinstance(data["event_id"], str) else data["event_id"]
        ts = datetime.fromisoformat(data["timestamp"]).replace(tzinfo=UTC) if isinstance(data["timestamp"], str) else data["timestamp"]
        return Event(
            event_id=ev_id,
            timestamp=ts,
            source=data.get("source", ""),
            version=data.get("version", "1.0"),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id"),
            event_type=data.get("event_type", ""),
            payload=data.get("payload", {}),
            integrity_hash=data.get("integrity_hash", ""),
        )

    @staticmethod
    def from_json(s: str) -> Event:
        return Event.from_dict(json.loads(s))

# ---------------------------------------------------------------------------
# EventType enum – exhaustive list from the spec (Section 8)
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    MARKET_TICK_RECEIVED = "MarketTickReceived"
    CANDLE_CLOSED = "CandleClosed"
    MARKET_DATA_UPDATED = "MarketDataUpdated"
    SESSION_CHANGED = "SessionChanged"
    MARKET_CALENDAR_CHANGED = "MarketCalendarChanged"
    SYMBOL_UNIVERSE_CHANGED = "SymbolUniverseChanged"
    FEATURE_VECTOR_UPDATED = "FeatureVectorUpdated"
    MARKET_STATE_CHANGED = "MarketStateChanged"
    REGIME_CHANGED = "RegimeChanged"
    PREDICTION_CREATED = "PredictionCreated"
    PREDICTION_CALIBRATED = "PredictionCalibrated"
    PREDICTION_ABSTAINED = "PredictionAbstained"
    PREDICTION_DISAGREEMENT_DETECTED = "PredictionDisagreementDetected"
    STRATEGY_EVALUATED = "StrategyEvaluated"
    STRATEGY_SELECTED = "StrategySelected"
    STRATEGY_QUARANTINED = "StrategyQuarantined"
    OPPORTUNITY_CREATED = "OpportunityCreated"
    OPPORTUNITY_DEFERRED = "OpportunityDeferred"
    OPPORTUNITY_EXPIRED = "OpportunityExpired"
    RISK_APPROVED = "RiskApproved"
    RISK_REJECTED = "RiskRejected"
    RISK_BUDGET_RESERVED = "RiskBudgetReserved"
    RISK_BUDGET_RELEASED = "RiskBudgetReleased"
    SAFETY_INVARIANT_VIOLATION = "SafetyInvariantViolation"
    TRADING_INTENT_CREATED = "TradingIntentCreated"
    TRADING_INTENT_EXPIRED = "TradingIntentExpired"
    ORDER_VALIDATED = "OrderValidated"
    ORDER_SUBMITTED = "OrderSubmitted"
    ORDER_ACCEPTED = "OrderAccepted"
    ORDER_REJECTED = "OrderRejected"
    ORDER_PARTIALLY_FILLED = "OrderPartiallyFilled"
    ORDER_FILLED = "OrderFilled"
    ORDER_CANCELLED = "OrderCancelled"
    POSITION_OPENED = "PositionOpened"
    POSITION_MODIFIED = "PositionModified"
    POSITION_CLOSED = "PositionClosed"
    TRADE_COMPLETED = "TradeCompleted"
    RECONCILIATION_MISMATCH = "ReconciliationMismatch"
    RISK_VERIFICATION_MISMATCH = "RiskVerificationMismatch"
    EXECUTION_VERIFICATION_MISMATCH = "ExecutionVerificationMismatch"
    ACCOUNTING_MISMATCH = "AccountingMismatch"
    MODEL_UPDATED = "ModelUpdated"
    STRATEGY_UPDATED = "StrategyUpdated"
    MODEL_DEGRADED = "ModelDegraded"
    STRATEGY_DEGRADED = "StrategyDegraded"
    SYSTEM_FAULT = "SystemFault"
    RECOVERY_STARTED = "RecoveryStarted"
    RECOVERY_COMPLETED = "RecoveryCompleted"
    DEPLOYMENT_STARTED = "DeploymentStarted"
    DEPLOYMENT_COMPLETED = "DeploymentCompleted"
    ROLLBACK_STARTED = "RollbackStarted"
    ROLLBACK_COMPLETED = "RollbackCompleted"
    SECURITY_EVENT = "SecurityEvent"
    CONFIGURATION_CHANGED = "ConfigurationChanged"
    AUTHORITY_CHANGED = "AuthorityChanged"
    CAPITAL_BUDGET_CHANGED = "CapitalBudgetChanged"
    CAPABILITY_DEGRADED = "CapabilityDegraded"
    CAPABILITY_RESTORED = "CapabilityRestored"

# ---------------------------------------------------------------------------
# DecisionSnapshot – immutable snapshot of a trading decision (Section 10)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionSnapshot:
    snapshot_id: uuid.UUID = field(default_factory=uuid.uuid4)
    market_state: dict[str, Any] = field(default_factory=dict)
    market_data_state: dict[str, Any] = field(default_factory=dict)
    feature_state: dict[str, Any] = field(default_factory=dict)
    model_versions: dict[str, str] = field(default_factory=dict)
    strategy_versions: dict[str, str] = field(default_factory=dict)
    risk_config: dict[str, Any] = field(default_factory=dict)
    portfolio_state: dict[str, Any] = field(default_factory=dict)
    broker_state: dict[str, Any] = field(default_factory=dict)
    execution_state: dict[str, Any] = field(default_factory=dict)
    data_source_state: dict[str, Any] = field(default_factory=dict)
    safety_state: dict[str, Any] = field(default_factory=dict)
    capital_state: dict[str, Any] = field(default_factory=dict)
    configuration_version: str = ""
    dependency_versions: dict[str, str] = field(default_factory=dict)
    system_version: str = "1.0"

# ---------------------------------------------------------------------------
# EventBus – publish/subscribe routing via multiprocessing.Queue
# ---------------------------------------------------------------------------

class EventBus:
    """A simple event bus supporting intra‑process (thread) and inter‑process modes.

    The bus is instantiated once (usually in the Orchestrator) and the same
    ``queue.Queue`` (for threads) or ``multiprocessing.Queue`` (for processes) is
    shared with any child processes.  Subscribers register a callable that
    receives a fully deserialized :class:`Event` instance.
    """

    def __init__(self, *, mode: str = "process") -> None:
        if mode not in {"process", "thread"}:
            raise ValueError("mode must be 'process' or 'thread'")
        self.mode = mode
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._shutdown = threading.Event()
        # Choose the appropriate queue implementation.
        self._queue: Any = (
            multiprocessing.Queue()
            if mode == "process"
            else queue.Queue()
        )
        # Start the dispatch loop in a daemon thread.
        self._thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._thread.start()

    @property
    def raw_queue(self) -> Any:
        """Expose the underlying multiprocessing.Queue.

        Child processes can safely share this object; it is picklable.
        """
        return self._queue

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def publish(self, event: Event) -> None:
        """Place an event onto the underlying queue.

        The call is non‑blocking; the event will be routed to matching
        subscribers by the internal dispatch loop.
        """
        if not isinstance(event, Event):
            raise TypeError("publish expects an Event instance")
        self._queue.put(event)

    def subscribe(self, event_type: str | EventType, callback: Callable[[Event], None]) -> None:
        """Register *callback* for a specific *event_type*.

        ``callback`` may be any callable; it will be invoked synchronously in the
        dispatch thread.
        """
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        self._subscribers.setdefault(key, []).append(callback)

    def stop(self) -> None:
        """Signal the dispatch thread to exit and join it.

        A special ``None`` sentinel is placed onto the queue to unblock any
        waiting ``get`` operation.
        """
        self._shutdown.set()
        # ``None`` acts as a sentinel understood by the dispatch loop.
        self._queue.put(None)
        self._thread.join(timeout=5)

    # ---------------------------------------------------------------------
    # Internal behaviour
    # ---------------------------------------------------------------------
    def _dispatch_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                item = self._queue.get()
                if item is None:
                    # Sentinel – exit loop.
                    break
                if not isinstance(item, Event):
                    # Defensive: ignore malformed items.
                    continue
                # Gather callbacks for the specific event type and any wildcard subscribers.
                callbacks = []
                # Exact matches
                callbacks.extend(self._subscribers.get(item.event_type, []))
                # Wildcard subscribers registered under "*"
                callbacks.extend(self._subscribers.get("*", []))
                for cb in callbacks:
                    try:
                        cb(item)
                    except Exception as exc:  # pragma: no cover – best‑effort logging
                        # Avoid bringing down the dispatch thread.
                        import logging

                        logging.getLogger(__name__).error(
                            "Error in event subscriber for %s: %s", item.event_type, exc
                        )
            except Exception:  # pragma: no cover – robust loop
                continue

# ---------------------------------------------------------------------------
# EventStore – SQLite persistence for event sourcing (Section 9)
# ---------------------------------------------------------------------------

class EventStore:
    """Append‑only event store using SQLite.

    The store is deliberately simple – it stores the JSON payload, together with
    the core event metadata, and provides replay utilities required by the
    specification.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        # Default location is ``event_store.db`` in the project root.
        default_path = Path.cwd() / "event_store.db"
        self.db_path = Path(db_path) if db_path else default_path
        self._ensure_schema()

    # ---------------------------------------------------------------------
    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    source TEXT,
                    version TEXT,
                    correlation_id TEXT,
                    causation_id TEXT,
                    event_type TEXT,
                    payload TEXT,
                    integrity_hash TEXT
                )
                """
            )
            conn.commit()

    # ---------------------------------------------------------------------
    def append(self, event: Event) -> None:
        """Persist *event*.

        If the event already exists (same ``event_id``) the call is ignored –
        event stores are append‑only.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO events (event_id, timestamp, source, version, correlation_id, causation_id, event_type, payload, integrity_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(event.event_id),
                    event.timestamp.isoformat(),
                    event.source,
                    event.version,
                    event.correlation_id,
                    event.causation_id,
                    event.event_type,
                    json.dumps(event.payload),
                    event.integrity_hash,
                ),
            )
            conn.commit()

    # ---------------------------------------------------------------------
    def replay(
        self,
        event_type: str | EventType,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Event]:
        """Return a list of events of *event_type* between *start_time* and *end_time*.
        """
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE event_type = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
                (key, start_time.isoformat(), end_time.isoformat()),
            ).fetchall()
        events: list[Event] = []
        for (
            ev_id,
            ts,
            source,
            version,
            correlation_id,
            causation_id,
            ev_type,
            payload,
            integrity_hash,
        ) in rows:
            ev = Event(
                event_id=uuid.UUID(ev_id),
                timestamp=datetime.fromisoformat(ts).replace(tzinfo=UTC),
                source=source,
                version=version,
                correlation_id=correlation_id,
                causation_id=causation_id,
                event_type=ev_type,
                payload=json.loads(payload),
                integrity_hash=integrity_hash,
            )
            events.append(ev)
        return events

    # ---------------------------------------------------------------------
    def get_events_by_correlation_id(self, correlation_id: str) -> list[Event]:
        """Fetch all events sharing the given *correlation_id*.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE correlation_id = ? ORDER BY timestamp",
                (correlation_id,),
            ).fetchall()
        result: list[Event] = []
        for (
            ev_id,
            ts,
            source,
            version,
            corr_id,
            causation_id,
            ev_type,
            payload,
            integrity_hash,
        ) in rows:
            result.append(
                Event(
                    event_id=uuid.UUID(ev_id),
                    timestamp=datetime.fromisoformat(ts).replace(tzinfo=UTC),
                    source=source,
                    version=version,
                    correlation_id=corr_id,
                    causation_id=causation_id,
                    event_type=ev_type,
                    payload=json.loads(payload),
                    integrity_hash=integrity_hash,
                )
            )
        return result
