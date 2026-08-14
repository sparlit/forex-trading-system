"""
Elite Autonomous Quantum Trading System - Strategy Selector
Automatic strategy selection based on market conditions, regime, and performance.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Types of trading strategies."""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MACD_MOMENTUM = "macd_momentum"
    DONCHIAN_SQUEEZE = "donchian_squeeze"
    CARRY_ROLLOVER = "carry_rollover"
    COST_AVERAGING_GRID = "cost_averaging_grid"
    QUANTUM_SCALPING = "quantum_scalping"
    QUANTUM_DAY_TRADING = "quantum_day_trading"
    QUANTUM_SWING = "quantum_swing"
    QUANTUM_POSITION = "quantum_position"
    ADAPTIVE_ENSEMBLE = "adaptive_ensemble"
    REGIME_AWARE = "regime_aware"
    MULTI_TIMEFRAME = "multi_timeframe"
    CROSS_ASSET_ARBITRAGE = "cross_asset_arbitrage"


class TradingStyle(Enum):
    """Trading styles."""
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"


@dataclass
class StrategyPerformance:
    """Performance metrics for a strategy."""
    strategy_type: StrategyType
    symbol: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def score(self) -> float:
        """Calculate composite performance score."""
        if self.total_trades < 10:
            return 0.5  # Neutral for insufficient data

        # Weighted score
        score = (
            self.win_rate * 0.3 +
            min(self.sharpe_ratio / 3.0, 1.0) * 0.3 +
            min(self.profit_factor / 3.0, 1.0) * 0.2 +
            max(0, 1 - self.max_drawdown / 0.2) * 0.2
        )
        return max(0.0, min(1.0, score))


