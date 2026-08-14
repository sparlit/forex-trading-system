from __future__ import annotations

"""Factor Risk Engine – V2.2 (Section 58 / EAQTS-3050-3070)
Implements factor exposures, crisis limits and correlation checks without heavy dependencies.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class Factor(Enum):
    USD = auto()
    RATES = auto()
    INFLATION = auto()
    COMMODITIES = auto()
    GOLD = auto()
    EQUITY_BETA = auto()
    CRYPTO_BETA = auto()
    VOLATILITY = auto()
    RISK_ON_OFF = auto()
    CARRY = auto()
    MOMENTUM = auto()
    LIQUIDITY = auto()


@dataclass
class FactorExposure:
    factor: Factor
    exposure_value: float
    contribution_to_risk: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class FactorRiskEngine:
    """Pure‑Python engine for factor risk calculations.
    All methods are static‑style – they take inputs and return results without
    mutating internal state, making the class easy to test and thread‑safe.
    """

    @staticmethod
    def compute_factor_exposure(positions: list[dict[str, Any]], factor_loadings: dict[Factor, float]) -> list[FactorExposure]:
        """Calculate exposure per factor.
        *positions* – list of dicts containing at least ``"size"`` (pos size) and optionally ``"price"``.
        *factor_loadings* – mapping from Factor to loading coefficient (e.g. beta).
        Returns a list of FactorExposure objects.
        """
        exposures: list[FactorExposure] = []
        for factor, loading in factor_loadings.items():
            total = 0.0
            for pos in positions:
                size = float(pos.get("size", 0))
                price = float(pos.get("price", 1))
                total += size * price * loading
            contribution = total ** 2  # simplistic risk contribution (variance proxy)
            exposures.append(FactorExposure(factor=factor, exposure_value=total, contribution_to_risk=contribution))
        logger.debug("Computed factor exposures for %d factors", len(factor_loadings))
        return exposures

    @staticmethod
    def compute_crisis_factor_limits(regime: str) -> dict[Factor, float]:
        """Return tighter factor limits when in a crisis regime.
        The *regime* string can be ``"normal"`` or ``"crisis"`` (case‑insensitive).
        """
        base_limits = {
            Factor.USD: 1.0,
            Factor.RATES: 0.8,
            Factor.INFLATION: 0.7,
            Factor.COMMODITIES: 0.9,
            Factor.GOLD: 0.6,
            Factor.EQUITY_BETA: 0.9,
            Factor.CRYPTO_BETA: 1.2,
            Factor.VOLATILITY: 0.5,
            Factor.RISK_ON_OFF: 0.8,
            Factor.CARRY: 0.7,
            Factor.MOMENTUM: 0.9,
            Factor.LIQUIDITY: 0.6,
        }
        if regime.lower() == "crisis":
            # tighten limits by 30% relative to base
            tightened = {f: lim * 0.7 for f, lim in base_limits.items()}
            logger.debug("Crisis regime – factor limits tightened")
            return tightened
        logger.debug("Normal regime – returning base factor limits")
        return base_limits

    @staticmethod
    def detect_correlation_convergence(corr_matrix: Any) -> bool:
        """Detect if the correlation matrix is approaching an identity of all ones.
        Accepts a list‑of‑lists, numpy.ndarray, or any 2‑D structure supporting
        ``len`` and element indexing.
        Returns True if *all* off‑diagonal absolute correlations exceed 0.95.
        """
        try:
            n = len(corr_matrix)
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    val = float(corr_matrix[i][j])
                    if abs(val) < 0.95:
                        return False
            return True
        except Exception as exc:
            logger.exception("Error evaluating correlation convergence: %s", exc)
            return False

    @staticmethod
    def detect_correlation_breakdown(corr_matrix: Any) -> bool:
        """Detect breakdown when many correlations drop toward zero.
        Returns True if more than 50% of off‑diagonal entries have absolute value < 0.2.
        """
        try:
            n = len(corr_matrix)
            total = 0
            low = 0
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    total += 1
                    if abs(float(corr_matrix[i][j])) < 0.2:
                        low += 1
            if total == 0:
                return False
            return low / total > 0.5
        except Exception as exc:
            logger.exception("Error evaluating correlation breakdown: %s", exc)
            return False

    @staticmethod
    def detect_contagion(spread_data: list[float]) -> bool:
        """Simple contagion detector.
        *spread_data* – list of recent bid‑ask spread values (or other liquidity metric).
        Returns True if the spread has increased > 150% over the last three observations.
        """
        if len(spread_data) < 3:
            return False
        recent = spread_data[-3:]
        if recent[0] == 0:
            return False
        growth = (recent[-1] - recent[0]) / recent[0]
        result = growth > 1.5
        logger.debug("Contagion detection – growth %.2f, result %s", growth, result)
        return result

    @staticmethod
    def feed_into_portfolio_optimization(exposures: list[FactorExposure], optimizer_config: dict[str, Any]) -> dict[str, Any]:
        """Transform factor exposures into optimizer constraints.
        Returns a dict that the optimizer can merge into its configuration.
        """
        constraints: dict[str, Any] = {}
        max_total = optimizer_config.get("max_total_exposure", 1.0)
        total = sum(fe.exposure_value for fe in exposures)
        scaling = max_total / total if total > 0 else 1.0
        for fe in exposures:
            constraints[fe.factor.name] = {
                "limit": fe.exposure_value * scaling,
                "weight": fe.contribution_to_risk,
            }
        logger.debug("Generated %d optimizer constraints (scaling %.3f)", len(constraints), scaling)
        return constraints
