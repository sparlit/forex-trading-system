"""

Advanced Portfolio Optimization & Capital Allocation
=====================================================

Implements:
- Modern Portfolio Theory (MPT) optimization
- Risk Parity / Equal Risk Contribution
- Black-Litterman model
- Hierarchical Risk Parity (HRP)
- Dynamic capital allocation
- Kelly Criterion for portfolio level
- Conditional Value at Risk (CVaR) optimization
- Maximum Diversification Portfolio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger
from scipy import optimize

from src.risk.portfolio_risk import PortfolioRiskManager
from src.risk.position_sizer import PositionSizer


def _utc_now() -> datetime:
    return datetime.now(UTC)



class OptimizationMethod(str, Enum):
    """Portfolio optimization methods."""
    MEAN_VARIANCE = "mean_variance"          # Classic Markowitz
    MAX_SHARPE = "max_sharpe"                # Maximum Sharpe ratio
    MIN_VARIANCE = "min_variance"            # Minimum variance
    RISK_PARITY = "risk_parity"              # Equal risk contribution
    HRP = "hrp"                              # Hierarchical Risk Parity
    BLACK_LITTERMAN = "black_litterman"      # Black-Litterman
    MAX_DIVERSIFICATION = "max_diversification"  # Maximum Diversification
    CVAR_OPTIMIZATION = "cvar_optimization"  # CVaR optimization
    KELLY_PORTFOLIO = "kelly_portfolio"      # Kelly criterion at portfolio level


class RebalanceFrequency(str, Enum):
    """Rebalancing frequency."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    THRESHOLD = "threshold"  # Rebalance when weights drift beyond threshold


@dataclass(slots=True)
class PortfolioConstraints:
    """Constraints for portfolio optimization."""
    max_weight: float = 0.20          # Max weight per asset
    min_weight: float = 0.01          # Min weight per asset (if included)
    max_leverage: float = 1.0         # Max portfolio leverage
    max_turnover: float = 0.20        # Max turnover per rebalance
    max_sector_exposure: float = 0.30 # Max sector exposure
    min_assets: int = 5               # Minimum number of assets
    max_assets: int = 20              # Maximum number of assets
    long_only: bool = True            # Long-only constraint
    target_return: float | None = None # Target return (for efficient frontier)
    target_risk: float | None = None  # Target risk (for efficient frontier)


@dataclass(slots=True)
class OptimizationResult:
    """Result of portfolio optimization."""
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    diversification_ratio: float
    effective_assets: int
    turnover: float
    method: OptimizationMethod
    timestamp: datetime = field(default_factory=_utc_now)
    success: bool = True
    message: str = ""


@dataclass(slots=True)
class CapitalAllocation:
    """Capital allocation decision."""
    symbol: str
    target_weight: float
    current_weight: float
    target_volume: float
    current_volume: float
    action: str  # "buy", "sell", "hold", "increase", "decrease"
    priority: int  # 1=highest priority
    reasoning: str


