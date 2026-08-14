"""
Elite Autonomous Quantum Trading System - Transaction Cost Analysis (TCA)
Pre-trade estimation, Post-trade analysis, Slippage, Market Impact, Timing Cost
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TCAModel(Enum):
    """TCA estimation models."""
    SIMPLE = "simple"              # Fixed cost + linear slippage
    ALMGREN_CHRISS = "almgren_chriss"  # Almgren-Chriss market impact
    SQUARE_ROOT = "square_root"    # Square root law
    POWER_LAW = "power_law"        # Power law impact
    MACHINE_LEARNING = "ml"        # ML-based estimation


@dataclass
class MarketConditions:
    """Market conditions at order time."""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    mid_price: float
    spread_bps: float
    volume: float
    volatility: float
    adv: float  # Average daily volume
    market_cap: float | None = None
    beta: float | None = None
    atr: float | None = None


@dataclass
class OrderSpec:
    """Order specification for TCA."""
    symbol: str
    side: str  # buy/sell
    quantity: float
    order_type: str  # market, limit, vwap, twap, pov
    limit_price: float | None = None
    participation_rate: float = 0.1
    duration_minutes: int = 60
    urgency: str = "normal"  # low, normal, high, urgent


@dataclass
class TCAEstimate:
    """Pre-trade TCA estimate."""
    order_spec: OrderSpec
    market_conditions: MarketConditions
    
    # Cost components (in basis points)
    explicit_cost_bps: float = 0.0       # Commission, fees
    implicit_cost_bps: float = 0.0       # Market impact
    spread_cost_bps: float = 0.0         # Half-spread cost
    timing_cost_bps: float = 0.0         # Opportunity cost
    total_cost_bps: float = 0.0
    
    # USD values
    explicit_cost_usd: float = 0.0
    implicit_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    
    # Risk metrics
    var_95_bps: float = 0.0
    var_99_bps: float = 0.0
    max_slippage_bps: float = 0.0
    
    # Model info
    model_used: TCAModel = TCAModel.SIMPLE
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TCAResult:
    """Post-trade TCA result."""
    order_id: str
    symbol: str
    side: str
    quantity: float
    benchmark_price: float  # Arrival mid / VWAP / etc.
    avg_fill_price: float
    filled_qty: float
    commission: float
    fill_timestamp: datetime
    
    # Cost analysis
    slippage_bps: float = 0.0
    spread_capture_bps: float = 0.0
    market_impact_bps: float = 0.0
    timing_cost_bps: float = 0.0
    total_cost_bps: float = 0.0
    
    # Detailed breakdown
    explicit_cost_bps: float = 0.0
    implicit_cost_bps: float = 0.0
    opportunity_cost_bps: float = 0.0
    
    # Benchmarks
    arrival_mid: float = 0.0
    vwap_benchmark: float = 0.0
    twap_benchmark: float = 0.0
    close_price: float = 0.0
    
    # Risk-adjusted
    implementation_shortfall_bps: float = 0.0
    alpha_bps: float = 0.0
    
    # Market context
    market_conditions: MarketConditions | None = None
    venue: str = ""
    algo_used: str = ""
    
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TCAReport:
    """Aggregated TCA report."""
    period_start: datetime
    period_end: datetime
    symbol: str | None = None
    
    # Aggregate metrics
    total_orders: int = 0
    total_volume: float = 0.0
    total_commission: float = 0.0
    
    # Average costs (bps)
    avg_slippage_bps: float = 0.0
    avg_spread_capture_bps: float = 0.0
    avg_market_impact_bps: float = 0.0
    avg_total_cost_bps: float = 0.0
    avg_implementation_shortfall_bps: float = 0.0
    
    # By side
    buy_metrics: dict[str, float] = field(default_factory=dict)
    sell_metrics: dict[str, float] = field(default_factory=dict)
    
    # By algorithm
    algo_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    
    # By venue/broker
    venue_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    
    # By time of day
    hourly_metrics: dict[int, dict[str, float]] = field(default_factory=dict)
    
    # Percentiles
    slippage_p50: float = 0.0
    slippage_p90: float = 0.0
    slippage_p95: float = 0.0
    slippage_p99: float = 0.0
    
    # Quality scores
    execution_quality_score: float = 0.0
    best_execution_ratio: float = 0.0  # % orders beating VWAP
    
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TCAEngine:
    """
    Transaction Cost Analysis Engine.
    
    Features:
    - Pre-trade cost estimation (multiple models)
    - Post-trade analysis (Implementation Shortfall, VWAP, TWAP, Arrival)
    - Market impact modeling (Almgren-Chriss, Square Root, Power Law)
    - Slippage decomposition (spread, impact, timing)
    - Venue/broker comparison
    - Time-of-day analysis
    - Best execution reporting
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.default_model = TCAModel(self.config.get("default_model", "square_root"))
        self.commission_bps = self.config.get("commission_bps", 1.0)
        self.fee_bps = self.config.get("fee_bps", 0.5)
        
        # Market data for estimation
        self.market_data: dict[str, MarketConditions] = {}
        self.historical_volume: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        self.historical_volatility: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        
        # Results storage
        self.estimates: list[TCAEstimate] = []
        self.results: list[TCAResult] = []
        
        # Model parameters (would be calibrated)
        self.impact_params = {
            "alpha": 0.1,      # Temporary impact
            "beta": 0.5,       # Permanent impact exponent
            "gamma": 0.1,      # Decay factor
            "eta": 0.01,       # Volatility scaling
        }
        
        # Callbacks
        self.on_estimate: list[callable] = []
        self.on_result: list[callable] = []
        
        logger.info("TCAEngine initialized")
    
    def update_market_data(self, conditions: MarketConditions):
        """Update market conditions for estimation."""
        self.market_data[conditions.symbol] = conditions
        self.historical_volume[conditions.symbol].append((conditions.timestamp, conditions.volume))
        self.historical_volatility[conditions.symbol].append((conditions.timestamp, conditions.volatility))
        
        # Keep history bounded
        cutoff = conditions.timestamp - timedelta(days=30)
        self.historical_volume[conditions.symbol] = [
            (t, v) for t, v in self.historical_volume[conditions.symbol] if t > cutoff
        ]
        self.historical_volatility[conditions.symbol] = [
            (t, v) for t, v in self.historical_volatility[conditions.symbol] if t > cutoff
        ]
    
    def estimate_cost(self, order: OrderSpec, model: TCAModel | None = None) -> TCAEstimate:
        """Estimate transaction costs pre-trade."""
        model = model or self.default_model
        
        # Get market conditions
        conditions = self.market_data.get(order.symbol)
        if not conditions:
            # Create default
            conditions = MarketConditions(
                symbol=order.symbol,
                timestamp=datetime.now(UTC),
                bid=0, ask=0, mid_price=100, spread_bps=10,
                volume=1000000, volatility=0.02, adv=10000000
            )
        
        estimate = TCAEstimate(
            order_spec=order,
            market_conditions=conditions,
            model_used=model
        )
        
        # Calculate costs based on model
        if model == TCAModel.SIMPLE:
            estimate = self._estimate_simple(estimate)
        elif model == TCAModel.SQUARE_ROOT:
            estimate = self._estimate_square_root(estimate)
        elif model == TCAModel.ALMGREN_CHRISS:
            estimate = self._estimate_almgren_chriss(estimate)
        elif model == TCAModel.POWER_LAW:
            estimate = self._estimate_power_law(estimate)
        elif model == TCAModel.MACHINE_LEARNING:
            estimate = self._estimate_ml(estimate)
        
        # Add explicit costs
        estimate.explicit_cost_bps = self.commission_bps + self.fee_bps
        estimate.explicit_cost_usd = estimate.explicit_cost_bps / 10000 * order.quantity * conditions.mid_price
        
        # Total
        estimate.total_cost_bps = (
            estimate.explicit_cost_bps + 
            estimate.implicit_cost_bps + 
            estimate.spread_cost_bps + 
            estimate.timing_cost_bps
        )
        estimate.total_cost_usd = estimate.total_cost_bps / 10000 * order.quantity * conditions.mid_price
        
        # Risk metrics
        estimate.var_95_bps = estimate.total_cost_bps * 1.65
        estimate.var_99_bps = estimate.total_cost_bps * 2.33
        estimate.max_slippage_bps = estimate.total_cost_bps * 3
        
        # Confidence based on model and data quality
        estimate.confidence = self._calculate_confidence(conditions, model)
        
        self.estimates.append(estimate)
        
        for callback in self.on_estimate:
            try:
                callback(estimate)
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')
        
        return estimate
    
    def _estimate_simple(self, estimate: TCAEstimate) -> TCAEstimate:
        """Simple fixed + linear model."""
        order = estimate.order_spec
        cond = estimate.market_conditions
        
        # Spread cost (half spread)
        estimate.spread_cost_bps = cond.spread_bps / 2
        
        # Linear market impact
        participation = order.quantity / max(cond.adv, 1)
        estimate.implicit_cost_bps = participation * 100 * cond.volatility * 10000  # bps
        
        # Timing cost (for non-market orders)
        if order.order_type in ["vwap", "twap", "pov"]:
            estimate.timing_cost_bps = cond.volatility * np.sqrt(order.duration_minutes / 390) * 10000
        
        return estimate
    
    def _estimate_square_root(self, estimate: TCAEstimate) -> TCAEstimate:
        """Square root law model: impact ~ sigma * sqrt(Q/ADV)"""
        order = estimate.order_spec
        cond = estimate.market_conditions
        
        # Spread cost
        estimate.spread_cost_bps = cond.spread_bps / 2
        
        # Square root market impact
        # I = alpha * sigma * sqrt(Q / ADV)
        alpha = self.impact_params.get("alpha", 0.1)
        participation = order.quantity / max(cond.adv, 1)
        estimate.implicit_cost_bps = alpha * cond.volatility * np.sqrt(max(participation, 0.0001)) * 10000
        
        # Timing cost
        if order.order_type in ["vwap", "twap", "pov"]:
            estimate.timing_cost_bps = cond.volatility * np.sqrt(order.duration_minutes / 390) * 10000 * 0.5
        
        return estimate
    
    def _estimate_almgren_chriss(self, estimate: TCAEstimate) -> TCAEstimate:
        """Almgren-Chriss model with temporary and permanent impact."""
        order = estimate.order_spec
        cond = estimate.market_conditions
        
        # Parameters
        sigma = cond.volatility * cond.mid_price  # Dollar volatility
        alpha = self.impact_params.get("alpha", 0.1)
        gamma = self.impact_params.get("gamma", 0.1)
        
        # Spread cost
        estimate.spread_cost_bps = cond.spread_bps / 2
        
        # Permanent impact: gamma * sigma * (Q/ADV)
        participation = order.quantity / max(cond.adv, 1)
        permanent_impact = gamma * sigma * participation
        estimate.implicit_cost_bps = (permanent_impact / cond.mid_price) * 10000
        
        # Temporary impact (for execution): alpha * sigma * sqrt(Q/ADV)
        temp_impact = alpha * sigma * np.sqrt(max(participation, 0.0001))
        estimate.timing_cost_bps = (temp_impact / cond.mid_price) * 10000 * 0.5
        
        return estimate
    
    def _estimate_power_law(self, estimate: TCAEstimate) -> TCAEstimate:
        """Power law impact model: impact ~ (Q/ADV)^beta"""
        order = estimate.order_spec
        cond = estimate.market_conditions
        
        beta = self.impact_params.get("beta", 0.5)
        eta = self.impact_params.get("eta", 0.01)
        
        # Spread cost
        estimate.spread_cost_bps = cond.spread_bps / 2
        
        # Power law impact
        participation = order.quantity / max(cond.adv, 1)
        impact = eta * cond.volatility * (participation ** beta)
        estimate.implicit_cost_bps = impact * 10000
        
        # Timing cost
        if order.order_type in ["vwap", "twap", "pov"]:
            estimate.timing_cost_bps = cond.volatility * (order.duration_minutes / 390) ** 0.5 * 10000 * 0.3
        
        return estimate
    
    def _estimate_ml(self, estimate: TCAEstimate) -> TCAEstimate:
        """ML-based estimation (placeholder for trained model)."""
        # Would use trained model here
        return self._estimate_square_root(estimate)
    
    def _calculate_confidence(self, conditions: MarketConditions, model: TCAModel) -> float:
        """Calculate estimation confidence."""
        base = 0.7
        
        # Data quality
        if conditions.volume > 0 and conditions.adv > 0:
            base += 0.1
        
        # Model sophistication
        model_bonus = {
            TCAModel.SIMPLE: 0.0,
            TCAModel.SQUARE_ROOT: 0.1,
            TCAModel.POWER_LAW: 0.15,
            TCAModel.ALMGREN_CHRISS: 0.2,
            TCAModel.MACHINE_LEARNING: 0.25
        }
        base += model_bonus.get(model, 0)
        
        return min(base, 0.95)
    
    def analyze_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        benchmark_price: float,
        avg_fill_price: float,
        filled_qty: float,
        commission: float,
        fill_timestamp: datetime,
        market_conditions: MarketConditions | None = None,
        venue: str = "",
        algo_used: str = "",
        arrival_mid: float | None = None,
        vwap_benchmark: float | None = None,
        twap_benchmark: float | None = None,
        close_price: float | None = None
    ) -> TCAResult:
        """Analyze executed fill post-trade."""
        result = TCAResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            benchmark_price=benchmark_price,
            avg_fill_price=avg_fill_price,
            filled_qty=filled_qty,
            commission=commission,
            fill_timestamp=fill_timestamp,
            market_conditions=market_conditions,
            venue=venue,
            algo_used=algo_used
        )
        
        # Set benchmarks
        result.arrival_mid = arrival_mid or benchmark_price
        result.vwap_benchmark = vwap_benchmark or benchmark_price
        result.twap_benchmark = twap_benchmark or benchmark_price
        result.close_price = close_price or benchmark_price
        
        # Calculate slippage vs arrival mid
        if result.arrival_mid > 0:
            if side.lower() == "buy":
                result.slippage_bps = (result.avg_fill_price - result.arrival_mid) / result.arrival_mid * 10000
            else:
                result.slippage_bps = (result.arrival_mid - result.avg_fill_price) / result.arrival_mid * 10000
        
        # Spread capture (vs VWAP)
        if result.vwap_benchmark > 0:
            if side.lower() == "buy":
                result.spread_capture_bps = (result.avg_fill_price - result.vwap_benchmark) / result.vwap_benchmark * 10000
            else:
                result.spread_capture_bps = (result.vwap_benchmark - result.avg_fill_price) / result.vwap_benchmark * 10000
        
        # Market impact (vs TWAP)
        if result.twap_benchmark > 0:
            if side.lower() == "buy":
                result.market_impact_bps = (result.avg_fill_price - result.twap_benchmark) / result.twap_benchmark * 10000
            else:
                result.market_impact_bps = (result.twap_benchmark - result.avg_fill_price) / result.twap_benchmark * 10000
        
        # Timing cost (vs close)
        if result.close_price > 0:
            if side.lower() == "buy":
                result.timing_cost_bps = (result.close_price - result.arrival_mid) / result.arrival_mid * 10000
            else:
                result.timing_cost_bps = (result.arrival_mid - result.close_price) / result.arrival_mid * 10000
        
        # Explicit costs
        notional = filled_qty * avg_fill_price
        result.explicit_cost_bps = (commission / notional) * 10000 if notional > 0 else 0
        
        # Total cost
        result.total_cost_bps = result.slippage_bps + result.explicit_cost_bps
        
        # Implementation Shortfall (vs arrival mid)
        result.implementation_shortfall_bps = result.total_cost_bps
        
        # Alpha (vs VWAP benchmark)
        if result.vwap_benchmark > 0:
            if side.lower() == "buy":
                result.alpha_bps = (result.vwap_benchmark - result.avg_fill_price) / result.vwap_benchmark * 10000
            else:
                result.alpha_bps = (result.avg_fill_price - result.vwap_benchmark) / result.vwap_benchmark * 10000
        
        self.results.append(result)
        
        for callback in self.on_result:
            try:
                callback(result)
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')
        
        return result
    
    def generate_report(
        self,
        period_start: datetime,
        period_end: datetime,
        symbol: str | None = None
    ) -> TCAReport:
        """Generate aggregated TCA report."""
        # Filter results
        filtered = [
            r for r in self.results
            if period_start <= r.fill_timestamp <= period_end
            and (symbol is None or r.symbol == symbol)
        ]
        
        if not filtered:
            return TCAReport(period_start=period_start, period_end=period_end, symbol=symbol)
        
        report = TCAReport(period_start=period_start, period_end=period_end, symbol=symbol)
        report.total_orders = len(filtered)
        report.total_volume = sum(r.filled_qty * r.avg_fill_price for r in filtered)
        report.total_commission = sum(r.commission for r in filtered)
        
        # Aggregate metrics
        slippages = [r.slippage_bps for r in filtered]
        spread_captures = [r.spread_capture_bps for r in filtered]
        impacts = [r.market_impact_bps for r in filtered]
        total_costs = [r.total_cost_bps for r in filtered]
        is_costs = [r.implementation_shortfall_bps for r in filtered]
        
        report.avg_slippage_bps = np.mean(slippages)
        report.avg_spread_capture_bps = np.mean(spread_captures)
        report.avg_market_impact_bps = np.mean(impacts)
        report.avg_total_cost_bps = np.mean(total_costs)
        report.avg_implementation_shortfall_bps = np.mean(is_costs)
        
        # Percentiles
        report.slippage_p50 = np.percentile(slippages, 50)
        report.slippage_p90 = np.percentile(slippages, 90)
        report.slippage_p95 = np.percentile(slippages, 95)
        report.slippage_p99 = np.percentile(slippages, 99)
        
        # By side
        buy_results = [r for r in filtered if r.side.lower() == "buy"]
        sell_results = [r for r in filtered if r.side.lower() == "sell"]
        
        for side_name, side_results in [("buy", buy_results), ("sell", sell_results)]:
            if side_results:
                report.buy_metrics if side_name == "buy" else report.sell_metrics
                metrics = {
                    "count": len(side_results),
                    "avg_slippage": np.mean([r.slippage_bps for r in side_results]),
                    "avg_cost": np.mean([r.total_cost_bps for r in side_results]),
                    "avg_alpha": np.mean([r.alpha_bps for r in side_results]),
                }
                if side_name == "buy":
                    report.buy_metrics = metrics
                else:
                    report.sell_metrics = metrics
        
        # By algorithm
        for r in filtered:
            if r.algo_used:
                if r.algo_used not in report.algo_metrics:
                    report.algo_metrics[r.algo_used] = {"orders": [], "costs": [], "slippage": []}
                report.algo_metrics[r.algo_used]["orders"].append(r)
                report.algo_metrics[r.algo_used]["costs"].append(r.total_cost_bps)
                report.algo_metrics[r.algo_used]["slippage"].append(r.slippage_bps)
        
        for algo, data in report.algo_metrics.items():
            data["avg_cost"] = np.mean(data["costs"])
            data["avg_slippage"] = np.mean(data["slippage"])
            data["count"] = len(data["orders"])
        
        # By venue
        for r in filtered:
            if r.venue:
                if r.venue not in report.venue_metrics:
                    report.venue_metrics[r.venue] = {"orders": [], "costs": [], "slippage": []}
                report.venue_metrics[r.venue]["orders"].append(r)
                report.venue_metrics[r.venue]["costs"].append(r.total_cost_bps)
                report.venue_metrics[r.venue]["slippage"].append(r.slippage_bps)
        
        for venue, data in report.venue_metrics.items():
            data["avg_cost"] = np.mean(data["costs"])
            data["avg_slippage"] = np.mean(data["slippage"])
            data["count"] = len(data["orders"])
        
        # By hour
        for r in filtered:
            hour = r.fill_timestamp.hour
            if hour not in report.hourly_metrics:
                report.hourly_metrics[hour] = {"costs": [], "slippage": [], "count": 0}
            report.hourly_metrics[hour]["costs"].append(r.total_cost_bps)
            report.hourly_metrics[hour]["slippage"].append(r.slippage_bps)
            report.hourly_metrics[hour]["count"] += 1
        
        for hour, data in report.hourly_metrics.items():
            data["avg_cost"] = np.mean(data["costs"])
            data["avg_slippage"] = np.mean(data["slippage"])
        
        # Quality scores
        beating_vwap = sum(1 for r in filtered if r.alpha_bps > 0)
        report.best_execution_ratio = beating_vwap / len(filtered) if filtered else 0
        
        # Execution quality score (0-1)
        # Based on: low cost, positive alpha, consistency
        cost_score = max(0, 1 - report.avg_total_cost_bps / 50)  # Normalize to 50 bps
        alpha_score = max(0, min(1, 0.5 + report.best_execution_ratio))
        consistency_score = 1 - (np.std(slippages) / max(abs(np.mean(slippages)), 1))
        
        report.execution_quality_score = (cost_score + alpha_score + consistency_score) / 3
        
        return report
    
    def compare_venues(self, symbol: str, period_days: int = 30) -> pd.DataFrame:
        """Compare execution quality across venues."""
        cutoff = datetime.now(UTC) - timedelta(days=period_days)
        filtered = [r for r in self.results if r.symbol == symbol and r.fill_timestamp > cutoff]
        
        if not filtered:
            return pd.DataFrame()
        
        venues = defaultdict(lambda: {"orders": [], "costs": [], "slippage": [], "alpha": []})
        for r in filtered:
            if r.venue:
                venues[r.venue]["orders"].append(r)
                venues[r.venue]["costs"].append(r.total_cost_bps)
                venues[r.venue]["slippage"].append(r.slippage_bps)
                venues[r.venue]["alpha"].append(r.alpha_bps)
        
        rows = []
        for venue, data in venues.items():
            rows.append({
                "venue": venue,
                "order_count": len(data["orders"]),
                "avg_cost_bps": np.mean(data["costs"]),
                "avg_slippage_bps": np.mean(data["slippage"]),
                "avg_alpha_bps": np.mean(data["alpha"]),
                "cost_std": np.std(data["costs"]),
                "slippage_std": np.std(data["slippage"]),
                "best_execution_rate": sum(1 for a in data["alpha"] if a > 0) / len(data["alpha"])
            })
        
        return pd.DataFrame(rows).sort_values("avg_cost_bps")
    
    def compare_algos(self, symbol: str, period_days: int = 30) -> pd.DataFrame:
        """Compare execution algorithms."""
        cutoff = datetime.now(UTC) - timedelta(days=period_days)
        filtered = [r for r in self.results if r.symbol == symbol and r.fill_timestamp > cutoff]
        
        if not filtered:
            return pd.DataFrame()
        
        algos = defaultdict(lambda: {"orders": [], "costs": [], "slippage": [], "alpha": []})
        for r in filtered:
            if r.algo_used:
                algos[r.algo_used]["orders"].append(r)
                algos[r.algo_used]["costs"].append(r.total_cost_bps)
                algos[r.algo_used]["slippage"].append(r.slippage_bps)
                algos[r.algo_used]["alpha"].append(r.alpha_bps)
        
        rows = []
        for algo, data in algos.items():
            rows.append({
                "algorithm": algo,
                "order_count": len(data["orders"]),
                "avg_cost_bps": np.mean(data["costs"]),
                "avg_slippage_bps": np.mean(data["slippage"]),
                "avg_alpha_bps": np.mean(data["alpha"]),
                "cost_std": np.std(data["costs"]),
                "best_execution_rate": sum(1 for a in data["alpha"] if a > 0) / len(data["alpha"])
            })
        
        return pd.DataFrame(rows).sort_values("avg_cost_bps")


# Global instance
tca_engine = TCAEngine()


async def get_tca_engine(config: dict | None = None) -> TCAEngine:
    """Get or create global TCA engine."""
    global tca_engine
    if config:
        tca_engine = TCAEngine(config)
    return tca_engine