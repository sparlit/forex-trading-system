from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger

from src.data.models import Bar, Signal, Timeframe


class StrategyState(str, Enum):
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"

# Alias for backward compatibility
StrategyStatus = StrategyState


@dataclass(slots=True)
class StrategyPerformance:
    """Performance metrics for a strategy"""
    strategy_id: str = ""
    
    # Returns
    total_return: float = 0.0
    daily_return: float = 0.0
    annualized_return: float = 0.0
    
    # Risk
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    volatility: float = 0.0
    
    # Ratios
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Trade stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Advanced
    avg_trade_duration: timedelta = timedelta(0)
    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    tail_ratio: float = 0.0
    
    # Out-of-sample
    oos_sharpe: float = 0.0
    oos_max_drawdown: float = 0.0
    
    # Parameter stability
    param_stability_score: float = 1.0
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, datetime) else v) 
                for k, v in self.__dict__.items()}


@dataclass(slots=True)
class StrategyConfig:
    """Configuration for a strategy."""
    strategy_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    asset_classes: list[str] = field(default_factory=lambda: ["forex"])
    timeframes: list[Timeframe] = field(default_factory=lambda: [Timeframe.H1])
    symbols: list[str] = field(default_factory=list)  # Empty = all
    parameters: dict[str, Any] = field(default_factory=dict)
    ml_model_path: str | None = None
    is_paper: bool = True
    max_positions: int = 5
    max_concurrent_signals: int = 10
    signal_expiry_seconds: int = 300
    min_confidence: float = 0.6
    risk_per_trade: float = 0.02  # 2% risk per trade


class BaseStrategy(ABC):
    """Abstract base strategy class."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.state = StrategyState.INACTIVE
        self._positions: dict[str, Any] = {}
        self._signals_generated = 0
        self._last_signal_time: datetime | None = None
        self._error_count = 0
        self._start_time: datetime | None = None

    @property
    def strategy_id(self) -> str:
        return self.config.strategy_id

    @property
    def is_active(self) -> bool:
        return self.state == StrategyState.ACTIVE

    async def initialize(self) -> None:
        """Initialize strategy (load models, connect to data, etc.)."""
        self.state = StrategyState.INITIALIZING
        try:
            await self._initialize()
            self.state = StrategyState.ACTIVE
            self._start_time = datetime.now(UTC)
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            self.state = StrategyState.ERROR
            raise

    @abstractmethod
    async def _initialize(self) -> None:
        """Strategy-specific initialization."""

    async def on_bar(self, bar: Bar) -> list[Signal]:
        """Process new bar and generate signals."""
        if not self.is_active:
            return []

        try:
            signals = await self._generate_signals(bar)
            for signal in signals:
                signal.strategy_id = self.strategy_id
                self._signals_generated += 1
                self._last_signal_time = datetime.now(UTC)
            return signals
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            self._error_count += 1
            if self._error_count > 10:
                self.state = StrategyState.ERROR
            raise

    @abstractmethod
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate trading signals from bar data."""

    async def on_tick(self, tick) -> list[Signal]:
        """Process tick data (optional override)."""
        return []

    async def on_fill(self, fill) -> None:
        """Handle fill notification (optional override)."""

    async def on_position_update(self, position) -> None:
        """Handle position update (optional override)."""

    def get_state(self) -> dict[str, Any]:
        """Get strategy state for monitoring."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.config.name,
            "state": self.state.value,
            "signals_generated": self._signals_generated,
            "last_signal_time": self._last_signal_time.isoformat() if self._last_signal_time else None,
            "error_count": self._error_count,
            "uptime_seconds": (datetime.now(UTC) - self._start_time).total_seconds() if self._start_time else 0,
            "active_positions": len(self._positions),
            "config": {
                "asset_classes": self.config.asset_classes,
                "timeframes": [tf.value for tf in self.config.timeframes],
                "symbols": self.config.symbols,
                "parameters": self.config.parameters,
            }
        }

    async def pause(self) -> None:
        """Pause strategy."""
        self.state = StrategyState.PAUSED

    async def resume(self) -> None:
        """Resume strategy."""
        if self.state == StrategyState.PAUSED:
            self.state = StrategyState.ACTIVE

    async def stop(self) -> None:
        """Stop strategy."""
        self.state = StrategyState.STOPPING
        await self._cleanup()
        self.state = StrategyState.INACTIVE

    async def _cleanup(self) -> None:
        """Cleanup resources."""

    def update_parameters(self, parameters: dict[str, Any]) -> None:
        """Update strategy parameters at runtime."""
        self.config.parameters.update(parameters)


class StrategyRegistry:
    """Registry for managing strategies."""

    def __init__(self):
        self._strategies: dict[str, Strategy] = {}
        self._strategy_classes: dict[str, type] = {}

    def register_class(self, name: str, strategy_class: type) -> None:
        """Register a strategy class."""
        self._strategy_classes[name] = strategy_class

    def create_strategy(self, name: str, config: StrategyConfig) -> Strategy:
        """Create strategy instance from registered class."""
        if name not in self._strategy_classes:
            raise ValueError(f"Unknown strategy class: {name}")
        strategy = self._strategy_classes[name](config)
        self._strategies[config.strategy_id] = strategy
        return strategy

    def get(self, strategy_id: str) -> Strategy | None:
        """Get strategy by ID."""
        return self._strategies.get(strategy_id)

    def get_all(self) -> list[Strategy]:
        """Get all strategies."""
        return list(self._strategies.values())

    def get_active(self) -> list[Strategy]:
        """Get all active strategies."""
        return [s for s in self._strategies.values() if s.is_active]

    def remove(self, strategy_id: str) -> bool:
        """Remove strategy."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            return True
        return False

    async def initialize_all(self) -> None:
        """Initialize all strategies."""
        for strategy in self._strategies.values():
            try:
                await strategy.initialize()
            except Exception as e:
                print(f"Failed to initialize {strategy.strategy_id}: {e}")

    async def stop_all(self) -> None:
        """Stop all strategies."""
        for strategy in self._strategies.values():
            try:
                await strategy.stop()
            except Exception as e:
                print(f"Error stopping {strategy.strategy_id}: {e}")


