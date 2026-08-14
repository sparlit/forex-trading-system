from __future__ import annotations

"""Capital Governance Engine – V2.2 (Section 53 / EAQTS-3011-3030)
Provides structured capital allocation, reservation and tracking with thread‑safety.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class CapitalBucket(Enum):
    RESERVE = auto()
    SAFETY = auto()
    OPERATING = auto()
    DEPLOYABLE_TRADING = auto()
    FOREX = auto()
    METALS = auto()
    EQUITIES = auto()
    FUTURES = auto()
    CRYPTO = auto()
    OPTIONS = auto()


@dataclass
class CapitalState:
    total_capital: float
    reserve_capital: float = 0.0
    safety_capital: float = 0.0
    operating_capital: float = 0.0
    deployable_trading_capital: float = 0.0
    asset_class_buckets: dict[CapitalBucket, float] = field(default_factory=dict)
    strategy_budgets: dict[str, float] = field(default_factory=dict)
    broker_budgets: dict[str, float] = field(default_factory=dict)
    venue_budgets: dict[str, float] = field(default_factory=dict)
    emergency_liquidity_reserve: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)


class CapitalGovernanceEngine:
    """Manages capital state, allocations and reservations.
    All mutating operations acquire a lock to guarantee thread‑safety.
    """

    def __init__(self, total_capital: float, config: dict[str, Any] | None = None):
        self._lock = threading.Lock()
        config = config or {}
        self.state = CapitalState(
            total_capital=total_capital,
            reserve_capital=config.get("reserve_capital", 0.0),
            safety_capital=config.get("safety_capital", 0.0),
            operating_capital=config.get("operating_capital", 0.0),
            deployable_trading_capital=config.get("deployable_trading_capital", 0.0),
        )
        # initialise buckets dict with zeroes for all asset classes
        for bucket in CapitalBucket:
            self.state.asset_class_buckets[bucket] = 0.0
        logger.info("CapitalGovernanceEngine initialized with total capital %s", total_capital)

    def get_deployable_capital(self) -> float:
        with self._lock:
            used = (
                self.state.reserve_capital
                + self.state.safety_capital
                + self.state.operating_capital
            )
            deployable = max(0.0, self.state.total_capital - used)
            logger.debug("Deployable capital calculated: %s", deployable)
            return deployable

    def allocate_to_asset_class(self, asset_class: CapitalBucket, amount: float) -> bool:
        with self._lock:
            if amount < 0:
                logger.warning("Negative allocation attempted for %s", asset_class)
                return False
            if amount > self.get_deployable_capital():
                logger.warning("Allocation of %s exceeds deployable capital", amount)
                return False
            self.state.asset_class_buckets[asset_class] += amount
            self.state.deployable_trading_capital -= amount
            self.state.last_updated = datetime.utcnow()
            logger.info("Allocated %s to asset class %s", amount, asset_class.name)
            return True

    def allocate_to_strategy(self, strategy_id: str, amount: float) -> bool:
        with self._lock:
            if amount > self.get_deployable_capital():
                logger.warning("Strategy allocation %s exceeds deployable capital", amount)
                return False
            self.state.strategy_budgets[strategy_id] = self.state.strategy_budgets.get(strategy_id, 0.0) + amount
            self.state.deployable_trading_capital -= amount
            self.state.last_updated = datetime.utcnow()
            logger.info("Allocated %s to strategy %s", amount, strategy_id)
            return True

    def allocate_to_broker(self, broker_id: str, amount: float) -> bool:
        with self._lock:
            if amount > self.get_deployable_capital():
                logger.warning("Broker allocation %s exceeds deployable capital", amount)
                return False
            self.state.broker_budgets[broker_id] = self.state.broker_budgets.get(broker_id, 0.0) + amount
            self.state.deployable_trading_capital -= amount
            self.state.last_updated = datetime.utcnow()
            logger.info("Allocated %s to broker %s", amount, broker_id)
            return True

    # Simple reservation tracking – stored in a dict keyed by reservation id (uuid string)
    _reservations: dict[str, dict[str, Any]] = {}

    def reserve_capital(self, intent_id: str, amount: float) -> bool:
        with self._lock:
            if amount > self.get_deployable_capital():
                logger.warning("Reservation of %s exceeds deployable capital", amount)
                return False
            reservation_id = f"res-{intent_id}-{datetime.utcnow().timestamp()}"
            self._reservations[reservation_id] = {
                "intent_id": intent_id,
                "amount": amount,
                "state": "RESERVED",
                "timestamp": datetime.utcnow(),
            }
            self.state.deployable_trading_capital -= amount
            self.state.last_updated = datetime.utcnow()
            logger.info("Reserved %s capital for intent %s (id=%s)", amount, intent_id, reservation_id)
            return True

    def commit_capital(self, reservation_id: str) -> bool:
        with self._lock:
            res = self._reservations.get(reservation_id)
            if not res or res["state"] != "RESERVED":
                logger.error("Commit failed: reservation %s not found or not reserved", reservation_id)
                return False
            res["state"] = "COMMITTED"
            self.state.last_updated = datetime.utcnow()
            logger.info("Committed reservation %s", reservation_id)
            return True

    def release_capital(self, reservation_id: str) -> None:
        with self._lock:
            res = self._reservations.pop(reservation_id, None)
            if res:
                self.state.deployable_trading_capital += res["amount"]
                self.state.last_updated = datetime.utcnow()
                logger.info("Released reservation %s, amount %s", reservation_id, res["amount"])
            else:
                logger.warning("Tried to release unknown reservation %s", reservation_id)

    def get_capital_state(self) -> CapitalState:
        with self._lock:
            # Return a shallow copy to prevent external mutation
            return CapitalState(**{k: getattr(self.state, k) for k in self.state.__dataclass_fields__})

    def check_concentration(self, symbol: str, amount: float) -> bool:
        # Placeholder: real implementation would inspect per‑symbol limits
        logger.debug("Concentration check for %s amount %s", symbol, amount)
        return True

    def check_drawdown_threshold(self) -> bool:
        # Placeholder – real system would compare to historical drawdown metrics
        logger.debug("Drawdown threshold check invoked")
        return False

    def check_capital_authorization(self, amount: float, component: str) -> bool:
        # Placeholder – integrate with ACL / role system
        logger.debug("Authorization check for component %s amount %s", component, amount)
        return True
