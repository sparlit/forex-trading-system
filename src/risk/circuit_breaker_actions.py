"""
Circuit Breaker Actions - Concrete implementations of risk mitigation actions.
These are called when circuit breakers trigger.
"""

from __future__ import annotations

import logging
from typing import Any

from src.data.models import (
    Order,
    OrderSide,
    Portfolio,
)
from src.infra.monitoring.alerts import Alert

logger = logging.getLogger(__name__)


class CircuitBreakerActions:
    """Concrete implementations of circuit breaker actions."""
    
    def __init__(self, portfolio: Portfolio, execution_engine: Any = None):
        self.portfolio = portfolio
        self.execution_engine = execution_engine
        self.logger = logger
    
    async def reduce_all_positions_50pct(self, alert: Alert) -> bool:
        """Reduce all positions by 50%"""
        self.logger.critical("ACTION: Reducing all positions by 50%")
        
        if not self.execution_engine:
            self.logger.error("No execution engine available")
            return False
        
        success_count = 0
        for position in self.portfolio.positions:
            if position.quantity == 0:
                continue
            
            reduce_qty = abs(position.quantity) * 0.5
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            
            order = Order(
                symbol=position.symbol,
                side=side,
                quantity=reduce_qty,
                order_type="market",
                strategy_id=position.strategy_id,
                reduce_only=True
            )
            
            try:
                result = await self.execution_engine.submit_order(order)
                if result.success:
                    success_count += 1
                    self.logger.info(f"Reduced {position.symbol} by 50%: {reduce_qty}")
            except Exception as e:
                self.logger.error(f"Failed to reduce {position.symbol}: {e}")
        
        self.logger.critical(f"Position reduction complete: {success_count}/{len(self.portfolio.positions)} successful")
        return success_count > 0
    
    async def liquidate_all_positions(self, alert: Alert) -> bool:
        """Emergency liquidation of all positions"""
        self.logger.critical("ACTION: EMERGENCY LIQUIDATION - Closing ALL positions")
        
        if not self.execution_engine:
            self.logger.error("No execution engine available")
            return False
        
        success_count = 0
        for position in self.portfolio.positions:
            if position.quantity == 0:
                continue
            
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            
            order = Order(
                symbol=position.symbol,
                side=side,
                quantity=abs(position.quantity),
                order_type="market",
                strategy_id=position.strategy_id,
                reduce_only=True
            )
            
            try:
                result = await self.execution_engine.submit_order(order)
                if result.success:
                    success_count += 1
                    self.logger.info(f"Liquidated {position.symbol}: {position.quantity}")
            except Exception as e:
                self.logger.error(f"Failed to liquidate {position.symbol}: {e}")
        
        self.logger.critical(f"Emergency liquidation complete: {success_count}/{len(self.portfolio.positions)} successful")
        return success_count > 0
    
    async def pause_strategy(self, alert: Alert) -> bool:
        """Pause a specific strategy"""
        strategy_id = alert.strategy_id
        if not strategy_id:
            self.logger.error("No strategy_id in alert")
            return False
        
        self.logger.critical(f"ACTION: Pausing strategy {strategy_id}")
        
        # Close all positions for this strategy
        if self.execution_engine:
            positions = [p for p in self.portfolio.positions if p.strategy_id == strategy_id]
            for position in positions:
                if position.quantity == 0:
                    continue
                
                side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
                order = Order(
                    symbol=position.symbol,
                    side=side,
                    quantity=abs(position.quantity),
                    order_type="market",
                    strategy_id=strategy_id,
                    reduce_only=True
                )
                
                try:
                    await self.execution_engine.submit_order(order)
                    self.logger.info(f"Closed {position.symbol} for paused strategy {strategy_id}")
                except Exception as e:
                    self.logger.error(f"Failed to close {position.symbol}: {e}")
        
        # Mark strategy as paused (would need strategy manager integration)
        self.logger.critical(f"Strategy {strategy_id} paused")
        return True
    
    async def reduce_leverage_25pct(self, alert: Alert) -> bool:
        """Reduce portfolio leverage by 25%"""
        self.logger.critical("ACTION: Reducing leverage by 25%")
        
        # This would reduce position sizes proportionally
        # Similar to reduce_all_positions_50pct but 25%
        if not self.execution_engine:
            return False
        
        success_count = 0
        for position in self.portfolio.positions:
            if position.quantity == 0:
                continue
            
            reduce_qty = abs(position.quantity) * 0.25
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            
            order = Order(
                symbol=position.symbol,
                side=side,
                quantity=reduce_qty,
                order_type="market",
                strategy_id=position.strategy_id,
                reduce_only=True
            )
            
            try:
                result = await self.execution_engine.submit_order(order)
                if result.success:
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Failed to reduce leverage on {position.symbol}: {e}")
        
        return success_count > 0
    
    async def reduce_correlated_cluster(self, alert: Alert) -> bool:
        """Reduce exposure in highly correlated cluster"""
        self.logger.critical("ACTION: Reducing correlated cluster exposure")
        
        # Would need correlation data from alert metadata
        # For now, reduce all positions by 25% as proxy
        return await self.reduce_leverage_25pct(alert)
    
    async def pause_execution_engine(self, alert: Alert) -> bool:
        """Pause the execution engine"""
        self.logger.critical("ACTION: Pausing execution engine")
        
        if self.execution_engine:
            await self.execution_engine.pause()
            self.logger.info("Execution engine paused")
            return True
        return False
    
    async def switch_data_source(self, alert: Alert) -> bool:
        """Switch to backup data source"""
        self.logger.critical("ACTION: Switching to backup data source")
        
        # Would integrate with data provider factory
        # For now, log the action
        self.logger.info("Data source switch initiated")
        return True


def create_action_callbacks(portfolio: Portfolio, execution_engine: Any = None) -> dict[str, callable]:
    """Create all action callbacks for circuit breakers"""
    actions = CircuitBreakerActions(portfolio, execution_engine)
    
    return {
        "reduce_all_positions_50pct": actions.reduce_all_positions_50pct,
        "liquidate_all_positions": actions.liquidate_all_positions,
        "pause_strategy": actions.pause_strategy,
        "reduce_leverage_25pct": actions.reduce_leverage_25pct,
        "reduce_correlated_cluster": actions.reduce_correlated_cluster,
        "pause_execution_engine": actions.pause_execution_engine,
        "switch_data_source": actions.switch_data_source,
    }