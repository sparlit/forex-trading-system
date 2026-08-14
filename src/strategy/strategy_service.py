"""
Strategy Service - Runs strategies, generates signals, manages lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from src.data.models import AssetClass, MarketData, Timeframe
from src.data.storage.timescale import TimescaleDB
from src.risk.risk_engine import RiskEngine
from src.strategy.base import (
    StrategyConfig,
    StrategyManager,
    StrategyRegistry,
    StrategyStatus,
)
from src.strategy.strategies import STRATEGY_FACTORIES

logger = logging.getLogger(__name__)


class StrategyService:
    """Background service that runs strategies and generates signals"""
    
    def __init__(self, 
                 market_data: MarketData,
                 timescaledb: TimescaleDB,
                 risk_engine: RiskEngine):
        self.market_data = market_data
        self.timescaledb = timescaledb
        self.risk_engine = risk_engine
        
        # Initialize registry and manager
        self.registry = StrategyRegistry()
        self._register_factories()
        
        self.manager = StrategyManager(self.registry, risk_engine)
        
        # State
        self.running = False
        self.signal_interval = 60  # seconds
        self.performance_interval = 300  # 5 minutes
        self.logger = logger
        
        # Callbacks
        self._signal_callbacks: list[Callable] = []
    
    def _register_factories(self):
        """Register all strategy factories"""
        for name, factory in STRATEGY_FACTORIES.items():
            self.registry.register_strategy_class(name, factory)
    
    def register_signal_callback(self, callback: Callable):
        """Register callback for signal processing"""
        self._signal_callbacks.append(callback)
    
    def create_strategy(self, config: StrategyConfig):
        """Create and register a strategy"""
        return self.registry.create_strategy(config)
    
    def create_default_strategies(self):
        """Create default strategy instances"""
        # Trend Following
        trend_config = StrategyConfig(
            strategy_id="trend_following_fx",
            name="Trend Following FX",
            description="Multi-timeframe EMA crossover with ATR stops",
            strategy_type="trend_following",
            asset_classes=[AssetClass.FOREX],
            timeframes=[Timeframe.M15, Timeframe.H1, Timeframe.H4],
            parameters={
                "strategy_type": "trend_following",
                "symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
                "trend": {
                    "fast_ema": 12,
                    "slow_ema": 26,
                    "signal_ema": 9,
                    "atr_period": 14,
                    "atr_multiplier": 2.0,
                    "trend_filter_period": 200,
                    "min_trend_strength": 0.02
                }
            },
            capital_allocation=0.4,
            max_leverage=2.0,
            max_positions=5,
            is_paper=True,
            status=StrategyStatus.PAPER_TRADING
        )
        
        # Mean Reversion
        mr_config = StrategyConfig(
            strategy_id="mean_reversion_fx",
            name="Mean Reversion FX",
            description="Bollinger Band Z-score mean reversion",
            strategy_type="mean_reversion",
            asset_classes=[AssetClass.FOREX],
            timeframes=[Timeframe.H1],
            parameters={
                "strategy_type": "mean_reversion",
                "symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
                "mean_reversion": {
                    "lookback_period": 20,
                    "entry_zscore": 2.0,
                    "exit_zscore": 0.5,
                    "stop_zscore": 3.0,
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "cooldown_bars": 10
                }
            },
            capital_allocation=0.3,
            max_leverage=1.5,
            max_positions=4,
            is_paper=True,
            status=StrategyStatus.PAPER_TRADING
        )
        
        # Carry Trade
        carry_config = StrategyConfig(
            strategy_id="carry_trade_fx",
            name="Carry Trade FX",
            description="Interest rate differential carry trades",
            strategy_type="carry_trade",
            asset_classes=[AssetClass.FOREX],
            timeframes=[Timeframe.D1],
            parameters={
                "strategy_type": "carry_trade",
                "carry": {
                    "min_carry_bps": 50.0,
                    "max_leverage": 3.0,
                    "vol_target": 0.10,
                    "max_drawdown_pct": 0.05
                }
            },
            capital_allocation=0.3,
            max_leverage=3.0,
            max_positions=8,
            is_paper=True,
            status=StrategyStatus.PAPER_TRADING
        )
        
        self.registry.create_strategy(trend_config)
        self.registry.create_strategy(mr_config)
        self.registry.create_strategy(carry_config)
        
        logger.info("Created default strategies")
    
    async def start(self):
        """Start the strategy service"""
        self.running = True
        
        # Create default strategies if none exist
        if not self.registry.strategies:
            self.create_default_strategies()
        
        # Start manager
        await self.manager.start_all()
        
        # Start background tasks
        asyncio.create_task(self._signal_generation_loop())
        asyncio.create_task(self._performance_loop())
        asyncio.create_task(self._health_check_loop())
        
        self.logger.info("StrategyService started")
    
    async def stop(self):
        """Stop the strategy service"""
        self.running = False
        await self.manager.stop_all()
        self.logger.info("StrategyService stopped")
    
    async def _signal_generation_loop(self):
        """Main signal generation loop"""
        while self.running:
            try:
                await self._generate_signals()
            except Exception as e:
                self.logger.error(f"Signal generation error: {e}")
            
            await asyncio.sleep(self.signal_interval)
    
    async def _generate_signals(self):
        """Generate signals from all active strategies"""
        # Get current market data
        market_data = self._get_current_market_data()
        
        # Process through all strategies
        results = await self.manager.process_market_data(market_data)
        
        # Process signals
        for signals in results.values():
            for signal in signals:
                # Risk check
                if not await self._check_signal_risk(signal):
                    self.logger.warning(f"Signal {signal.signal_id} rejected by risk engine")
                    continue
                
                # Call callbacks
                for callback in self._signal_callbacks:
                    try:
                        await callback(signal)
                    except Exception as e:
                        self.logger.error(f"Signal callback error: {e}")
        
        if results:
            total = sum(len(s) for s in results.values())
            self.logger.debug(f"Generated {total} signals from {len(results)} strategies")
    
    def _get_current_market_data(self) -> MarketData:
        """Get current market data for signal generation"""
        # This would fetch from the market data service
        # For now, return a placeholder
        return self.market_data
    
    async def _check_signal_risk(self, signal) -> bool:
        """Check signal against risk limits"""
        # This would integrate with risk engine
        # For now, basic checks
        if signal.stop_loss == 0:
            return False
        return not signal.entry_price <= 0
    
    async def _performance_loop(self):
        """Calculate and store performance metrics"""
        while self.running:
            try:
                await self._calculate_performance()
            except Exception as e:
                self.logger.error(f"Performance calculation error: {e}")
            
            await asyncio.sleep(self.performance_interval)
    
    async def _calculate_performance(self):
        """Calculate performance for all strategies"""
        for strategy in self.registry.get_all_strategies():
            try:
                perf = strategy.get_performance()
                
                # Store in TimescaleDB
                await self._store_performance(strategy.strategy_id, perf)
                
            except Exception as e:
                self.logger.error(f"Performance calc error for {strategy.strategy_id}: {e}")
    
    async def _store_performance(self, strategy_id: str, perf):
        """Store performance metrics in TimescaleDB"""
        try:
            async with self.timescaledb.acquire() as conn:
                await conn.execute("""
                    INSERT INTO analytics.performance_metrics (
                        date, strategy_id, broker, total_return, daily_return,
                        sharpe_ratio, sortino_ratio, calmar_ratio,
                        max_drawdown, current_drawdown, win_rate, profit_factor,
                        expectancy, total_trades, winning_trades, losing_trades,
                        avg_win, avg_loss, largest_win, largest_loss
                    ) VALUES (
                        CURRENT_DATE, $1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16, $17, $18
                    )
                    ON CONFLICT (date, strategy_id, broker) DO UPDATE SET
                        total_return = EXCLUDED.total_return,
                        daily_return = EXCLUDED.daily_return,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        sortino_ratio = EXCLUDED.sortino_ratio,
                        calmar_ratio = EXCLUDED.calmar_ratio,
                        max_drawdown = EXCLUDED.max_drawdown,
                        current_drawdown = EXCLUDED.current_drawdown,
                        win_rate = EXCLUDED.win_rate,
                        profit_factor = EXCLUDED.profit_factor,
                        expectancy = EXCLUDED.expectancy,
                        total_trades = EXCLUDED.total_trades,
                        winning_trades = EXCLUDED.winning_trades,
                        losing_trades = EXCLUDED.losing_trades,
                        avg_win = EXCLUDED.avg_win,
                        avg_loss = EXCLUDED.avg_loss,
                        largest_win = EXCLUDED.largest_win,
                        largest_loss = EXCLUDED.largest_loss
                """,
                    perf.strategy_id, "paper",
                    perf.total_return, perf.daily_return,
                    perf.sharpe_ratio, perf.sortino_ratio, perf.calmar_ratio,
                    perf.max_drawdown, perf.current_drawdown,
                    perf.win_rate, perf.profit_factor, perf.expectancy,
                    perf.total_trades, perf.winning_trades, perf.losing_trades,
                    perf.avg_win, perf.avg_loss, perf.largest_win, perf.largest_loss
                )
        except Exception as e:
            self.logger.error(f"Failed to store performance: {e}")
    
    async def _health_check_loop(self):
        """Health check loop"""
        while self.running:
            try:
                await self._health_check()
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
            
            await asyncio.sleep(60)
    
    async def _health_check(self):
        """Check strategy health."""
        for strategy in self.registry.get_all_strategies():
            # Check if strategy is generating signals
            if strategy.status == StrategyStatus.ACTIVE and not strategy.active_signals:
                self.logger.warning(
                    f"Strategy {strategy.strategy_id} is active but has no signals"
                )

            # Check performance
            perf = strategy.get_performance()
            if perf.max_drawdown > 0.10:
                self.logger.warning(f"Strategy {strategy.strategy_id} drawdown > 10%")
    
    def get_status(self) -> dict[str, Any]:
        """Get service status"""
        return {
            "running": self.running,
            "strategies": {
                sid: {
                    "name": s.name,
                    "status": s.status.value,
                    "capital_allocation": s.config.capital_allocation,
                    "active_signals": len(s.active_signals),
                    "performance": s.get_performance().to_dict()
                }
                for sid, s in self.registry.strategies.items()
            },
            "total_strategies": len(self.registry.strategies),
            "active_strategies": len(self.registry.get_active_strategies())
        }
    
    # For type hints
    from collections.abc import Callable