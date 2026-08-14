"""
Reality Gap Engine & Digital Twin Calibration — EAQTS V2.3 N1425–N1433.

Continuously compares:
  BACKTEST vs DIGITAL TWIN vs SHADOW vs DEMO vs CANARY vs PRODUCTION

Calculates Reality Gap Score. Large divergence reduces confidence and authority.
Digital Twin itself must be periodically recalibrated against real execution.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class Environment(str, Enum):
    BACKTEST = "backtest"
    DIGITAL_TWIN = "digital_twin"
    SHADOW = "shadow"
    DEMO = "demo"
    CANARY = "canary"
    PRODUCTION = "production"


@dataclass
class EnvironmentMetrics:
    environment: Environment
    returns: list[float] = field(default_factory=list)
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    trade_count: int = 0
    execution_latency_ms: float = 0.0
    slippage_bps: float = 0.0
    rejection_rate: float = 0.0
    fill_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class RealityGapResult:
    primary_env: Environment
    comparison_env: Environment
    gap_score: float  # 0-100, higher = larger gap
    return_diff: float
    sharpe_diff: float
    drawdown_diff: float
    execution_diff: float
    exceeded_threshold: bool = False


class DigitalTwinCalibrationEngine:
    """
    N1425–N1433: Reality Gap measurement and Digital Twin calibration.

    Digital Twin simulates real execution (spread, latency, fills, rejections,
    slippage, broker responses). It must be recalibrated against real
    production data to maintain fidelity.
    """

    def __init__(
        self,
        gap_threshold: float = 15.0,  # % divergence threshold
    ) -> None:
        self.gap_threshold = gap_threshold
        self._metrics: dict[Environment, EnvironmentMetrics] = {}
        self._calibration_history: list[dict[str, Any]] = []

    def record_metrics(self, env: Environment, metrics: EnvironmentMetrics) -> None:
        """Record metrics from an environment."""
        self._metrics[env] = metrics
        logger.debug(f"Reality Gap: recorded {env.value} metrics ({metrics.trade_count} trades)")

    def _compute_basic_stats(self, env: Environment) -> dict[str, float]:
        m = self._metrics.get(env)
        if not m or m.trade_count < 5:
            return {}
        returns = m.returns
        return {
            "mean_return": statistics.mean(returns) if returns else 0.0,
            "sharpe": m.sharpe,
            "max_dd": m.max_drawdown,
            "win_rate": m.win_rate,
            "avg_pnl": m.avg_trade_pnl,
            "latency": m.execution_latency_ms,
            "slippage": m.slippage_bps,
            "rejection": m.rejection_rate,
            "fill": m.fill_rate,
        }

    def calculate_gap(
        self,
        primary: Environment = Environment.PRODUCTION,
        comparison: Environment = Environment.BACKTEST,
    ) -> RealityGapResult:
        """N1425–N1430 — Compare two environments and calculate gap score."""
        if primary not in self._metrics or comparison not in self._metrics:
            return RealityGapResult(
                primary_env=primary,
                comparison_env=comparison,
                gap_score=100.0,
                return_diff=0.0,
                sharpe_diff=0.0,
                drawdown_diff=0.0,
                execution_diff=0.0,
                exceeded_threshold=True,
            )

        p_stats = self._compute_basic_stats(primary)
        c_stats = self._compute_basic_stats(comparison)

        if not p_stats or not c_stats:
            return RealityGapResult(
                primary_env=primary,
                comparison_env=comparison,
                gap_score=100.0,
                return_diff=0.0,
                sharpe_diff=0.0,
                drawdown_diff=0.0,
                execution_diff=0.0,
                exceeded_threshold=True,
            )

        # Calculate percentage differences
        return_diff = (
            abs(p_stats["mean_return"] - c_stats["mean_return"])
            / max(abs(p_stats["mean_return"]), 1e-6) * 100
        )
        sharpe_diff = (
            abs(p_stats["sharpe"] - c_stats["sharpe"])
            / max(abs(p_stats["sharpe"]), 0.1) * 100
        )
        dd_diff = (
            abs(p_stats["max_dd"] - c_stats["max_dd"])
            / max(abs(p_stats["max_dd"]), 0.01) * 100
        )

        # Execution quality gap
        exec_diff = (
            abs(p_stats["latency"] - c_stats["latency"]) / 100.0  # ms -> score
            + abs(p_stats["slippage"] - c_stats["slippage"])  # bps
            + abs(p_stats["rejection"] - c_stats["rejection"]) * 100  # rate
            + abs(p_stats["fill"] - c_stats["fill"]) * 100
        )

        gap_score = (
            return_diff * 0.3
            + sharpe_diff * 0.3
            + dd_diff * 0.2
            + exec_diff * 0.2
        )

        exceeded = gap_score > self.gap_threshold

        result = RealityGapResult(
            primary_env=primary,
            comparison_env=comparison,
            gap_score=gap_score,
            return_diff=return_diff,
            sharpe_diff=sharpe_diff,
            drawdown_diff=dd_diff,
            execution_diff=exec_diff,
            exceeded_threshold=exceeded,
        )

        if exceeded:
            logger.warning(
                f"Reality Gap EXCEEDED: {primary.value} vs {comparison.value} "
                f"score={gap_score:.1f} (threshold={self.gap_threshold})"
            )
        else:
            logger.info(
                f"Reality Gap: {primary.value} vs {comparison.value} "
                f"score={gap_score:.1f}"
            )

        return result

    def full_comparison(self) -> list[RealityGapResult]:
        """N1426–N1429 — Compare all adjacent environments in chain."""
        chain = [
            Environment.BACKTEST,
            Environment.DIGITAL_TWIN,
            Environment.SHADOW,
            Environment.DEMO,
            Environment.CANARY,
            Environment.PRODUCTION,
        ]
        results = []
        for i in range(len(chain) - 1):
            r = self.calculate_gap(chain[i + 1], chain[i])
            results.append(r)
        return results

    def calibrate_digital_twin(self, production_metrics: EnvironmentMetrics) -> dict[str, float]:
        """
        N1432–N1433 — Recalibrate Digital Twin parameters to match production.
        Returns calibration adjustments for spread, latency, slippage, rejection.
        """
        if Environment.DIGITAL_TWIN not in self._metrics:
            return {}

        twin = self._metrics[Environment.DIGITAL_TWIN]
        prod = production_metrics

        # Compute needed adjustments
        adjustments = {
            "spread_multiplier": (
                prod.slippage_bps / max(twin.slippage_bps, 1e-6)
                if twin.slippage_bps > 0 else 1.0
            ),
            "latency_multiplier": (
                prod.execution_latency_ms / max(twin.execution_latency_ms, 1e-6)
                if twin.execution_latency_ms > 0 else 1.0
            ),
            "rejection_adjustment": (
                prod.rejection_rate - twin.rejection_rate
            ),
            "fill_adjustment": (
                prod.fill_rate - twin.fill_rate
            ),
        }

        # Apply bounds
        for k in adjustments:
            adjustments[k] = max(0.1, min(10.0, adjustments[k]))

        self._calibration_history.append({
            "timestamp": time.time(),
            "adjustments": adjustments,
            "gap_before": self.calculate_gap(Environment.PRODUCTION, Environment.DIGITAL_TWIN).gap_score,
        })

        logger.info(f"Digital Twin calibrated: {adjustments}")
        return adjustments

    def reduce_authority_on_gap(self, result: RealityGapResult) -> tuple[bool, str]:
        """N1432 — Trigger authority reduction on excessive gap."""
        if result.exceeded_threshold:
            return True, f"Reality gap {result.gap_score:.1f}% exceeds threshold {self.gap_threshold}%"
        return False, ""


# Singleton
reality_gap_engine = DigitalTwinCalibrationEngine()
