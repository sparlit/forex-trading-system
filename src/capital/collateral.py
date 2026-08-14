from __future__ import annotations

"""Collateral Management Engine — EAQTS V2.3
Tracks initial_margin, maintenance_margin, available_collateral, used_collateral,
collateral_concentration, liquidity_buffer. Generates warnings and restrictions
when buffer low or concentration high.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto

from loguru import logger


class CollateralStatus(Enum):
    HEALTHY = auto()
    WARNING = auto()
    RESTRICTED = auto()
    CRITICAL = auto()


class WarningType(Enum):
    LOW_BUFFER = "low_liquidity_buffer"
    HIGH_CONCENTRATION = "high_collateral_concentration"
    MARGIN_APPROACHING = "margin_approaching_maintenance"
    INSUFFICIENT_COLLATERAL = "insufficient_available_collateral"


class RestrictionType(Enum):
    REDUCE_POSITION = "reduce_position_size"
    BLOCK_NEW_TRADES = "block_new_trades"
    FORCE_LIQUIDATION = "force_liquidation"
    INCREASE_MARGIN = "increase_margin_requirement"


@dataclass(slots=True)
class CollateralWarning:
    warning_type: WarningType
    message: str
    severity: CollateralStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class CollateralRestriction:
    restriction_type: RestrictionType
    message: str
    severity: CollateralStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class CollateralState:
    initial_margin: float = 0.0
    maintenance_margin: float = 0.0
    available_collateral: float = 0.0
    used_collateral: float = 0.0
    collateral_concentration: float = 0.0
    liquidity_buffer: float = 0.0
    status: CollateralStatus = CollateralStatus.HEALTHY
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CollateralEngine:
    """Manages collateral state, margin tracking, and risk warnings/restrictions."""

    _LOW_BUFFER_THRESHOLD = 0.15
    _HIGH_CONCENTRATION_THRESHOLD = 0.25
    _MARGIN_WARNING_RATIO = 1.25

    def __init__(self, config: dict[str, float] | None = None):
        self._lock = threading.RLock()
        self._config = config or {}
        self._state = CollateralState()
        self._warnings: list[CollateralWarning] = []
        self._restrictions: list[CollateralRestriction] = []
        self._concentration_by_symbol: dict[str, float] = {}
        logger.info("CollateralEngine initialized")

    @property
    def state(self) -> CollateralState:
        with self._lock:
            return CollateralState(
                initial_margin=self._state.initial_margin,
                maintenance_margin=self._state.maintenance_margin,
                available_collateral=self._state.available_collateral,
                used_collateral=self._state.used_collateral,
                collateral_concentration=self._state.collateral_concentration,
                liquidity_buffer=self._state.liquidity_buffer,
                status=self._state.status,
                last_updated=self._state.last_updated,
            )

    def update_margin(
        self,
        initial_margin: float,
        maintenance_margin: float,
        available_collateral: float,
        used_collateral: float,
        concentration_by_symbol: dict[str, float] | None = None,
    ) -> None:
        with self._lock:
            self._state.initial_margin = initial_margin
            self._state.maintenance_margin = maintenance_margin
            self._state.available_collateral = available_collateral
            self._state.used_collateral = used_collateral

            if concentration_by_symbol is not None:
                self._concentration_by_symbol = concentration_by_symbol.copy()
                total_used = sum(concentration_by_symbol.values())
                max_single = max(concentration_by_symbol.values(), default=0.0)
                self._state.collateral_concentration = max_single / total_used if total_used > 0 else 0.0
            else:
                self._state.collateral_concentration = 0.0

            self._state.liquidity_buffer = (
                (available_collateral - used_collateral) / available_collateral if available_collateral > 0 else 0.0
            )
            self._state.last_updated = datetime.now(timezone.utc)

    def check_collateral_health(self) -> CollateralStatus:
        with self._lock:
            buffer_ratio = self._state.liquidity_buffer
            concentration = self._state.collateral_concentration
            margin_ratio = (
                self._state.available_collateral / self._state.maintenance_margin
                if self._state.maintenance_margin > 0 else float("inf")
            )

            if buffer_ratio < self._LOW_BUFFER_THRESHOLD or margin_ratio < 1.0:
                self._state.status = CollateralStatus.CRITICAL
            elif buffer_ratio < self._LOW_BUFFER_THRESHOLD * 2 or concentration > self._HIGH_CONCENTRATION_THRESHOLD or margin_ratio < self._MARGIN_WARNING_RATIO:
                self._state.status = CollateralStatus.WARNING
            elif concentration > self._HIGH_CONCENTRATION_THRESHOLD * 0.8:
                self._state.status = CollateralStatus.RESTRICTED
            else:
                self._state.status = CollateralStatus.HEALTHY
            return self._state.status

    def generate_warning(self) -> list[CollateralWarning]:
        with self._lock:
            warnings = []
            buffer_ratio = self._state.liquidity_buffer
            concentration = self._state.collateral_concentration
            margin_ratio = (
                self._state.available_collateral / self._state.maintenance_margin
                if self._state.maintenance_margin > 0 else float("inf")
            )

            if buffer_ratio < self._LOW_BUFFER_THRESHOLD:
                warnings.append(CollateralWarning(WarningType.LOW_BUFFER,
                    f"Liquidity buffer critically low: {buffer_ratio:.1%}", CollateralStatus.CRITICAL,
                    {"buffer_ratio": buffer_ratio, "threshold": self._LOW_BUFFER_THRESHOLD}))
            elif buffer_ratio < self._LOW_BUFFER_THRESHOLD * 2:
                warnings.append(CollateralWarning(WarningType.LOW_BUFFER,
                    f"Liquidity buffer below warning threshold: {buffer_ratio:.1%}", CollateralStatus.WARNING,
                    {"buffer_ratio": buffer_ratio, "threshold": self._LOW_BUFFER_THRESHOLD * 2}))

            if concentration > self._HIGH_CONCENTRATION_THRESHOLD:
                warnings.append(CollateralWarning(WarningType.HIGH_CONCENTRATION,
                    f"Collateral concentration too high: {concentration:.1%} in single asset", CollateralStatus.CRITICAL,
                    {"concentration": concentration, "threshold": self._HIGH_CONCENTRATION_THRESHOLD}))
            elif concentration > self._HIGH_CONCENTRATION_THRESHOLD * 0.8:
                warnings.append(CollateralWarning(WarningType.HIGH_CONCENTRATION,
                    f"Collateral concentration elevated: {concentration:.1%}", CollateralStatus.WARNING,
                    {"concentration": concentration, "threshold": self._HIGH_CONCENTRATION_THRESHOLD * 0.8}))

            if margin_ratio < 1.0:
                warnings.append(CollateralWarning(WarningType.INSUFFICIENT_COLLATERAL,
                    f"Available collateral below maintenance margin: ratio {margin_ratio:.2f}", CollateralStatus.CRITICAL,
                    {"margin_ratio": margin_ratio}))
            elif margin_ratio < self._MARGIN_WARNING_RATIO:
                warnings.append(CollateralWarning(WarningType.MARGIN_APPROACHING,
                    f"Margin approaching maintenance level: ratio {margin_ratio:.2f}", CollateralStatus.WARNING,
                    {"margin_ratio": margin_ratio, "threshold": self._MARGIN_WARNING_RATIO}))

            self._warnings.extend(warnings)
            for w in warnings:
                logger.warning("Collateral warning: %s", w.message)
            return warnings

    def generate_restriction(self) -> list[CollateralRestriction]:
        with self._lock:
            restrictions = []
            buffer_ratio = self._state.liquidity_buffer
            concentration = self._state.collateral_concentration
            margin_ratio = (
                self._state.available_collateral / self._state.maintenance_margin
                if self._state.maintenance_margin > 0 else float("inf")
            )

            if buffer_ratio < self._LOW_BUFFER_THRESHOLD or margin_ratio < 1.0:
                restrictions.append(CollateralRestriction(RestrictionType.FORCE_LIQUIDATION,
                    "Critical buffer or margin breach — force liquidation required", CollateralStatus.CRITICAL,
                    {"buffer_ratio": buffer_ratio, "margin_ratio": margin_ratio}))
                restrictions.append(CollateralRestriction(RestrictionType.BLOCK_NEW_TRADES,
                    "Block all new trade entries", CollateralStatus.CRITICAL, {}))
            elif buffer_ratio < self._LOW_BUFFER_THRESHOLD * 2:
                restrictions.append(CollateralRestriction(RestrictionType.REDUCE_POSITION,
                    "Reduce position sizes by 50%", CollateralStatus.WARNING, {"buffer_ratio": buffer_ratio}))
                restrictions.append(CollateralRestriction(RestrictionType.BLOCK_NEW_TRADES,
                    "Block new trades until buffer recovers", CollateralStatus.WARNING, {}))

            if concentration > self._HIGH_CONCENTRATION_THRESHOLD:
                restrictions.append(CollateralRestriction(RestrictionType.REDUCE_POSITION,
                    f"Reduce concentrated position — single asset at {concentration:.1%}", CollateralStatus.CRITICAL,
                    {"concentration": concentration}))
                restrictions.append(CollateralRestriction(RestrictionType.INCREASE_MARGIN,
                    "Increase margin requirement for concentrated asset by 50%", CollateralStatus.CRITICAL,
                    {"concentration": concentration}))
            elif concentration > self._HIGH_CONCENTRATION_THRESHOLD * 0.8:
                restrictions.append(CollateralRestriction(RestrictionType.INCREASE_MARGIN,
                    "Increase margin requirement for concentrated asset by 25%", CollateralStatus.WARNING,
                    {"concentration": concentration}))

            self._restrictions.extend(restrictions)
            for r in restrictions:
                logger.warning("Collateral restriction: %s", r.message)
            return restrictions

    def get_active_warnings(self) -> list[CollateralWarning]:
        with self._lock:
            return list(self._warnings)

    def get_active_restrictions(self) -> list[CollateralRestriction]:
        with self._lock:
            return list(self._restrictions)

    def clear_warnings(self) -> None:
        with self._lock: self._warnings.clear(); logger.info("Collateral warnings cleared")

    def clear_restrictions(self) -> None:
        with self._lock: self._restrictions.clear(); logger.info("Collateral restrictions cleared")

    def get_concentration_by_symbol(self) -> dict[str, float]:
        with self._lock: return self._concentration_by_symbol.copy()

    def set_thresholds(self, low_buffer: float | None = None, high_concentration: float | None = None,
                       margin_warning_ratio: float | None = None) -> None:
        with self._lock:
            if low_buffer is not None: self._LOW_BUFFER_THRESHOLD = low_buffer
            if high_concentration is not None: self._HIGH_CONCENTRATION_THRESHOLD = high_concentration
            if margin_warning_ratio is not None: self._MARGIN_WARNING_RATIO = margin_warning_ratio
            logger.info("Collateral thresholds updated: low_buffer=%s high_concentration=%s margin_warning_ratio=%s",
                        self._LOW_BUFFER_THRESHOLD, self._HIGH_CONCENTRATION_THRESHOLD, self._MARGIN_WARNING_RATIO)

collateral_engine = CollateralEngine()