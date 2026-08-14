"""
Risk Service - Runs risk engine continuously as a background service.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.data.models import Portfolio
from src.data.storage.timescale import TimescaleDB
from src.risk.circuit_breaker_actions import create_action_callbacks
from src.risk.metrics import RiskMetricsCalculator
from src.risk.risk_engine import Alert, RiskEngine

logger = logging.getLogger(__name__)


class RiskService:
    """Background service that runs risk checks continuously"""
    
    def __init__(self, 
                 portfolio: Portfolio,
                 timescaledb: TimescaleDB,
                 execution_engine: Any = None):
        self.portfolio = portfolio
        self.timescaledb = timescaledb
        self.execution_engine = execution_engine
        
        # Initialize risk engine
        self.risk_engine = RiskEngine("config/risk_limits.yaml")
        self.metrics_calculator = RiskMetricsCalculator()
        
        # Register callbacks
        self.risk_engine.register_alert_callback(self._handle_alert)
        
        # Register circuit breaker actions
        action_callbacks = create_action_callbacks(portfolio, execution_engine)
        for action, callback in action_callbacks.items():
            self.risk_engine.register_action_callback(action, callback)
        
        # State
        self.running = False
        self.check_interval = 30  # seconds
        self.last_metrics: Any = None
        self.logger = logger
    
    async def start(self):
        """Start the risk service"""
        self.running = True
        self.logger.info("RiskService started")
        
        # Start background tasks
        asyncio.create_task(self._risk_check_loop())
        asyncio.create_task(self._metrics_loop())
        asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        """Stop the risk service"""
        self.running = False
        self.logger.info("RiskService stopped")
    
    async def _risk_check_loop(self):
        """Main risk check loop"""
        while self.running:
            try:
                await self._run_risk_checks()
            except Exception as e:
                self.logger.error(f"Risk check loop error: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def _metrics_loop(self):
        """Calculate and store risk metrics periodically"""
        while self.running:
            try:
                await self._calculate_and_store_metrics()
            except Exception as e:
                self.logger.error(f"Metrics calculation error: {e}")
            
            await asyncio.sleep(300)  # Every 5 minutes
    
    async def _heartbeat_loop(self):
        """Heartbeat for monitoring"""
        while self.running:
            self.logger.debug("RiskService heartbeat - OK")
            await asyncio.sleep(60)
    
    async def _run_risk_checks(self):
        """Run all risk checks"""
        # Get returns history
        returns_history = await self._get_returns_history()
        
        # Get price history for correlation
        price_history = await self._get_price_history()
        
        # Run risk checks
        alerts, triggered_actions = await self.risk_engine.run_risk_checks(
            portfolio=self.portfolio,
            returns_history=returns_history,
            price_history=price_history
        )
        
        if alerts:
            self.logger.info(f"Risk check generated {len(alerts)} alerts")
        
        if triggered_actions:
            self.logger.warning(f"Circuit breakers triggered: {triggered_actions}")
    
    async def _calculate_and_store_metrics(self):
        """Calculate and store risk metrics"""
        returns_history = await self._get_returns_history()
        price_history = await self._get_price_history()
        
        if len(returns_history) < 30:
            return
        
        # Calculate metrics
        metrics = self.metrics_calculator.calculate_all(
            portfolio=self.portfolio,
            returns_history=returns_history,
            price_history=price_history,
            positions=self.portfolio.positions
        )
        
        self.last_metrics = metrics
        
        # Store in TimescaleDB
        await self._store_metrics(metrics)
        
        self.logger.debug(f"Risk metrics calculated: VaR95={metrics.var_95_1d:.4f}, DD={metrics.current_drawdown:.4f}")
    
    async def _get_returns_history(self) -> np.ndarray:
        """Get portfolio returns history from TimescaleDB"""
        try:
            async with self.timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT return_pct 
                    FROM risk.portfolio_returns 
                    WHERE timestamp > NOW() - INTERVAL '252 days'
                    ORDER BY timestamp ASC
                """)
                return np.array([float(r['return_pct']) for r in rows]) if rows else np.array([])
        except Exception as e:
            self.logger.warning(f"Failed to get returns history: {e}")
            return np.array([])
    
    async def _get_price_history(self) -> dict[str, np.ndarray]:
        """Get price history for correlation calculation"""
        try:
            # Get symbols from current positions
            symbols = list({p.symbol for p in self.portfolio.positions})
            if not symbols:
                return {}
            
            async with self.timescaledb.acquire() as conn:
                # Get last 60 days of 1h bars for each symbol
                placeholders = ','.join([f'${i+1}' for i in range(len(symbols))])
                rows = await conn.fetch(f"""
                    SELECT symbol, close, time
                    FROM market_data.bars
                    WHERE symbol IN ({placeholders})
                      AND timeframe = '1h'
                      AND time > NOW() - INTERVAL '60 days'
                      AND is_complete = TRUE
                    ORDER BY symbol, time
                """, *symbols)
                
                # Group by symbol
                result = {}
                for row in rows:
                    sym = row['symbol']
                    if sym not in result:
                        result[sym] = []
                    result[sym].append(float(row['close']))
                
                # Convert to numpy arrays
                return {k: np.array(v) for k, v in result.items() if len(v) > 10}
        except Exception as e:
            self.logger.warning(f"Failed to get price history: {e}")
            return {}
    
    async def _store_metrics(self, metrics: Any):
        """Store risk metrics in TimescaleDB"""
        try:
            async with self.timescaledb.acquire() as conn:
                await conn.execute("""
                    INSERT INTO risk.risk_metrics (
                        timestamp, var_95_1d, var_99_1d, var_95_10d, var_99_10d,
                        es_95_1d, es_99_1d, portfolio_volatility, portfolio_beta,
                        max_drawdown, current_drawdown, gross_leverage, net_leverage,
                        max_position_pct, herfindahl_index, effective_positions,
                        avg_correlation, max_correlation, skewness, kurtosis
                    ) VALUES (
                        NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19
                    )
                """,
                    metrics.var_95_1d, metrics.var_99_1d, metrics.var_95_10d, metrics.var_99_10d,
                    metrics.es_95_1d, metrics.es_99_1d, metrics.portfolio_volatility, metrics.portfolio_beta,
                    metrics.max_drawdown, metrics.current_drawdown, metrics.gross_leverage, metrics.net_leverage,
                    metrics.max_position_pct, metrics.herfindahl_index, metrics.effective_positions,
                    metrics.avg_correlation, metrics.max_correlation, metrics.skewness, metrics.kurtosis
                )
        except Exception as e:
            self.logger.error(f"Failed to store metrics: {e}")
    
    async def _handle_alert(self, alert: Alert):
        """Handle alert from risk engine"""
        # Log based on severity
        if alert.severity.value == "critical":
            self.logger.critical(f"RISK ALERT: {alert.message}")
        elif alert.severity.value == "warning":
            self.logger.warning(f"RISK ALERT: {alert.message}")
        else:
            self.logger.info(f"RISK ALERT: {alert.message}")
        
        # Store alert
        try:
            async with self.timescaledb.acquire() as conn:
                await conn.execute("""
                    INSERT INTO risk.alerts (
                        timestamp, alert_type, severity, message,
                        strategy_id, symbol, current_value, limit_value, metadata
                    ) VALUES (
                        NOW(), $1, $2, $3, $4, $5, $6, $7, $8
                    )
                """,
                    alert.type.value, alert.severity.value, alert.message,
                    alert.strategy_id, alert.symbol,
                    alert.current_value, alert.limit_value,
                    str(alert.metadata) if alert.metadata else None
                )
        except Exception as e:
            self.logger.error(f"Failed to store alert: {e}")
    
    def get_status(self) -> dict[str, Any]:
        """Get current risk service status"""
        return {
            "running": self.running,
            "last_metrics": self.last_metrics.__dict__ if self.last_metrics else None,
            "recovery_status": self.risk_engine.get_recovery_status(),
            "active_alerts_1h": len([
                a for a in self.risk_engine.alert_history
                if a.timestamp > datetime.now(UTC) - timedelta(hours=1)
            ]),
            "circuit_breakers": {
                name: {
                    "triggered": state.triggered,
                    "trigger_count": state.trigger_count,
                    "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None
                }
                for name, state in self.risk_engine.circuit_states.items()
            }
        }


# For type hints
from datetime import timedelta

import numpy as np
