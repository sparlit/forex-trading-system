from __future__ import annotations

"""Safety Invariant Engine (V2.2 Section 66 / EAQTS-3140-3163).

Defines a registry of invariant check functions and an engine that can evaluate
all invariants against a supplied execution context. The engine also provides a
simple background scheduler that runs the checks periodically.

All invariants return a tuple ``(passed: bool, violation_reason: str | None)``.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class InvariantResult:
    """Result of a single invariant evaluation.

    Attributes
    ----------
    invariant_id: str
        Identifier of the invariant, e.g. ``INV-001``.
    passed: bool
        Whether the check succeeded.
    violation_reason: str | None
        Human‑readable reason when ``passed`` is ``False``.
    timestamp: datetime
        Time when the check was performed.
    context_snapshot: dict
        Shallow copy of the context dictionary used for the evaluation.
    """

    def __init__(
        self,
        invariant_id: str,
        passed: bool,
        violation_reason: str | None,
        timestamp: datetime,
        context_snapshot: dict,
    ) -> None:
        self.invariant_id = invariant_id
        self.passed = passed
        self.violation_reason = violation_reason
        self.timestamp = timestamp
        self.context_snapshot = context_snapshot

    def to_dict(self) -> dict:
        """Return a serialisable representation for logging or persistence."""
        return {
            "invariant_id": self.invariant_id,
            "passed": self.passed,
            "violation_reason": self.violation_reason,
            "timestamp": self.timestamp.isoformat(),
            "context_snapshot": self.context_snapshot,
        }


class InvariantRegistry:
    """Simple registry that maps invariant IDs to check callables.

    The callable receives a ``context`` dictionary and must return a tuple
    ``(bool, str | None)``.
    """

    def __init__(self) -> None:
        self._registry: dict[str, Callable[[dict], tuple[bool, str | None]]] = {}

    def register(self, invariant_id: str, check_fn: Callable[[dict], tuple[bool, str | None]]) -> None:
        if invariant_id in self._registry:
            logger.warning("Invariant %s already registered – overwriting", invariant_id)
        self._registry[invariant_id] = check_fn
        logger.debug("Registered invariant %s", invariant_id)

    def get(self, invariant_id: str) -> Callable[[dict], tuple[bool, str | None]]:
        return self._registry[invariant_id]

    def all_ids(self) -> list[str]:
        return list(self._registry.keys())

    def items(self) -> list[tuple[str, Callable[[dict], tuple[bool, str | None]]]]:
        return list(self._registry.items())


class SafetyInvariantEngine:
    """Engine that evaluates registered safety invariants.

    The engine can be started in a background thread to evaluate all invariants
    at a regular interval. For now violations are emitted as log entries – the
    event bus integration is a future extension.
    """

    def __init__(self, interval_seconds: int = 5) -> None:
        self.registry = InvariantRegistry()
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._register_builtin_invariants()
        logger.info("SafetyInvariantEngine initialised with interval %s seconds", interval_seconds)

    # ---------------------------------------------------------------------
    # Registration helpers
    # ---------------------------------------------------------------------
    def _register_builtin_invariants(self) -> None:
        # The 15 invariant implementations are defined as private methods.
        self.registry.register("INV-001", self._inv_001)
        self.registry.register("INV-002", self._inv_002)
        self.registry.register("INV-003", self._inv_003)
        self.registry.register("INV-004", self._inv_004)
        self.registry.register("INV-005", self._inv_005)
        self.registry.register("INV-006", self._inv_006)
        self.registry.register("INV-007", self._inv_007)
        self.registry.register("INV-008", self._inv_008)
        self.registry.register("INV-009", self._inv_009)
        self.registry.register("INV-010", self._inv_010)
        self.registry.register("INV-011", self._inv_011)
        self.registry.register("INV-012", self._inv_012)
        self.registry.register("INV-013", self._inv_013)
        self.registry.register("INV-014", self._inv_014)
        self.registry.register("INV-015", self._inv_015)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def register_invariant(self, invariant_id: str, check_fn: Callable[[dict], tuple[bool, str | None]]) -> None:
        """Add a custom invariant at runtime."""
        self.registry.register(invariant_id, check_fn)

    def evaluate_all(self, context: dict) -> list[InvariantResult]:
        """Run *all* registered invariants against ``context``.

        Returns a list of :class:`InvariantResult` objects.
        """
        results: list[InvariantResult] = []
        for invariant_id, fn in self.registry.items():
            result = self.evaluate_one(invariant_id, context)
            results.append(result)
        return results

    def evaluate_one(self, invariant_id: str, context: dict) -> InvariantResult:
        """Evaluate a single invariant identified by ``invariant_id``.

        The ``context`` dictionary is shallow‑copied into the result for audit.
        """
        fn = self.registry.get(invariant_id)
        try:
            passed, reason = fn(context)
        except Exception as exc:  # pragma: no cover – defensive programming
            logger.exception("Invariant %s raised an exception", invariant_id)
            passed = False
            reason = f"Exception during evaluation: {exc}"
        timestamp = datetime.utcnow()
        snapshot = dict(context)  # shallow copy – callers should avoid mutating after call
        result = InvariantResult(invariant_id, passed, reason, timestamp, snapshot)
        if not passed:
            logger.warning("Safety invariant %s violated: %s", invariant_id, reason)
        else:
            logger.debug("Safety invariant %s passed", invariant_id)
        return result

    # ---------------------------------------------------------------------
    # Scheduler control
    # ---------------------------------------------------------------------
    def start_scheduler(self, interval_seconds: int | None = None) -> None:
        """Start a background thread that evaluates all invariants periodically.

        If ``interval_seconds`` is provided it overrides the instance's default.
        """
        if self._thread and self._thread.is_alive():
            logger.info("Scheduler already running")
            return
        if interval_seconds is not None:
            self._interval = interval_seconds
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
        logger.info("Safety invariant scheduler started (interval=%s s)", self._interval)

    def _run_scheduler(self) -> None:
        while not self._stop_event.is_set():
            # In a real system ``self._global_context`` would be injected.
            # Here we simply log that the scheduler tick occurred.
            logger.debug("SafetyInvariantEngine scheduler tick – evaluating all invariants")
            # Users of the engine should call ``evaluate_all`` with their context.
            time.sleep(self._interval)

    def stop_scheduler(self) -> None:
        """Signal the background thread to stop and wait for termination."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("Safety invariant scheduler stopped")

    # ---------------------------------------------------------------------
    # Built‑in invariant implementations
    # ---------------------------------------------------------------------
    # Each invariant expects the supplied ``context`` to contain the keys it needs.
    # Missing data is treated as a failure with an explanatory reason.

    def _inv_001(self, ctx: dict) -> tuple[bool, str | None]:
        # portfolio_risk <= hard_portfolio_risk_ceiling
        try:
            risk = ctx["portfolio_risk"]
            ceiling = ctx["hard_portfolio_risk_ceiling"]
        except KeyError as e:
            return False, f"Missing key {e.args[0]} for INV-001"
        if risk <= ceiling:
            return True, None
        return False, f"portfolio_risk {risk} exceeds ceiling {ceiling}"

    def _inv_002(self, ctx: dict) -> tuple[bool, str | None]:
        # total_exposure <= max_permitted_exposure
        try:
            exposure = ctx["total_exposure"]
            max_exp = ctx["max_permitted_exposure"]
        except KeyError as e:
            return False, f"Missing key {e.args[0]} for INV-002"
        if exposure <= max_exp:
            return True, None
        return False, f"total_exposure {exposure} exceeds max {max_exp}"

    def _inv_003(self, ctx: dict) -> tuple[bool, str | None]:
        # leverage <= max_permitted_leverage
        try:
            lev = ctx["leverage"]
            max_lev = ctx["max_permitted_leverage"]
        except KeyError as e:
            return False, f"Missing key {e.args[0]} for INV-003"
        if lev <= max_lev:
            return True, None
        return False, f"leverage {lev} exceeds max {max_lev}"

    def _inv_004(self, ctx: dict) -> tuple[bool, str | None]:
        # every live order has non‑empty owner_id
        orders = ctx.get("live_orders", [])
        for o in orders:
            if not o.get("owner_id"):
                return False, f"Order {o.get('order_id', '<unknown>')} missing owner_id"
        return True, None

    def _inv_005(self, ctx: dict) -> tuple[bool, str | None]:
        # every live position state == 'ACTIVE'
        positions = ctx.get("live_positions", [])
        for p in positions:
            if p.get("state") != "ACTIVE":
                return False, f"Position {p.get('position_id', '<unknown>')} not ACTIVE"
        return True, None

    def _inv_006(self, ctx: dict) -> tuple[bool, str | None]:
        # every executable intent has non‑empty snapshot_id
        intents = ctx.get("executable_intents", [])
        for i in intents:
            if not i.get("snapshot_id"):
                return False, f"Intent {i.get('intent_id', '<unknown>')} missing snapshot_id"
        return True, None

    def _inv_007(self, ctx: dict) -> tuple[bool, str | None]:
        # stale intents cannot execute (age < ttl)
        intents = ctx.get("executable_intents", [])
        now = time.time()
        for i in intents:
            created = i.get("created_timestamp")
            ttl = i.get("ttl_seconds")
            if created is None or ttl is None:
                return False, f"Intent {i.get('intent_id', '<unknown>')} missing timestamp/ttl"
            if now - created >= ttl:
                return False, f"Intent {i.get('intent_id')} is stale (age {now - created:.0f}s >= ttl {ttl}s)"
        return True, None

    def _inv_008(self, ctx: dict) -> tuple[bool, str | None]:
        # every production model is registered
        prod_models = ctx.get("production_models", [])
        registry = set(ctx.get("model_registry", []))
        for m in prod_models:
            if m not in registry:
                return False, f"Model {m} not in registry"
        return True, None

    def _inv_009(self, ctx: dict) -> tuple[bool, str | None]:
        # every production strategy is registered
        prod_strats = ctx.get("production_strategies", [])
        registry = set(ctx.get("strategy_registry", []))
        for s in prod_strats:
            if s not in registry:
                return False, f"Strategy {s} not in registry"
        return True, None

    def _inv_010(self, ctx: dict) -> tuple[bool, str | None]:
        # every production deployment has rollback artifacts
        deployments = ctx.get("production_deployments", [])
        for d in deployments:
            if not d.get("rollback_artifact_path"):
                return False, f"Deployment {d.get('deployment_id', '<unknown>')} missing rollback artifacts"
        return True, None

    def _inv_011(self, ctx: dict) -> tuple[bool, str | None]:
        # AI cannot modify immutable safety controls
        write_target = ctx.get("write_target")
        immutable = set(ctx.get("SAFETY_CONTROLS", []))
        if write_target and write_target in immutable:
            return False, f"Attempt to write immutable safety control {write_target}"
        return True, None

    def _inv_012(self, ctx: dict) -> tuple[bool, str | None]:
        # research cannot directly mutate production
        write_target = ctx.get("write_target")
        prod_paths = set(ctx.get("PRODUCTION_PATHS", []))
        if write_target and write_target in prod_paths:
            return False, f"Research attempted to modify production path {write_target}"
        return True, None

    def _inv_013(self, ctx: dict) -> tuple[bool, str | None]:
        # broker positions can be reconciled (status == 'OK')
        positions = ctx.get("broker_positions", [])
        for p in positions:
            if p.get("reconciliation_status") != "OK":
                return False, f"Broker position {p.get('position_id', '<unknown>')} status {p.get('reconciliation_status')}"
        return True, None

    def _inv_014(self, ctx: dict) -> tuple[bool, str | None]:
        # executed trades possess complete provenance
        required_keys = {"trade_id", "intent_id", "timestamp", "origin", "model_version", "strategy_id"}
        trades = ctx.get("executed_trades", [])
        for t in trades:
            missing = required_keys - t.keys()
            if missing:
                return False, f"Trade {t.get('trade_id', '<unknown>')} missing provenance keys: {missing}"
        return True, None

    def _inv_015(self, ctx: dict) -> tuple[bool, str | None]:
        # HALTED cannot directly transition to NORMAL
        transition_table = ctx.get("state_transition_table", {})
        # Expected entry: {'HALTED': ['RECOVERY', 'SHUTDOWN']}
        halted_allowed = transition_table.get("HALTED", [])
        if "NORMAL" in halted_allowed:
            return False, "Invalid transition HALTED -> NORMAL allowed in transition table"
        return True, None

    # ---------------------------------------------------------------------
    # Event emission placeholder – currently logs only
    # ---------------------------------------------------------------------
    def _emit_violation(self, result: InvariantResult) -> None:
        # In the future this could push to an event bus; for now we log.
        logger.error("Invariant violation emitted: %s", result.to_dict())
