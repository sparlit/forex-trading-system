"""
Capital Allocator - Dynamic portfolio allocation with Risk Parity and Kelly Criterion.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from src.data.models import Portfolio
from src.data.storage.timescale import TimescaleDB
from src.risk.metrics import RiskMetricsCalculator
from src.risk.risk_engine import RiskEngine
from src.strategy.regime_detector import MarketRegime, RegimeDetector

logger = logging.getLogger(__name__)


@dataclass
class AllocationConfig:
    """Configuration for capital allocation"""
    # Risk parity settings
    target_volatility: float = 0.10  # 10% annual target
    max_leverage: float = 3.0
    max_strategy_weight: float = 0.5  # Max 50% to single strategy
    min_strategy_weight: float = 0.0  # Min 0% (can go negative for short)
    
    # Kelly settings
    kelly_fraction: float = 0.5  # Half-Kelly for safety
    kelly_lookback_days: int = 252
    min_kelly_weight: float = 0.0
    max_kelly_weight: float = 0.25
    
    # Regime blending
    regime_blend_weight: float = 0.3  # Weight of regime-based allocation
    
    # Rebalancing
    rebalance_frequency: str = "daily"  # daily, weekly, monthly
    turnover_limit: float = 0.10  # Max 10% daily turnover
    min_rebalance_threshold: float = 0.02  # 2% weight change triggers rebalance
    
    # Risk constraints
    max_portfolio_var: float = 0.02
    max_correlation: float = 0.7
    max_sector_exposure: float = 0.30
    max_single_strategy_dd: float = 0.05


@dataclass
class AllocationResult:
    """Result of capital allocation"""
    weights: dict[str, float]  # strategy_id -> weight
    capital: dict[str, float]  # strategy_id -> dollar amount
    risk_metrics: dict[str, float]
    rebalance_needed: bool
    turnover: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class CovarianceEstimator:
    """Robust covariance estimation for risk parity"""
    
    def __init__(self, method: str = "ledoit_wolf", shrinkage: float = 0.1):
        self.method = method
        self.shrinkage = shrinkage
    
    def estimate(self, returns: np.ndarray) -> np.ndarray:
        """Estimate covariance matrix with regularization"""
        if len(returns) < 30:
            return np.eye(returns.shape[1]) * 0.04  # Default 20% vol
        
        # Remove NaN
        returns = np.nan_to_num(returns, nan=0.0)
        
        _n_assets = returns.shape[1]
        sample_cov = np.cov(returns.T)
        
        if self.method == "ledoit_wolf":
            return self._ledoit_wolf(returns, sample_cov)
        elif self.method == "shrinkage":
            return self._shrinkage(sample_cov, self.shrinkage)
        elif self.method == "ewma":
            return self._ewma_cov(returns)
        else:
            return sample_cov
    
    def _ledoit_wolf(self, returns: np.ndarray, sample_cov: np.ndarray) -> np.ndarray:
        """Ledoit-Wolf shrinkage estimator"""
        n, p = returns.shape
        
        # Target: diagonal matrix with average variance
        mean_var = np.trace(sample_cov) / p
        target = np.eye(p) * mean_var
        
        # Compute shrinkage intensity
        # Simplified Ledoit-Wolf
        centered = returns - returns.mean(axis=0)
        pi_hat = np.sum(np.var(centered @ centered.T, axis=1)) / n
        rho_hat = np.trace(sample_cov @ sample_cov) / p
        gamma_hat = np.linalg.norm(sample_cov - target) ** 2
        
        kappa = (pi_hat - rho_hat) / gamma_hat if gamma_hat > 0 else 0
        shrinkage = max(0, min(1, kappa / n))
        
        return shrinkage * target + (1 - shrinkage) * sample_cov
    
    def _shrinkage(self, sample_cov: np.ndarray, shrinkage: float) -> np.ndarray:
        """Simple shrinkage toward diagonal"""
        mean_var = np.trace(sample_cov) / sample_cov.shape[0]
        target = np.eye(sample_cov.shape[0]) * mean_var
        return shrinkage * target + (1 - shrinkage) * sample_cov
    
    def _ewma_cov(self, returns: np.ndarray, lambda_: float = 0.94) -> np.ndarray:
        """Exponentially weighted moving average covariance"""
        n, p = returns.shape
        cov = np.zeros((p, p))
        weight = 1.0
        
        for i in range(n - 1, -1, -1):
            r = returns[i].reshape(-1, 1)
            cov += weight * (r @ r.T)
            weight *= lambda_
        
        return cov / (1 - lambda_**n) * (1 - lambda_)


class RiskParityAllocator:
    """Risk Parity allocation - equal risk contribution"""
    
    def __init__(self, target_vol: float = 0.10, max_leverage: float = 3.0):
        self.target_vol = target_vol
        self.max_leverage = max_leverage
        self.cov_estimator = CovarianceEstimator("ledoit_wolf")
    
    def allocate(self, returns: np.ndarray, 
                 max_weight: float = 1.0,
                 min_weight: float = 0.0) -> np.ndarray:
        """
        Compute risk parity weights using Newton's method
        
        Returns weights that equalize risk contributions
        """
        n = returns.shape[1]
        if n == 0:
            return np.array([])
        
        # Estimate covariance
        cov = self.cov_estimator.estimate(returns)
        
        # Initial guess: inverse volatility
        vol = np.sqrt(np.diag(cov))
        vol[vol == 0] = 0.01
        x = 1.0 / vol
        x = x / np.sum(x)
        
        # Newton's method for risk parity
        target_risk = 1.0 / n
        
        for iteration in range(100):
            # Portfolio variance
            port_var = x @ cov @ x
            port_vol = np.sqrt(max(port_var, 1e-10))
            
            # Marginal risk contributions
            mrc = cov @ x / port_vol
            rc = x * mrc
            
            # Error from target
            error = rc - target_risk
            
            if np.max(np.abs(error)) < 1e-6:
                break
            
            # Jacobian
            J = np.diag(mrc) + np.outer(x, np.diag(cov)) / port_vol - \
                np.outer(x, mrc) * (x @ mrc) / port_var
            
            # Newton step
            try:
                dx = np.linalg.solve(J, -error)
                x_new = x + dx
                
                # Project to constraints
                x_new = np.clip(x_new, min_weight, max_weight)
                x_new = x_new / np.sum(x_new) if np.sum(x_new) > 0 else x
                
                if np.linalg.norm(x_new - x) < 1e-8:
                    x = x_new
                    break
                x = x_new
            except np.linalg.LinAlgError:
                break
        
        # Normalize to target volatility
        port_vol = np.sqrt(x @ cov @ x)
        if port_vol > 0:
            scale = min(self.target_vol / port_vol, self.max_leverage)
            x = x * scale
        
        # Final normalization
        if np.sum(x) > self.max_leverage:
            x = x / np.sum(x) * self.max_leverage
        
        return np.maximum(x, 0)  # Long-only for now


class KellyAllocator:
    """Kelly Criterion allocation"""
    
    def __init__(self, 
                 kelly_fraction: float = 0.5,
                 lookback_days: int = 252,
                 min_weight: float = 0.0,
                 max_weight: float = 0.25):
        self.kelly_fraction = kelly_fraction
        self.lookback_days = lookback_days
        self.min_weight = min_weight
        self.max_weight = max_weight
    
    def calculate_kelly(self, 
                        returns: np.ndarray,
                        win_rate: float,
                        avg_win: float,
                        avg_loss: float) -> float:
        """Calculate Kelly fraction for a single strategy"""
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0
        
        # Kelly formula: f* = (p * b - q) / b
        # where b = avg_win / avg_loss, p = win_rate, q = 1 - win_rate
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - win_rate
        
        kelly = (p * b - q) / b
        
        # Apply safety fraction
        kelly = kelly * self.kelly_fraction
        
        # Apply bounds
        return np.clip(kelly, self.min_weight, self.max_weight)
    
    def allocate(self, 
                 strategy_returns: dict[str, np.ndarray],
                 strategy_stats: dict[str, dict]) -> dict[str, float]:
        """Calculate Kelly weights for all strategies"""
        weights = {}
        
        for strategy_id, returns in strategy_returns.items():
            if len(returns) < 30:
                weights[strategy_id] = 0.0
                continue
            
            stats = strategy_stats.get(strategy_id, {})
            win_rate = stats.get("win_rate", 0.5)
            avg_win = stats.get("avg_win", 0.01)
            avg_loss = stats.get("avg_loss", 0.01)
            
            kelly = self.calculate_kelly(returns, win_rate, avg_win, avg_loss)
            weights[strategy_id] = kelly
        
        # Normalize
        total = sum(weights.values())
        if total > 1.0:
            weights = {k: v / total for k, v in weights.items()}
        
        return weights


class RegimeBlender:
    """Blend allocations based on market regime"""
    
    def __init__(self, regime_detector: Any | None = None, blend_weight: float = 0.3):
        self.regime_detector = regime_detector
        self.blend_weight = blend_weight
        
        # Pre-defined regime weights
        self.regime_weights = {
            MarketRegime.TRENDING_BULL: {
                "trend_following": 0.60,
                "mean_reversion": 0.10,
                "carry_trade": 0.30,
                "volatility": 0.0,
                "hedge": 0.0,
            },
            MarketRegime.TRENDING_BEAR: {
                "trend_following": 0.50,
                "mean_reversion": 0.10,
                "volatility": 0.20,
                "hedge": 0.20,
                "carry_trade": 0.0,
            },
            MarketRegime.RANGE_BOUND: {
                "mean_reversion": 0.50,
                "stat_arb": 0.20,
                "carry_trade": 0.20,
                "trend_following": 0.10,
            },
            MarketRegime.HIGH_VOL: {
                "volatility": 0.40,
                "trend_following": 0.20,
                "hedge": 0.30,
                "mean_reversion": 0.10,
            },
            MarketRegime.CRISIS: {
                "hedge": 0.60,
                "cash": 0.30,
                "volatility": 0.10,
            },
        }
    
    def get_weights(self, 
                    base_weights: dict[str, float],
                    current_regime: MarketRegime,
                    regime_confidence: float) -> dict[str, float]:
        """Blend base allocation with regime-specific weights"""
        
        if current_regime not in self.regime_weights:
            return base_weights
        
        regime_w = self.regime_weights[current_regime]
        
        # Blend: (1 - alpha) * base + alpha * regime
        alpha = self.blend_weight * regime_confidence
        
        blended = {}
        all_keys = set(base_weights.keys()) | set(regime_w.keys())
        
        for key in all_keys:
            base_w = base_weights.get(key, 0)
            reg_w = regime_w.get(key, 0)
            blended[key] = (1 - alpha) * base_w + alpha * reg_w
        
        # Normalize
        total = sum(blended.values())
        if total > 0:
            blended = {k: v / total for k, v in blended.items()}
        
        return blended


class CapitalAllocator:
    """Main capital allocation engine"""
    
    def __init__(self, 
                 config: AllocationConfig,
                 risk_engine: RiskEngine,
                 regime_detector: RegimeDetector | None = None,
                 timescaledb: TimescaleDB | None = None):
        self.config = config
        self.risk_engine = risk_engine
        self.regime_detector = regime_detector
        self.timescaledb = timescaledb
        
        # Sub-allocators
        self.risk_parity = RiskParityAllocator(
            target_vol=config.target_volatility,
            max_leverage=config.max_leverage
        )
        self.kelly = KellyAllocator(
            kelly_fraction=config.kelly_fraction,
            lookback_days=config.kelly_lookback_days,
            min_weight=config.min_kelly_weight,
            max_weight=config.max_kelly_weight
        )
        self.regime_blender = RegimeBlender(
            regime_detector=regime_detector,
            blend_weight=config.regime_blend_weight
        )
        
        # State
        self.current_weights: dict[str, float] = {}
        self.last_rebalance: datetime | None = None
        self.allocation_history: list[AllocationResult] = []
        
        # Metrics calculator
        self.metrics_calc = RiskMetricsCalculator()
    
    async def allocate(self, 
                       portfolio: Portfolio,
                       strategy_returns: dict[str, np.ndarray],
                       strategy_stats: dict[str, dict]) -> AllocationResult:
        """Main allocation function"""
        
        # 1. Risk Parity allocation
        if strategy_returns:
            returns_matrix = np.column_stack([
                strategy_returns[sid] for sid in sorted(strategy_returns.keys())
            ])
            strategy_ids = sorted(strategy_returns.keys())
            
            rp_weights = self.risk_parity.allocate(
                returns_matrix,
                max_weight=self.config.max_strategy_weight,
                min_weight=self.config.min_strategy_weight
            )
            rp_dict = dict(zip(strategy_ids, rp_weights))
        else:
            rp_dict = {}
        
        # 2. Kelly allocation
        kelly_dict = self.kelly.allocate(strategy_returns, {})
        
        # 3. Blend: Risk Parity as base, Kelly as overlay
        base_weights = {}
        for sid in set(rp_dict.keys()) | set(kelly_dict.keys()):
            rp_w = rp_dict.get(sid, 0)
            kelly_w = kelly_dict.get(sid, 0)
            # 70% risk parity, 30% Kelly
            base_weights[sid] = 0.7 * rp_w + 0.3 * kelly_w
        
        # 3. Regime blending
        current_regime = MarketRegime.RANGE_BOUND
        regime_conf = 0.5
        
        if self.regime_detector:
            regime_state = self.regime_detector.current_regime
            current_regime = regime_state.primary
            regime_conf = regime_state.confidence
        
        final_weights = self.regime_blender.get_weights(
            base_weights, current_regime, regime_conf
        )
        
        # Apply constraints
        final_weights = self._apply_constraints(final_weights)
        
        # Check if rebalance needed
        rebalance_needed = self._should_rebalance(final_weights)
        turnover = self._calculate_turnover(final_weights)
        
        # Convert to capital amounts
        total_equity = portfolio.total_equity
        capital = {sid: w * total_equity for sid, w in final_weights.items()}
        
        # Calculate risk metrics
        risk_metrics = await self._calculate_portfolio_risk(portfolio, final_weights)
        
        result = AllocationResult(
            weights=final_weights,
            capital=capital,
            risk_metrics=risk_metrics,
            rebalance_needed=rebalance_needed,
            turnover=turnover
        )
        
        # Update state
        if rebalance_needed:
            self.current_weights = final_weights
            self.last_rebalance = datetime.now(UTC)
        
        self.allocation_history.append(result)
        if len(self.allocation_history) > 1000:
            self.allocation_history = self.allocation_history[-1000:]
        
        return result
    
    def _apply_constraints(self, weights: dict[str, float]) -> dict[str, float]:
        """Apply allocation constraints"""
        # Clip to bounds
        constrained = {}
        for sid, w in weights.items():
            constrained[sid] = np.clip(w, 
                                       self.config.min_strategy_weight, 
                                       self.config.max_strategy_weight)
        
        # Normalize to max leverage
        total = sum(constrained.values())
        if total > self.config.max_leverage:
            constrained = {k: v / total * self.config.max_leverage for k, v in constrained.items()}
        
        # Sector/correlation limits would go here
        
        return constrained
    
    def _should_rebalance(self, new_weights: dict[str, float]) -> bool:
        """Check if rebalancing is needed"""
        if not self.current_weights:
            return True
        
        if not self.last_rebalance:
            return True
        
        # Check time-based
        if self.config.rebalance_frequency == "daily":
            if datetime.now(UTC) - self.last_rebalance > timedelta(days=1):
                return True
        elif self.config.rebalance_frequency == "weekly":
            if datetime.now(UTC) - self.last_rebalance > timedelta(weeks=1):
                return True
        
        # Check weight drift
        turnover = self._calculate_turnover(new_weights)
        if turnover > self.config.turnover_limit:
            return True
        
        # Check individual weight drift
        for sid, new_w in new_weights.items():
            old_w = self.current_weights.get(sid, 0)
            if abs(new_w - old_w) > self.config.min_rebalance_threshold:
                return True
        
        return False
    
    def _calculate_turnover(self, new_weights: dict[str, float]) -> float:
        """Calculate portfolio turnover"""
        if not self.current_weights:
            return 1.0
        
        all_keys = set(new_weights.keys()) | set(self.current_weights.keys())
        turnover = sum(
            abs(new_weights.get(k, 0) - self.current_weights.get(k, 0))
            for k in all_keys
        ) / 2
        
        return turnover
    
    async def _calculate_portfolio_risk(self, 
                                        portfolio: Portfolio,
                                        weights: dict[str, float]) -> dict[str, float]:
        """Calculate portfolio risk metrics for allocation"""
        metrics = {
            "expected_vol": 0.0,
            "var_95": 0.0,
            "expected_shortfall": 0.0,
            "max_drawdown_estimate": 0.0,
            "leverage": sum(abs(w) for w in weights.values()),
            "concentration": max(weights.values()) if weights else 0,
            "effective_n": 1.0 / sum(w**2 for w in weights.values()) if weights else 0
        }
        
        return metrics
    
    def get_status(self) -> dict[str, Any]:
        return {
            "current_weights": self.current_weights,
            "last_rebalance": self.last_rebalance.isoformat() if self.last_rebalance else None,
            "num_strategies": len(self.current_weights),
            "leverage": sum(abs(w) for w in self.current_weights.values()),
            "regime": self.regime_detector.current_regime.primary.value if self.regime_detector else "unknown",
            "regime_confidence": self.regime_detector.current_regime.confidence if self.regime_detector else 0,
            "config": {
                "target_volatility": self.config.target_volatility,
                "max_leverage": self.config.max_leverage,
                "kelly_fraction": self.config.kelly_fraction,
            }
        }


class AllocationService:
    """Service that runs allocation periodically"""
    
    def __init__(self, 
                 allocator: CapitalAllocator,
                 portfolio: Portfolio,
                 timescaledb: TimescaleDB):
        self.allocator = allocator
        self.portfolio = portfolio
        self.timescaledb = timescaledb
        
        self.running = False
        self.interval = 3600  # 1 hour
    
    async def start(self):
        self.running = True
        asyncio.create_task(self._allocation_loop())
        logger.info("AllocationService started")
    
    async def stop(self):
        self.running = False
        logger.info("AllocationService stopped")
    
    async def _allocation_loop(self):
        while self.running:
            try:
                await self._run_allocation()
            except Exception as e:
                logger.error(f"Allocation loop error: {e}")
            
            await asyncio.sleep(self.interval)
    
    async def _run_allocation(self):
        """Run allocation cycle"""
        # Get strategy returns from database
        strategy_returns = await self._get_strategy_returns()
        strategy_stats = await self._get_strategy_stats()
        
        if not strategy_returns:
            logger.warning("No strategy returns available for allocation")
            return
        
        # Run allocation
        result = await self.allocator.allocate(
            self.portfolio,
            strategy_returns,
            strategy_stats
        )
        
        # Store result
        await self._store_allocation(result)
        
        if result.rebalance_needed:
            logger.info(f"Rebalance triggered: turnover={result.turnover:.2%}")
            # Would trigger actual rebalancing via execution engine
        
        logger.debug(f"Allocation: {result.weights}")
    
    async def _get_strategy_returns(self) -> dict[str, np.ndarray]:
        """Get historical returns for each strategy"""
        try:
            async with self.timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT strategy_id, return_pct, time
                    FROM risk.portfolio_returns
                    WHERE time > NOW() - INTERVAL '252 days'
                    ORDER BY strategy_id, time
                """)
            
            # Group by strategy
            returns = {}
            for row in rows:
                sid = row['strategy_id']
                if sid not in returns:
                    returns[sid] = []
                returns[sid].append(float(row['return_pct']) / 100)
            
            return {k: np.array(v) for k, v in returns.items() if len(v) > 30}
        except Exception as e:
            logger.error(f"Failed to get strategy returns: {e}")
            return {}
    
    async def _get_strategy_stats(self) -> dict[str, dict]:
        """Get strategy performance statistics"""
        try:
            async with self.timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT strategy_id, win_rate, profit_factor, avg_win, avg_loss
                    FROM analytics.performance_metrics
                    WHERE date = (SELECT MAX(date) FROM analytics.performance_metrics)
                """)
            
            return {row['strategy_id']: dict(row) for row in rows}
        except Exception as e:
            logger.error(f"Failed to get strategy stats: {e}")
            return {}
    
    async def _store_allocation(self, result: AllocationResult):
        """Store allocation in database"""
        try:
            async with self.timescaledb.acquire() as conn:
                for sid, weight in result.weights.items():
                    await conn.execute("""
                        INSERT INTO analytics.capital_allocation (
                            timestamp, strategy_id, weight, capital, 
                            rebalance_needed, turnover, risk_metrics
                        ) VALUES (NOW(), $1, $2, $3, $4, $5, $6)
                    """,
                        sid, weight, result.capital.get(sid, 0),
                        result.rebalance_needed, result.turnover,
                        json.dumps(result.risk_metrics)
                    )
        except Exception as e:
            logger.error(f"Failed to store allocation: {e}")