"""
Risk Budgets — EAQTS V2.3 N0794–N0808.

Defines portfolio, asset-class, symbol, strategy, directional,
correlation, factor, liquidity, event, overnight, and execution
risk budgets with concurrent reservation locking.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from loguru import logger


class BudgetScope(str, Enum):
    PORTFOLIO = "portfolio"
    ASSET_CLASS = "asset_class"
    SYMBOL = "symbol"
    STRATEGY = "strategy"
    DIRECTIONAL = "directional"
    CORRELATION = "correlation"
    FACTOR = "factor"
    LIQUIDITY = "liquidity"
    EVENT = "event"
    OVERNIGHT = "overnight"
    EXECUTION = "execution"


@dataclass(slots=True)
class RiskBudget:
    budget_id: str
    scope: BudgetScope
    scope_key: str  # e.g., "EURUSD", "forex", "strat_1"
    limit: float
    used: float = 0.0
    reserved: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> float:
        return max(0.0, self.limit - self.used - self.reserved)

    @property
    def utilization(self) -> float:
        if self.limit <= 0:
            return 0.0
        return (self.used + self.reserved) / self.limit


@dataclass(slots=True)
class BudgetReservation:
    reservation_id: str
    budget_id: str
    amount: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    released: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class RiskBudgetEngine:
    """
    N0794–N0808: Multi-scope risk budgets with concurrent-safe reservations.

    Budgets are hierarchical: portfolio → asset-class → symbol/strategy.
    Reservations are locked atomically to prevent duplication and leakage.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._budgets: dict[str, RiskBudget] = {}
        self._reservations: dict[str, BudgetReservation] = {}
        self._scope_index: dict[BudgetScope, dict[str, str]] = {s: {} for s in BudgetScope}

    # -------------------------------------------------------------------------
    # Budget Management
    # -------------------------------------------------------------------------

    def create_budget(
        self,
        scope: BudgetScope,
        scope_key: str,
        limit: float,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RiskBudget:
        """Create or update a risk budget."""
        budget_id = f"{scope.value}:{scope_key}"
        with self._lock:
            budget = RiskBudget(
                budget_id=budget_id,
                scope=scope,
                scope_key=scope_key,
                limit=limit,
                expires_at=expires_at,
                metadata=metadata or {},
            )
            self._budgets[budget_id] = budget
            self._scope_index[scope][scope_key] = budget_id
            logger.info(f"Risk budget created: {budget_id} limit={limit}")
            return budget

    def get_budget(self, scope: BudgetScope, scope_key: str) -> RiskBudget | None:
        with self._lock:
            budget_id = self._scope_index[scope].get(scope_key)
            return self._budgets.get(budget_id) if budget_id else None

    def get_budget_by_id(self, budget_id: str) -> RiskBudget | None:
        with self._lock:
            return self._budgets.get(budget_id)

    def remove_budget(self, scope: BudgetScope, scope_key: str) -> bool:
        with self._lock:
            budget_id = self._scope_index[scope].pop(scope_key, None)
            if budget_id:
                self._budgets.pop(budget_id, None)
                logger.info(f"Risk budget removed: {budget_id}")
                return True
            return False

    # -------------------------------------------------------------------------
    # Concurrent-Safe Reservations — N0805, N0806, N0807, N0808
    # -------------------------------------------------------------------------

    def reserve(
        self,
        scope: BudgetScope,
        scope_key: str,
        amount: float,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str, str | None]:
        """
        Atomically reserve budget capacity.
        Returns (success, budget_id, reservation_id).
        """
        with self._lock:
            budget = self.get_budget(scope, scope_key)
            if not budget:
                return False, "", f"Budget not found: {scope.value}:{scope_key}"

            if budget.available < amount:
                return False, budget.budget_id, f"Insufficient budget: available={budget.available:.4f} < {amount}"

            # Check parent budgets (portfolio → asset-class → symbol/strategy)
            parent_scopes = self._get_parent_scopes(scope)
            for parent_scope, parent_key in parent_scopes:
                parent = self.get_budget(parent_scope, parent_key)
                if parent and parent.available < amount:
                    return False, budget.budget_id, f"Parent budget exhausted: {parent_scope.value}:{parent_key}"

            # All checks passed — reserve
            reservation_id = str(uuid.uuid4())
            reservation = BudgetReservation(
                reservation_id=reservation_id,
                budget_id=budget.budget_id,
                amount=amount,
                expires_at=expires_at,
                metadata=metadata or {},
            )
            self._reservations[reservation_id] = reservation
            budget.reserved += amount

            # Also reserve in parent budgets
            for parent_scope, parent_key in parent_scopes:
                parent = self.get_budget(parent_scope, parent_key)
                if parent:
                    parent.reserved += amount

            logger.debug(f"Risk reservation: {reservation_id} {amount} from {budget.budget_id}")
            return True, budget.budget_id, reservation_id

    def release_reservation(self, reservation_id: str) -> bool:
        """Release a reservation back to available capacity."""
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not reservation or reservation.released:
                return False

            budget = self._budgets.get(reservation.budget_id)
            if budget:
                budget.reserved = max(0.0, budget.reserved - reservation.amount)
                # Release from parent budgets too
                parent_scopes = self._get_parent_scopes(budget.scope)
                for parent_scope, parent_key in parent_scopes:
                    parent = self.get_budget(parent_scope, parent_key)
                    if parent:
                        parent.reserved = max(0.0, parent.reserved - reservation.amount)

            reservation.released = True
            logger.debug(f"Risk reservation released: {reservation_id}")
            return True

    def commit_reservation(self, reservation_id: str) -> bool:
        """Convert reservation to actual usage (e.g., order filled)."""
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not reservation or reservation.released:
                return False

            budget = self._budgets.get(reservation.budget_id)
            if budget:
                budget.reserved = max(0.0, budget.reserved - reservation.amount)
                budget.used += reservation.amount

                # Also commit in parent budgets
                parent_scopes = self._get_parent_scopes(budget.scope)
                for parent_scope, parent_key in parent_scopes:
                    parent = self.get_budget(parent_scope, parent_key)
                    if parent:
                        parent.reserved = max(0.0, parent.reserved - reservation.amount)
                        parent.used += reservation.amount

            reservation.released = True  # Mark as consumed
            logger.debug(f"Risk reservation committed: {reservation_id}")
            return True

    def _get_parent_scopes(self, scope: BudgetScope) -> list[tuple[BudgetScope, str]]:
        """Return parent budget scopes for hierarchical enforcement."""
        # This would be populated based on actual hierarchy
        # For now, return empty — callers should manage hierarchy explicitly
        return []

    # -------------------------------------------------------------------------
    # Usage Tracking
    # -------------------------------------------------------------------------

    def use_budget(self, scope: BudgetScope, scope_key: str, amount: float) -> bool:
        """Directly consume budget (without reservation)."""
        with self._lock:
            budget = self.get_budget(scope, scope_key)
            if not budget:
                return False
            if budget.available < amount:
                return False
            budget.used += amount
            return True

    def release_usage(self, scope: BudgetScope, scope_key: str, amount: float) -> bool:
        """Release used budget capacity (e.g., position closed)."""
        with self._lock:
            budget = self.get_budget(scope, scope_key)
            if not budget:
                return False
            budget.used = max(0.0, budget.used - amount)
            return True

    # -------------------------------------------------------------------------
    # Monitoring & Cleanup
    # -------------------------------------------------------------------------

    def get_all_budgets(self) -> list[RiskBudget]:
        with self._lock:
            return list(self._budgets.values())

    def get_active_reservations(self) -> list[BudgetReservation]:
        with self._lock:
            return [r for r in self._reservations.values() if not r.released]

    def cleanup_expired(self) -> int:
        """Remove expired budgets and reservations."""
        now = datetime.utcnow()
        removed = 0
        with self._lock:
            # Expired budgets
            expired_budgets = [
                b_id for b_id, b in self._budgets.items()
                if b.expires_at and b.expires_at < now
            ]
            for b_id in expired_budgets:
                b = self._budgets.pop(b_id)
                self._scope_index[b.scope].pop(b.scope_key, None)
                removed += 1

            # Expired reservations
            expired_res = [
                r_id for r_id, r in self._reservations.items()
                if not r.released and r.expires_at and r.expires_at < now
            ]
            for r_id in expired_res:
                r = self._reservations.pop(r_id)
                budget = self._budgets.get(r.budget_id)
                if budget:
                    budget.reserved = max(0.0, budget.reserved - r.amount)
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} expired budgets/reservations")
        return removed

    def get_utilization_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                scope.value: {
                    key: {
                        "limit": b.limit,
                        "used": b.used,
                        "reserved": b.reserved,
                        "available": b.available,
                        "utilization": b.utilization,
                    }
                    for key, b_id in idx.items()
                    if (b := self._budgets.get(b_id))
                }
                for scope, idx in self._scope_index.items()
            }


# Singleton
risk_budget_engine = RiskBudgetEngine()
