"""
Critical Strategic Blind Spot Management
=========================================

Comprehensive monitoring and management of strategic blind spots:
- Correlation risk and contagion detection
- Regime change early warning
- Liquidity risk and slippage modeling
- Model degradation detection and auto-retrain
- Black swan / tail risk hedging
- Concentration risk monitoring
- Counterparty and operational risk
- Behavioral bias detection
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from src.risk.advanced_risk import AdvancedRiskManager
from src.strategy.market_regime import MarketRegimeDetector, RegimeType


class BlindSpotType(str, Enum):
    """Types of strategic blind spots."""
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    REGIME_CHANGE = "regime_change"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    MODEL_DEGRADATION = "model_degradation"
    TAIL_RISK = "tail_risk"
    CONCENTRATION_RISK = "concentration_risk"
    COUNTERPARTY_RISK = "counterparty_risk"
    OPERATIONAL_RISK = "operational_risk"
    BEHAVIORAL_BIAS = "behavioral_bias"
    CORRELATION_CONCENTRATION = "correlation_concentration"


class BlindSpotSeverity(str, Enum):
    """Severity levels for blind spots."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ActionType(str, Enum):
    """Actions to take when blind spot detected."""
    MONITOR = "monitor"
    REDUCE_EXPOSURE = "reduce_exposure"
    HEDGE = "hedge"
    CLOSE_POSITIONS = "close_positions"
    PAUSE_STRATEGY = "pause_strategy"
    RETRAIN_MODEL = "retrain_model"
    ALERT_ONLY = "alert_only"
    EMERGENCY_STOP = "emergency_stop"


@dataclass(slots=True)
class BlindSpotAlert:
    """Alert for a detected blind spot."""
    blind_spot_type: BlindSpotType
    severity: BlindSpotSeverity
    title: str
    description: str
    affected_symbols: list[str]
    affected_strategies: list[str]
    metrics: dict[str, float]
    recommended_actions: list[ActionType]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    resolved: bool = False
    resolution_time: datetime | None = None


@dataclass(slots=True)
class CorrelationCluster:
    """A cluster of highly correlated assets."""
    cluster_id: int
    symbols: list[str]
    avg_correlation: float
    max_correlation: float
    cluster_size: int
    risk_score: float


@dataclass(slots=True)
class RegimeChangeSignal:
    """Signal indicating potential regime change."""
    from_regime: RegimeType
    to_regime: RegimeType
    confidence: float
    indicators: dict[str, float]
    time_to_transition: int  # estimated bars
    affected_strategies: list[str]


@dataclass(slots=True)
class LiquidityMetrics:
    """Liquidity risk metrics."""
    symbol: str
    bid_ask_spread: float
    spread_percentile: float
    volume_ratio: float
    order_book_depth: float
    slippage_estimate: float
    liquidity_score: float  # 0-1, higher = more liquid
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ModelPerformanceTracker:
    """Track ML model performance for degradation detection."""
    model_id: str
    strategy_id: str
    window_predictions: deque = field(default_factory=lambda: deque(maxlen=1000))
    window_actuals: deque = field(default_factory=lambda: deque(maxlen=1000))
    baseline_sharpe: float = 0.0
    baseline_accuracy: float = 0.0
    last_retrain: datetime | None = None
    retrain_count: int = 0
    degradation_alerts: int = 0