# Global registry
strategy_registry = StrategyRegistry()

# Alias for backward compatibility
Strategy = BaseStrategy


class PerformanceTracker:
    """Tracks and calculates strategy performance metrics"""
    
    def __init__(self, timescaledb=None):
        self.timescaledb = timescaledb
        self.daily_snapshots: dict[str, list[dict]] = {}
    
    def record_daily_snapshot(self, strategy_id: str, equity: float, 
                              balance: float, unrealized_pnl: float,
                              daily_pnl: float, trades: list[dict]):
        """Record daily performance snapshot"""
        snapshot = {
            "date": datetime.now(UTC).date(),
            "equity": equity,
            "balance": balance,
            "unrealized_pnl": unrealized_pnl,
            "daily_pnl": daily_pnl,
            "trades": trades,
            "open_positions": len([t for t in trades if t.get("status") == "open"])
        }
        
        if strategy_id not in self.daily_snapshots:
            self.daily_snapshots[strategy_id] = []
        self.daily_snapshots[strategy_id].append(snapshot)
    
    def calculate_performance(self, strategy_id: str) -> StrategyPerformance:
        """Calculate performance metrics from snapshots"""
        snapshots = self.daily_snapshots.get(strategy_id, [])
        if len(snapshots) < 2:
            return StrategyPerformance(strategy_id=strategy_id)
        
        # Extract time series
        _dates = [s["date"] for s in snapshots]
        equity = np.array([s["equity"] for s in snapshots])
        daily_returns = np.diff(equity) / equity[:-1]
        
        perf = StrategyPerformance(strategy_id=strategy_id)
        
        # Returns
        perf.total_return = (equity[-1] - equity[0]) / equity[0] if equity[0] > 0 else 0
        perf.daily_return = daily_returns[-1] if len(daily_returns) > 0 else 0
        perf.annualized_return = np.mean(daily_returns) * 252 if len(daily_returns) > 0 else 0
        
        # Volatility
        perf.volatility = np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0
        
        # Sharpe
        if perf.volatility > 0:
            perf.sharpe_ratio = perf.annualized_return / perf.volatility
        
        # Drawdown
        equity_series = equity
        peak = np.maximum.accumulate(equity_series)
        drawdown = (peak - equity_series) / peak
        perf.max_drawdown = float(np.max(drawdown))
        perf.current_drawdown = float(drawdown[-1])
        
        # Calmar
        if perf.max_drawdown > 0:
            perf.calmar_ratio = perf.annualized_return / perf.max_drawdown
        
        # Sortino (downside deviation)
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0:
            downside_dev = np.std(negative_returns) * np.sqrt(252)
            if downside_dev > 0:
                perf.sortino_ratio = perf.annualized_return / downside_dev
        
        return perf
    
    def get_equity_curve(self, strategy_id: str) -> list[dict]:
        """Get equity curve data"""
        return self.daily_snapshots.get(strategy_id, [])


class StrategyManager:
    """High-level strategy management"""
    
    def __init__(self, registry: StrategyRegistry, risk_engine=None):
        self.registry = registry
        self.risk_engine = risk_engine
        self.performance_tracker = PerformanceTracker()
    
    async def start_all(self):
        """Start all active strategies"""
        for strategy in self.registry.get_active_strategies():
            await strategy.on_start()
    
    async def stop_all(self):
        """Stop all strategies"""
        for strategy in self.registry.get_all_strategies():
            await strategy.on_stop()
    
    async def process_market_data(self, market_data) -> dict[str, list]:
        """Process market data through all active strategies"""
        results = {}
        
        for strategy in self.registry.get_active_strategies():
            try:
                signals = await strategy.generate_signals(market_data)
                
                # Filter by risk engine
                if self.risk_engine:
                    filtered = []
                    for signal in signals:
                        # Would check risk limits here
                        filtered.append(signal)
                    signals = filtered
                
                if signals:
                    results[strategy.strategy_id] = signals
                    for signal in signals:
                        await strategy.on_signal_generated(signal)
                        
            except Exception as e:
                logger.error(f"Strategy {strategy.strategy_id} error: {e}")
        
        return results
    
    def get_all_performance(self) -> dict[str, StrategyPerformance]:
        return {sid: s.get_performance() for sid, s in self.registry.strategies.items()}


# Global registry
strategy_registry = StrategyRegistry()

# Alias for backward compatibility
Strategy = BaseStrategy