"""Event Bus implementation for EAQTS V2.4.
Provides:
- Event dataclass with integrity hash
- EventType enum (placeholder values)
- EventBus publish/subscribe using multiprocessing.Queue
- EventStore SQLite persistence
"""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from multiprocessing import Lock, Process, Queue
from typing import Any


class EventType(Enum):
    """Placeholder event types – extend as needed per design."""
    MarketTickReceived = auto()
    CandleClosed = auto()
    MarketDataUpdated = auto()
    SessionChanged = auto()
    OpportunityGenerated = auto()
    OrderExecuted = auto()
    PositionClosed = auto()
    # Add more event types according to EAQTS spec


@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp: datetime
    source: str
    version: str
    correlation_id: str
    causation_id: str | None
    event_type: EventType
    payload: dict[str, Any]
    integrity_hash: str = ""

    def __post_init__(self):
        # Compute integrity hash if not provided
        if not self.integrity_hash:
            # Ensure deterministic JSON representation
            payload_json = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
            hash_bytes = hashlib.sha256(payload_json.encode()).hexdigest()
            object.__setattr__(self, "integrity_hash", hash_bytes)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["event_type"] = self.event_type.name
        return data

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Event":
        d = d.copy()
        d["timestamp"] = datetime.fromisoformat(d["timestamp"]).replace(tzinfo=timezone.utc)
        d["event_type"] = EventType[d["event_type"]]
        return Event(**d)


class EventBus:
    """Simple publish/subscribe bus using a multiprocessing Queue.
    Supports intra‑process callbacks and cross‑process routing.
    """

    def __init__(self, maxsize: int = 0, start_immediately: bool = False):
        self._queue: Queue = Queue(maxsize=maxsize)
        self._subscriptions: dict[EventType, list[Callable[[Event], None]]] = {}
        self._lock = Lock()
        self._router_process = Process(target=self._router, daemon=True)
        if start_immediately:
            self._router_process.start()

    def start(self):
        """Start the router process. Must be called after process‑creation guard on Windows."""
        if not self._router_process.is_alive():
            self._router_process.start()

    def _router(self):
        while True:
            event = self._queue.get()
            if event is None:
                # Sentinel for shutdown
                break
            if not isinstance(event, Event):
                continue
            # Dispatch to local callbacks safely
            callbacks = []
            with self._lock:
                callbacks = list(self._subscriptions.get(event.event_type, []))
            for cb in callbacks:
                try:
                    cb(event)
                except Exception:
                    # In production route to safety kernel; here we just ignore
                    pass
        # Clean up on exit

    def publish(self, event: Event):
        self._queue.put(event)

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        with self._lock:
            self._subscriptions.setdefault(event_type, []).append(callback)

    def stop(self):
        # Send sentinel and join router process
        self._queue.put(None)
        self._router_process.join()


class EventStore:
    """SQLite based event store for persistence and replay."""

    def __init__(self, db_path: str = "event_store.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                event_json TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def append(self, event: Event):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO events (id, event_json, ts) VALUES (?, ?, ?)",
            (event.event_id, json.dumps(event.to_dict()), event.timestamp.isoformat()),
        )
        conn.commit()
        conn.close()

    def replay(
        self,
        event_type: EventType,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Event]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        query = "SELECT event_json FROM events WHERE json_extract(event_json, '$.event_type') = ?"
        params = [event_type.name]
        if start_time:
            query += " AND ts >= ?"
            params.append(start_time.isoformat())
        if end_time:
            query += " AND ts <= ?"
            params.append(end_time.isoformat())
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return [Event.from_dict(json.loads(r[0])) for r in rows]

    def get_events_by_correlation_id(self, correlation_id: str) -> list[Event]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT event_json FROM events WHERE json_extract(event_json, '$.correlation_id') = ?",
            (correlation_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [Event.from_dict(json.loads(r[0])) for r in rows]

# Simple test harness (removed in production)
if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    bus = EventBus()
    store = EventStore()

    def printer(ev: Event):
        print("Received", ev.event_type, ev.payload)

    bus.subscribe(EventType.MarketTickReceived, printer)
    ev = Event(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
        source="test",
        version="2.4",
        correlation_id="run-001",
        causation_id=None,
        event_type=EventType.MarketTickReceived,
        payload={"symbol": "EURUSD", "bid": 1.2345, "ask": 1.2350},
    )
    bus.publish(ev)
    store.append(ev)
    bus.stop()
