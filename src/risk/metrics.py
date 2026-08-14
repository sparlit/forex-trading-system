"""
Risk Metrics - VaR, Expected Shortfall, and portfolio risk calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.data.models import Portfolio, Position


@dataclass
class RiskMetrics:
    """Container for all risk metrics"""
    # VaR
    var_95_1d: float = 0.0
    var_99_1d: float = 0.0
    var_95_10d: float = 0.0
    var_99_10d: float = 0.0
    
    # Expected Shortfall (CVaR)
    es_95_1d: float = 0.0
    es_99_1d: float = 0.0
    
    # Portfolio metrics
    portfolio_volatility: float = 0.0
    portfolio_beta: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    
    # Leverage
    gross_leverage: float = 0.0
    net_leverage: float = 0.0
    
    # Concentration
    max_position_pct: float = 0.0
    herfindahl_index: float = 0.0
    effective_positions: float = 0.0
    
    # Correlation
    avg_correlation: float = 0.0
    max_correlation: float = 0.0
    
    # Tail risk
    skewness: float = 0.0
    kurtosis: float = 0.0
    
    # Stress test results
    stress_scenarios: dict[str, float] = None
    
    def __post_init__(self):
        if self.stress_scenarios is None:
            self.stress_scenarios = {}


class RiskMetricsCalculator:
    """Calculates comprehensive risk metrics for portfolio"""
    
    def __init__(self, confidence_levels: list[float] | None = None):
        self.confidence_levels = confidence_levels or [0.95, 0.99]
        self.lookback_days = 252  # 1 year
    
    def calculate_all(self, 
                      portfolio: Portfolio,
                      returns_history: np.ndarray,
                      price_history: dict[str, np.ndarray],
                      positions: list[Position],
                      benchmark_returns: np.ndarray | None = None) -> RiskMetrics:
        """Calculate all risk metrics"""
        
        metrics = RiskMetrics()
        
        # VaR and ES
        metrics.var_95_1d = self._var(returns_history, 0.95)
        metrics.var_99_1d = self._var(returns_history, 0.99)
        metrics.var_95_10d = metrics.var_95_1d * np.sqrt(10)
        metrics.var_99_10d = metrics.var_99_1d * np.sqrt(10)
        
        metrics.es_95_1d = self._expected_shortfall(returns_history, 0.95)
        metrics.es_99_1d = self._expected_shortfall(returns_history, 0.99)
        
        # Portfolio volatility
        metrics.portfolio_volatility = np.std(returns_history) * np.sqrt(252)
        
        # Beta to benchmark
        if benchmark_returns is not None and len(benchmark_returns) == len(returns_history):
            metrics.portfolio_beta = self._calculate_beta(returns_history, benchmark_returns)
        
        # Drawdown
        metrics.max_drawdown, metrics.current_drawdown = self._calculate_drawdown(returns_history)
        
        # Leverage
        metrics.gross_leverage, metrics.net_leverage = self._calculate_leverage(portfolio)
        
        # Concentration
        metrics.max_position_pct, metrics.herfindahl_index, metrics.effective_positions = \
            self._calculate_concentration(positions, portfolio.total_equity)
        
        # Correlation
        metrics.avg_correlation, metrics.max_correlation = self._calculate_correlation(price_history)
        
        # Tail risk
        metrics.skewness = self._skewness(returns_history)
        metrics.kurtosis = self._kurtosis(returns_history)
        
        # Stress tests
        metrics.stress_scenarios = self._run_stress_tests(portfolio, price_history)
        
        return metrics
    
    def _var(self, returns: np.ndarray, confidence: float) -> float:
        """Value at Risk using historical simulation"""
        if len(returns) < 30:
            return 0.0
        return abs(np.percentile(returns, (1 - confidence) * 100))
    
    def _expected_shortfall(self, returns: np.ndarray, confidence: float) -> float:
        """Expected Shortfall (Conditional VaR)"""
        if len(returns) < 30:
            return 0.0
        var = self._var(returns, confidence)
        tail_returns = returns[returns <= -var]
        return abs(tail_returns.mean()) if len(tail_returns) > 0 else var
    
    def _calculate_beta(self, portfolio_returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
        """Calculate portfolio beta to benchmark"""
        if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 30:
            return 1.0
        
        covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
        benchmark_var = np.var(benchmark_returns)
        
        if benchmark_var == 0:
            return 1.0
        
        return covariance / benchmark_var
    
    def _calculate_drawdown(self, returns: np.ndarray) -> tuple[float, float]:
        """Calculate max and current drawdown"""
        if len(returns) == 0:
            return 0.0, 0.0
        
        # Convert returns to equity curve
        equity = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        
        max_dd = np.max(drawdown)
        current_dd = drawdown[-1]
        
        return float(max_dd), float(current_dd)
    
    def _calculate_leverage(self, portfolio: Portfolio) -> tuple[float, float]:
        """Calculate gross and net leverage"""
        if portfolio.total_equity == 0:
            return 0.0, 0.0
        
        gross = sum(abs(p.market_value) for p in portfolio.positions) / portfolio.total_equity
        net = sum(p.market_value for p in portfolio.positions) / portfolio.total_equity
        
        return float(gross), float(net)
    
    def _calculate_concentration(self, positions: list[Position], total_equity: float) -> tuple[float, float, float]:
        """Calculate concentration metrics"""
        if total_equity == 0 or not positions:
            return 0.0, 0.0, 0.0
        
        weights = np.array([abs(p.market_value) / total_equity for p in positions])
        weights = weights[weights > 0]
        
        if len(weights) == 0:
            return 0.0, 0.0, 0.0
        
        max_pos = float(np.max(weights))
        hhi = float(np.sum(weights ** 2))
        eff_n = 1.0 / hhi if hhi > 0 else 0.0
        
        return max_pos, hhi, eff_n
    
    def _calculate_correlation(self, price_history: dict[str, np.ndarray]) -> tuple[float, float]:
        """Calculate average and max correlation"""
        if len(price_history) < 2:
            return 0.0, 0.0
        
        # Calculate returns
        returns = {}
        for sym, prices in price_history.items():
            if len(prices) > 2:
                returns[sym] = np.diff(np.log(prices))
        
        if len(returns) < 2:
            return 0.0, 0.0
        
        sym_list = list(returns.keys())
        n = len(sym_list)
        
        # Align lengths
        min_len = min(len(returns[s]) for s in sym_list)
        if min_len < 30:
            return 0.0, 0.0
        
        aligned = np.array([returns[s][-min_len:] for s in sym_list])
        corr_matrix = np.corrcoef(aligned)
        
        # Get upper triangle (excluding diagonal)
        upper_tri = corr_matrix[np.triu_indices(n, k=1)]
        upper_tri = upper_tri[~np.isnan(upper_tri)]
        
        if len(upper_tri) == 0:
            return 0.0, 0.0
        
        return float(np.mean(upper_tri)), float(np.max(upper_tri))
    
    def _skewness(self, returns: np.ndarray) -> float:
        """Calculate skewness"""
        if len(returns) < 30:
            return 0.0
        mean = np.mean(returns)
        std = np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 3))
    
    def _kurtosis(self, returns: np.ndarray) -> float:
        """Calculate excess kurtosis"""
        if len(returns) < 30:
            return 0.0
        mean = np.mean(returns)
        std = np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 4) - 3)
    
    def _run_stress_tests(self, portfolio: Portfolio, price_history: dict[str, np.ndarray]) -> dict[str, float]:
        """Run historical and hypothetical stress scenarios"""
        scenarios = {}
        
        # Get position symbols
        symbols = [p.symbol for p in portfolio.positions]
        if not symbols:
            return scenarios
        
        # Historical scenarios
        stress_periods = {
            "covid_crash_2020": ("2020-02-15", "2020-03-31"),
            "financial_crisis_2008": ("2008-09-01", "2008-12-31"),
            "flash_crash_2010": ("2010-05-06", "2010-05-06"),
            "eurozone_crisis_2011": ("2011-07-01", "2011-12-31"),
            "rate_hike_2022": ("2022-01-01", "2022-12-31"),
        }
        
        # For each position, calculate stress loss
        for name in stress_periods:
            # This would need historical price data for the period
            # Simplified: estimate based on asset class
            total_loss = 0.0
            for position in portfolio.positions:
                # Estimate based on asset class typical stress
                stress_multiplier = self._get_stress_multiplier(position.symbol, name)
                loss = abs(position.market_value) * stress_multiplier
                total_loss += loss
            
            scenarios[name] = total_loss / portfolio.total_equity if portfolio.total_equity > 0 else 0
        
        # Hypothetical scenarios
        scenarios.update({
            "equity_-20%": 0.20 * sum(abs(p.market_value) for p in portfolio.positions if "USD" in p.symbol) / portfolio.total_equity if portfolio.total_equity > 0 else 0,
            "fx_-10%": 0.10 * sum(abs(p.market_value) for p in portfolio.positions if p.symbol.endswith("USD") or p.symbol.startswith("USD")) / portfolio.total_equity if portfolio.total_equity > 0 else 0,
            "crypto_-50%": 0.50 * sum(abs(p.market_value) for p in portfolio.positions if "BTC" in p.symbol or "ETH" in p.symbol) / portfolio.total_equity if portfolio.total_equity > 0 else 0,
            "rates_+200bp": 0.02 * portfolio.total_equity / portfolio.total_equity if portfolio.total_equity > 0 else 0,
            "vol_2x": 0.10,  # 10% portfolio loss if vol doubles
        })
        
        return scenarios
    
    def _get_stress_multiplier(self, symbol: str, scenario: str) -> float:
        """Get estimated stress loss multiplier for symbol in scenario"""
        # Simplified multipliers based on asset class
        is_crypto = "BTC" in symbol or "ETH" in symbol
        is_fx = any(ccy in symbol for ccy in ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"])
        is_metal = "XAU" in symbol or "XAG" in symbol
        
        multipliers = {
            "covid_crash_2020": {"crypto": 0.50, "fx": 0.08, "metal": 0.15, "default": 0.20},
            "financial_crisis_2008": {"crypto": 0.0, "fx": 0.15, "metal": 0.25, "default": 0.30},
            "flash_crash_2010": {"crypto": 0.0, "fx": 0.05, "metal": 0.10, "default": 0.10},
            "eurozone_crisis_2011": {"crypto": 0.0, "fx": 0.12, "metal": 0.20, "default": 0.15},
            "rate_hike_2022": {"crypto": 0.60, "fx": 0.10, "metal": 0.15, "default": 0.20},
        }
        
        asset_class = "crypto" if is_crypto else ("fx" if is_fx else ("metal" if is_metal else "default"))
        return multipliers.get(scenario, {}).get(asset_class, multipliers.get(scenario, {}).get("default", 0.10))


class MonteCarloRiskEngine:
    """Monte Carlo simulation for risk analysis"""
    
    def __init__(self, n_simulations: int = 10000, horizon_days: int = 10):
        self.n_simulations = n_simulations
        self.horizon_days = horizon_days
    
    def simulate_portfolio(self, 
                           portfolio: Portfolio,
                           returns_history: np.ndarray,
                           price_history: dict[str, np.ndarray]) -> dict[str, Any]:
        """Run Monte Carlo simulation"""
        
        if len(returns_history) < 60:
            return {}
        
        # Estimate parameters
        mu = np.mean(returns_history)
        sigma = np.std(returns_history)
        
        # Generate paths
        _dt = 1 / 252
        paths = np.zeros((self.n_simulations, self.horizon_days))
        
        for i in range(self.n_simulations):
            shocks = np.random.normal(0, 1, self.horizon_days)
            daily_returns = mu + sigma * shocks
            path = np.cumprod(1 + daily_returns)
            paths[i] = path
        
        # Portfolio values
        initial_value = portfolio.total_equity
        final_values = initial_value * paths[:, -1]
        
        # Calculate metrics
        returns = (final_values - initial_value) / initial_value
        
        return {
            "mean_return": float(np.mean(returns)),
            "std_return": float(np.std(returns)),
            "var_95": float(np.percentile(returns, 5)),
            "var_99": float(np.percentile(returns, 1)),
            "es_95": float(np.mean(returns[returns <= np.percentile(returns, 5)])),
            "prob_loss": float(np.mean(returns < 0)),
            "max_loss": float(np.min(returns)),
            "paths": paths.tolist()[:100],  # Store first 100 for visualization
        }
    
    def simulate_stress(self, portfolio: Portfolio, shock: dict[str, float]) -> dict[str, float]:
        """Apply specific shock scenario"""
        losses = {}
        
        for position in portfolio.positions:
            symbol = position.symbol
            shock_pct = shock.get(symbol, 0.0)
            loss = abs(position.market_value) * abs(shock_pct)
            losses[symbol] = loss
        
        total_loss = sum(losses.values())
        portfolio_pct = total_loss / portfolio.total_equity if portfolio.total_equity > 0 else 0
        
        return {
            "total_loss": total_loss,
            "portfolio_pct": portfolio_pct,
            "by_symbol": losses
        }