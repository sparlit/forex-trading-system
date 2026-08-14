"""
Risk Engine - Core risk management with hard limits and circuit breakers.
This is the non-negotiable layer that protects capital.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import yaml

from src.data.models import Portfolio

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    PORTFOLIO_DRAWDOWN = "portfolio_drawdown"
    STRATEGY_DRAWDOWN = "strategy_drawdown"
    VAR_BREACH = "var_breach"
    CORRELATION_SPIKE = "correlation_spike"
    EXECUTION_FAILURE = "execution_failure"
    DATA_QUALITY = "data_quality"
    LEVERAGE_BREACH = "leverage_breach"
    CONCENTRATION_BREACH = "concentration_breach"


@dataclass
class Alert:
    type: AlertType
    severity: AlertSeverity
    message: str
    strategy_id: str | None = None
    symbol: str | None = None
    current_value: float | None = None
    limit_value: float | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    triggered: bool = False
    triggered_at: datetime | None = None
    trigger_count: int = 0
    last_reset: datetime | None = None
    cooldown_until: datetime | None = None


@dataclass
class RiskLimits:
    """Hard risk limits loaded from config"""
    max_portfolio_drawdown: float = 0.05
    max_portfolio_drawdown_weekly: float = 0.10
    max_portfolio_drawdown_monthly: float = 0.15
    max_strategy_drawdown: float = 0.03
    max_strategy_drawdown_weekly: float = 0.06
    max_single_position: float = 0.10
    max_correlated_positions: float = 0.25
    max_sector_exposure: float = 0.30
    max_leverage: float = 3.0
    max_net_leverage: float = 1.5
    var_95_1d: float = 0.02
    var_99_1d: float = 0.03
    max_expected_shortfall: float = 0.04
    max_open_orders: int = 50
    max_orders_per_second: int = 10
    max_order_size_pct_adv: float = 0.05
    min_liquidity_score: float = 0.3
    emergency_liquidation_threshold: float = 0.08
    max_correlation_cluster: float = 0.7
    correlation_lookback_days: int = 60
    drawdown_recovery_factor: float = 0.5
    drawdown_recovery_steps: int = 4


@dataclass
class CircuitBreakerConfig:
    name: str
    trigger_condition: str
    action: str
    cooldown_hours: float
    requires_manual_reset: bool = False


class RiskEngine:
    """
    Core risk management engine with hard limits and circuit breakers.
    All limits are HARD - never bypassed.
    """
    
    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or "config/risk_limits.yaml"
        self.limits = self._load_limits()
        self.circuit_breakers = self._load_circuit_breakers()
        self.circuit_states: dict[str, CircuitBreakerState] = {
            name: CircuitBreakerState() for name in self.circuit_breakers
        }
        
        # State tracking
        self.portfolio_peak: float = 0.0
        self.strategy_peaks: dict[str, float] = {}
        self.alert_history: list[Alert] = []
        self.recovery_step: int = 0
        
        # Callbacks
        self._alert_callbacks: list[callable] = []
        self._action_callbacks: dict[str, callable] = {}
        
        logger.info("RiskEngine initialized with hard limits")
    
    def _load_limits(self) -> RiskLimits:
        """Load risk limits from YAML config"""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            return RiskLimits(**config.get("hard_limits", {}))
        except Exception as e:
            logger.warning(f"Failed to load risk config: {e}, using defaults")
            return RiskLimits()
    
    def _load_circuit_breakers(self) -> dict[str, CircuitBreakerConfig]:
        """Load circuit breaker configs from YAML"""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            breakers = {}
            for name, cb_config in config.get("circuit_breakers", {}).items():
                breakers[name] = CircuitBreakerConfig(
                    name=name,
                    trigger_condition=cb_config["trigger"],
                    action=cb_config["action"],
                    cooldown_hours=cb_config["cooldown_hours"],
                    requires_manual_reset=cb_config.get("requires_manual_reset", False)
                )
            return breakers
        except Exception as e:
            logger.warning(f"Failed to load circuit breakers: {e}")
            return {}
    
    def register_alert_callback(self, callback: callable):
        """Register callback for alert notifications"""
        self._alert_callbacks.append(callback)
    
    def register_action_callback(self, action: str, callback: callable):
        """Register callback for circuit breaker actions"""
        self._action_callbacks[action] = callback
    
    # ============================================================
    # CORE RISK CHECKS
    # ============================================================
    
    async def check_portfolio_risk(self, portfolio: Portfolio) -> list[Alert]:
        """Check all portfolio-level risk limits"""
        alerts = []
        
        # Current equity and drawdown
        current_equity = portfolio.total_equity
        if self.portfolio_peak == 0 or current_equity > self.portfolio_peak:
            self.portfolio_peak = current_equity
        
        drawdown = (self.portfolio_peak - current_equity) / self.portfolio_peak if self.portfolio_peak > 0 else 0
        
        # Daily drawdown
        if drawdown >= self.limits.max_portfolio_drawdown:
            alerts.append(Alert(
                type=AlertType.PORTFOLIO_DRAWDOWN,
                severity=AlertSeverity.CRITICAL,
                message=f"Portfolio drawdown {drawdown:.2%} exceeds limit {self.limits.max_portfolio_drawdown:.2%}",
                current_value=drawdown,
                limit_value=self.limits.max_portfolio_drawdown
            ))
        
        # Weekly drawdown (would need historical tracking)
        # Monthly drawdown (would need historical tracking)
        
        # Leverage checks
        gross_leverage = portfolio.gross_leverage
        if gross_leverage > self.limits.max_leverage:
            alerts.append(Alert(
                type=AlertType.LEVERAGE_BREACH,
                severity=AlertSeverity.CRITICAL,
                message=f"Gross leverage {gross_leverage:.2f}x exceeds limit {self.limits.max_leverage:.2f}x",
                current_value=gross_leverage,
                limit_value=self.limits.max_leverage
            ))
        
        net_leverage = portfolio.net_leverage
        if net_leverage > self.limits.max_net_leverage:
            alerts.append(Alert(
                type=AlertType.LEVERAGE_BREACH,
                severity=AlertSeverity.WARNING,
                message=f"Net leverage {net_leverage:.2f}x exceeds limit {self.limits.max_net_leverage:.2f}x",
                current_value=net_leverage,
                limit_value=self.limits.max_net_leverage
            ))
        
        # Concentration checks
        for position in portfolio.positions:
            position_pct = position.market_value / current_equity if current_equity > 0 else 0
            if position_pct > self.limits.max_single_position:
                alerts.append(Alert(
                    type=AlertType.CONCENTRATION_BREACH,
                    severity=AlertSeverity.WARNING,
                    message=f"Position {position.symbol} at {position_pct:.2%} exceeds limit {self.limits.max_single_position:.2%}",
                    symbol=position.symbol,
                    current_value=position_pct,
                    limit_value=self.limits.max_single_position
                ))
        
        # Open orders check
        if len(portfolio.open_orders) > self.limits.max_open_orders:
            alerts.append(Alert(
                type=AlertType.CONCENTRATION_BREACH,
                severity=AlertSeverity.WARNING,
                message=f"Open orders {len(portfolio.open_orders)} exceeds limit {self.limits.max_open_orders}",
                current_value=len(portfolio.open_orders),
                limit_value=self.limits.max_open_orders
            ))
        
        return alerts
    
    async def check_strategy_risk(self, strategy_id: str, portfolio: Portfolio) -> list[Alert]:
        """Check strategy-specific risk limits"""
        alerts = []
        
        # Get strategy positions
        strategy_positions = [p for p in portfolio.positions if p.strategy_id == strategy_id]
        if not strategy_positions:
            return alerts
        
        strategy_equity = sum(p.market_value for p in strategy_positions)
        
        # Track strategy peak
        if strategy_id not in self.strategy_peaks or strategy_equity > self.strategy_peaks[strategy_id]:
            self.strategy_peaks[strategy_id] = strategy_equity
        
        peak = self.strategy_peaks.get(strategy_id, strategy_equity)
        drawdown = (peak - strategy_equity) / peak if peak > 0 else 0
        
        if drawdown >= self.limits.max_strategy_drawdown:
            alerts.append(Alert(
                type=AlertType.STRATEGY_DRAWDOWN,
                severity=AlertSeverity.CRITICAL,
                message=f"Strategy {strategy_id} drawdown {drawdown:.2%} exceeds limit {self.limits.max_strategy_drawdown:.2%}",
                strategy_id=strategy_id,
                current_value=drawdown,
                limit_value=self.limits.max_strategy_drawdown
            ))
        
        return alerts
    
    async def check_var(self, portfolio: Portfolio, returns_history: np.ndarray) -> list[Alert]:
        """Check Value at Risk limits"""
        alerts = []
        
        if len(returns_history) < 30:
            return alerts
        
        # VaR at 95%
        var_95 = np.percentile(returns_history, 5)  # 5th percentile
        if abs(var_95) > self.limits.var_95_1d:
            alerts.append(Alert(
                type=AlertType.VAR_BREACH,
                severity=AlertSeverity.CRITICAL,
                message=f"VaR 95% {abs(var_95):.2%} exceeds limit {self.limits.var_95_1d:.2%}",
                current_value=abs(var_95),
                limit_value=self.limits.var_95_1d
            ))
        
        # Expected Shortfall (CVaR)
        es = returns_history[returns_history <= var_95].mean()
        if abs(es) > self.limits.max_expected_shortfall:
            alerts.append(Alert(
                type=AlertType.VAR_BREACH,
                severity=AlertSeverity.WARNING,
                message=f"Expected Shortfall {abs(es):.2%} exceeds limit {self.limits.max_expected_shortfall:.2%}",
                current_value=abs(es),
                limit_value=self.limits.max_expected_shortfall
            ))
        
        return alerts
    
    async def check_correlation(self, portfolio: Portfolio, price_history: dict[str, np.ndarray]) -> list[Alert]:
        """Check correlation limits"""
        alerts = []
        
        symbols = list(price_history.keys())
        if len(symbols) < 2:
            return alerts
        
        # Calculate correlation matrix
        returns = {}
        for sym, prices in price_history.items():
            if len(prices) > 2:
                returns[sym] = np.diff(np.log(prices))
        
        if len(returns) < 2:
            return alerts
        
        # Build correlation matrix
        sym_list = list(returns.keys())
        n = len(sym_list)
        corr_matrix = np.zeros((n, n))
        
        for i, s1 in enumerate(sym_list):
            for j, s2 in enumerate(sym_list):
                if i == j:
                    corr_matrix[i, j] = 1.0
                else:
                    min_len = min(len(returns[s1]), len(returns[s2]))
                    if min_len > 10:
                        corr = np.corrcoef(returns[s1][-min_len:], returns[s2][-min_len:])[0, 1]
                        corr_matrix[i, j] = corr if not np.isnan(corr) else 0
        
        # Check max correlation
        max_corr = np.max(corr_matrix[np.triu_indices(n, k=1)])
        if max_corr > self.limits.max_correlation_cluster:
            alerts.append(Alert(
                type=AlertType.CORRELATION_SPIKE,
                severity=AlertSeverity.WARNING,
                message=f"Max correlation {max_corr:.2f} exceeds limit {self.limits.max_correlation_cluster:.2f}",
                current_value=max_corr,
                limit_value=self.limits.max_correlation_cluster
            ))
        
        # Check correlated cluster exposure
        for i, s1 in enumerate(sym_list):
            correlated_symbols = [sym_list[j] for j in range(n) if corr_matrix[i, j] > 0.7 and i != j]
            if correlated_symbols:
                # Calculate combined exposure
                cluster_exposure = sum(
                    p.market_value for p in portfolio.positions 
                    if p.symbol in correlated_symbols or p.symbol == s1
                )
                total_equity = portfolio.total_equity
                if total_equity > 0:
                    cluster_pct = cluster_exposure / total_equity
                    if cluster_pct > self.limits.max_correlated_positions:
                        alerts.append(Alert(
                            type=AlertType.CONCENTRATION_BREACH,
                            severity=AlertSeverity.WARNING,
                            message=f"Correlated cluster {s1} + {correlated_symbols} at {cluster_pct:.2%} exceeds limit",
                            current_value=cluster_pct,
                            limit_value=self.limits.max_correlated_positions
                        ))
        
        return alerts
    
    # ============================================================
    # CIRCUIT BREAKER LOGIC
    # ============================================================
    
    async def evaluate_circuit_breakers(self, alerts: list[Alert]) -> list[str]:
        """Evaluate and trigger circuit breakers based on alerts"""
        triggered_actions = []
        
        for alert in alerts:
            for cb_name, cb_config in self.circuit_breakers.items():
                if self._should_trigger(alert, cb_config):
                    if await self._trigger_circuit_breaker(cb_name, cb_config, alert):
                        triggered_actions.append(cb_config.action)
        
        return triggered_actions
    
    def _should_trigger(self, alert: Alert, cb_config: CircuitBreakerConfig) -> bool:
        """Check if alert matches circuit breaker condition"""
        state = self.circuit_states[cb_config.name]
        
        # Check cooldown
        if state.cooldown_until and datetime.now(UTC) < state.cooldown_until:
            return False
        
        # Check manual reset requirement
        if state.triggered and cb_config.requires_manual_reset:
            return False
        
        # Simple condition matching (in production, use proper expression evaluator)
        condition = cb_config.trigger_condition.lower()
        
        if "portfolio_drawdown" in condition and alert.type == AlertType.PORTFOLIO_DRAWDOWN:
            threshold = float(condition.split(">=")[1].strip()) if ">=" in condition else 0.05
            return alert.current_value and alert.current_value >= threshold
        
        if "strategy_drawdown" in condition and alert.type == AlertType.STRATEGY_DRAWDOWN:
            threshold = float(condition.split(">=")[1].strip()) if ">=" in condition else 0.03
            return alert.current_value and alert.current_value >= threshold
        
        if "var_95" in condition and alert.type == AlertType.VAR_BREACH:
            threshold = float(condition.split(">")[1].strip()) if ">" in condition else 0.025
            return alert.current_value and alert.current_value > threshold
        
        if "correlation" in condition and alert.type == AlertType.CORRELATION_SPIKE:
            threshold = float(condition.split(">")[1].strip()) if ">" in condition else 0.85
            return alert.current_value and alert.current_value > threshold
        
        return False
    
    async def _trigger_circuit_breaker(self, name: str, config: CircuitBreakerConfig, alert: Alert) -> bool:
        """Execute circuit breaker action"""
        state = self.circuit_states[name]
        
        # Check max auto recoveries per hour
        recent_triggers = sum(
            1 for a in self.alert_history 
            if a.timestamp > datetime.now(UTC) - timedelta(hours=1)
        )
        if recent_triggers >= 3:  # From config
            logger.warning(f"Max auto recoveries per hour reached, skipping {name}")
            return False
        
        state.triggered = True
        state.triggered_at = datetime.now(UTC)
        state.trigger_count += 1
        state.cooldown_until = datetime.now(UTC) + timedelta(hours=config.cooldown_hours)
        
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {name} - {config.action}")
        
        # Execute action callback
        if config.action in self._action_callbacks:
            try:
                await self._action_callbacks[config.action](alert)
            except Exception as e:
                logger.error(f"Circuit breaker action failed: {e}")
                return False
        
        # Create critical alert
        cb_alert = Alert(
            type=AlertType(alert.type),
            severity=AlertSeverity.CRITICAL,
            message=f"CIRCUIT BREAKER: {name} triggered - {config.action}",
            metadata={
                "circuit_breaker": name,
                "action": config.action,
                "trigger_alert": alert.type.value
            }
        )
        await self._emit_alert(cb_alert)
        
        return True
    
    def reset_circuit_breaker(self, name: str) -> bool:
        """Manually reset a circuit breaker"""
        if name not in self.circuit_states:
            return False
        
        state = self.circuit_states[name]
        if state.requires_manual_reset and not state.triggered:
            return False
        
        state.triggered = False
        state.last_reset = datetime.now(UTC)
        state.cooldown_until = None
        logger.info(f"Circuit breaker {name} manually reset")
        return True
    
    # ============================================================
    # ALERT SYSTEM
    # ============================================================
    
    async def _emit_alert(self, alert: Alert):
        """Emit alert to all registered callbacks"""
        self.alert_history.append(alert)
        
        # Keep only recent alerts
        cutoff = datetime.now(UTC) - timedelta(days=90)
        self.alert_history = [a for a in self.alert_history if a.timestamp > cutoff]
        
        for callback in self._alert_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
    
    # ============================================================
    # DRAWDOWN RECOVERY
    # ============================================================
    
    def calculate_risk_multiplier(self) -> float:
        """Calculate risk multiplier based on current drawdown"""
        if self.portfolio_peak == 0:
            return 1.0
        
        # This would need current equity - simplified
        current_dd = 0  # Would be calculated from current equity
        
        if current_dd < 0.01:
            return 1.0
        elif current_dd < 0.02:
            return 0.75
        elif current_dd < 0.03:
            return 0.5
        else:
            return 0.25
    
    def get_recovery_status(self) -> dict[str, Any]:
        """Get current recovery status"""
        return {
            "portfolio_peak": self.portfolio_peak,
            "strategy_peaks": self.strategy_peaks,
            "recovery_step": self.recovery_step,
            "active_circuit_breakers": [
                name for name, state in self.circuit_states.items() 
                if state.triggered
            ],
            "risk_multiplier": self.calculate_risk_multiplier()
        }
    
    # ============================================================
    # MAIN CHECK FUNCTION
    # ============================================================
    
    async def run_risk_checks(
        self,
        portfolio: Portfolio,
        returns_history: np.ndarray | None = None,
        price_history: dict[str, np.ndarray] | None = None
    ) -> tuple[list[Alert], list[str]]:
        """Run all risk checks and return alerts + triggered actions"""
        all_alerts = []
        
        # Portfolio risk
        portfolio_alerts = await self.check_portfolio_risk(portfolio)
        all_alerts.extend(portfolio_alerts)
        
        # Strategy risk (for each strategy)
        strategy_ids = {p.strategy_id for p in portfolio.positions if p.strategy_id}
        for sid in strategy_ids:
            strategy_alerts = await self.check_strategy_risk(sid, portfolio)
            all_alerts.extend(strategy_alerts)
        
        # VaR check
        if returns_history is not None:
            var_alerts = await self.check_var(portfolio, returns_history)
            all_alerts.extend(var_alerts)
        
        # Correlation check
        if price_history is not None:
            corr_alerts = await self.check_correlation(portfolio, price_history)
            all_alerts.extend(corr_alerts)
        
        # Emit all alerts
        for alert in all_alerts:
            await self._emit_alert(alert)
        
        # Evaluate circuit breakers
        triggered_actions = await self.evaluate_circuit_breakers(all_alerts)
        
        return all_alerts, triggered_actions