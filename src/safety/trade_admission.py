from __future__ import annotations

"""Trade Admission Controller (V2.2 Section 70 / EAQTS-3226-3245).

Provides a deterministic admission decision for a trading intent based on a series of
validation steps, including the Safety Invariant Engine.
"""

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums & Result structures
# ---------------------------------------------------------------------------

class AdmissionDecision(Enum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    DEFER = "DEFER"
    EXPIRE = "EXPIRE"

@dataclass(slots=True)
class AdmissionResult:
    decision: AdmissionDecision
    reasons: list[str]
    timestamp: datetime
    intent_id: str
    snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision"] = self.decision.value
        d["timestamp"] = self.timestamp.isoformat()
        return d

# ---------------------------------------------------------------------------
# Helper persistence – simple JSON file based audit log and idempotency store.
# ---------------------------------------------------------------------------

_LOG_PATH = os.path.join(os.path.dirname(__file__), "admission_audit.log")
_IDEMPOTENCY_DB = os.path.join(os.path.dirname(__file__), "admission_idempotency.json")

_lock = threading.Lock()

def _load_idempotency() -> dict[str, dict]:
    if not os.path.exists(_IDEMPOTENCY_DB):
        return {}
    with open(_IDEMPOTENCY_DB, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Failed to parse idempotency DB, resetting")
            return {}

def _save_idempotency(store: dict[str, dict]) -> None:
    with open(_IDEMPOTENCY_DB, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)

def _append_audit_entry(entry: dict) -> None:
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# ---------------------------------------------------------------------------
# Admission controller implementation
# ---------------------------------------------------------------------------

class TradeAdmissionController:
    """Orchestrates the admission pipeline for a trading intent.

    The controller is stateless aside from the idempotency cache and audit log.
    It delegates safety invariant evaluation to a ``SafetyInvariantEngine``
    instance supplied at construction.
    """

    def __init__(self, invariant_engine: Any) -> None:
        self.engine = invariant_engine
        # Load idempotency cache once – subsequent calls are guarded by a lock.
        self._idempotency_store: dict[str, dict] = _load_idempotency()

    # ---------------------------------------------------------------------
    # Public admission entry point
    # ---------------------------------------------------------------------
    def admit(self, intent: dict[str, Any], context: dict[str, Any]) -> AdmissionResult:
        intent_id = intent.get("intent_id")
        if not intent_id:
            raise ValueError("Intent must contain an 'intent_id' key for admission tracking")

        # Idempotency check – if we have already processed this intent, return cached result.
        with _lock:
            cached = self._idempotency_store.get(intent_id)
            if cached:
                logger.info("Admission idempotency hit for intent %s", intent_id)
                return AdmissionResult(
                    decision=AdmissionDecision(cached["decision"]),
                    reasons=cached["reasons"],
                    timestamp=datetime.fromisoformat(cached["timestamp"]),
                    intent_id=intent_id,
                    snapshot=cached.get("snapshot"),
                )

        # -----------------------------------------------------------------
        # 1. Validate Opportunity – symbol, direction, strategy presence.
        # -----------------------------------------------------------------
        reasons: list[str] = []
        symbol = intent.get("symbol")
        direction = intent.get("direction")
        strategy = intent.get("strategy_id")
        if not symbol:
            reasons.append("Missing symbol in intent")
        if direction not in {"LONG", "SHORT"}:
            reasons.append(f"Invalid or missing direction: {direction}")
        if not strategy:
            reasons.append("Missing strategy identifier")

        # -----------------------------------------------------------------
        # 2. Validate TradingIntent – non‑expired, idempotency key, snapshot.
        # -----------------------------------------------------------------
        now = time.time()
        ttl = intent.get("ttl_seconds")
        created_ts = intent.get("created_timestamp")
        if created_ts is None or ttl is None:
            reasons.append("Intent missing created_timestamp or ttl_seconds for expiry check")
        elif now - created_ts >= ttl:
            reasons.append("Intent has expired")
        if not intent.get("idempotency_key"):
            reasons.append("Intent missing idempotency_key")
        if not intent.get("snapshot_id"):
            reasons.append("Intent missing decision snapshot_id")

        # -----------------------------------------------------------------
        # 3. Validate capital reservation
        # -----------------------------------------------------------------
        if not context.get("capital_reserved"):
            reasons.append("Capital not reserved for intent")

        # -----------------------------------------------------------------
        # 4. Validate risk reservation
        # -----------------------------------------------------------------
        if not context.get("risk_reserved"):
            reasons.append("Risk not reserved for intent")

        # -----------------------------------------------------------------
        # 5. Validate Safety Invariants via engine
        # -----------------------------------------------------------------
        inv_results = self.engine.evaluate_all(context)
        failed_invariants = [r for r in inv_results if not r.passed]
        if failed_invariants:
            reasons.extend([f"{r.invariant_id}: {r.violation_reason}" for r in failed_invariants])

        # -----------------------------------------------------------------
        # 6. Validate Safety Kernel approval flag
        # -----------------------------------------------------------------
        if not context.get("kernel_approved"):
            reasons.append("Safety kernel did not approve the intent")

        # -----------------------------------------------------------------
        # 7. Verifier agreement
        # -----------------------------------------------------------------
        if not context.get("risk_verifier_agrees"):
            reasons.append("Independent risk verifier did not agree")

        # -----------------------------------------------------------------
        # 8. Broker capability for the symbol
        # -----------------------------------------------------------------
        if not context.get("broker_supports_symbol"):
            reasons.append("Broker does not support the requested symbol")

        # -----------------------------------------------------------------
        # 9. Execution authority flag
        # -----------------------------------------------------------------
        if not context.get("execution_authorized"):
            reasons.append("Execution authority not granted for intent")

        # -----------------------------------------------------------------
        # Decision synthesis
        # -----------------------------------------------------------------
        if not reasons:
            decision = AdmissionDecision.ADMIT
        else:
            # If any reason is critical (capital, risk, kernel, verifier, broker, execution)
            # we REJECT; otherwise we DEFER.
            critical = {
                "Capital not reserved for intent",
                "Risk not reserved for intent",
                "Safety kernel did not approve the intent",
                "Independent risk verifier did not agree",
                "Broker does not support the requested symbol",
                "Execution authority not granted for intent",
            }
            if any(r in critical for r in reasons):
                decision = AdmissionDecision.REJECT
            else:
                decision = AdmissionDecision.DEFER

        result = AdmissionResult(
            decision=decision,
            reasons=reasons,
            timestamp=datetime.utcnow(),
            intent_id=intent_id,
            snapshot=intent.get("snapshot"),
        )

        # -----------------------------------------------------------------
        # Persistence – audit log and idempotency store.
        # -----------------------------------------------------------------
        entry = result.to_dict()
        _append_audit_entry(entry)
        with _lock:
            self._idempotency_store[intent_id] = entry
            _save_idempotency(self._idempotency_store)

        logger.info("Admission decision for intent %s: %s", intent_id, decision.value)
        return result

# ---------------------------------------------------------------------------
# Helper – expose a singleton for convenience when imported elsewhere.
# ---------------------------------------------------------------------------

# The invariant engine is a heavy object; we lazily instantiate a single shared
# instance for the process. Users can replace it via ``set_engine`` if needed.

_engine_instance = None

def get_engine() -> Any:
    global _engine_instance
    if _engine_instance is None:
        from .invariants import SafetyInvariantEngine

        _engine_instance = SafetyInvariantEngine()
    return _engine_instance


def set_engine(engine: Any) -> None:
    global _engine_instance
    _engine_instance = engine

def get_controller() -> TradeAdmissionController:
    return TradeAdmissionController(get_engine())
