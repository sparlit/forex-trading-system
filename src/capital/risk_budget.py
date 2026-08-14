from __future__ import annotations

"""Risk Budget System – V2.2 (Sections 54‑56 / EAQTS‑3031‑3049)
Provides typed budgets, reservations and atomic updates with thread‑safety.
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto

logger = logging.getLogger(__name__)


class RiskBudgetType(Enum):
    PORTFOLIO = auto()
    ASSET_CLASS = auto()
    SYMBOL = auto()
    STRATEGY = auto()
    DIRECTIONAL = auto()
    CORRELATION = auto()
    FACTOR = auto()
    LIQUIDITY = auto()
    EVENT = auto()
    OVERNIGHT = auto()
    EXECUTION = auto()


@dataclass
class RiskBudget:
    budget_type: RiskBudgetType
    limit: float
    used: float = 0.0
    available: float = field(init=False)
    reserved: float = 0.0
    committed: float = 0.0

    def __post_init__(self) -> None:
        self.available = self.limit - self.used
        logger.debug("RiskBudget %s initialized: limit=%s used=%s", self.budget_type, self.limit, self.used)


class RiskReservationState(Enum):
    AVAILABLE = auto()
    RESERVED = auto()
    COMMITTED = auto()
    RELEASED = auto()


@dataclass
class RiskReservation:
    reservation_id: str
    budget_type: RiskBudgetType
    amount: float
    state: RiskReservationState = RiskReservationState.RESERVED
    intent_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))


class RiskBudgetManager:
    """Manages a collection of RiskBudget objects and supports atomic reservations.
    All mutation methods lock a single re‑entrant lock to guarantee consistency.
    """

    def __init__(self, config: dict[RiskBudgetType, float] | None = None):
        self._lock = threading.Lock()
        self._budgets: dict[RiskBudgetType, RiskBudget] = {}
        config = config or {}
        for bt, limit in config.items():
            self._budgets[bt] = RiskBudget(budget_type=bt, limit=limit)
        self._reservations: dict[str, RiskReservation] = {}
        logger.info("RiskBudgetManager initialized with %d budgets", len(self._budgets))

    def get_budget(self, budget_type: RiskBudgetType) -> RiskBudget:
        with self._lock:
            return self._budgets[budget_type]

    def reserve(self, intent_id: str, budget_type: RiskBudgetType, amount: float) -> RiskReservation | None:
        with self._lock:
            budget = self._budgets.get(budget_type)
            if not budget:
                logger.error("Attempted reservation for unknown budget type %s", budget_type)
                return None
            if amount > budget.available - budget.reserved:
                logger.warning("Insufficient available budget for %s: requested %s, available %s", budget_type, amount, budget.available - budget.reserved)
                return None
            reservation_id = str(uuid.uuid4())
            reservation = RiskReservation(
                reservation_id=reservation_id,
                budget_type=budget_type,
                amount=amount,
                intent_id=intent_id,
            )
            self._reservations[reservation_id] = reservation
            budget.reserved += amount
            budget.available = budget.limit - budget.used - budget.reserved
            logger.info("Reserved %s of %s for intent %s (id=%s)", amount, budget_type.name, intent_id, reservation_id)
            return reservation

    def commit(self, reservation_id: str) -> bool:
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not reservation or reservation.state != RiskReservationState.RESERVED:
                logger.error("Commit failed for reservation %s – not found or wrong state", reservation_id)
                return False
            budget = self._budgets[reservation.budget_type]
            budget.reserved -= reservation.amount
            budget.committed += reservation.amount
            budget.used += reservation.amount
            budget.available = budget.limit - budget.used - budget.reserved
            reservation.state = RiskReservationState.COMMITTED
            logger.info("Committed reservation %s of %s", reservation_id, reservation.amount)
            return True

    def release(self, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation:
                budget = self._budgets[reservation.budget_type]
                if reservation.state == RiskReservationState.RESERVED:
                    budget.reserved -= reservation.amount
                elif reservation.state == RiskReservationState.COMMITTED:
                    budget.committed -= reservation.amount
                    budget.used -= reservation.amount
                budget.available = budget.limit - budget.used - budget.reserved
                logger.info("Released reservation %s (state=%s)", reservation_id, reservation.state.name)
            else:
                logger.warning("Attempted to release unknown reservation %s", reservation_id)

    def recalculate_after_fill(self, positions: list) -> None:
        """Re‑evaluates all budgets based on a new set of positions.
        This placeholder simply resets used to 0 and recomputes available.
        In a real system you would aggregate position risk exposures per budget.
        """
        with self._lock:
            for budget in self._budgets.values():
                budget.used = 0.0
                budget.reserved = 0.0
                budget.committed = 0.0
                budget.available = budget.limit
            logger.debug("Risk budgets recalculated after fill – all usage reset")

    def check_concurrency_safe(self, intent_id: str, amounts: dict[RiskBudgetType, float]) -> bool:
        """Atomically verify that each requested amount can be reserved.
        Returns True only if *all* amounts fit within their respective budgets.
        """
        with self._lock:
            for bt, amt in amounts.items():
                budget = self._budgets.get(bt)
                if not budget or amt > budget.available - budget.reserved:
                    logger.warning("Concurrency check failed for %s: amount %s exceeds availability", bt, amt)
                    return False
            logger.debug("Concurrency check passed for intent %s", intent_id)
            return True

    def prevent_double_reservation(self, intent_id: str) -> bool:
        """Returns True if the intent does *not* already have an active reservation.
        """
        with self._lock:
            for res in self._reservations.values():
                if res.intent_id == intent_id and res.state == RiskReservationState.RESERVED:
                    logger.warning("Intent %s already has a reservation %s", intent_id, res.reservation_id)
                    return False
            logger.debug("No existing reservation for intent %s", intent_id)
            return True

    def get_all_budgets(self) -> dict[RiskBudgetType, RiskBudget]:
        with self._lock:
            # Return a shallow copy to avoid external mutation
            return dict(self._budgets)
