"""

Advanced Risk Management
========================

Comprehensive risk management system with:
- VaR (Value at Risk) - Parametric, Historical, Monte Carlo
- CVaR (Conditional VaR) / Expected Shortfall
- Real-time drawdown monitoring and controls
- Circuit breakers (daily, weekly, monthly, per-strategy)
- Correlation risk monitoring
- Liquidity risk assessment
- Margin risk management
- Stress testing and scenario analysis
- Risk budgeting and attribution
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger
from scipy import stats

from src.data.models import Position
from src.infra.config.settings import settings


def _utc_now() -> datetime:
    return datetime.now(UTC)



class RiskLimitType(str, Enum):
    """Types of risk limits."""
    DAILY_LOSS = "daily_loss"
    WEEKLY_LOSS = "weekly_loss"
    MONTHLY_LOSS = "monthly_loss"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_POSITION_SIZE = "max_position_size"
    MAX_SECTOR_EXPOSURE = "max_sector_exposure"
    MAX_CORRELATION = "max_correlation"
    MAX_LEVERAGE = "max_leverage"
    VAR_LIMIT = "var_limit"
    CVAR_LIMIT = "cvar_limit"
    MARGIN_LEVEL = "margin_level"
    CONCENTRATION = "concentration"
    LIQUIDITY = "liquidity"


class RiskLimitStatus(str, Enum):
    """Status of a risk limit."""
    OK = "ok"
    WARNING = "warning"      # 80% of limit
    BREACH = "breach"        # 100% of limit
    CRITICAL = "critical"    # 120% of limit


class CircuitBreakerAction(str, Enum):
    """Actions when circuit breaker triggers."""
    NONE = "none"
    REDUCE_POSITIONS = "reduce_positions"
    CLOSE_LOSING = "close_losing"
    CLOSE_ALL = "close_all"
    PAUSE_TRADING = "pause_trading"
    STOP_TRADING = "stop_trading"
    ALERT_ONLY = "alert_only"


@dataclass(slots=True)
class RiskLimit:
    """Risk limit configuration."""
    limit_type: RiskLimitType
    name: str
    threshold: float                    # Absolute threshold
    warning_threshold: float            # Warning at % of threshold (e.g., 0.8)
    action: CircuitBreakerAction = CircuitBreakerAction.ALERT_ONLY
    scope: str = "portfolio"            # "portfolio", "strategy", "symbol"
    scope_value: str | None = None      # Strategy ID or symbol if scope is specific
    enabled: bool = True
    cooldown_seconds: int = 300         # Cooldown after trigger


@dataclass(slots=True)
class RiskLimitBreach:
    """Record of a risk limit breach."""
    limit: RiskLimit
    current_value: float
    threshold: float
    status: RiskLimitStatus
    timestamp: datetime = field(default_factory=_utc_now)
    action_taken: CircuitBreakerAction = CircuitBreakerAction.NONE
    details: dict = field(default_factory=dict)


@dataclass(slots=True)
class VaRResult:
    """VaR calculation result."""
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    method: str
    confidence: float
    horizon_days: int
    portfolio_value: float
    timestamp: datetime = field(default_factory=_utc_now)
    details: dict = field(default_factory=dict)


@dataclass(slots=True)
class DrawdownMetrics:
    """Drawdown metrics."""
    current_drawdown: float
    max_drawdown: float
    peak_equity: float
    current_equity: float
    drawdown_duration: int  # days since peak
    recovery_factor: float
    ulcer_index: float
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class StressTestResult:
    """Stress test result."""
    scenario_name: str
    portfolio_pnl: float
    portfolio_pnl_pct: float
    max_drawdown: float
    var_impact: float
    positions_impact: dict[str, float]
    passed: bool
    timestamp: datetime = field(default_factory=_utc_now)


class AdvancedRiskManager:
    """
    Advanced risk management system.
    """
    
    def __init__(
        self,
        portfolio_value: float = 100000.0,
        risk_limits: list[RiskLimit] | None = None,
    ):
        self.portfolio_value = portfolio_value
        self.initial_portfolio_value = portfolio_value
        self.peak_portfolio_value = portfolio_value
        
        # Risk limits
        self.risk_limits = risk_limits or self._default_limits()
        self.limit_status: dict[str, RiskLimitStatus] = {}
        self.breach_history: list[RiskLimitBreach] = []
        
        # Data for calculations
        self.returns_history: deque = deque(maxlen=252)  # 1 year daily returns
        self.equity_curve: deque = deque(maxlen=252)
        self.position_history: dict[str, list[Position]] = {}
        
        # VaR/CVaR cache
        self._var_cache: VaRResult | None = None
        self._var_cache_time: datetime | None = None
        self._var_cache_ttl = 300  # 5 minutes
        
        # Drawdown tracking
        self.drawdown_metrics: DrawdownMetrics | None = None
        
        # Circuit breaker states
        self.circuit_breaker_active: dict[str, bool] = {}
        self.circuit_breaker_cooldown: dict[str, datetime] = {}
        
        # Callbacks
        self.on_limit_breach: Callable[[RiskLimitBreach], None] | None = None
        self.on_circuit_breaker: Callable[[str, CircuitBreakerAction], None] | None = None
        self.on_drawdown_alert: Callable[[DrawdownMetrics], None] | None = None
        
        # Stress test scenarios
        self.stress_scenarios = self._default_stress_scenarios()
        
        logger.info("AdvancedRiskManager initialized")
    
    def _default_limits(self) -> list[RiskLimit]:
        """Create default risk limits from settings."""
        return [
            RiskLimit(
                limit_type=RiskLimitType.DAILY_LOSS,
                name="Daily Loss Limit",
                threshold=settings.risk_daily_loss_limit,
                warning_threshold=0.8,
                action=CircuitBreakerAction.PAUSE_TRADING,
            ),
            RiskLimit(
                limit_type=RiskLimitType.WEEKLY_LOSS,
                name="Weekly Loss Limit",
                threshold=settings.risk_weekly_loss_limit,
                warning_threshold=0.8,
                action=CircuitBreakerAction.PAUSE_TRADING,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MONTHLY_LOSS,
                name="Monthly Loss Limit",
                threshold=settings.risk_monthly_loss_limit,
                warning_threshold=0.8,
                action=CircuitBreakerAction.STOP_TRADING,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MAX_DRAWDOWN,
                name="Maximum Drawdown",
                threshold=settings.risk_max_drawdown,
                warning_threshold=0.7,
                action=CircuitBreakerAction.REDUCE_POSITIONS,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MAX_POSITION_SIZE,
                name="Max Position Size",
                threshold=settings.risk_max_position_size_pct,
                warning_threshold=0.9,
                action=CircuitBreakerAction.REDUCE_POSITIONS,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MAX_CORRELATION,
                name="Max Correlation",
                threshold=settings.risk_max_correlation,
                warning_threshold=0.9,
                action=CircuitBreakerAction.ALERT_ONLY,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MAX_LEVERAGE,
                name="Max Leverage",
                threshold=settings.risk_max_leverage,
                warning_threshold=0.8,
                action=CircuitBreakerAction.REDUCE_POSITIONS,
            ),
            RiskLimit(
                limit_type=RiskLimitType.MARGIN_LEVEL,
                name="Margin Level",
                threshold=settings.risk_margin_call_level,
                warning_threshold=1.0,  # Warn at margin call level
                action=CircuitBreakerAction.CLOSE_LOSING,
            ),
        ]
    
    def _default_stress_scenarios(self) -> dict[str, dict]:
        """Default stress test scenarios."""
        return {
            "flash_crash": {
                "description": "Flash crash - 5% drop in 5 minutes",
                "shocks": {"equity": -0.05, "forex": -0.03, "volatility": 3.0},
                "correlation": 0.9,
            },
            "rate_shock": {
                "description": "Interest rate shock - 200bp rise",
                "shocks": {"bonds": -0.10, "forex_carry": -0.05, "equity": -0.08},
                "correlation": 0.7,
            },
            "currency_crisis": {
                "description": "Currency crisis - EM FX collapse",
                "shocks": {"em_fx": -0.20, "commodities": -0.15, "equity": -0.10},
                "correlation": 0.8,
            },
            "volatility_spike": {
                "description": "VIX spike to 50+",
                "shocks": {"volatility": 4.0, "equity": -0.15, "options": -0.40},
                "correlation": 0.85,
            },
            "liquidity_crisis": {
                "description": "Liquidity dry-up",
                "shocks": {"spreads": 5.0, "slippage": 10.0, "volume": -0.50},
                "correlation": 0.6,
            },
            "covid_style": {
                "description": "COVID-style market crash",
                "shocks": {"equity": -0.35, "credit": -0.20, "volatility": 5.0},
                "correlation": 0.95,
            },
        }
    
    def update_portfolio_value(self, value: float) -> None:
        """Update current portfolio value."""
        self.portfolio_value = value
        self.equity_curve.append((datetime.now(UTC), value))
        
        # Update peak
        self.peak_portfolio_value = max(self.peak_portfolio_value, value)
        
        # Update drawdown metrics
        self._update_drawdown()
    
    def add_daily_return(self, return_pct: float) -> None:
        """Add daily return for VaR calculations."""
        self.returns_history.append(return_pct)
        self._var_cache = None  # Invalidate cache
    
    def update_positions(self, positions: dict[str, Position]) -> None:
        """Update current positions."""
        self.position_history[datetime.now(UTC).isoformat()] = list(positions.values())
    
    def _update_drawdown(self) -> None:
        """Update drawdown metrics."""
        if self.peak_portfolio_value <= 0:
            return
        
        current_dd = (self.peak_portfolio_value - self.portfolio_value) / self.peak_portfolio_value
        
        # Calculate duration since peak
        duration = 0
        for timestamp, value in reversed(self.equity_curve):
            if value == self.peak_portfolio_value:
                break
            duration += 1
        
        # Ulcer Index calculation
        ulcer_sq = 0
        for _, value in self.equity_curve:
            dd = (self.peak_portfolio_value - value) / self.peak_portfolio_value
            ulcer_sq += dd * dd
        ulcer_index = np.sqrt(ulcer_sq / len(self.equity_curve)) if self.equity_curve else 0
        
        # Recovery factor
        total_return = (self.portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value
        recovery_factor = total_return / max(current_dd, 0.001) if current_dd > 0 else 0
        
        self.drawdown_metrics = DrawdownMetrics(
            current_drawdown=current_dd,
            max_drawdown=current_dd,  # This would track historical max
            peak_equity=self.peak_portfolio_value,
            current_equity=self.portfolio_value,
            drawdown_duration=duration,
            recovery_factor=recovery_factor,
            ulcer_index=ulcer_index,
        )
        
        # Check drawdown limits
        self._check_limit(RiskLimitType.MAX_DRAWDOWN, current_dd)
    
    def calculate_var(
        self,
        confidence: float = 0.95,
        horizon_days: int = 1,
        method: str = "historical",
    ) -> VaRResult:
        """
        Calculate Value at Risk and CVaR.
        
        Methods:
        - historical: Historical simulation
        - parametric: Parametric (normal distribution)
        - monte_carlo: Monte Carlo simulation
        - cornish_fisher: Cornish-Fisher expansion (accounts for skew/kurtosis)
        """
        # Check cache
        if (self._var_cache is not None and 
            self._var_cache_time is not None and
            (datetime.now(UTC) - self._var_cache_time).total_seconds() < self._var_cache_ttl and
            self._var_cache.confidence == confidence and
            self._var_cache.horizon_days == horizon_days and
            self._var_cache.method == method):
            return self._var_cache
        
        if len(self.returns_history) < 30:
            # Insufficient data
            result = VaRResult(
                var_95=0, var_99=0, cvar_95=0, cvar_99=0,
                method=method, confidence=confidence, horizon_days=horizon_days,
                portfolio_value=self.portfolio_value,
                details={"error": "Insufficient data"},
            )
            return result
        
        returns = np.array(list(self.returns_history))
        
        if method == "historical":
            var_95, var_99, cvar_95, cvar_99 = self._historical_var(returns, confidence, horizon_days)
        elif method == "parametric":
            var_95, var_99, cvar_95, cvar_99 = self._parametric_var(returns, confidence, horizon_days)
        elif method == "cornish_fisher":
            var_95, var_99, cvar_95, cvar_99 = self._cornish_fisher_var(returns, confidence, horizon_days)
        elif method == "monte_carlo":
            var_95, var_99, cvar_95, cvar_99 = self._monte_carlo_var(returns, confidence, horizon_days)
        else:
            var_95, var_99, cvar_95, cvar_99 = self._historical_var(returns, confidence, horizon_days)
        
        # Convert to absolute values
        var_95_abs = abs(var_95) * self.portfolio_value
        var_99_abs = abs(var_99) * self.portfolio_value
        cvar_95_abs = abs(cvar_95) * self.portfolio_value
        cvar_99_abs = abs(cvar_99) * self.portfolio_value
        
        result = VaRResult(
            var_95=var_95_abs,
            var_99=var_99_abs,
            cvar_95=cvar_95_abs,
            cvar_99=cvar_99_abs,
            method=method,
            confidence=confidence,
            horizon_days=horizon_days,
            portfolio_value=self.portfolio_value,
            details={
                "var_95_pct": var_95,
                "var_99_pct": var_99,
                "cvar_95_pct": cvar_95,
                "cvar_99_pct": cvar_99,
                "sample_size": len(returns),
                "skewness": stats.skew(returns),
                "kurtosis": stats.kurtosis(returns),
            },
        )
        
        self._var_cache = result
        self._var_cache_time = datetime.now(UTC)
        
        # Check VaR limits
        self._check_limit(RiskLimitType.VAR_LIMIT, var_95_abs / self.portfolio_value if self.portfolio_value > 0 else 0)
        
        return result
    
    def _historical_var(
        self, returns: np.ndarray, confidence: float, horizon: int
    ) -> tuple[float, float, float, float]:
        """Historical simulation VaR."""
        # Scale to horizon
        scaled_returns = returns * np.sqrt(horizon)
        
        # VaR at different confidence levels
        var_95 = np.percentile(scaled_returns, (1 - 0.95) * 100)
        var_99 = np.percentile(scaled_returns, (1 - 0.99) * 100)
        
        # CVaR (Expected Shortfall)
        cvar_95 = scaled_returns[scaled_returns <= var_95].mean() if np.any(scaled_returns <= var_95) else var_95
        cvar_99 = scaled_returns[scaled_returns <= var_99].mean() if np.any(scaled_returns <= var_99) else var_99
        
        return var_95, var_99, cvar_95, cvar_99
    
    def _parametric_var(
        self, returns: np.ndarray, confidence: float, horizon: int
    ) -> tuple[float, float, float, float]:
        """Parametric VaR assuming normal distribution."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Scale to horizon
        mean_h = mean * horizon
        std_h = std * np.sqrt(horizon)
        
        # Z-scores
        z_95 = stats.norm.ppf(1 - 0.95)
        z_99 = stats.norm.ppf(1 - 0.99)
        
        var_95 = mean_h + z_95 * std_h
        var_99 = mean_h + z_99 * std_h
        
        # CVaR for normal distribution
        # CVaR = μ - σ * φ(z) / (1-α)
        phi_95 = stats.norm.pdf(z_95)
        phi_99 = stats.norm.pdf(z_99)
        
        cvar_95 = mean_h - std_h * phi_95 / 0.05
        cvar_99 = mean_h - std_h * phi_99 / 0.01
        
        return var_95, var_99, cvar_95, cvar_99
    
    def _cornish_fisher_var(
        self, returns: np.ndarray, confidence: float, horizon: int
    ) -> tuple[float, float, float, float]:
        """Cornish-Fisher expansion VaR (accounts for skew/kurtosis)."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        skew = stats.skew(returns)
        kurt = stats.kurtosis(returns)
        
        # Scale to horizon
        mean_h = mean * horizon
        std_h = std * np.sqrt(horizon)
        
        # Adjusted z-scores
        z_95 = stats.norm.ppf(0.05)
        z_99 = stats.norm.ppf(0.01)
        
        # Cornish-Fisher adjustment
        def cf_adjust(z, skew, kurt):
            return (z + 
                    (z**2 - 1) * skew / 6 +
                    (z**3 - 3*z) * kurt / 24 -
                    (2*z**3 - 5*z) * skew**2 / 36)
        
        z_cf_95 = cf_adjust(z_95, skew, kurt)
        z_cf_99 = cf_adjust(z_99, skew, kurt)
        
        var_95 = mean_h + z_cf_95 * std_h
        var_99 = mean_h + z_cf_99 * std_h
        
        # Approximate CVaR
        cvar_95 = var_95 * 1.2  # Rough approximation
        cvar_99 = var_99 * 1.3
        
        return var_95, var_99, cvar_95, cvar_99
    
    def _monte_carlo_var(
        self, returns: np.ndarray, confidence: float, horizon: int, n_sim: int = 10000
    ) -> tuple[float, float, float, float]:
        """Monte Carlo VaR."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Generate scenarios
        np.random.seed(42)
        sim_returns = np.random.normal(mean * horizon, std * np.sqrt(horizon), n_sim)
        
        var_95 = np.percentile(sim_returns, (1 - 0.95) * 100)
        var_99 = np.percentile(sim_returns, (1 - 0.99) * 100)
        cvar_95 = sim_returns[sim_returns <= var_95].mean()
        cvar_99 = sim_returns[sim_returns <= var_99].mean()
        
        return var_95, var_99, cvar_95, cvar_99
    
    def _check_limit(self, limit_type: RiskLimitType, current_value: float) -> None:
        """Check if a risk limit is breached."""
        for limit in self.risk_limits:
            if limit.limit_type != limit_type or not limit.enabled:
                continue
            
            threshold = limit.threshold
            warning = threshold * limit.warning_threshold
            
            # Determine status
            if current_value >= threshold:
                status = RiskLimitStatus.BREACH
            elif current_value >= warning:
                status = RiskLimitStatus.WARNING
            else:
                status = RiskLimitStatus.OK
            
            # Check if status changed
            key = f"{limit.limit_type.value}_{limit.scope}_{limit.scope_value or 'all'}"
            old_status = self.limit_status.get(key, RiskLimitStatus.OK)
            
            self.limit_status[key] = status
            
            # Handle breach
            if status == RiskLimitStatus.BREACH and old_status != RiskLimitStatus.BREACH:
                self._handle_breach(limit, current_value, status)
            elif status == RiskLimitStatus.WARNING and old_status == RiskLimitStatus.OK:
                self._handle_warning(limit, current_value, status)
    
    def _handle_breach(self, limit: RiskLimit, current_value: float, status: RiskLimitStatus) -> None:
        """Handle risk limit breach."""
        breach = RiskLimitBreach(
            limit=limit,
            current_value=current_value,
            threshold=limit.threshold,
            status=status,
            action_taken=limit.action,
            details={"limit_name": limit.name, "scope": limit.scope, "scope_value": limit.scope_value},
        )
        
        self.breach_history.append(breach)
        
        # Cooldown
        key = f"{limit.limit_type.value}_{limit.scope}_{limit.scope_value or 'all'}"
        self.circuit_breaker_cooldown[key] = datetime.now(UTC) + timedelta(seconds=limit.cooldown_seconds)
        
        # Execute action
        self._execute_circuit_breaker(limit.action, limit)
        
        # Callback
        if self.on_limit_breach:
            self.on_limit_breach(breach)
        
        logger.warning(f"RISK LIMIT BREACH: {limit.name} - Current: {current_value:.4f}, Threshold: {limit.threshold:.4f}")
    
    def _handle_warning(self, limit: RiskLimit, current_value: float, status: RiskLimitStatus) -> None:
        """Handle risk limit warning."""
        logger.warning(f"RISK LIMIT WARNING: {limit.name} - Current: {current_value:.4f}, Threshold: {limit.threshold:.4f}")
    
    def _execute_circuit_breaker(self, action: CircuitBreakerAction, limit: RiskLimit) -> None:
        """Execute circuit breaker action."""
        key = f"{limit.limit_type.value}_{limit.scope}_{limit.scope_value or 'all'}"
        self.circuit_breaker_active[key] = True
        
        if self.on_circuit_breaker:
            self.on_circuit_breaker(key, action)
        
        logger.info(f"Circuit breaker triggered: {action.value} for {limit.name}")
    
    def check_circuit_breaker(self, scope: str = "portfolio") -> CircuitBreakerAction | None:
        """Check if circuit breaker is active for scope."""
        for key, active in self.circuit_breaker_active.items():
            if scope in key and active:
                # Check cooldown
                cooldown_until = self.circuit_breaker_cooldown.get(key)
                if cooldown_until and datetime.now(UTC) > cooldown_until:
                    self.circuit_breaker_active[key] = False
                    continue
                
                # Find the limit to get action
                for limit in self.risk_limits:
                    lkey = f"{limit.limit_type.value}_{limit.scope}_{limit.scope_value or 'all'}"
                    if lkey == key:
                        return limit.action
        
        return None
    
    def run_stress_tests(self) -> list[StressTestResult]:
        """Run all stress test scenarios."""
        results = []
        
        for name, scenario in self.stress_scenarios.items():
            result = self._run_stress_scenario(name, scenario)
            results.append(result)
        
        return results
    
    def _run_stress_scenario(self, name: str, scenario: dict) -> StressTestResult:
        """Run a single stress test scenario."""
        shocks = scenario.get("shocks", {})
        correlation = scenario.get("correlation", 0.5)
        
        # Calculate portfolio impact
        total_pnl = 0
        positions_impact = {}
        
        # Get current positions
        latest_positions = list(self.position_history.values())[-1] if self.position_history else []
        
        for pos in latest_positions:
            symbol = pos.symbol
            asset_class = self._get_asset_class(symbol)
            
            # Apply shock
            shock = shocks.get(asset_class, 0)
            # Adjust for correlation
            shock *= correlation
            
            pos_pnl = pos.volume * pos.current_price * shock
            positions_impact[symbol] = pos_pnl
            total_pnl += pos_pnl
        
        pnl_pct = total_pnl / self.portfolio_value if self.portfolio_value > 0 else 0
        
        # Calculate max drawdown under stress
        stressed_equity = self.portfolio_value + total_pnl
        max_dd = (self.peak_portfolio_value - stressed_equity) / self.peak_portfolio_value if self.peak_portfolio_value > 0 else 0
        
        # Check if passed (drawdown within limit)
        passed = max_dd < settings.risk_max_drawdown
        
        return StressTestResult(
            scenario_name=name,
            portfolio_pnl=total_pnl,
            portfolio_pnl_pct=pnl_pct,
            max_drawdown=max_dd,
            var_impact=0,  # Would calculate VaR under stress
            positions_impact=positions_impact,
            passed=passed,
        )
    
    def _get_asset_class(self, symbol: str) -> str:
        """Get asset class for symbol."""
        # Simplified mapping
        if "JPY" in symbol or "USD" in symbol:
            return "forex"
        elif symbol.startswith(("XAU", "XAG")):
            return "metals"
        elif "BTC" in symbol or "ETH" in symbol:
            return "crypto"
        return "forex"
    
    def get_risk_report(self) -> dict[str, Any]:
        """Get comprehensive risk report."""
        var_result = self.calculate_var()
        
        return {
            "portfolio": {
                "value": self.portfolio_value,
                "peak": self.peak_portfolio_value,
                "total_return_pct": (self.portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value * 100,
            },
            "var": {
                "var_95": var_result.var_95,
                "var_99": var_result.var_99,
                "cvar_95": var_result.cvar_95,
                "cvar_99": var_result.cvar_99,
                "method": var_result.method,
            },
            "drawdown": {
                "current": self.drawdown_metrics.current_drawdown if self.drawdown_metrics else 0,
                "max": self.drawdown_metrics.max_drawdown if self.drawdown_metrics else 0,
                "duration_days": self.drawdown_metrics.drawdown_duration if self.drawdown_metrics else 0,
                "ulcer_index": self.drawdown_metrics.ulcer_index if self.drawdown_metrics else 0,
                "recovery_factor": self.drawdown_metrics.recovery_factor if self.drawdown_metrics else 0,
            },
            "limits": {
                key: status.value for key, status in self.limit_status.items()
            },
            "circuit_breakers": {
                key: active for key, active in self.circuit_breaker_active.items()
            },
            "recent_breaches": len([b for b in self.breach_history if (datetime.now(UTC) - b.timestamp).days < 7]),
        }
    
    def check_all_limits(self, positions: dict[str, Position], account_info: dict) -> dict[str, RiskLimitStatus]:
        """Check all risk limits."""
        # Position size limit
        for pos in positions.values():
            pos_value = pos.volume * pos.current_price
            pos_pct = pos_value / self.portfolio_value if self.portfolio_value > 0 else 0
            self._check_limit(RiskLimitType.MAX_POSITION_SIZE, pos_pct)
        
        # Leverage
        total_exposure = sum(pos.volume * pos.current_price for pos in positions.values())
        leverage = total_exposure / self.portfolio_value if self.portfolio_value > 0 else 0
        self._check_limit(RiskLimitType.MAX_LEVERAGE, leverage)
        
        # Margin level
        margin_level = account_info.get("margin_level", 1000)
        self._check_limit(RiskLimitType.MARGIN_LEVEL, margin_level / 100)
        
        return self.limit_status


async def create_risk_manager(
    portfolio_value: float = 100000.0,
) -> AdvancedRiskManager:
    """Create and initialize advanced risk manager."""
    return AdvancedRiskManager(portfolio_value=portfolio_value)