class BlindSpotManager:
    """
    Central manager for all strategic blind spots.
    Continuously monitors and alerts on critical blind spots.
    """
    
    def __init__(
        self,
        risk_manager: AdvancedRiskManager | None = None,
        regime_detector: MarketRegimeDetector | None = None,
    ):
        self.risk_manager = risk_manager
        self.regime_detector = regime_detector or MarketRegimeDetector()
        
        # State
        self._running = False
        self._main_task: asyncio.Task | None = None
        self._check_interval = 60  # seconds
        
        # Blind spot tracking
        self.active_alerts: dict[str, BlindSpotAlert] = {}
        self.alert_history: list[BlindSpotAlert] = []
        
        # Correlation monitoring
        self.correlation_history: deque = deque(maxlen=1000)
        self.correlation_clusters: list[CorrelationCluster] = []
        self.correlation_threshold = 0.8
        self.cluster_correlation_threshold = 0.7
        
        # Regime change detection
        self.regime_history: deque = deque(maxlen=100)
        self.regime_transition_prob = np.eye(len(RegimeType))
        self.regime_persistence: dict[RegimeType, int] = {}
        
        # Liquidity monitoring
        self.liquidity_history: dict[str, deque] = {}
        self.liquidity_threshold = 0.3
        
        # Model performance tracking
        self.model_trackers: dict[str, ModelPerformanceTracker] = {}
        self.degradation_threshold = 0.2  # 20% degradation from baseline
        self.retrain_cooldown = timedelta(days=7)
        
        # Tail risk
        self.tail_risk_history: deque = deque(maxlen=252)  # 1 year
        self.tail_risk_threshold = 0.05  # 5% CVaR
        
        # Concentration limits
        self.max_single_position = 0.15
        self.max_sector_exposure = 0.30
        self.max_correlated_exposure = 0.40
        
        # Behavioral bias tracking
        self.trade_history: deque = deque(maxlen=10000)
        self.bias_metrics: dict[str, float] = {}
        
        # Callbacks
        self.on_alert: Callable[[BlindSpotAlert], None] | None = None
        self.on_action: Callable[[ActionType, dict], None] | None = None
        
        logger.info("BlindSpotManager initialized")
    
    async def start(self) -> None:
        """Start the blind spot monitoring."""
        if self._running:
            return
        
        self._running = True
        self._main_task = asyncio.create_task(self._monitoring_loop())
        logger.info("BlindSpotManager started")
    
    async def stop(self) -> None:
        """Stop the blind spot monitoring."""
        self._running = False
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                raise NotImplementedError("Not implemented")
        logger.info("BlindSpotManager stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                start_time = datetime.now(UTC)
                
                # Run all checks
                await self._check_correlation_risk()
                await self._check_regime_change()
                await self._check_liquidity_risk()
                await self._check_model_degradation()
                await self._check_tail_risk()
                await self._check_concentration_risk()
                await self._check_behavioral_bias()
                
                # Clean up old alerts
                self._cleanup_alerts()
                
                # Sleep until next check
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                sleep_time = max(1, self._check_interval - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in blind spot monitoring: {e}")
                await asyncio.sleep(10)
    
    # ================================================================
    # CORRELATION RISK MONITORING
    # ================================================================
    
    async def _check_correlation_risk(self) -> None:
        """Check for correlation breakdown and concentration."""
        # Get current positions
        if not self.risk_manager:
            return
        
        # In production, would get actual positions from risk manager
        # For now, simulate correlation matrix
        positions = self._get_current_positions()
        if len(positions) < 2:
            return
        
        symbols = list(positions.keys())
        
        # Build correlation matrix (in production, use real historical data)
        corr_matrix = self._estimate_correlation_matrix(symbols)
        
        # Store in history
        self.correlation_history.append({
            "timestamp": datetime.now(UTC),
            "symbols": symbols,
            "matrix": corr_matrix,
        })
        
        # Detect correlation clusters
        clusters = self._detect_correlation_clusters(corr_matrix, symbols)
        self.correlation_clusters = clusters
        
        # Check for correlation breakdown (sudden drops)
        if len(self.correlation_history) >= 2:
            prev = self.correlation_history[-2]["matrix"]
            curr = corr_matrix
            breakdown = self._detect_correlation_breakdown(prev, curr, symbols)
            if breakdown:
                await self._create_alert(
                    BlindSpotType.CORRELATION_BREAKDOWN,
                    BlindSpotSeverity.WARNING,
                    "Correlation Breakdown Detected",
                    f"Significant correlation changes detected in {len(breakdown)} pairs",
                    symbols=[s for pair in breakdown for s in pair],
                    affected_strategies=self._get_affected_strategies(breakdown),
                    metrics={"pairs_affected": len(breakdown), "avg_change": np.mean([b["change"] for b in breakdown])},
                    recommended_actions=[ActionType.REDUCE_EXPOSURE, ActionType.HEDGE, ActionType.MONITOR],
                )
        
        # Check correlation concentration
        for cluster in clusters:
            if cluster.risk_score > 0.7:
                await self._create_alert(
                    BlindSpotType.CORRELATION_CONCENTRATION,
                    BlindSpotSeverity.WARNING,
                    f"High Correlation Cluster: {cluster.cluster_size} assets",
                    f"Cluster with avg correlation {cluster.avg_correlation:.2f} exceeds threshold",
                    symbols=cluster.symbols,
                    affected_strategies=self._get_affected_strategies_from_symbols(cluster.symbols),
                    metrics={
                        "avg_correlation": cluster.avg_correlation,
                        "max_correlation": cluster.max_correlation,
                        "cluster_size": cluster.cluster_size,
                        "risk_score": cluster.risk_score,
                    },
                    recommended_actions=[ActionType.REDUCE_EXPOSURE, ActionType.HEDGE, ActionType.MONITOR],
                )
    
    def _estimate_correlation_matrix(self, symbols: list[str]) -> np.ndarray:
        """Estimate correlation matrix for symbols."""
        n = len(symbols)
        # In production, use actual historical returns
        # For now, create realistic correlation matrix
        corr = np.eye(n)
        
        # Add realistic forex correlations
        for i in range(n):
            for j in range(i+1, n):
                # Simple heuristic based on currency overlap
                sym1, sym2 = symbols[i], symbols[j]
                corr_val = self._estimate_pair_correlation(sym1, sym2)
                corr[i, j] = corr[j, i] = corr_val
        
        return corr
    
    def _estimate_pair_correlation(self, sym1: str, sym2: str) -> float:
        """Estimate correlation between two forex pairs."""
        # Currency overlap heuristic
        currencies1 = {sym1[:3], sym1[3:6]}
        currencies2 = {sym2[:3], sym2[3:6]}
        overlap = len(currencies1 & currencies2)
        
        if overlap == 2:  # Same pair
            return 1.0
        elif overlap == 1:  # One common currency
            return np.random.uniform(0.5, 0.8)
        else:  # No common currency
            return np.random.uniform(-0.3, 0.3)
    
    def _detect_correlation_clusters(
        self, 
        corr_matrix: np.ndarray, 
        symbols: list[str]
    ) -> list[CorrelationCluster]:
        """Detect clusters of highly correlated assets."""
        n = len(symbols)
        if n < 3:
            return []
        
        # Convert correlation to distance
        dist_matrix = np.sqrt(0.5 * (1 - corr_matrix))
        dist_condensed = squareform(dist_matrix)
        
        # Hierarchical clustering
        try:
            link = linkage(dist_condensed, method='ward')
            clusters = fcluster(link, t=1-self.cluster_correlation_threshold, criterion='distance')
        except Exception:
            return []
        
        # Build cluster objects
        cluster_dict: dict[int, list[int]] = {}
        for i, cluster_id in enumerate(clusters):
            if cluster_id not in cluster_dict:
                cluster_dict[cluster_id] = []
            cluster_dict[cluster_id].append(i)
        
        result = []
        for cluster_id, indices in cluster_dict.items():
            if len(indices) < 2:
                continue
            
            cluster_symbols = [symbols[i] for i in indices]
            sub_matrix = corr_matrix[np.ix_(indices, indices)]
            
            # Calculate cluster metrics
            upper_tri = sub_matrix[np.triu_indices_from(sub_matrix, k=1)]
            avg_corr = float(np.mean(upper_tri)) if len(upper_tri) > 0 else 0
            max_corr = float(np.max(upper_tri)) if len(upper_tri) > 0 else 0
            
            # Risk score based on correlation and cluster size
            risk_score = avg_corr * (1 - np.exp(-len(indices) / 5))
            
            result.append(CorrelationCluster(
                cluster_id=cluster_id,
                symbols=cluster_symbols,
                avg_correlation=avg_corr,
                max_correlation=max_corr,
                cluster_size=len(indices),
                risk_score=risk_score,
            ))
        
        return result
    
    def _detect_correlation_breakdown(
        self, 
        prev: np.ndarray, 
        curr: np.ndarray, 
        symbols: list[str]
    ) -> list[dict]:
        """Detect significant correlation changes."""
        breakdown = []
        n = len(symbols)
        
        for i in range(n):
            for j in range(i+1, n):
                change = abs(curr[i, j] - prev[i, j])
                if change > 0.3:  # 30% correlation change threshold
                    breakdown.append({
                        "pair": (symbols[i], symbols[j]),
                        "prev": float(prev[i, j]),
                        "curr": float(curr[i, j]),
                        "change": float(change),
                    })
        
        return breakdown
    
    def _get_affected_strategies(self, breakdown: list[dict]) -> list[str]:
        """Get strategies affected by correlation breakdown."""
        # In production, would map symbols to strategies
        return ["ensemble_ml", "trend_following", "mean_reversion"]
    
    def _get_affected_strategies_from_symbols(self, symbols: list[str]) -> list[str]:
        """Get strategies affected by symbol issues."""
        return ["ensemble_ml", "trend_following", "mean_reversion", "pairs_trading"]
    
    # ================================================================
    # REGIME CHANGE DETECTION
    # ================================================================
    
    async def _check_regime_change(self) -> None:
        """Check for impending regime changes."""
        # Get current regime from detector
        # In production, would use real market data
        current_regime = self._get_current_regime()
        
        # Track regime persistence
        if current_regime not in self.regime_persistence:
            self.regime_persistence[current_regime] = 0
        self.regime_persistence[current_regime] += 1
        
        # Check for regime transition signals
        transition_signal = self._detect_regime_transition(current_regime)
        
        if transition_signal:
            await self._create_alert(
                BlindSpotType.REGIME_CHANGE,
                BlindSpotSeverity.WARNING,
                f"Regime Change Signal: {transition_signal.from_regime.value} -> {transition_signal.to_regime.value}",
                f"Regime transition detected with {transition_signal.confidence:.1%} confidence",
                symbols=list(set().union(*[self.config.symbols for s in transition_signal.affected_strategies])),
                affected_strategies=transition_signal.affected_strategies,
                metrics={
                    "confidence": transition_signal.confidence,
                    "time_to_transition": transition_signal.time_to_transition,
                    "persistence": self.regime_persistence.get(current_regime, 0),
                },
                recommended_actions=[
                    ActionType.REDUCE_EXPOSURE, 
                    ActionType.HEDGE, 
                    ActionType.PAUSE_STRATEGY,
                    ActionType.MONITOR
                ],
            )
        
        # Store regime history
        self.regime_history.append({
            "timestamp": datetime.now(UTC),
            "regime": current_regime,
            "persistence": self.regime_persistence.copy(),
        })
    
    def _get_current_regime(self) -> RegimeType:
        """Get current market regime."""
        # In production, use regime detector with real data
        # For now, simulate
        return np.random.choice(list(RegimeType), p=[0.2, 0.2, 0.3, 0.15, 0.1, 0.05])
    
    def _detect_regime_transition(self, current: RegimeType) -> RegimeChangeSignal | None:
        """Detect potential regime transition."""
        # Simplified transition detection
        # In production, use regime detector with leading indicators
        
        # Check persistence - long persistence increases transition probability
        persistence = self.regime_persistence.get(current, 0)
        
        if persistence > 50:  # Extended regime
            # Higher chance of transition
            transition_prob = min(0.3, persistence / 200)
            if np.random.random() < transition_prob:
                # Pick likely next regime
                transitions = {
                    RegimeType.TRENDING_UP: [RegimeType.RANGING, RegimeType.VOLATILE],
                    RegimeType.TRENDING_DOWN: [RegimeType.RANGING, RegimeType.VOLATILE],
                    RegimeType.RANGING: [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN, RegimeType.BREAKOUT],
                    RegimeType.VOLATILE: [RegimeType.RANGING, RegimeType.BREAKOUT],
                    RegimeType.BREAKOUT: [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN],
                    RegimeType.MEAN_REVERTING: [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN],
                }
                
                possible = transitions.get(current, [RegimeType.RANGING])
                to_regime = np.random.choice(possible)
                
                return RegimeChangeSignal(
                    from_regime=current,
                    to_regime=to_regime,
                    confidence=np.random.uniform(0.6, 0.9),
                    indicators={
                        "persistence": persistence,
                        "volatility_change": np.random.uniform(-0.5, 0.5),
                        "correlation_shift": np.random.uniform(-0.3, 0.3),
                    },
                    time_to_transition=np.random.randint(5, 20),
                    affected_strategies=["trend_following", "mean_reversion", "breakout", "momentum"],
                )
        
        return None
    
    # ================================================================
    # LIQUIDITY RISK MONITORING
    # ================================================================
    
    async def _check_liquidity_risk(self) -> None:
        """Monitor liquidity risk across all symbols."""
        symbols = self._get_all_symbols()
        
        for symbol in symbols:
            metrics = self._calculate_liquidity_metrics(symbol)
            
            if symbol not in self.liquidity_history:
                self.liquidity_history[symbol] = deque(maxlen=1000)
            self.liquidity_history[symbol].append(metrics)
            
            # Check liquidity thresholds
            if metrics.liquidity_score < self.liquidity_threshold:
                await self._create_alert(
                    BlindSpotType.LIQUIDITY_CRISIS,
                    BlindSpotSeverity.CRITICAL,
                    f"Liquidity Crisis: {symbol}",
                    f"Liquidity score {metrics.liquidity_score:.2f} below threshold {self.liquidity_threshold}",
                    symbols=[symbol],
                    affected_strategies=self._get_affected_strategies_from_symbols([symbol]),
                    metrics={
                        "liquidity_score": metrics.liquidity_score,
                        "spread_percentile": metrics.spread_percentile,
                        "volume_ratio": metrics.volume_ratio,
                        "slippage_estimate": metrics.slippage_estimate,
                    },
                    recommended_actions=[
                        ActionType.REDUCE_EXPOSURE,
                        ActionType.CLOSE_POSITIONS,
                        ActionType.HEDGE,
                    ],
                )
    
    def _calculate_liquidity_metrics(self, symbol: str) -> LiquidityMetrics:
        """Calculate liquidity metrics for a symbol."""
        # In production, use real order book data
        # Simulate for now
        spread = np.random.uniform(0.5, 5.0)  # pips
        spread_pct = np.random.uniform(10, 90)
        volume_ratio = np.random.uniform(0.3, 2.0)
        depth = np.random.uniform(100000, 1000000)
        slippage = np.random.uniform(0.1, 3.0)
        
        # Liquidity score: lower spread, higher volume, more depth = higher score
        score = (1 - spread / 10) * 0.4 + min(volume_ratio, 2) / 2 * 0.4 + (1 - slippage / 5) * 0.2
        score = max(0, min(1, score))
        
        return LiquidityMetrics(
            symbol=symbol,
            bid_ask_spread=spread,
            spread_percentile=spread_pct,
            volume_ratio=volume_ratio,
            order_book_depth=depth,
            slippage_estimate=slippage,
            liquidity_score=score,
        )
    
    def _get_all_symbols(self) -> list[str]:
        """Get all symbols being traded."""
        # In production, get from position manager
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "BTCUSD", "ETHUSD"]
    
    # ================================================================
    # MODEL DEGRADATION DETECTION
    # ================================================================
    
    async def _check_model_degradation(self) -> None:
        """Check for ML model performance degradation."""
        for tracker in self.model_trackers.values():
            if len(tracker.window_predictions) < 50:
                continue
            
            # Calculate current performance
            preds = np.array(tracker.window_predictions)
            actuals = np.array(tracker.window_actuals)
            
            # Directional accuracy
            pred_dir = np.sign(preds)
            actual_dir = np.sign(actuals)
            accuracy = np.mean(pred_dir == actual_dir)
            
            # Sharpe of model returns
            model_returns = preds * actuals  # Simplified
            sharpe = np.mean(model_returns) / (np.std(model_returns) + 1e-6) * np.sqrt(252)
            
            # Check degradation
            sharpe_degradation = (tracker.baseline_sharpe - sharpe) / max(abs(tracker.baseline_sharpe), 0.01)
            accuracy_degradation = (tracker.baseline_accuracy - accuracy) / max(tracker.baseline_accuracy, 0.01)
            
            max_degradation = max(sharpe_degradation, accuracy_degradation)
            
            if max_degradation > self.degradation_threshold:
                # Check cooldown
                if (tracker.last_retrain is None or 
                    datetime.now(UTC) - tracker.last_retrain > self.retrain_cooldown):
                    
                    tracker.degradation_alerts += 1
                    
                    await self._create_alert(
                        BlindSpotType.MODEL_DEGRADATION,
                        BlindSpotSeverity.WARNING,
                        f"Model Degradation: {tracker.model_id}",
                        f"Model performance degraded by {max_degradation:.1%} from baseline",
                        symbols=[],  # Would be strategy-specific
                        affected_strategies=[tracker.strategy_id],
                        metrics={
                            "sharpe_degradation": sharpe_degradation,
                            "accuracy_degradation": accuracy_degradation,
                            "current_sharpe": sharpe,
                            "baseline_sharpe": tracker.baseline_sharpe,
                            "current_accuracy": accuracy,
                            "baseline_accuracy": tracker.baseline_accuracy,
                        },
                        recommended_actions=[
                            ActionType.RETRAIN_MODEL,
                            ActionType.PAUSE_STRATEGY,
                            ActionType.MONITOR,
                        ],
                    )
    
    def register_model(
        self, 
        model_id: str, 
        strategy_id: str, 
        baseline_sharpe: float, 
        baseline_accuracy: float
    ) -> None:
        """Register a model for degradation monitoring."""
        tracker = ModelPerformanceTracker(
            model_id=model_id,
            strategy_id=strategy_id,
            baseline_sharpe=baseline_sharpe,
            baseline_accuracy=baseline_accuracy,
        )
        self.model_trackers[model_id] = tracker
        logger.info(f"Registered model {model_id} for degradation monitoring")
    
    def update_model_performance(self, model_id: str, prediction: float, actual: float) -> None:
        """Update model performance with new prediction."""
        if model_id in self.model_trackers:
            tracker = self.model_trackers[model_id]
            tracker.window_predictions.append(prediction)
            tracker.window_actuals.append(actual)
    
    def mark_model_retrained(self, model_id: str) -> None:
        """Mark model as retrained."""
        if model_id in self.model_trackers:
            tracker = self.model_trackers[model_id]
            tracker.last_retrain = datetime.now(UTC)
            tracker.retrain_count += 1
            tracker.window_predictions.clear()
            tracker.window_actuals.clear()
            logger.info(f"Model {model_id} marked as retrained (count: {tracker.retrain_count})")
    
    # ================================================================
    # TAIL RISK MONITORING
    # ================================================================
    
    async def _check_tail_risk(self) -> None:
        """Monitor for tail risk / black swan conditions."""
        # Calculate portfolio CVaR
        if not self.risk_manager:
            return
        
        positions = self._get_current_positions()
        if not positions:
            return
        
        # Calculate portfolio returns distribution
        # In production, use actual historical returns
        portfolio_returns = self._simulate_portfolio_returns()
        
        # Calculate CVaR
        cvar_95 = self._calculate_cvar(portfolio_returns, 0.95)
        cvar_99 = self._calculate_cvar(portfolio_returns, 0.99)
        
        # Store in history
        self.tail_risk_history.append({
            "timestamp": datetime.now(UTC),
            "cvar_95": cvar_95,
            "cvar_99": cvar_99,
            "var_95": np.percentile(portfolio_returns, 5),
            "var_99": np.percentile(portfolio_returns, 1),
        })
        
        # Check thresholds
        if cvar_95 > self.tail_risk_threshold:
            await self._create_alert(
                BlindSpotType.TAIL_RISK,
                BlindSpotSeverity.CRITICAL,
                "Extreme Tail Risk Detected",
                f"95% CVaR ({cvar_95:.2%}) exceeds threshold ({self.tail_risk_threshold:.2%})",
                symbols=list(self._get_current_positions().keys()),
                affected_strategies=self._get_all_active_strategies(),
                metrics={
                    "cvar_95": cvar_95,
                    "cvar_99": cvar_99,
                    "threshold": self.tail_risk_threshold,
                },
                recommended_actions=[
                    ActionType.REDUCE_EXPOSURE,
                    ActionType.HEDGE,
                    ActionType.CLOSE_POSITIONS,
                ],
            )
    
    def _simulate_portfolio_returns(self) -> np.ndarray:
        """Simulate portfolio returns for tail risk calculation."""
        # In production, use actual position returns
        return np.random.normal(0.0001, 0.015, 10000)
    
    def _calculate_cvar(self, returns: np.ndarray, confidence: float) -> float:
        """Calculate Conditional Value at Risk."""
        var = np.percentile(returns, (1 - confidence) * 100)
        tail_returns = returns[returns <= var]
        return abs(tail_returns.mean()) if len(tail_returns) > 0 else 0
    
    def _get_current_positions(self) -> dict:
        """Get current positions."""
        # In production, get from position manager
        return {
            "EURUSD": {"volume": 0.5, "side": "long"},
            "GBPUSD": {"volume": 0.3, "side": "short"},
        }
    
    def _get_all_active_strategies(self) -> list[str]:
        """Get all active strategy IDs."""
        return ["ensemble_ml", "trend_following", "mean_reversion", "breakout", "momentum", "pairs_trading", "news_based"]
    
    # ================================================================
    # CONCENTRATION RISK
    # ================================================================
    
    async def _check_concentration_risk(self) -> None:
        """Check for concentration risk across positions and strategies."""
        positions = self._get_current_positions()
        if not positions:
            return
        
        # Single position concentration
        total_exposure = sum(abs(p.get("volume", 0)) for p in positions.values())
        if total_exposure > 0:
            for symbol, pos in positions.items():
                pct = abs(pos.get("volume", 0)) / total_exposure
                if pct > self.max_single_position:
                    await self._create_alert(
                        BlindSpotType.CONCENTRATION_RISK,
                        BlindSpotSeverity.WARNING,
                        f"Concentration Risk: {symbol}",
                        f"Single position {pct:.1%} exceeds limit {self.max_single_position:.1%}",
                        symbols=[symbol],
                        affected_strategies=self._get_affected_strategies_from_symbols([symbol]),
                        metrics={"concentration": pct, "limit": self.max_single_position},
                        recommended_actions=[ActionType.REDUCE_EXPOSURE],
                    )
        
        # Strategy concentration
        strategy_exposures = self._get_strategy_exposures()
        total_strat_exp = sum(strategy_exposures.values())
        if total_strat_exp > 0:
            for strat, exp in strategy_exposures.items():
                pct = exp / total_strat_exp
                if pct > 0.5:  # No single strategy > 50%
                    await self._create_alert(
                        BlindSpotType.CONCENTRATION_RISK,
                        BlindSpotSeverity.WARNING,
                        f"Strategy Concentration: {strat}",
                        f"Strategy {strat} represents {pct:.1%} of total exposure",
                        symbols=[],
                        affected_strategies=[strat],
                        metrics={"concentration": pct, "limit": 0.5},
                        recommended_actions=[ActionType.REDUCE_EXPOSURE, ActionType.MONITOR],
                    )
    
    def _get_strategy_exposures(self) -> dict[str, float]:
        """Get exposure by strategy."""
        # In production, get from position manager
        return {
            "ensemble_ml": 10000,
            "trend_following": 8000,
            "mean_reversion": 5000,
            "breakout": 3000,
        }
    
    # ================================================================
    # BEHAVIORAL BIAS DETECTION
    # ================================================================
    
    async def _check_behavioral_bias(self) -> None:
        """Detect behavioral biases in trading patterns."""
        # Need sufficient trade history
        if len(self.trade_history) < 100:
            return
        
        # Analyze recent trades
        recent_trades = list(self.trade_history)[-500:]
        
        # Disposition effect: selling winners too early, holding losers too long
        winners = [t for t in recent_trades if t.get("pnl", 0) > 0]
        losers = [t for t in recent_trades if t.get("pnl", 0) < 0]
        
        if winners and losers:
            avg_winner_hold = np.mean([t.get("hold_time", 0) for t in winners])
            avg_loser_hold = np.mean([t.get("hold_time", 0) for t in losers])
            
            if avg_loser_hold > avg_winner_hold * 1.5:
                await self._create_alert(
                    BlindSpotType.BEHAVIORAL_BIAS,
                    BlindSpotSeverity.WARNING,
                    "Disposition Effect Detected",
                    f"Holding losers {avg_loser_hold/avg_winner_hold:.1f}x longer than winners",
                    symbols=[],
                    affected_strategies=self._get_all_active_strategies(),
                    metrics={
                        "avg_winner_hold": avg_winner_hold,
                        "avg_loser_hold": avg_loser_hold,
                        "ratio": avg_loser_hold / avg_winner_hold,
                    },
                    recommended_actions=[ActionType.MONITOR],
                )
        
        # Overtrading detection
        trades_per_day = len(recent_trades) / max(1, 30)  # Assuming 30 days
        if trades_per_day > 50:  # Arbitrary threshold
            await self._create_alert(
                BlindSpotType.BEHAVIORAL_BIAS,
                BlindSpotSeverity.WARNING,
                "Potential Overtrading",
                f"Trading frequency: {trades_per_day:.1f} trades/day",
                symbols=[],
                affected_strategies=self._get_all_active_strategies(),
                metrics={"trades_per_day": trades_per_day},
                recommended_actions=[ActionType.MONITOR, ActionType.PAUSE_STRATEGY],
            )
        
        # Revenge trading: increasing size after losses
        # Check if position size increases after consecutive losses
        recent_pnls = [t.get("pnl", 0) for t in recent_trades[-20:]]
        if len(recent_pnls) >= 5:
            recent_losses = [p for p in recent_pnls[-5:] if p < 0]
            if len(recent_losses) >= 3:
                # Check if next trade size increased
                raise NotImplementedError("Not implemented")  # Would need position size history
    
    def record_trade(self, trade: dict) -> None:
        """Record a trade for behavioral analysis."""
        self.trade_history.append({
            **trade,
            "timestamp": datetime.now(UTC),
        })
    
    # ================================================================
    # ALERT MANAGEMENT
    # ================================================================
    
    async def _create_alert(
        self,
        blind_spot_type: BlindSpotType,
        severity: BlindSpotSeverity,
        title: str,
        description: str,
        symbols: list[str],
        affected_strategies: list[str],
        metrics: dict[str, float],
        recommended_actions: list[ActionType],
    ) -> None:
        """Create and process a blind spot alert."""
        alert_id = f"{blind_spot_type.value}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        
        # Check for duplicate active alerts
        for existing in self.active_alerts.values():
            if (existing.blind_spot_type == blind_spot_type and 
                not existing.resolved and
                (datetime.now(UTC) - existing.timestamp).total_seconds() < 3600):
                return  # Don't spam duplicate alerts
        
        alert = BlindSpotAlert(
            blind_spot_type=blind_spot_type,
            severity=severity,
            title=title,
            description=description,
            affected_symbols=symbols,
            affected_strategies=affected_strategies,
            metrics=metrics,
            recommended_actions=recommended_actions,
        )
        
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        # Execute automatic actions
        for action in recommended_actions:
            if action in [ActionType.REDUCE_EXPOSURE, ActionType.HEDGE, 
                         ActionType.CLOSE_POSITIONS, ActionType.PAUSE_STRATEGY,
                         ActionType.EMERGENCY_STOP]:
                await self._execute_action(action, alert)
        
        # Callback
        if self.on_alert:
            self.on_alert(alert)
        
        logger.warning(f"BLIND SPOT ALERT: {title} - {description}")
    
    async def _execute_action(self, action: ActionType, alert: BlindSpotAlert) -> None:
        """Execute automatic action for alert."""
        action_data = {
            "alert_id": id(alert),
            "action": action.value,
            "symbols": alert.affected_symbols,
            "strategies": alert.affected_strategies,
        }
        
        if self.on_action:
            self.on_action(action, action_data)
        
        logger.info(f"Executed action {action.value} for alert {alert.title}")
    
    def _cleanup_alerts(self) -> None:
        """Remove old resolved alerts."""
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        self.active_alerts = {
            k: v for k, v in self.active_alerts.items()
            if not v.resolved or v.timestamp > cutoff
        }
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self.active_alerts.values():
            if str(id(alert)) == alert_id or (hasattr(alert, "id") and alert.id == alert_id):
                alert.acknowledged = True
                return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        for alert in self.active_alerts.values():
            if str(id(alert)) == alert_id or (hasattr(alert, "id") and alert.id == alert_id):
                alert.resolved = True
                alert.resolution_time = datetime.now(UTC)
                return True
        return False
    
    def get_active_alerts(self) -> list[BlindSpotAlert]:
        """Get all active alerts."""
        return list(self.active_alerts.values())
    
    def get_alert_summary(self) -> dict:
        """Get summary of alert status."""
        return {
            "active": len(self.active_alerts),
            "by_severity": {
                s.value: len([a for a in self.active_alerts.values() if a.severity == s])
                for s in BlindSpotSeverity
            },
            "by_type": {
                t.value: len([a for a in self.active_alerts.values() if a.blind_spot_type == t])
                for t in BlindSpotType
            },
            "total_historical": len(self.alert_history),
        }
    
    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status."""
        return {
            "running": self._running,
            "alerts": self.get_alert_summary(),
            "correlation_clusters": len(self.correlation_clusters),
            "models_monitored": len(self.model_trackers),
            "regime_persistence": self.regime_persistence,
            "liquidity_symbols": len(self.liquidity_history),
            "trade_history_size": len(self.trade_history),
        }


async def create_blind_spot_manager(
    risk_manager: AdvancedRiskManager | None = None,
    regime_detector: MarketRegimeDetector | None = None,
) -> BlindSpotManager:
    """Create and start blind spot manager."""
    manager = BlindSpotManager(
        risk_manager=risk_manager,
        regime_detector=regime_detector,
    )
    await manager.start()
    return manager