@dataclass
class StrategyConfig:
    """Configuration for a strategy."""
    strategy_type: StrategyType
    symbols: list[str]
    timeframes: list[str]
    parameters: dict[str, Any]
    enabled: bool = True
    min_confidence: float = 0.6
    max_position_size: float = 0.1
    risk_per_trade: float = 0.02
    max_holding_period: timedelta = field(default_factory=lambda: timedelta(hours=4))
    trading_style: TradingStyle = TradingStyle.DAY_TRADING
    regime_filter: list[str] = field(default_factory=list)  # Regimes where strategy works best
    session_filter: list[str] = field(default_factory=list)  # Sessions where strategy works best


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.performance = StrategyPerformance(strategy_type=config.strategy_type, symbol="")
        self.active_signals: dict[str, Any] = {}
        self.last_signal_time: dict[str, datetime] = {}

    @abstractmethod
    async def generate_signal(self, symbol: str, market_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
        """Generate trading signal for a symbol."""

    @abstractmethod
    def get_required_indicators(self) -> list[str]:
        """Return list of required technical indicators."""

    def update_performance(self, trade_result: dict[str, Any]) -> None:
        """Update performance metrics with trade result."""
        pnl = trade_result.get('pnl', 0)
        self.performance.total_trades += 1
        self.performance.total_pnl += pnl

        if pnl > 0:
            self.performance.winning_trades += 1
            self.performance.avg_win = (
                (self.performance.avg_win * (self.performance.winning_trades - 1) + pnl) /
                self.performance.winning_trades
            )
        else:
            self.performance.losing_trades += 1
            self.performance.avg_loss = (
                (self.performance.avg_loss * (self.performance.losing_trades - 1) + abs(pnl)) /
                self.performance.losing_trades
            )

        self.performance.win_rate = (
            self.performance.winning_trades / self.performance.total_trades
            if self.performance.total_trades > 0 else 0
        )

        if self.performance.avg_loss > 0:
            self.performance.profit_factor = self.performance.avg_win / self.performance.avg_loss

        self.performance.last_updated = datetime.now(UTC)
        logger.info(f"Updated performance for {self.config.strategy_type.value}: score={self.performance.score:.3f}")


class StrategySelector:
    """
    Automatic strategy selector that chooses the best strategy
    based on market regime, performance, and market conditions.
    """

    def __init__(self):
        self.strategies: dict[StrategyType, BaseStrategy] = {}
        self.strategy_configs: dict[StrategyType, StrategyConfig] = {}
        self.performance_history: dict[StrategyType, list[StrategyPerformance]] = defaultdict(list)
        self.current_best: dict[str, StrategyType] = {}  # symbol -> best strategy
        self.selection_interval = timedelta(minutes=15)
        self.min_performance_threshold = 0.55
        self.exploration_rate = 0.1  # 10% exploration for discovering new strategies

        # Regime-strategy mapping
        self.regime_strategy_map = {
            "trending": [StrategyType.TREND_FOLLOWING, StrategyType.MACD_MOMENTUM, StrategyType.QUANTUM_SWING, StrategyType.QUANTUM_POSITION],
            "ranging": [StrategyType.MEAN_REVERSION, StrategyType.DONCHIAN_SQUEEZE, StrategyType.COST_AVERAGING_GRID, StrategyType.QUANTUM_SCALPING, StrategyType.QUANTUM_DAY_TRADING],
            "volatile": [StrategyType.DONCHIAN_SQUEEZE, StrategyType.MACD_MOMENTUM, StrategyType.QUANTUM_SCALPING],
            "low_volatility": [StrategyType.MEAN_REVERSION, StrategyType.COST_AVERAGING_GRID, StrategyType.CARRY_ROLLOVER],
            "high_volatility": [StrategyType.DONCHIAN_SQUEEZE, StrategyType.MACD_MOMENTUM, StrategyType.QUANTUM_SCALPING],
            "unknown": [StrategyType.ADAPTIVE_ENSEMBLE, StrategyType.REGIME_AWARE],
        }

        # Style-strategy map
        self.style_strategy_map = {
            TradingStyle.SCALPING: [StrategyType.QUANTUM_SCALPING, StrategyType.DONCHIAN_SQUEEZE, StrategyType.MACD_MOMENTUM],
            TradingStyle.DAY_TRADING: [StrategyType.QUANTUM_DAY_TRADING, StrategyType.TREND_FOLLOWING, StrategyType.MEAN_REVERSION, StrategyType.MACD_MOMENTUM],
            TradingStyle.SWING_TRADING: [StrategyType.QUANTUM_SWING, StrategyType.TREND_FOLLOWING, StrategyType.REGIME_AWARE],
            TradingStyle.POSITION_TRADING: [StrategyType.QUANTUM_POSITION, StrategyType.CARRY_ROLLOVER, StrategyType.COST_AVERAGING_GRID],
        }

        logger.info("Strategy Selector initialized")

    async def initialize(self) -> None:
        """Initialize all strategies."""
        await self._register_default_strategies()
        await self._load_performance_history()
        logger.info("Strategy Selector initialized")

    async def _register_default_strategies(self) -> None:
        """Register default strategy configurations."""
        default_configs = {
            StrategyType.TREND_FOLLOWING: StrategyConfig(
                strategy_type=StrategyType.TREND_FOLLOWING,
                symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
                timeframes=["15m", "1h", "4h"],
                parameters={"ema_fast": 20, "ema_slow": 50, "rsi_period": 14},
                trading_style=TradingStyle.DAY_TRADING,
                regime_filter=["trending"],
            ),
            StrategyType.MEAN_REVERSION: StrategyConfig(
                strategy_type=StrategyType.MEAN_REVERSION,
                symbols=["EURUSD", "GBPUSD", "XAUUSD"],
                timeframes=["5m", "15m", "1h"],
                parameters={"bb_period": 20, "bb_std": 2, "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
                trading_style=TradingStyle.SCALPING,
                regime_filter=["ranging", "low_volatility"],
            ),
            StrategyType.MACD_MOMENTUM: StrategyConfig(
                strategy_type=StrategyType.MACD_MOMENTUM,
                symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
                timeframes=["15m", "1h", "4h"],
                parameters={"macd_fast": 12, "macd_slow": 26, "macd_signal": 9},
                trading_style=TradingStyle.DAY_TRADING,
                regime_filter=["trending", "volatile", "high_volatility"],
            ),
            StrategyType.DONCHIAN_SQUEEZE: StrategyConfig(
                strategy_type=StrategyType.DONCHIAN_SQUEEZE,
                symbols=["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"],
                timeframes=["5m", "15m", "1h"],
                parameters={"donchian_period": 20, "squeeze_threshold": 0.001},
                trading_style=TradingStyle.SCALPING,
                regime_filter=["ranging", "volatile", "high_volatility"],
            ),
            StrategyType.CARRY_ROLLOVER: StrategyConfig(
                strategy_type=StrategyType.CARRY_ROLLOVER,
                symbols=["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
                timeframes=["1h", "4h", "1d"],
                parameters={"carry_threshold": 0.005, "rollover_hour": 17},
                trading_style=TradingStyle.POSITION_TRADING,
                regime_filter=["trending", "low_volatility"],
            ),
            StrategyType.COST_AVERAGING_GRID: StrategyConfig(
                strategy_type=StrategyType.COST_AVERAGING_GRID,
                symbols=["XAUUSD", "BTCUSD"],
                timeframes=["1h", "4h"],
                parameters={"grid_size": 10, "grid_spacing": 0.002, "position_size": 0.01},
                trading_style=TradingStyle.POSITION_TRADING,
                regime_filter=["ranging", "low_volatility"],
            ),
        }

        for config in default_configs.values():
            self.register_strategy(config)

    def register_strategy(self, config: StrategyConfig) -> None:
        """Register a new strategy configuration."""
        self.strategy_configs[config.strategy_type] = config
        logger.info(f"Registered strategy: {config.strategy_type.value}")

    async def _load_performance_history(self) -> None:
        """Load historical performance data."""
        # In production, load from database

    def get_strategies_for_regime(self, regime: str) -> list[StrategyType]:
        """Get strategies suitable for a market regime."""
        return self.regime_strategy_map.get(regime, [StrategyType.ADAPTIVE_ENSEMBLE])

    def get_strategies_for_style(self, style: TradingStyle) -> list[StrategyType]:
        """Get strategies suitable for a trading style."""
        return self.style_strategy_map.get(style, [StrategyType.ADAPTIVE_ENSEMBLE])

    async def select_best_strategy(
        self,
        symbol: str,
        regime: str,
        style: TradingStyle,
        market_context: dict[str, Any]
    ) -> StrategyType | None:
        """Select the best strategy for given conditions."""
        # Get candidate strategies
        regime_strategies = self.get_strategies_for_regime(regime)
        style_strategies = self.get_strategies_for_style(style)

        # Intersection of regime and style strategies
        candidates = set(regime_strategies) & set(style_strategies)

        if not candidates:
            candidates = set(regime_strategies) | set(style_strategies)

        if not candidates:
            candidates = {StrategyType.ADAPTIVE_ENSEMBLE, StrategyType.REGIME_AWARE}

        # Filter by performance
        valid_candidates = []
        for strategy in candidates:
            if strategy in self.strategy_configs:
                config = self.strategy_configs[strategy]
                if config.enabled and symbol in config.symbols:
                    valid_candidates.append(strategy)

        if not valid_candidates:
            valid_candidates = list(candidates)

        # Score candidates based on performance
        scored_candidates = []
        for strategy in valid_candidates:
            score = await self._calculate_strategy_score(strategy, symbol, market_context)
            scored_candidates.append((strategy, score))

        if not scored_candidates:
            return StrategyType.ADAPTIVE_ENSEMBLE

        # Sort by score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Exploration vs exploitation
        if np.random.random() < self.exploration_rate and len(scored_candidates) > 1:
            # Explore: pick randomly from top 3
            top_3 = scored_candidates[:3]
            return np.random.choice([s for s, _ in top_3])

        # Exploitation: pick best
        best_strategy = scored_candidates[0][0]

        # Update current best
        self.current_best[symbol] = best_strategy

        logger.info(f"Selected strategy {best_strategy.value} for {symbol} (regime: {regime}, style: {style.value})")
        return best_strategy

    async def _calculate_strategy_score(
        self,
        strategy: StrategyType,
        symbol: str,
        market_context: dict[str, Any]
    ) -> float:
        """Calculate composite score for a strategy."""
        base_score = 0.5

        # Performance score
        if strategy in self.performance_history:
            perf = self.performance_history[strategy][-1] if self.performance_history[strategy] else None
            if perf:
                base_score = perf.score

        # Regime alignment bonus
        config = self.strategy_configs.get(strategy)
        if config and config.regime_filter:
            regime = market_context.get('regime', 'unknown')
            if regime in config.regime_filter:
                base_score += 0.15

        # Session alignment bonus
        session = market_context.get('session', 'unknown')
        if config and config.session_filter:
            if session in config.session_filter:
                base_score += 0.1

        # Volatility alignment
        volatility = market_context.get('volatility', 0.01)
        if config:
            if volatility > 0.02 and StrategyType.DONCHIAN_SQUEEZE in config.regime_filter or volatility < 0.01 and 'low_volatility' in config.regime_filter:
                base_score += 0.1

        # Recent performance
        if strategy in self.performance_history:
            recent = self.performance_history[strategy][-10:]
            if recent:
                recent_scores = [p.score for p in recent]
                avg_recent = np.mean(recent_scores)
                base_score = 0.7 * base_score + 0.3 * avg_recent

        # Exploration bonus for underused strategies
        if strategy not in self.current_best.values():
            base_score += 0.05

        return max(0.0, min(1.0, base_score))

    async def select_trading_style(
        self,
        symbol: str,
        market_context: dict[str, Any],
        account_context: dict[str, Any]
    ) -> TradingStyle:
        """Automatically select the best trading style."""
        # Factors for style selection
        volatility = market_context.get('volatility', 0.01)
        session = market_context.get('session', 'unknown')
        account_size = account_context.get('equity', 10000)
        _ = account_context.get('risk_tolerance', 0.02)  # unused
        time_available = account_context.get('time_available_hours', 4)

        scores = {}

        # Scalping: high volatility, active session, small account, high time
        scalping_score = 0
        if volatility > 0.015:
            scalping_score += 0.3
        if session in ['london', 'new_york', 'overlap']:
            scalping_score += 0.2
        if account_size < 5000:
            scalping_score += 0.2
        if time_available > 2:
            scalping_score += 0.1
        scores[TradingStyle.SCALPING] = scalping_score

        # Day trading: moderate volatility, active session, medium account
        day_score = 0
        if 0.008 < volatility < 0.02:
            day_score += 0.3
        if session in ['london', 'new_york', 'overlap']:
            day_score += 0.2
        if 5000 <= account_size <= 50000:
            day_score += 0.2
        if time_available >= 1:
            day_score += 0.1
        scores[TradingStyle.DAY_TRADING] = day_score

        # Swing trading: lower volatility, less time needed
        swing_score = 0
        if volatility < 0.015:
            swing_score += 0.3
        if account_size > 10000:
            swing_score += 0.2
        if time_available < 2:
            swing_score += 0.2
        scores[TradingStyle.SWING_TRADING] = swing_score

        # Position trading: low volatility, large account, long horizon
        position_score = 0
        if volatility < 0.01:
            position_score += 0.3
        if account_size > 50000:
            position_score += 0.3
        if time_available < 1:
            position_score += 0.2
        scores[TradingStyle.POSITION_TRADING] = position_score

        # Select best style
        best_style = max(scores, key=scores.get)
        logger.info(f"Selected trading style {best_style.value} for {symbol} (scores: {scores})")
        return best_style

    async def auto_configure(self, symbol: str, market_context: dict[str, Any], account_context: dict[str, Any]) -> dict[str, Any]:
        """Fully automatic configuration: select style, strategy, and parameters."""
        # Select trading style
        style = await self.select_trading_style(symbol, market_context, account_context)

        # Select strategy
        regime = market_context.get('regime', 'unknown')
        strategy = await self.select_best_strategy(symbol, regime, style, market_context)

        # Get config
        config = self.strategy_configs.get(strategy)
        if not config:
            config = StrategyConfig(
                strategy_type=StrategyType.ADAPTIVE_ENSEMBLE,
                symbols=[symbol],
                timeframes=["15m", "1h"],
                parameters={},
                trading_style=style,
            )

        return {
            "strategy_type": strategy,
            "trading_style": style,
            "config": config,
            "parameters": config.parameters,
            "timeframes": config.timeframes,
            "risk_params": {
                "max_position_size": config.max_position_size,
                "risk_per_trade": config.risk_per_trade,
                "max_holding_period": config.max_holding_period,
            }
        }

    def get_performance_report(self) -> dict[str, Any]:
        """Get performance report for all strategies."""
        report = {}
        for strategy, performances in self.performance_history.items():
            if performances:
                latest = performances[-1]
                report[strategy.value] = {
                    "total_trades": latest.total_trades,
                    "win_rate": latest.win_rate,
                    "total_pnl": latest.total_pnl,
                    "sharpe_ratio": latest.sharpe_ratio,
                    "max_drawdown": latest.max_drawdown,
                    "score": latest.score,
                    "enabled": self.strategy_configs.get(StrategyType(strategy.value), StrategyConfig(strategy_type=StrategyType(strategy.value), symbols=[], timeframes=[], parameters={})).enabled if strategy in self.strategy_configs else False,
                }
        return report


# Global instance
strategy_selector = StrategySelector()