class PortfolioOptimizer:
    """
    Advanced portfolio optimizer with multiple methods.
    """
    
    def __init__(
        self,
        constraints: PortfolioConstraints | None = None,
        risk_free_rate: float = 0.02,
        lookback_days: int = 252,
    ):
        self.constraints = constraints or PortfolioConstraints()
        self.risk_free_rate = risk_free_rate
        self.lookback_days = lookback_days
        
        # Data
        self.returns_history: dict[str, list[float]] = {}
        self.current_weights: dict[str, float] = {}
        self.current_prices: dict[str, float] = {}
        
        # Covariance matrix
        self.cov_matrix: np.ndarray | None = None
        self.corr_matrix: np.ndarray | None = None
        self.symbols_list: list[str] = []
        
        # Performance tracking
        self.optimization_history: list[OptimizationResult] = []
        self.last_optimization: datetime | None = None
        
    def update_returns(self, symbol: str, returns: list[float]) -> None:
        """Update return history for a symbol."""
        self.returns_history[symbol] = returns[-self.lookback_days:]
    
    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices."""
        self.current_prices = prices
    
    def update_weights(self, weights: dict[str, float]) -> None:
        """Update current portfolio weights."""
        self.current_weights = weights
    
    def _prepare_matrices(self) -> tuple[np.ndarray, list[str]]:
        """Prepare covariance and correlation matrices."""
        # Align symbols with return data
        symbols = [s for s in self.returns_history if len(self.returns_history[s]) >= 30]
        
        if len(symbols) < 2:
            return np.array([]), []
        
        # Build returns matrix
        min_len = min(len(self.returns_history[s]) for s in symbols)
        returns_matrix = np.array([
            self.returns_history[s][-min_len:] for s in symbols
        ])
        
        # Calculate covariance and correlation
        cov = np.cov(returns_matrix) * 252  # Annualize
        std = np.sqrt(np.diag(cov))
        corr = cov / np.outer(std, std)
        
        self.cov_matrix = cov
        self.corr_matrix = corr
        self.symbols_list = symbols
        
        return cov, symbols
    
    def optimize(
        self,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        expected_returns: dict[str, float] | None = None,
        views: dict[str, float] | None = None,
        view_confidence: dict[str, float] | None = None,
    ) -> OptimizationResult:
        """
        Run portfolio optimization.
        
        Args:
            method: Optimization method
            expected_returns: Expected returns for each symbol (annualized)
            views: Black-Litterman views (symbol -> expected return)
            view_confidence: Confidence in views (symbol -> confidence 0-1)
            
        Returns:
            OptimizationResult with optimal weights
        """
        cov, symbols = self._prepare_matrices()
        
        if len(symbols) < 2:
            return OptimizationResult(
                weights={},
                expected_return=0,
                expected_volatility=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                max_drawdown=0,
                var_95=0,
                cvar_95=0,
                diversification_ratio=0,
                effective_assets=0,
                turnover=0,
                method=method,
                success=False,
                message="Insufficient data for optimization",
            )
        
        n = len(symbols)
        
        # Prepare expected returns
        if expected_returns is None:
            # Use historical mean returns
            mu = np.array([np.mean(self.returns_history[s]) * 252 for s in symbols])
        else:
            mu = np.array([expected_returns.get(s, 0) for s in symbols])
        
        # Current weights vector
        w_current = np.array([self.current_weights.get(s, 0) for s in symbols])
        
        # Run selected optimization method
        if method == OptimizationMethod.MEAN_VARIANCE:
            result = self._mean_variance(mu, cov, n)
        elif method == OptimizationMethod.MAX_SHARPE:
            result = self._max_sharpe(mu, cov, n)
        elif method == OptimizationMethod.MIN_VARIANCE:
            result = self._min_variance(cov, n)
        elif method == OptimizationMethod.RISK_PARITY:
            result = self._risk_parity(cov, n)
        elif method == OptimizationMethod.HRP:
            result = self._hrp(cov, symbols)
        elif method == OptimizationMethod.BLACK_LITTERMAN:
            result = self._black_litterman(mu, cov, n, views, view_confidence)
        elif method == OptimizationMethod.MAX_DIVERSIFICATION:
            result = self._max_diversification(cov, n)
        elif method == OptimizationMethod.CVAR_OPTIMIZATION:
            result = self._cvar_optimization(mu, cov, n)
        elif method == OptimizationMethod.KELLY_PORTFOLIO:
            result = self._kelly_portfolio(mu, cov, n)
        else:
            result = self._max_sharpe(mu, cov, n)
        
        # Apply constraints
        result = self._apply_constraints(result, symbols, w_current)
        
        # Calculate metrics
        weights_dict = dict(zip(symbols, result))
        
        # Portfolio metrics
        port_return = np.dot(result, mu)
        port_vol = np.sqrt(np.dot(result, np.dot(cov, result)))
        sharpe = (port_return - self.risk_free_rate) / port_vol if port_vol > 0 else 0
        
        # Sortino (downside deviation)
        downside_returns = [r for r in np.dot(
            np.array([self.returns_history[s] for s in symbols]).T, result
        ) if r < 0]
        downside_vol = np.std(downside_returns) * np.sqrt(252) if downside_returns else port_vol
        sortino = (port_return - self.risk_free_rate) / downside_vol if downside_vol > 0 else 0
        
        # VaR and CVaR (parametric)
        var_95 = port_return - 1.645 * port_vol
        cvar_95 = port_return - 2.063 * port_vol
        
        # Diversification ratio
        weighted_vol = np.dot(result, np.sqrt(np.diag(cov)))
        div_ratio = weighted_vol / port_vol if port_vol > 0 else 1
        
        # Effective number of assets
        effective_n = 1 / np.sum(result**2) if np.sum(result**2) > 0 else 0
        
        # Turnover
        turnover = 0.5 * np.sum(np.abs(result - w_current))
        
        opt_result = OptimizationResult(
            weights=weights_dict,
            expected_return=port_return,
            expected_volatility=port_vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=0,  # Would need historical simulation
            var_95=var_95,
            cvar_95=cvar_95,
            diversification_ratio=div_ratio,
            effective_assets=int(effective_n),
            turnover=turnover,
            method=method,
            success=True,
        )
        
        self.optimization_history.append(opt_result)
        self.last_optimization = datetime.now(UTC)
        
        return opt_result
    
    def _mean_variance(self, mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
        """Classic mean-variance optimization."""
        # Maximize utility: w'μ - λ/2 * w'Σw
        risk_aversion = 3.0  # Lambda
        
        # Solve: Σw = (1/λ)μ  =>  w = (1/λ)Σ⁻¹μ
        try:
            inv_cov = np.linalg.inv(cov + 1e-6 * np.eye(n))
            w = inv_cov @ mu / risk_aversion
        except np.linalg.LinAlgError:
            w = np.ones(n) / n
        
        return self._project_to_constraints(w, n)
    
    def _max_sharpe(self, mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
        """Maximum Sharpe ratio portfolio."""
        # Maximize (w'μ - rf) / sqrt(w'Σw)
        # Equivalent to: minimize -Sharpe
        
        def neg_sharpe(w):
            port_ret = w @ mu
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol == 0:
                return 1e6
            return -(port_ret - self.risk_free_rate) / port_vol
        
        # Constraints
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = [(self.constraints.min_weight if self.constraints.long_only else -self.constraints.max_weight, 
                   self.constraints.max_weight) for _ in range(n)]
        
        # Initial guess
        x0 = np.ones(n) / n
        
        try:
            res = optimize.minimize(
                neg_sharpe, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 1000}
            )
            return res.x
        except Exception:
            return np.ones(n) / n
    
    def _min_variance(self, cov: np.ndarray, n: int) -> np.ndarray:
        """Minimum variance portfolio."""
        # Minimize w'Σw subject to sum(w) = 1
        
        def portfolio_var(w):
            return w @ cov @ w
        
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = [(self.constraints.min_weight if self.constraints.long_only else -self.constraints.max_weight,
                   self.constraints.max_weight) for _ in range(n)]
        x0 = np.ones(n) / n
        
        try:
            res = optimize.minimize(
                portfolio_var, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 1000}
            )
            return res.x
        except Exception:
            return np.ones(n) / n
    
    def _risk_parity(self, cov: np.ndarray, n: int) -> np.ndarray:
        """Risk Parity / Equal Risk Contribution."""
        # Each asset contributes equally to portfolio risk
        # Risk contribution: RC_i = w_i * (Σw)_i / (w'Σw)
        # Target: RC_i = 1/n for all i
        
        def risk_parity_objective(w):
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol == 0:
                return 1e6
            mrc = cov @ w / port_vol  # Marginal risk contributions
            rc = w * mrc  # Risk contributions
            target = port_vol / n
            return np.sum((rc - target)**2)
        
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = [(self.constraints.min_weight, self.constraints.max_weight) for _ in range(n)]
        x0 = np.ones(n) / n
        
        try:
            res = optimize.minimize(
                risk_parity_objective, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 2000}
            )
            return res.x
        except Exception:
            return np.ones(n) / n
    
    def _hrp(self, cov: np.ndarray, symbols: list[str]) -> np.ndarray:
        """Hierarchical Risk Parity (HRP)."""
        # 1. Compute correlation matrix
        std = np.sqrt(np.diag(cov))
        corr = cov / np.outer(std, std)
        
        # 2. Hierarchical clustering
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform
        
        # Convert correlation to distance
        dist = np.sqrt(0.5 * (1 - corr))
        dist_condensed = squareform(dist)
        
        # Perform clustering
        link = linkage(dist_condensed, method='ward')
        
        # 3. Quasi-diagonalization (get sorted order)
        def get_quasi_diag(link):
            link = link.astype(int)
            sort_ix = []
            def _recursive(cluster):
                if cluster < len(symbols):
                    sort_ix.append(cluster)
                else:
                    left = int(link[cluster - len(symbols), 0])
                    right = int(link[cluster - len(symbols), 1])
                    _recursive(left)
                    _recursive(right)
            _recursive(len(link) - 1 + len(symbols))
            return sort_ix
        
        sort_ix = get_quasi_diag(link)
        
        # 4. Recursive bisection
        def get_rec_bipart(cov, sort_ix):
            w = np.ones(len(sort_ix))
            c_items = [sort_ix]
            
            while c_items:
                c_items = [i[j:k] for i in c_items 
                          for j, k in ((0, len(i)//2), (len(i)//2, len(i))) if len(i) > 1]
                
                for i in range(0, len(c_items), 2):
                    if i + 1 >= len(c_items):
                        break
                    c1, c2 = c_items[i], c_items[i+1]
                    
                    # Variance of each cluster
                    v1 = np.diag(cov[np.ix_(c1, c1)])
                    v2 = np.diag(cov[np.ix_(c2, c2)])
                    
                    # Inverse variance weighting
                    w1 = 1 / v1
                    w2 = 1 / v2
                    w1 = w1 / w1.sum()
                    w2 = w2 / w2.sum()
                    
                    # Cluster variances
                    c1_var = w1 @ cov[np.ix_(c1, c1)] @ w1
                    c2_var = w2 @ cov[np.ix_(c2, c2)] @ w2
                    
                    # Allocation
                    alpha = 1 - c1_var / (c1_var + c2_var)
                    
                    w[c1] *= alpha
                    w[c2] *= (1 - alpha)
            
            return w
        
        try:
            w = get_rec_bipart(cov, sort_ix)
            return w
        except Exception:
            return np.ones(len(symbols)) / len(symbols)
    
    def _black_litterman(
        self, 
        mu: np.ndarray, 
        cov: np.ndarray, 
        n: int,
        views: dict[str, float] | None,
        view_confidence: dict[str, float] | None,
    ) -> np.ndarray:
        """Black-Litterman model."""
        if not views:
            return self._max_sharpe(mu, cov, n)
        
        # Market equilibrium returns (implied from market cap weights)
        # For simplicity, use equal weights as market weights
        w_market = np.ones(n) / n
        pi = cov @ w_market * 3.0  # Risk aversion = 3
        
        # Views matrix P and view returns Q
        k = len(views)
        P = np.zeros((k, n))
        Q = np.zeros(k)
        Omega = np.zeros((k, k))
        
        for i, (symbol, view_return) in enumerate(views.items()):
            if symbol in self.symbols_list:
                idx = self.symbols_list.index(symbol)
                P[i, idx] = 1
                Q[i] = view_return
                confidence = view_confidence.get(symbol, 0.5) if view_confidence else 0.5
                Omega[i, i] = (1 - confidence) / confidence * (P[i:i+1] @ cov @ P[i:i+1].T)[0, 0]
        
        # Black-Litterman formula
        tau = 0.05  # Uncertainty scaling
        
        try:
            inv_cov = np.linalg.inv(cov)
            inv_omega = np.linalg.inv(Omega)
            
            mu_bl = np.linalg.inv(inv_cov + tau * P.T @ inv_omega @ P) @ (
                inv_cov @ pi + tau * P.T @ inv_omega @ Q
            )
            cov_bl = np.linalg.inv(inv_cov + tau * P.T @ inv_omega @ P)
            
            # Optimize with new posterior
            return self._max_sharpe(mu_bl, cov_bl, n)
        except np.linalg.LinAlgError:
            return self._max_sharpe(mu, cov, n)
    
    def _max_diversification(self, cov: np.ndarray, n: int) -> np.ndarray:
        """Maximum Diversification Portfolio."""
        # Maximize Diversification Ratio = w'σ / sqrt(w'Σw)
        # where σ = sqrt(diag(Σ))
        
        sigma = np.sqrt(np.diag(cov))
        
        def neg_div_ratio(w):
            w = np.maximum(w, 0)  # Long only
            w_sum = np.sum(w)
            if w_sum == 0:
                return 1e6
            w = w / w_sum
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol == 0:
                return 1e6
            weighted_vol = w @ sigma
            return -weighted_vol / port_vol
        
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = [(0, self.constraints.max_weight) for _ in range(n)]
        x0 = np.ones(n) / n
        
        try:
            res = optimize.minimize(
                neg_div_ratio, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 1000}
            )
            return res.x
        except Exception:
            return np.ones(n) / n
    
    def _cvar_optimization(self, mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
        """CVaR (Conditional Value at Risk) Optimization."""
        # Minimize CVaR subject to return target
        # Using parametric approximation: CVaR ≈ μ - k * σ
        # where k depends on confidence level (e.g., 2.06 for 95%)
        
        # For simplicity, use mean-variance with CVaR-adjusted risk aversion
        cvar_multiplier = 2.063  # 95% CVaR
        risk_aversion = 3.0 * cvar_multiplier
        
        try:
            inv_cov = np.linalg.inv(cov + 1e-6 * np.eye(n))
            w = inv_cov @ mu / risk_aversion
        except np.linalg.LinAlgError:
            w = np.ones(n) / n
        
        return self._project_to_constraints(w, n)
    
    def _kelly_portfolio(self, mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
        """Kelly Criterion at portfolio level."""
        # Kelly optimal: w* = Σ⁻¹(μ - rf)
        excess_mu = mu - self.risk_free_rate
        
        try:
            inv_cov = np.linalg.inv(cov + 1e-6 * np.eye(n))
            w = inv_cov @ excess_mu
        except np.linalg.LinAlgError:
            w = np.ones(n) / n
        
        # Scale to target volatility
        port_vol = np.sqrt(w @ cov @ w)
        target_vol = 0.15  # 15% target volatility
        if port_vol > 0:
            w = w * target_vol / port_vol
        
        # Apply Kelly fraction
        w = w * 0.5  # Half Kelly
        
        return self._project_to_constraints(w, n)
    
    def _project_to_constraints(self, w: np.ndarray, n: int) -> np.ndarray:
        """Project weights to satisfy constraints."""
        # Long only
        if self.constraints.long_only:
            w = np.maximum(w, 0)
        
        # Min/max weight
        w = np.clip(w, self.constraints.min_weight, self.constraints.max_weight)
        
        # Normalize to sum to 1
        w_sum = np.sum(w)
        if w_sum > 0:
            w = w / w_sum
        else:
            w = np.ones(n) / n
        
        # Max leverage
        if np.sum(np.abs(w)) > self.constraints.max_leverage:
            w = w / np.sum(np.abs(w)) * self.constraints.max_leverage
        
        return w
    
    def _apply_constraints(
        self, 
        weights: np.ndarray, 
        symbols: list[str],
        current_weights: np.ndarray,
    ) -> np.ndarray:
        """Apply all constraints including turnover."""
        # Project to basic constraints
        weights = self._project_to_constraints(weights, len(symbols))
        
        # Turnover constraint
        turnover = 0.5 * np.sum(np.abs(weights - current_weights))
        if turnover > self.constraints.max_turnover:
            # Scale towards current weights
            scale = self.constraints.max_turnover / turnover
            weights = current_weights + scale * (weights - current_weights)
            weights = self._project_to_constraints(weights, len(symbols))
        
        return weights
    
    def generate_allocation_plan(
        self,
        optimization_result: OptimizationResult,
        account_equity: float,
        position_sizer: PositionSizer,
    ) -> list[CapitalAllocation]:
        """Generate capital allocation plan from optimization result."""
        allocations = []
        
        for symbol, target_weight in optimization_result.weights.items():
            current_weight = self.current_weights.get(symbol, 0)
            weight_diff = target_weight - current_weight
            
            if abs(weight_diff) < 0.001:  # Below threshold
                action = "hold"
            elif weight_diff > 0:
                action = "increase" if current_weight > 0 else "buy"
            else:
                action = "decrease" if target_weight > 0 else "sell"
            
            # Calculate target volume
            target_notional = account_equity * target_weight
            current_price = self.current_prices.get(symbol, 1.0)
            target_volume = target_notional / current_price if current_price > 0 else 0
            current_volume = current_weight * account_equity / current_price if current_price > 0 else 0
            
            # Priority based on absolute weight difference
            priority = int(abs(weight_diff) * 1000) + 1
            
            reasoning = f"Target weight: {target_weight:.2%}, Current: {current_weight:.2%}"
            
            allocations.append(CapitalAllocation(
                symbol=symbol,
                target_weight=target_weight,
                current_weight=current_weight,
                target_volume=target_volume,
                current_volume=current_volume,
                action=action,
                priority=priority,
                reasoning=reasoning,
            ))
        
        # Sort by priority
        allocations.sort(key=lambda x: x.priority, reverse=True)
        
        return allocations
    
    def get_efficient_frontier(
        self,
        n_portfolios: int = 50,
    ) -> list[OptimizationResult]:
        """Generate efficient frontier."""
        cov, symbols = self._prepare_matrices()
        if len(symbols) < 2:
            return []
        
        n = len(symbols)
        mu = np.array([np.mean(self.returns_history[s]) * 252 for s in symbols])
        
        # Range of target returns
        min_ret = self._min_variance(cov, n) @ mu
        max_ret = np.max(mu)
        target_returns = np.linspace(min_ret, max_ret, n_portfolios)
        
        frontier = []
        for target in target_returns:
            # Minimize variance for target return
            def portfolio_var(w):
                return w @ cov @ w
            
            constraints = (
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
                {'type': 'eq', 'fun': lambda w: w @ mu - target}
            )
            bounds = [(0, self.constraints.max_weight) for _ in range(n)]
            x0 = np.ones(n) / n
            
            try:
                res = optimize.minimize(
                    portfolio_var, x0, method='SLSQP',
                    bounds=bounds, constraints=constraints,
                    options={'maxiter': 1000}
                )
                if res.success:
                    w = res.x
                    ret = w @ mu
                    vol = np.sqrt(w @ cov @ w)
                    sharpe = (ret - self.risk_free_rate) / vol if vol > 0 else 0
                    frontier.append(OptimizationResult(
                        weights=dict(zip(symbols, w)),
                        expected_return=ret,
                        expected_volatility=vol,
                        sharpe_ratio=sharpe,
                        sortino_ratio=0,
                        max_drawdown=0,
                        var_95=0,
                        cvar_95=0,
                        diversification_ratio=0,
                        effective_assets=0,
                        turnover=0,
                        method=OptimizationMethod.MEAN_VARIANCE,
                    ))
            except Exception:
                continue
        
        return frontier
    
    def should_rebalance(
        self,
        frequency: RebalanceFrequency = RebalanceFrequency.WEEKLY,
        threshold: float = 0.05,
    ) -> bool:
        """Check if portfolio should be rebalanced."""
        if self.last_optimization is None:
            return True
        
        if frequency == RebalanceFrequency.THRESHOLD:
            # Check weight drift
            current_drift = 0.5 * np.sum(np.abs(
                np.array([self.current_weights.get(s, 0) for s in self.symbols_list]) -
                np.array([self.optimization_history[-1].weights.get(s, 0) for s in self.symbols_list])
            ))
            return current_drift > threshold
        
        # Time-based
        elapsed = datetime.now(UTC) - self.last_optimization
        if frequency == RebalanceFrequency.DAILY:
            return elapsed > timedelta(days=1)
        elif frequency == RebalanceFrequency.WEEKLY:
            return elapsed > timedelta(weeks=1)
        elif frequency == RebalanceFrequency.MONTHLY:
            return elapsed > timedelta(days=30)
        elif frequency == RebalanceFrequency.QUARTERLY:
            return elapsed > timedelta(days=90)
        
        return False


class CapitalAllocator:
    """
    High-level capital allocator that coordinates optimization,
    position sizing, and execution.
    """
    
    def __init__(
        self,
        optimizer: PortfolioOptimizer,
        position_sizer: PositionSizer,
        risk_manager: PortfolioRiskManager,
    ):
        self.optimizer = optimizer
        self.position_sizer = position_sizer
        self.risk_manager = risk_manager
        
        self.target_method = OptimizationMethod.MAX_SHARPE
        self.rebalance_frequency = RebalanceFrequency.WEEKLY
        self.drift_threshold = 0.05
        
        # Allocation state
        self.pending_allocations: list[CapitalAllocation] = []
        self.allocation_history: list[dict] = []
        
    async def run_allocation_cycle(
        self,
        account_equity: float,
        expected_returns: dict[str, float] | None = None,
        views: dict[str, float] | None = None,
    ) -> list[CapitalAllocation]:
        """Run a complete capital allocation cycle."""
        # Check if rebalance needed
        if not self.optimizer.should_rebalance(self.rebalance_frequency, self.drift_threshold):
            logger.info("No rebalancing needed")
            return []
        
        # Run optimization
        opt_result = self.optimizer.optimize(
            method=self.target_method,
            expected_returns=expected_returns,
            views=views,
        )
        
        if not opt_result.success:
            logger.warning(f"Optimization failed: {opt_result.message}")
            return []
        
        # Generate allocation plan
        allocations = self.optimizer.generate_allocation_plan(
            opt_result, account_equity, self.position_sizer
        )
        
        # Validate with risk manager
        validated_allocations = await self._validate_allocations(allocations)
        
        # Store pending allocations
        self.pending_allocations = validated_allocations
        
        # Log allocation decision
        self.allocation_history.append({
            "timestamp": datetime.now(UTC),
            "method": opt_result.method.value,
            "sharpe": opt_result.sharpe_ratio,
            "allocations": [a.__dict__ for a in validated_allocations],
        })
        
        return validated_allocations
    
    async def _validate_allocations(
        self,
        allocations: list[CapitalAllocation],
    ) -> list[CapitalAllocation]:
        """Validate allocations against risk limits."""
        validated = []
        
        for alloc in allocations:
            # Check position size limits
            if alloc.target_weight > self.optimizer.constraints.max_weight:
                alloc.target_weight = self.optimizer.constraints.max_weight
                alloc.action = "hold"
                alloc.reasoning += " (capped at max weight)"
            
            # Check sector exposure (simplified)
            # In practice, would check sector mapping
            
            # Check portfolio risk
            # Would integrate with risk manager
            
            validated.append(alloc)
        
        return validated
    
    def execute_allocations(self, allocations: list[CapitalAllocation]) -> dict[str, Any]:
        """Execute validated allocations (placeholder for order manager integration)."""
        results = {
            "executed": [],
            "failed": [],
            "skipped": [],
        }
        
        for alloc in allocations:
            if alloc.action == "hold":
                results["skipped"].append(alloc.symbol)
                continue
            
            # In practice, would place orders via order manager
            # For now, just log
            logger.info(f"Would execute: {alloc.action} {alloc.symbol} "
                       f"target_vol={alloc.target_volume:.4f}")
            results["executed"].append(alloc.symbol)
        
        self.pending_allocations = []
        return results


async def create_capital_allocator(
    position_sizer: PositionSizer,
    risk_manager: PortfolioRiskManager,
    constraints: PortfolioConstraints | None = None,
) -> CapitalAllocator:
    """Create and initialize capital allocator."""
    optimizer = PortfolioOptimizer(constraints=constraints)
    allocator = CapitalAllocator(optimizer, position_sizer, risk_manager)
    return allocator
