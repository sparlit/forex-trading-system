"""
Advanced Trading Strategies
============================

Advanced strategies including:
- Reinforcement Learning based strategies
- Regime-aware adaptive strategies
- Multi-timeframe strategies
- Portfolio-level strategies
- Meta-learning strategies
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

import numpy as np
from loguru import logger

from src.data.models import Bar, Direction, Signal, Timeframe
from src.strategy.base.strategy import BaseStrategy, StrategyConfig, StrategyPerformance
from src.strategy.market_regime import MarketRegimeDetector, RegimeType
from src.strategy.ml.strategies import (
    BreakoutStrategy,
    EnsembleStrategy,
    MeanReversionStrategy,
    TrendFollowingStrategy,
)


class StrategyType(str, Enum):
    """Types of advanced strategies."""
    RL_PPO = "rl_ppo"
    RL_SAC = "rl_sac"
    REGIME_AWARE = "regime_aware"
    MULTI_TIMEFRAME = "multi_timeframe"
    PORTFOLIO_ARBITRAGE = "portfolio_arbitrage"
    META_LEARNING = "meta_learning"
    ENSEMBLE_ADAPTIVE = "ensemble_adaptive"
    NEWS_BASED = "news_based"
    PAIRS_TRADING = "pairs_trading"
    MOMENTUM = "momentum"
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"


@dataclass(slots=True)
class RLState:
    """State representation for RL agent."""
    prices: np.ndarray  # Normalized price history
    indicators: np.ndarray  # Technical indicators
    position: float  # Current position (-1 to 1)
    unrealized_pnl: float
    regime: int  # Encoded regime
    volatility: float
    timestamp: datetime


@dataclass(slots=True)
class RLAction:
    """Action from RL agent."""
    action_type: str  # "buy", "sell", "hold", "close"
    size: float  # Position size as fraction of capital
    confidence: float
    stop_loss_pct: float
    take_profit_pct: float


class RegimeAwareStrategy(BaseStrategy):
    """
    Strategy that adapts its behavior based on detected market regime.
    Uses different sub-strategies for different regimes.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Sub-strategies for each regime
        self.sub_strategies: dict[RegimeType, BaseStrategy] = {}
        self.regime_detector = MarketRegimeDetector()
        
        # Performance tracking per regime
        self.regime_performance: dict[RegimeType, StrategyPerformance] = {}
        self.current_regime: RegimeType = RegimeType.UNKNOWN
        
        # Configuration
        self.regime_switch_cooldown = config.parameters.get("regime_switch_cooldown", 10)  # bars
        self._bars_since_switch = 0
        self._last_regime = RegimeType.UNKNOWN
    
    async def _initialize(self) -> None:
        """Initialize sub-strategies."""
        # Create sub-strategies with shared config
        base_params = self.config.parameters.copy()
        
        # Trend following for trending regimes
        trend_config = StrategyConfig(
            strategy_id=f"{self.config.strategy_id}_trend",
            name=f"{self.config.name} Trend",
            description="Trend following sub-strategy",
            asset_classes=self.config.asset_classes,
            timeframes=self.config.timeframes,
            symbols=self.config.symbols,
            parameters={
                **base_params,
                "fast_ema": 20,
                "slow_ema": 50,
                "adx_threshold": 25,
            },
            min_confidence=0.6,
            risk_per_trade=self.config.risk_per_trade * 0.5,  # Reduced risk for sub-strategy
        )
        self.sub_strategies[RegimeType.TRENDING_UP] = TrendFollowingStrategy(trend_config)
        self.sub_strategies[RegimeType.TRENDING_DOWN] = TrendFollowingStrategy(trend_config)
        
        # Mean reversion for ranging/mean reverting regimes
        mr_config = StrategyConfig(
            strategy_id=f"{self.config.strategy_id}_mr",
            name=f"{self.config.name} MeanRev",
            description="Mean reversion sub-strategy",
            asset_classes=self.config.asset_classes,
            timeframes=self.config.timeframes,
            symbols=self.config.symbols,
            parameters={
                **base_params,
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
            },
            min_confidence=0.55,
            risk_per_trade=self.config.risk_per_trade * 0.5,
        )
        self.sub_strategies[RegimeType.RANGING] = MeanReversionStrategy(mr_config)
        self.sub_strategies[RegimeType.MEAN_REVERTING] = MeanReversionStrategy(mr_config)
        
        # Breakout for breakout/volatile regimes
        bo_config = StrategyConfig(
            strategy_id=f"{self.config.strategy_id}_breakout",
            name=f"{self.config.name} Breakout",
            description="Breakout sub-strategy",
            asset_classes=self.config.asset_classes,
            timeframes=self.config.timeframes,
            symbols=self.config.symbols,
            parameters={
                **base_params,
                "channel_period": 20,
                "volume_threshold": 1.5,
            },
            min_confidence=0.6,
            risk_per_trade=self.config.risk_per_trade * 0.5,
        )
        self.sub_strategies[RegimeType.BREAKOUT] = BreakoutStrategy(bo_config)
        self.sub_strategies[RegimeType.VOLATILE] = BreakoutStrategy(bo_config)
        
        # Low volatility - use ensemble
        ensemble_config = StrategyConfig(
            strategy_id=f"{self.config.strategy_id}_ensemble",
            name=f"{self.config.name} Ensemble",
            description="Ensemble sub-strategy",
            asset_classes=self.config.asset_classes,
            timeframes=self.config.timeframes,
            symbols=self.config.symbols,
            parameters={
                **base_params,
                "lookback": 100,
                "prediction_horizon": 10,
            },
            min_confidence=0.65,
            risk_per_trade=self.config.risk_per_trade * 0.5,
        )
        self.sub_strategies[RegimeType.LOW_VOLATILITY] = EnsembleStrategy(ensemble_config)
        
        # Initialize all sub-strategies
        for regime, strategy in self.sub_strategies.items():
            await strategy.initialize()
            self.regime_performance[regime] = StrategyPerformance(strategy_id=f"{self.config.strategy_id}_{regime.value}")
        
        logger.info(f"RegimeAwareStrategy initialized with {len(self.sub_strategies)} sub-strategies")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using regime-appropriate sub-strategy."""
        # Update regime detector
        # This would use recent bars - simplified for now
        
        # For now, delegate to appropriate sub-strategy based on current regime
        if self.current_regime in self.sub_strategies:
            strategy = self.sub_strategies[self.current_regime]
            signals = await strategy._generate_signals(bar)
            
            # Tag signals with regime info
            for signal in signals:
                signal.metadata = signal.metadata or {}
                signal.metadata["regime"] = self.current_regime.value
                signal.metadata["sub_strategy"] = strategy.config.strategy_id
            
            return signals
        
        return []


class MultiTimeframeStrategy(BaseStrategy):
    """
    Strategy that analyzes multiple timeframes simultaneously
    and requires alignment across timeframes for signals.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Timeframe hierarchy
        self.timeframes = config.parameters.get("timeframes", ["H4", "H1", "M15"])
        self.alignment_required = config.parameters.get("alignment_required", 2)  # How many TFs must agree
        
        # Bar buffers per timeframe
        self._bar_buffers: dict[str, deque] = {tf: deque(maxlen=200) for tf in self.timeframes}
        
        # Sub-strategies per timeframe
        self.tf_strategies: dict[str, BaseStrategy] = {}
        
        # Current signals per timeframe
        self.tf_signals: dict[str, list[Signal]] = {tf: [] for tf in self.timeframes}
    
    async def _initialize(self) -> None:
        """Initialize timeframe-specific strategies."""
        base_params = self.config.parameters.copy()
        
        for tf_name in self.timeframes:
            tf = Timeframe(tf_name)
            
            # Use different strategy types for different timeframes
            if tf_name in ["D1", "H4"]:
                # Higher timeframes: trend following
                strat_config = StrategyConfig(
                    strategy_id=f"{self.config.strategy_id}_{tf_name}",
                    name=f"{self.config.name} {tf_name}",
                    description=f"Trend following for {tf_name}",
                    asset_classes=self.config.asset_classes,
                    timeframes=[tf],
                    symbols=self.config.symbols,
                    parameters={**base_params, "fast_ema": 50, "slow_ema": 200},
                    min_confidence=0.65,
                    risk_per_trade=self.config.risk_per_trade * 0.3,
                )
                self.tf_strategies[tf_name] = TrendFollowingStrategy(strat_config)
            elif tf_name in ["H1", "H2", "H3"]:
                # Medium timeframes: swing/ensemble
                strat_config = StrategyConfig(
                    strategy_id=f"{self.config.strategy_id}_{tf_name}",
                    name=f"{self.config.name} {tf_name}",
                    description=f"Ensemble for {tf_name}",
                    asset_classes=self.config.asset_classes,
                    timeframes=[tf],
                    symbols=self.config.symbols,
                    parameters={**base_params, "lookback": 100},
                    min_confidence=0.6,
                    risk_per_trade=self.config.risk_per_trade * 0.3,
                )
                self.tf_strategies[tf_name] = EnsembleStrategy(strat_config)
            else:
                # Lower timeframes: mean reversion/scalping
                strat_config = StrategyConfig(
                    strategy_id=f"{self.config.strategy_id}_{tf_name}",
                    name=f"{self.config.name} {tf_name}",
                    description=f"Mean reversion for {tf_name}",
                    asset_classes=self.config.asset_classes,
                    timeframes=[tf],
                    symbols=self.config.symbols,
                    parameters={**base_params, "bb_period": 14, "rsi_period": 7},
                    min_confidence=0.55,
                    risk_per_trade=self.config.risk_per_trade * 0.3,
                )
                self.tf_strategies[tf_name] = MeanReversionStrategy(strat_config)
            
            await self.tf_strategies[tf_name].initialize()
        
        logger.info(f"MultiTimeframeStrategy initialized with {len(self.tf_strategies)} timeframe strategies")
    
    def _add_bar(self, bar: Bar) -> None:
        """Add bar to appropriate timeframe buffer."""
        tf_key = bar.timeframe.value
        if tf_key in self._bar_buffers:
            self._bar_buffers[tf_key].append(bar)
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals requiring multi-timeframe alignment."""
        # Add bar to buffer
        self._add_bar(bar)
        
        # Generate signals for each timeframe
        all_tf_signals = {}
        
        for tf_name, strategy in self.tf_strategies.items():
            tf_buffer = self._bar_buffers[tf_name]
            if len(tf_buffer) >= 50:
                latest_bar = tf_buffer[-1]
                signals = await strategy._generate_signals(latest_bar)
                self.tf_signals[tf_name] = signals
                all_tf_signals[tf_name] = signals
        
        # Check alignment
        aligned_signals = self._check_alignment(all_tf_signals)
        
        return aligned_signals
    
    def _check_alignment(self, tf_signals: dict[str, list[Signal]]) -> list[Signal]:
        """Check if signals align across timeframes."""
        # Count signals by symbol and direction
        signal_counts: dict[tuple[str, Direction], int] = {}
        signal_details: dict[tuple[str, Direction], list[Signal]] = {}
        
        for signals in tf_signals.values():
            for signal in signals:
                key = (signal.symbol, signal.direction)
                signal_counts[key] = signal_counts.get(key, 0) + 1
                if key not in signal_details:
                    signal_details[key] = []
                signal_details[key].append(signal)
        
        # Find aligned signals
        aligned = []
        for (symbol, direction), count in signal_counts.items():
            if count >= self.alignment_required:
                # Use the highest timeframe signal as primary
                primary_signal = max(
                    signal_details[(symbol, direction)],
                    key=lambda s: self._tf_priority(s.timeframe)
                )
                
                # Boost confidence based on alignment
                primary_signal.confidence = min(0.95, primary_signal.confidence * (1 + 0.1 * count))
                primary_signal.metadata = primary_signal.metadata or {}
                primary_signal.metadata["aligned_timeframes"] = count
                primary_signal.metadata["alignment_details"] = {
                    tf: len([s for s in sigs if s.symbol == symbol and s.direction == direction])
                    for tf, sigs in tf_signals.items()
                }
                
                aligned.append(primary_signal)
        
        return aligned
    
    def _tf_priority(self, tf: Timeframe) -> int:
        """Get priority for timeframe (higher = more important)."""
        priorities = {
            Timeframe.MN1: 10,
            Timeframe.W1: 9,
            Timeframe.D1: 8,
            Timeframe.H12: 7,
            Timeframe.H8: 6,
            Timeframe.H6: 5,
            Timeframe.H4: 4,
            Timeframe.H3: 3,
            Timeframe.H2: 2,
            Timeframe.H1: 1,
            Timeframe.M30: 0,
            Timeframe.M15: 0,
        }
        return priorities.get(tf, 0)


class AdaptiveEnsembleStrategy(BaseStrategy):
    """
    Ensemble strategy that dynamically weights sub-strategies based on
    recent performance and current market regime.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        self.sub_strategies: dict[str, BaseStrategy] = {}
        self.strategy_weights: dict[str, float] = {}
        self.performance_window = config.parameters.get("performance_window", 50)  # trades
        self.regime_detector = MarketRegimeDetector()
        self.current_regime: RegimeType = RegimeType.UNKNOWN
        
        # Minimum weight for any strategy
        self.min_weight = config.parameters.get("min_weight", 0.1)
        self.weight_update_frequency = config.parameters.get("weight_update_frequency", 10)  # bars
        self._bars_since_weight_update = 0
    
    async def _initialize(self) -> None:
        """Initialize ensemble sub-strategies."""
        base_params = self.config.parameters.copy()
        
        # Define sub-strategies
        strategies_config = [
            ("trend_following", TrendFollowingStrategy, {
                "fast_ema": 20, "slow_ema": 50, "adx_threshold": 25
            }),
            ("mean_reversion", MeanReversionStrategy, {
                "bb_period": 20, "bb_std": 2.0, "rsi_period": 14
            }),
            ("breakout", BreakoutStrategy, {
                "channel_period": 20, "volume_threshold": 1.5
            }),
            ("ml_ensemble", EnsembleStrategy, {
                "lookback": 100, "prediction_horizon": 10
            }),
        ]
        
        for name, strat_class, params in strategies_config:
            strat_config = StrategyConfig(
                strategy_id=f"{self.config.strategy_id}_{name}",
                name=f"{self.config.name} {name}",
                description=f"{name} sub-strategy",
                asset_classes=self.config.asset_classes,
                timeframes=self.config.timeframes,
                symbols=self.config.symbols,
                parameters={**base_params, **params},
                min_confidence=0.55,
                risk_per_trade=self.config.risk_per_trade * 0.5,
            )
            strategy = strat_class(strat_config)
            await strategy.initialize()
            self.sub_strategies[name] = strategy
            self.strategy_weights[name] = 1.0 / len(strategies_config)
        
        logger.info(f"AdaptiveEnsembleStrategy initialized with {len(self.sub_strategies)} sub-strategies")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate weighted ensemble signals."""
        # Update regime
        # In practice, would use recent bars
        
        # Update weights periodically
        self._bars_since_weight_update += 1
        if self._bars_since_weight_update >= self.weight_update_frequency:
            await self._update_weights()
            self._bars_since_weight_update = 0
        
        # Collect signals from all sub-strategies
        all_signals: dict[tuple[str, Direction], list[tuple[Signal, float]]] = {}
        
        for name, strategy in self.sub_strategies.items():
            weight = self.strategy_weights.get(name, 0)
            if weight < self.min_weight:
                continue
            
            signals = await strategy._generate_signals(bar)
            for signal in signals:
                key = (signal.symbol, signal.direction)
                if key not in all_signals:
                    all_signals[key] = []
                all_signals[key].append((signal, weight))
        
        # Combine signals
        combined_signals = []
        for weighted_signals in all_signals.values():
            if not weighted_signals:
                continue
            
            # Weighted average
            total_weight = sum(w for _, w in weighted_signals)
            if total_weight == 0:
                continue
            
            # Use highest confidence signal as base
            base_signal = max(weighted_signals, key=lambda x: x[0].confidence)[0]
            
            # Calculate weighted confidence
            weighted_conf = sum(s.confidence * w for s, w in weighted_signals) / total_weight
            base_signal.confidence = min(0.95, weighted_conf)
            
            # Weighted stop loss / take profit
            weighted_sl = sum(s.stop_loss * w for s, w in weighted_signals) / total_weight
            weighted_tp = sum(s.take_profit * w for s, w in weighted_signals) / total_weight
            base_signal.stop_loss = weighted_sl
            base_signal.take_profit = weighted_tp
            
            base_signal.metadata = base_signal.metadata or {}
            base_signal.metadata["ensemble_weights"] = {
                s.metadata.get("sub_strategy", "unknown"): w for s, w in weighted_signals
            }
            base_signal.metadata["sub_strategies"] = [
                s.metadata.get("sub_strategy", "unknown") for s, _ in weighted_signals
            ]
            
            combined_signals.append(base_signal)
        
        return combined_signals
    
    async def _update_weights(self) -> None:
        """Update strategy weights based on recent performance."""
        # Calculate performance metrics for each sub-strategy
        performances = {}
        
        for name, strategy in self.sub_strategies.items():
            perf = strategy.performance
            # Combined score: Sharpe * win_rate * profit_factor
            score = (
                max(0, perf.sharpe_ratio) * 0.4 +
                perf.win_rate * 0.3 +
                min(2.0, perf.profit_factor) * 0.3
            )
            performances[name] = max(0.01, score)
        
        # Normalize weights
        total = sum(performances.values())
        if total > 0:
            for name in self.strategy_weights:
                if name in performances:
                    new_weight = performances[name] / total
                    # Apply minimum weight constraint
                    self.strategy_weights[name] = max(self.min_weight, new_weight)
            
            # Renormalize
            total = sum(self.strategy_weights.values())
            for name in self.strategy_weights:
                self.strategy_weights[name] /= total
        
        logger.debug(f"Updated ensemble weights: {self.strategy_weights}")


class RLTradingStrategy(BaseStrategy):
    """
    Reinforcement Learning based trading strategy.
    Uses PPO or SAC agent for decision making.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        self.algorithm = config.parameters.get("algorithm", "PPO")
        self.state_dim = config.parameters.get("state_dim", 50)
        self.action_dim = config.parameters.get("action_dim", 5)  # buy, sell, hold, close_long, close_short
        self.hidden_dim = config.parameters.get("hidden_dim", 256)
        
        # Training parameters
        self.learning_rate = config.parameters.get("learning_rate", 3e-4)
        self.gamma = config.parameters.get("gamma", 0.99)
        self.gae_lambda = config.parameters.get("gae_lambda", 0.95)
        self.clip_epsilon = config.parameters.get("clip_epsilon", 0.2)
        self.entropy_coef = config.parameters.get("entropy_coef", 0.01)
        self.value_coef = config.parameters.get("value_coef", 0.5)
        
        # Experience buffer
        self.buffer_size = config.parameters.get("buffer_size", 2048)
        self.batch_size = config.parameters.get("batch_size", 64)
        self.epochs = config.parameters.get("epochs", 10)
        
        # State
        self._experience_buffer: list[dict] = []
        self._current_state: RLState | None = None
        self._episode_reward = 0.0
        self._training_step = 0
        
        # Neural networks (placeholder - would use PyTorch/TensorFlow)
        self.actor = None
        self.critic = None
        
        # For inference mode
        self.inference_mode = config.parameters.get("inference_mode", True)
        self.model_path = config.parameters.get("model_path", "./models/rl_agent")
    
    async def _initialize(self) -> None:
        """Initialize RL agent."""
        if self.inference_mode:
            # Load pre-trained model
            await self._load_model()
        else:
            # Initialize new networks
            await self._init_networks()
        
        logger.info(f"RLTradingStrategy ({self.algorithm}) initialized")
    
    async def _init_networks(self) -> None:
        """Initialize neural networks."""
        # Placeholder - would initialize PyTorch models
        # self.actor = ActorNetwork(self.state_dim, self.action_dim, self.hidden_dim)
        # self.critic = CriticNetwork(self.state_dim, self.hidden_dim)
    
    async def _load_model(self) -> None:
        """Load pre-trained model."""
        # Placeholder - would load from disk
        logger.info(f"Loading RL model from {self.model_path}")
    
    def _encode_state(self, market_context: dict) -> RLState:
        """Encode market context into RL state."""
        # This would create the state representation
        return RLState(
            prices=np.zeros(20),
            indicators=np.zeros(30),
            position=0.0,
            unrealized_pnl=0.0,
            regime=0,
            volatility=0.0,
            timestamp=datetime.now(UTC),
        )
    
    def _select_action(self, state: RLState) -> RLAction:
        """Select action using policy network."""
        # Placeholder - would run inference
        return RLAction(
            action_type="hold",
            size=0.0,
            confidence=0.5,
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
        )
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using RL agent."""
        # Encode current state
        state = self._encode_state({})
        
        # Select action
        action = self._select_action(state)
        
        # Convert to signal
        if action.action_type in ("buy", "sell") and action.size > 0.01:
            direction = Direction.LONG if action.action_type == "buy" else Direction.SHORT
            
            # Estimate entry price
            entry_price = bar.close
            
            # Calculate SL/TP
            bar.high - bar.low  # Simplified
            stop_loss = entry_price - action.stop_loss_pct * entry_price if direction == Direction.LONG else entry_price + action.stop_loss_pct * entry_price
            take_profit = entry_price + action.take_profit_pct * entry_price if direction == Direction.LONG else entry_price - action.take_profit_pct * entry_price
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=action.confidence,
                position_size_pct=action.size,
                timeframe=bar.timeframe,
                reasoning=f"RL {self.algorithm} action: {action.action_type}",
            )
            return [signal]
        
        return []
    
    async def train_step(self, experiences: list[dict]) -> dict[str, float]:
        """Perform one training step."""
        # Placeholder for PPO/SAC training
        metrics = {
            "actor_loss": 0.0,
            "critic_loss": 0.0,
            "entropy": 0.0,
        }
        self._training_step += 1
        return metrics


# Strategy factory for easy creation
def create_strategy(strategy_type: StrategyType, config: StrategyConfig) -> BaseStrategy:
    """Factory function to create strategies by type."""
    strategies = {
        StrategyType.REGIME_AWARE: RegimeAwareStrategy,
        StrategyType.MULTI_TIMEFRAME: MultiTimeframeStrategy,
        StrategyType.ENSEMBLE_ADAPTIVE: AdaptiveEnsembleStrategy,
        StrategyType.RL_PPO: lambda c: RLTradingStrategy(StrategyConfig(
            **c.__dict__, parameters={**c.parameters, "algorithm": "PPO"}
        )),
        StrategyType.RL_SAC: lambda c: RLTradingStrategy(StrategyConfig(
            **c.__dict__, parameters={**c.parameters, "algorithm": "SAC"}
        )),
    }
    
    if strategy_type not in strategies:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
    
    return strategies[strategy_type](config)


class TradingStyle(str, Enum):
    """Trading style/timeframe classification."""
    SCALPING = "scalping"       # Seconds to minutes, M1-M5
    DAY_TRADING = "day_trading" # Minutes to hours, M15-H1
    SWING_TRADING = "swing_trading"  # Hours to days, H4-D1
    POSITION_TRADING = "position_trading"  # Days to weeks, D1-W1


@dataclass(slots=True)
class StyleConfig:
    """Configuration for a trading style."""
    style: TradingStyle
    primary_timeframe: Timeframe
    secondary_timeframes: list[Timeframe]
    max_hold_time: timedelta
    typical_target_pips: float
    typical_stop_pips: float
    max_positions: int
    risk_per_trade: float
    min_confidence: float
    session_filter: list[str] = field(default_factory=list)  # e.g., ["London", "NY"]


# Default configurations for each style
STYLE_CONFIGS = {
    TradingStyle.SCALPING: StyleConfig(
        style=TradingStyle.SCALPING,
        primary_timeframe=Timeframe.M1,
        secondary_timeframes=[Timeframe.M5, Timeframe.M15],
        max_hold_time=timedelta(minutes=30),
        typical_target_pips=5,
        typical_stop_pips=3,
        max_positions=10,
        risk_per_trade=0.005,  # 0.5% per trade
        min_confidence=0.7,
        session_filter=["London", "NY", "Overlap"],
    ),
    TradingStyle.DAY_TRADING: StyleConfig(
        style=TradingStyle.DAY_TRADING,
        primary_timeframe=Timeframe.M15,
        secondary_timeframes=[Timeframe.H1, Timeframe.H4],
        max_hold_time=timedelta(hours=8),
        typical_target_pips=20,
        typical_stop_pips=10,
        max_positions=5,
        risk_per_trade=0.01,  # 1% per trade
        min_confidence=0.65,
        session_filter=["London", "NY"],
    ),
    TradingStyle.SWING_TRADING: StyleConfig(
        style=TradingStyle.SWING_TRADING,
        primary_timeframe=Timeframe.H4,
        secondary_timeframes=[Timeframe.D1, Timeframe.H1],
        max_hold_time=timedelta(days=5),
        typical_target_pips=100,
        typical_stop_pips=50,
        max_positions=3,
        risk_per_trade=0.015,  # 1.5% per trade
        min_confidence=0.6,
        session_filter=[],
    ),
    TradingStyle.POSITION_TRADING: StyleConfig(
        style=TradingStyle.POSITION_TRADING,
        primary_timeframe=Timeframe.D1,
        secondary_timeframes=[Timeframe.W1, Timeframe.H4],
        max_hold_time=timedelta(weeks=4),
        typical_target_pips=300,
        typical_stop_pips=150,
        max_positions=2,
        risk_per_trade=0.02,  # 2% per trade
        min_confidence=0.55,
        session_filter=[],
    ),
}


class ScalpingStrategy(BaseStrategy):
    """
    High-frequency scalping strategy for M1-M5 timeframes.
    Uses tight spreads, quick entries/exits, high win rate target.
    Best during high liquidity sessions (London/NY overlap).
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.style_config = STYLE_CONFIGS[TradingStyle.SCALPING]
        self._tick_buffer: deque = deque(maxlen=1000)
        self._spread_history: deque = deque(maxlen=100)
        self._last_trade_time: datetime | None = None
        self._min_trade_interval = timedelta(seconds=30)
    
    async def _initialize(self) -> None:
        logger.info(f"ScalpingStrategy initialized for {self.config.symbols}")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        # Scalping needs tick data - use bar as proxy
        self._tick_buffer.append({
            'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
        })
        
        if len(self._tick_buffer) < 50:
            return signals
        
        # Check session filter
        if not self._is_valid_session(bar.timestamp):
            return signals
        
        # Check minimum trade interval
        if self._last_trade_time and (bar.timestamp - self._last_trade_time) < self._min_trade_interval:
            return signals
        
        # Calculate micro-trend using EMA ribbon
        closes = np.array([t['close'] for t in self._tick_buffer])
        ema_fast = self._ema(closes, 5)
        ema_medium = self._ema(closes, 13)
        ema_slow = self._ema(closes, 34)
        
        # Spread filter
        current_spread = (bar.high - bar.low) / bar.close * 10000  # pips
        avg_spread = np.mean(self._spread_history) if self._spread_history else current_spread
        if current_spread > avg_spread * 1.5:
            return signals  # Spread too wide
        
        # Momentum
        momentum = (closes[-1] - closes[-10]) / closes[-10] * 10000  # pips
        
        # Volume spike detection
        volumes = np.array([t['volume'] for t in self._tick_buffer])
        avg_volume = np.mean(volumes[-20:])
        current_volume = volumes[-1]
        volume_spike = current_volume > avg_volume * 1.5
        
        # Scalping signal: EMA alignment + momentum + volume
        if ema_fast > ema_medium > ema_slow and momentum > 2 and volume_spike:
            # Long scalp
            entry = bar.close
            stop = entry - self.style_config.typical_stop_pips / 10000
            target = entry + self.style_config.typical_target_pips / 10000
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.LONG,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.75,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Scalping: EMA ribbon bullish + momentum + volume spike",
            )
            signals.append(signal)
            self._last_trade_time = bar.timestamp
            
        elif ema_fast < ema_medium < ema_slow and momentum < -2 and volume_spike:
            # Short scalp
            entry = bar.close
            stop = entry + self.style_config.typical_stop_pips / 10000
            target = entry - self.style_config.typical_target_pips / 10000
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.SHORT,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.75,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Scalping: EMA ribbon bearish + momentum + volume spike",
            )
            signals.append(signal)
            self._last_trade_time = bar.timestamp
        
        return signals
    
    def _ema(self, data: np.ndarray, period: int) -> float:
        """Calculate EMA."""
        if len(data) < period:
            return data[-1]
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    def _is_valid_session(self, timestamp: datetime) -> bool:
        """Check if current time is in valid trading session."""
        if not self.style_config.session_filter:
            return True
        hour = timestamp.hour
        # London: 8-17 UTC, NY: 13-22 UTC, Overlap: 13-17 UTC
        sessions = {
            "London": (8, 17),
            "NY": (13, 22),
            "Overlap": (13, 17),
        }
        for session in self.style_config.session_filter:
            start, end = sessions.get(session, (0, 24))
            if start <= hour < end:
                return True
        return False


class DayTradingStrategy(BaseStrategy):
    """
    Intraday day trading strategy for M15-H1 timeframes.
    Captures intraday trends and reversals, closes all positions by end of day.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.style_config = STYLE_CONFIGS[TradingStyle.DAY_TRADING]
        self._bar_buffer: dict[str, deque] = {}
        self._daily_high = 0.0
        self._daily_low = float('inf')
        self._day_open = 0.0
        self._current_day = None
    
    async def _initialize(self) -> None:
        logger.info(f"DayTradingStrategy initialized for {self.config.symbols}")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        # Track daily levels
        if self._current_day != bar.timestamp.date():
            self._current_day = bar.timestamp.date()
            self._daily_high = bar.high
            self._daily_low = bar.low
            self._day_open = bar.open
        else:
            self._daily_high = max(self._daily_high, bar.high)
            self._daily_low = min(self._daily_low, bar.low)
        
        # Add to buffer
        if bar.symbol not in self._bar_buffer:
            self._bar_buffer[bar.symbol] = deque(maxlen=200)
        self._bar_buffer[bar.symbol].append(bar)
        
        if len(self._bar_buffer[bar.symbol]) < 50:
            return signals
        
        # Check session filter
        if not self._is_valid_session(bar.timestamp):
            # End of day - close all positions
            if bar.timestamp.hour >= 21:  # After NY close
                return self._generate_close_signals(bar)
            return signals
        
        # Force close before market close
        if bar.timestamp.hour >= 20:  # 1 hour before close
            return self._generate_close_signals(bar)
        
        df = self._bars_to_dataframe(self._bar_buffer[bar.symbol])
        
        # VWAP calculation
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        vwap = df['vwap'].iloc[-1]
        
        # Intraday trend: EMA 9/21 on M15
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        
        # RSI for mean reversion
        df['rsi'] = self._rsi(df['close'], 14)
        
        # Bollinger Bands
        df['bb_mid'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        
        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current
        
        # Day trading signals
        # 1. VWAP trend following
        if current['close'] > vwap and current['ema_9'] > current['ema_21'] and prev['ema_9'] <= prev['ema_21']:
            # Bullish VWAP crossover
            entry = current['close']
            stop = current['low'] - (current['high'] - current['low']) * 0.5
            target = entry + (entry - stop) * 2  # 2:1 RR
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.LONG,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.7,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Day Trade: VWAP bullish crossover + EMA alignment",
            )
            signals.append(signal)
            
        elif current['close'] < vwap and current['ema_9'] < current['ema_21'] and prev['ema_9'] >= prev['ema_21']:
            # Bearish VWAP crossover
            entry = current['close']
            stop = current['high'] + (current['high'] - current['low']) * 0.5
            target = entry - (stop - entry) * 2
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.SHORT,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.7,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Day Trade: VWAP bearish crossover + EMA alignment",
            )
            signals.append(signal)
        
        # 2. Mean reversion at extremes (BB + RSI)
        if current['rsi'] < 30 and current['close'] <= current['bb_lower']:
            # Oversold bounce
            entry = current['close']
            stop = current['bb_lower'] - (current['bb_mid'] - current['bb_lower']) * 0.5
            target = current['bb_mid']
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.LONG,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.65,
                position_size_pct=self.style_config.risk_per_trade * 0.5,
                timeframe=bar.timeframe,
                reasoning="Day Trade: Mean reversion at BB lower + RSI oversold",
            )
            signals.append(signal)
            
        elif current['rsi'] > 70 and current['close'] >= current['bb_upper']:
            # Overbought reversal
            entry = current['close']
            stop = current['bb_upper'] + (current['bb_upper'] - current['bb_mid']) * 0.5
            target = current['bb_mid']
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.SHORT,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.65,
                position_size_pct=self.style_config.risk_per_trade * 0.5,
                timeframe=bar.timeframe,
                reasoning="Day Trade: Mean reversion at BB upper + RSI overbought",
            )
            signals.append(signal)
        
        return signals
    
    def _generate_close_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals to close all open positions."""
        # This would be handled by the brain - return empty for now
        return []
    
    def _rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _is_valid_session(self, timestamp: datetime) -> bool:
        if not self.style_config.session_filter:
            return True
        hour = timestamp.hour
        sessions = {"London": (8, 17), "NY": (13, 22)}
        for session in self.style_config.session_filter:
            start, end = sessions.get(session, (0, 24))
            if start <= hour < end:
                return True
        return False


class SwingTradingStrategy(BaseStrategy):
    """
    Swing trading strategy for H4-D1 timeframes.
    Captures multi-day moves, holds positions for days.
    Uses trend following and pullback entries.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.style_config = STYLE_CONFIGS[TradingStyle.SWING_TRADING]
        self._bar_buffer: dict[str, deque] = {}
    
    async def _initialize(self) -> None:
        logger.info(f"SwingTradingStrategy initialized for {self.config.symbols}")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        if bar.symbol not in self._bar_buffer:
            self._bar_buffer[bar.symbol] = deque(maxlen=200)
        self._bar_buffer[bar.symbol].append(bar)
        
        if len(self._bar_buffer[bar.symbol]) < 100:
            return signals
        
        df = self._bars_to_dataframe(self._bar_buffer[bar.symbol])
        
        # Higher timeframe trend
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['atr'] = self._atr(df, 14)
        
        # ADX for trend strength
        df['adx'] = self._adx(df, 14)
        
        # MACD
        df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Support/Resistance levels
        df['swing_high'] = df['high'].rolling(10).max()
        df['swing_low'] = df['low'].rolling(10).min()
        
        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current
        
        # Trend filter
        trend_up = current['ema_50'] > current['ema_200']
        trend_down = current['ema_50'] < current['ema_200']
        strong_trend = current['adx'] > 25
        
        if trend_up and strong_trend:
            # Pullback entry on MACD histogram reversal
            if current['macd_hist'] > 0 and prev['macd_hist'] <= 0 and current['close'] > current['ema_50']:
                entry = current['close']
                stop = current['close'] - current['atr'] * 2
                target = entry + (entry - stop) * 2.5
                
                signal = Signal.create_entry(
                    strategy_id=self.config.strategy_id,
                    strategy_name=self.config.name,
                    symbol=bar.symbol,
                    direction=Direction.LONG,
                    entry_price=entry,
                    stop_loss=stop,
                    take_profit=target,
                    confidence=0.7,
                    position_size_pct=self.style_config.risk_per_trade,
                    timeframe=bar.timeframe,
                    reasoning="Swing Trade: Pullback in uptrend + MACD bullish + ADX strong",
                )
                signals.append(signal)
                
        elif trend_down and strong_trend:
            if current['macd_hist'] < 0 and prev['macd_hist'] >= 0 and current['close'] < current['ema_50']:
                entry = current['close']
                stop = current['close'] + current['atr'] * 2
                target = entry - (stop - entry) * 2.5
                
                signal = Signal.create_entry(
                    strategy_id=self.config.strategy_id,
                    strategy_name=self.config.name,
                    symbol=bar.symbol,
                    direction=Direction.SHORT,
                    entry_price=entry,
                    stop_loss=stop,
                    take_profit=target,
                    confidence=0.7,
                    position_size_pct=self.style_config.risk_per_trade,
                    timeframe=bar.timeframe,
                    reasoning="Swing Trade: Pullback in downtrend + MACD bearish + ADX strong",
                )
                signals.append(signal)
        
        # Breakout entries
        if current['close'] > current['swing_high'].iloc[-2] and current['volume'] > df['volume'].rolling(20).mean().iloc[-1] * 1.5:
            entry = current['close']
            stop = current['swing_low'].iloc[-1]
            target = entry + (entry - stop) * 2
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.LONG,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.65,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Swing Trade: Breakout above resistance + volume confirmation",
            )
            signals.append(signal)
        
        return signals
    
    def _atr(self, df, period: int = 14):
        """Calculate ATR."""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        return tr.rolling(period).mean()
    
    def _adx(self, df, period: int = 14):
        """Calculate ADX."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        tr1 = high - low
        tr2 = np.abs(high - close.shift())
        tr3 = np.abs(low - close.shift())
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (-minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(period).mean()


class PositionTradingStrategy(BaseStrategy):
    """
    Position trading strategy for D1-W1 timeframes.
    Captures major trends, holds for weeks to months.
    Fundamental + technical confluence.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.style_config = STYLE_CONFIGS[TradingStyle.POSITION_TRADING]
        self._bar_buffer: dict[str, deque] = {}
    
    async def _initialize(self) -> None:
        logger.info(f"PositionTradingStrategy initialized for {self.config.symbols}")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        if bar.symbol not in self._bar_buffer:
            self._bar_buffer[bar.symbol] = deque(maxlen=500)
        self._bar_buffer[bar.symbol].append(bar)
        
        if len(self._bar_buffer[bar.symbol]) < 200:
            return signals
        
        df = self._bars_to_dataframe(self._bar_buffer[bar.symbol])
        
        # Long-term trend
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        
        # Weekly/monthly levels
        df['weekly_high'] = df['high'].rolling(5).max()  # Approximate weekly
        df['weekly_low'] = df['low'].rolling(5).min()
        
        # RSI for long-term momentum
        df['rsi'] = self._rsi(df['close'], 14)
        
        # Rate of change (momentum)
        df['roc'] = df['close'].pct_change(10) * 100
        
        current = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else current
        
        # Golden Cross / Death Cross
        golden_cross = current['sma_50'] > current['sma_200'] and prev['sma_50'] <= prev['sma_200']
        death_cross = current['sma_50'] < current['sma_200'] and prev['sma_50'] >= prev['sma_200']
        
        # Long-term trend
        trend_up = current['ema_50'] > current['ema_200'] and current['close'] > current['ema_200']
        trend_down = current['ema_50'] < current['ema_200'] and current['close'] < current['ema_200']
        
        if golden_cross and trend_up and current['rsi'] < 70:
            # Major bullish signal
            entry = current['close']
            stop = current['ema_200'] * 0.98  # Below 200 EMA
            target = entry + (entry - stop) * 3
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.LONG,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.8,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Position Trade: Golden Cross + uptrend + RSI not overbought",
            )
            signals.append(signal)
            
        elif death_cross and trend_down and current['rsi'] > 30:
            # Major bearish signal
            entry = current['close']
            stop = current['ema_200'] * 1.02
            target = entry - (stop - entry) * 3
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=Direction.SHORT,
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                confidence=0.8,
                position_size_pct=self.style_config.risk_per_trade,
                timeframe=bar.timeframe,
                reasoning="Position Trade: Death Cross + downtrend + RSI not oversold",
            )
            signals.append(signal)
        
        # Trend continuation on pullback to 50 EMA
        if trend_up and current['close'] <= current['ema_50'] * 1.005 and current['close'] >= current['ema_50'] * 0.995:
            if current['roc'] > 0:  # Positive momentum
                entry = current['close']
                stop = current['ema_50'] * 0.98
                target = entry + (entry - stop) * 3
                
                signal = Signal.create_entry(
                    strategy_id=self.config.strategy_id,
                    strategy_name=self.config.name,
                    symbol=bar.symbol,
                    direction=Direction.LONG,
                    entry_price=entry,
                    stop_loss=stop,
                    take_profit=target,
                    confidence=0.65,
                    position_size_pct=self.style_config.risk_per_trade,
                    timeframe=bar.timeframe,
                    reasoning="Position Trade: Pullback to 50 EMA in strong uptrend",
                )
                signals.append(signal)
        
        return signals
    
    def _rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))




class NewsBasedTradingStrategy(BaseStrategy):
    """
    News-based trading strategy that incorporates sentiment analysis and 
    economic calendar events for trading decisions.
    
    Features:
    - Real-time news sentiment analysis
    - Economic calendar event tracking
    - Central bank policy monitoring
    - Geopolitical event impact assessment
    - Earnings/guidance surprise detection
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.sentiment_threshold = config.parameters.get("sentiment_threshold", 0.3)
        self.news_lookback_hours = config.parameters.get("news_lookback_hours", 24)
        self.event_impact_window = config.parameters.get("event_impact_window", 4)  # hours
        self.min_news_count = config.parameters.get("min_news_count", 3)
        self.sentiment_sources = config.parameters.get("sentiment_sources", 
            ["reuters", "bloomberg", "forexfactory", "investing"])
        
        # News cache
        self._news_cache: dict[str, list[dict]] = {}
        self._event_calendar: list[dict] = []
        self._sentiment_scores: dict[str, float] = {}
        
    async def _initialize(self) -> None:
        logger.info(f"NewsBasedTradingStrategy initialized for {self.config.symbols}")
        # In production, would connect to news APIs
        await self._fetch_economic_calendar()
    
    async def _fetch_economic_calendar(self) -> None:
        """Fetch upcoming economic events."""
        # Placeholder - would connect to economic calendar API
        self._event_calendar = [
            {
                "event": "FOMC Rate Decision",
                "currency": "USD",
                "impact": "high",
                "time": datetime.now(UTC) + timedelta(days=1),
                "forecast": "5.25%",
                "previous": "5.25%"
            },
            {
                "event": "ECB Rate Decision",
                "currency": "EUR",
                "impact": "high",
                "time": datetime.now(UTC) + timedelta(days=2),
                "forecast": "4.00%",
                "previous": "4.00%"
            },
            {
                "event": "NFP Employment Change",
                "currency": "USD",
                "impact": "high",
                "time": datetime.now(UTC) + timedelta(days=3),
                "forecast": "180K",
                "previous": "200K"
            }
        ]
    
    async def _fetch_news_sentiment(self, symbol: str) -> dict:
        """Fetch news sentiment for a symbol."""
        # Placeholder - would connect to news API
        symbol[:3]
        symbol[3:6]
        
        # Simulate sentiment based on recent events
        sentiment = np.random.uniform(-0.5, 0.5)
        news_count = np.random.randint(1, 10)
        
        return {
            "symbol": symbol,
            "sentiment": sentiment,
            "news_count": news_count,
            "confidence": min(1.0, news_count / 10),
            "timestamp": datetime.now(UTC)
        }
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        for symbol in self.config.symbols:
            # Check for upcoming high-impact events
            if self._has_high_impact_event(symbol, bar.timestamp):
                continue  # Avoid trading before major events
            
            # Fetch sentiment
            sentiment_data = await self._fetch_news_sentiment(symbol)
            self._sentiment_scores[symbol] = sentiment_data["sentiment"]
            
            # Skip if insufficient news
            if sentiment_data["news_count"] < self.min_news_count:
                continue
            
            # Get current price
            entry_price = bar.close
            
            # Sentiment-based signal
            sentiment = sentiment_data["sentiment"]
            confidence = sentiment_data["confidence"]
            
            if abs(sentiment) < self.sentiment_threshold:
                continue
            
            direction = Direction.LONG if sentiment > 0 else Direction.SHORT
            
            # Calculate stop loss and take profit based on ATR
            atr = self._calculate_atr(symbol, bar)
            stop_loss = entry_price - atr * 2 if direction == Direction.LONG else entry_price + atr * 2
            take_profit = entry_price + atr * 3 if direction == Direction.LONG else entry_price - atr * 3
            
            # Adjust for event risk
            event_risk = self._get_event_risk(symbol, bar.timestamp)
            if event_risk > 0.5:
                continue  # Too much event risk
            
            signal = Signal.create_entry(
                strategy_id=self.config.strategy_id,
                strategy_name=self.config.name,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence * (1 - event_risk),
                position_size_pct=self.config.risk_per_trade * 0.5,  # Reduced size for news trading
                timeframe=bar.timeframe,
                reasoning=f"News sentiment: {sentiment:.2f} ({sentiment_data['news_count']} articles)",
            )
            signals.append(signal)
        
        return signals
    
    def _has_high_impact_event(self, symbol: str, timestamp: datetime) -> bool:
        """Check if there's a high-impact event soon for this symbol."""
        base_currency = symbol[:3]
        quote_currency = symbol[3:6]
        
        for event in self._event_calendar:
            if event["currency"] in (base_currency, quote_currency):
                if event["impact"] == "high":
                    time_diff = (event["time"] - timestamp).total_seconds() / 3600
                    if 0 < time_diff < 24:  # Within 24 hours
                        return True
        return False
    
    def _get_event_risk(self, symbol: str, timestamp: datetime) -> float:
        """Calculate event risk for a symbol."""
        risk = 0.0
        base_currency = symbol[:3]
        quote_currency = symbol[3:6]
        
        for event in self._event_calendar:
            if event["currency"] in (base_currency, quote_currency):
                time_diff = (event["time"] - timestamp).total_seconds() / 3600
                if 0 < time_diff < 48:
                    impact_weight = {"high": 0.3, "medium": 0.15, "low": 0.05}.get(event["impact"], 0)
                    risk += impact_weight * max(0, 1 - time_diff / 48)
        
        return min(1.0, risk)
    
    def _calculate_atr(self, symbol: str, bar: Bar) -> float:
        """Calculate ATR for stop loss."""
        # Simplified ATR - in production would use historical data
        return (bar.high - bar.low) * 1.5


class PairsTradingStrategy(BaseStrategy):
    """
    Statistical arbitrage / pairs trading strategy.
    
    Features:
    - Cointegration testing for pair selection
    - Z-score based entry/exit signals
    - Dynamic hedge ratio calculation
    - Mean reversion with half-life estimation
    - Multi-pair portfolio management
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.lookback_period = config.parameters.get("lookback_period", 252)
        self.entry_zscore = config.parameters.get("entry_zscore", 2.0)
        self.exit_zscore = config.parameters.get("exit_zscore", 0.5)
        self.stop_zscore = config.parameters.get("stop_zscore", 3.5)
        self.min_correlation = config.parameters.get("min_correlation", 0.7)
        self.min_cointegration_pvalue = config.parameters.get("min_cointegration_pvalue", 0.05)
        self.max_pairs = config.parameters.get("max_pairs", 10)
        self.half_life_lookback = config.parameters.get("half_life_lookback", 63)
        
        # Pair tracking
        self._pairs: dict[str, dict] = {}
        self._price_history: dict[str, deque] = {}
        self._pair_positions: dict[str, dict] = {}
        
    async def _initialize(self) -> None:
        logger.info(f"PairsTradingStrategy initialized for {self.config.symbols}")
        await self._identify_pairs()
    
    async def _identify_pairs(self) -> None:
        """Identify cointegrated pairs from symbol universe."""
        symbols = self.config.symbols
        if len(symbols) < 2:
            return
        
        # In production, would fetch historical prices and test cointegration
        # For now, define some known forex pairs
        forex_pairs = [
            ("EURUSD", "GBPUSD", 0.85),
            ("EURUSD", "AUDUSD", 0.72),
            ("GBPUSD", "EURGBP", 0.78),
            ("USDJPY", "USDCHF", 0.65),
            ("AUDUSD", "NZDUSD", 0.88),
        ]
        
        for sym1, sym2, corr in forex_pairs:
            if sym1 in symbols and sym2 in symbols:
                pair_id = f"{sym1}_{sym2}"
                self._pairs[pair_id] = {
                    "symbol1": sym1,
                    "symbol2": sym2,
                    "correlation": corr,
                    "hedge_ratio": 1.0,  # Would be calculated from regression
                    "mean_spread": 0.0,
                    "std_spread": 1.0,
                    "half_life": 5,
                    "active": True
                }
                
                # Initialize price history
                if sym1 not in self._price_history:
                    self._price_history[sym1] = deque(maxlen=self.lookback_period)
                if sym2 not in self._price_history:
                    self._price_history[sym2] = deque(maxlen=self.lookback_period)
        
        logger.info(f"PairsTradingStrategy identified {len(self._pairs)} pairs")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        # Update price history
        self._price_history[bar.symbol].append(bar.close)
        
        # Check each active pair
        for pair_id, pair in self._pairs.items():
            if not pair["active"]:
                continue
            
            sym1, sym2 = pair["symbol1"], pair["symbol2"]
            
            if len(self._price_history[sym1]) < 20 or len(self._price_history[sym2]) < 20:
                continue
            
            # Calculate current spread
            prices1 = np.array(list(self._price_history[sym1]))
            prices2 = np.array(list(self._price_history[sym2]))
            
            # Hedge ratio (simplified - would use OLS in production)
            hedge_ratio = pair["hedge_ratio"]
            spread = prices1[-1] - hedge_ratio * prices2[-1]
            
            # Update rolling statistics
            recent_spreads = prices1[-20:] - hedge_ratio * prices2[-20:]
            mean_spread = np.mean(recent_spreads)
            std_spread = np.std(recent_spreads)
            
            if std_spread == 0:
                continue
            
            zscore = (spread - mean_spread) / std_spread
            
            # Check for existing position
            position_key = f"{pair_id}_position"
            has_position = position_key in self._pair_positions
            
            if not has_position:
                # Entry signals
                if zscore > self.entry_zscore:
                    # Short spread: short sym1, long sym2
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.SHORT, Direction.LONG,
                        zscore, pair, bar, "pairs_entry_short"
                    ))
                    self._pair_positions[position_key] = {"direction": "short_spread", "zscore": zscore}
                    
                elif zscore < -self.entry_zscore:
                    # Long spread: long sym1, short sym2
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.LONG, Direction.SHORT,
                        zscore, pair, bar, "pairs_entry_long"
                    ))
                    self._pair_positions[position_key] = {"direction": "long_spread", "zscore": zscore}
            else:
                # Exit signals
                position = self._pair_positions[position_key]
                if position["direction"] == "short_spread" and zscore < self.exit_zscore:
                    # Exit short spread
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.LONG, Direction.SHORT,
                        zscore, pair, bar, "pairs_exit_short"
                    ))
                    del self._pair_positions[position_key]
                    
                elif position["direction"] == "long_spread" and zscore > -self.exit_zscore:
                    # Exit long spread
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.SHORT, Direction.LONG,
                        zscore, pair, bar, "pairs_exit_long"
                    ))
                    del self._pair_positions[position_key]
                
                # Stop loss
                elif position["direction"] == "short_spread" and zscore > self.stop_zscore:
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.LONG, Direction.SHORT,
                        zscore, pair, bar, "pairs_stop_short"
                    ))
                    del self._pair_positions[position_key]
                    
                elif position["direction"] == "long_spread" and zscore < -self.stop_zscore:
                    signals.extend(self._create_pair_signals(
                        sym1, sym2, Direction.SHORT, Direction.LONG,
                        zscore, pair, bar, "pairs_stop_long"
                    ))
                    del self._pair_positions[position_key]
        
        return signals
    
    def _create_pair_signals(self, sym1: str, sym2: str, dir1: Direction, dir2: Direction,
                            zscore: float, pair: dict, bar: Bar, reasoning: str) -> list[Signal]:
        """Create paired signals for both legs."""
        signals = []
        
        # Calculate position sizes
        entry_price1 = bar.close if bar.symbol == sym1 else self._price_history[sym1][-1]
        entry_price2 = bar.close if bar.symbol == sym2 else self._price_history[sym2][-1]
        
        # Risk per leg
        risk_per_leg = self.config.risk_per_trade * 0.5
        
        # Leg 1
        atr1 = (bar.high - bar.low) * 1.5 if bar.symbol == sym1 else 0.001
        stop1 = entry_price1 - atr1 * 2 if dir1 == Direction.LONG else entry_price1 + atr1 * 2
        target1 = entry_price1 + atr1 * 3 if dir1 == Direction.LONG else entry_price1 - atr1 * 3
        
        signal1 = Signal.create_entry(
            strategy_id=self.config.strategy_id,
            strategy_name=self.config.name,
            symbol=sym1,
            direction=dir1,
            entry_price=entry_price1,
            stop_loss=stop1,
            take_profit=target1,
            confidence=min(0.8, abs(zscore) / 3),
            position_size_pct=risk_per_leg,
            timeframe=bar.timeframe,
            reasoning=f"{reasoning}: zscore={zscore:.2f}",
        )
        signals.append(signal1)
        
        # Leg 2
        atr2 = (bar.high - bar.low) * 1.5 if bar.symbol == sym2 else 0.001
        stop2 = entry_price2 - atr2 * 2 if dir2 == Direction.LONG else entry_price2 + atr2 * 2
        target2 = entry_price2 + atr2 * 3 if dir2 == Direction.LONG else entry_price2 - atr2 * 3
        
        signal2 = Signal.create_entry(
            strategy_id=self.config.strategy_id,
            strategy_name=self.config.name,
            symbol=sym2,
            direction=dir2,
            entry_price=entry_price2,
            stop_loss=stop2,
            take_profit=target2,
            confidence=min(0.8, abs(zscore) / 3),
            position_size_pct=risk_per_leg,
            timeframe=bar.timeframe,
            reasoning=f"{reasoning}: zscore={zscore:.2f} (hedge)",
        )
        signals.append(signal2)
        
        return signals


class MomentumTradingStrategy(BaseStrategy):
    """
    Momentum trading strategy capturing trend continuation.
    
    Features:
    - Multi-timeframe momentum alignment
    - Rate of Change (ROC) and RSI momentum
    - Volume-weighted momentum
    - Breakout confirmation
    - Trend strength filtering (ADX)
    - Momentum reversal detection
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.momentum_period = config.parameters.get("momentum_period", 14)
        self.roc_period = config.parameters.get("roc_period", 10)
        self.rsi_period = config.parameters.get("rsi_period", 14)
        self.adx_period = config.parameters.get("adx_period", 14)
        self.adx_threshold = config.parameters.get("adx_threshold", 25)
        self.momentum_threshold = config.parameters.get("momentum_threshold", 0.02)
        self.volume_factor = config.parameters.get("volume_factor", 1.5)
        self.trend_confirmation = config.parameters.get("trend_confirmation", True)
        
        # State
        self._bar_buffer: dict[str, deque] = {}
        self._momentum_cache: dict[str, float] = {}
        
    async def _initialize(self) -> None:
        logger.info(f"MomentumTradingStrategy initialized for {self.config.symbols}")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        # Update buffer
        if bar.symbol not in self._bar_buffer:
            self._bar_buffer[bar.symbol] = deque(maxlen=200)
        self._bar_buffer[bar.symbol].append(bar)
        
        if len(self._bar_buffer[bar.symbol]) < max(self.momentum_period, self.adx_period) + 10:
            return signals
        
        df = self._bars_to_dataframe(self._bar_buffer[bar.symbol])
        
        # Calculate indicators
        df["roc"] = df["close"].pct_change(self.roc_period)
        df["rsi"] = self._rsi(df["close"], self.rsi_period)
        df["adx"] = self._adx(df, self.adx_period)
        
        # Volume momentum
        df["volume_sma"] = df["volume"].rolling(20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]
        
        # Trend EMAs
        df["ema_20"] = df["close"].ewm(span=20).mean()
        df["ema_50"] = df["close"].ewm(span=50).mean()
        df["ema_200"] = df["close"].ewm(span=200).mean()
        
        current = df.iloc[-1]
        df.iloc[-2] if len(df) > 1 else current
        
        # Momentum signals
        momentum = current["roc"]
        rsi = current["rsi"]
        adx = current["adx"]
        volume_ratio = current["volume_ratio"]
        
        # Trend direction
        trend_up = current["ema_20"] > current["ema_50"] > current["ema_200"]
        trend_down = current["ema_20"] < current["ema_50"] < current["ema_200"]
        
        # Momentum confirmation
        strong_momentum = abs(momentum) > self.momentum_threshold
        volume_confirmed = volume_ratio > self.volume_factor
        trend_strong = adx > self.adx_threshold
        
        entry_price = current["close"]
        atr = self._atr(df, 14).iloc[-1]
        
        # Long momentum signal
        if (strong_momentum and 
            rsi < 70 and  # Not overbought
            trend_up and
            trend_strong and
            volume_confirmed):
            
            # Trend confirmation check
            if self.trend_confirmation and not (current["ema_20"] > current["ema_50"]):
                raise NotImplementedError("Not implemented")  # Skip if trend not confirmed
            else:
                stop_loss = entry_price - atr * 2
                take_profit = entry_price + atr * 3
                
                signal = Signal.create_entry(
                    strategy_id=self.config.strategy_id,
                    strategy_name=self.config.name,
                    symbol=bar.symbol,
                    direction=Direction.LONG,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=min(0.85, (adx / 50) * (volume_ratio / 2)),
                    position_size_pct=self.config.risk_per_trade,
                    timeframe=bar.timeframe,
                    reasoning=f"Momentum: ROC={momentum:.4f}, RSI={rsi:.1f}, ADX={adx:.1f}, VolRatio={volume_ratio:.2f}",
                )
                signals.append(signal)
        
        # Short momentum signal
        elif (strong_momentum and 
              rsi > 30 and  # Not oversold
              trend_down and
              trend_strong and
              volume_confirmed):
            
            if self.trend_confirmation and not (current["ema_20"] < current["ema_50"]):
                raise NotImplementedError("Not implemented")
            else:
                stop_loss = entry_price + atr * 2
                take_profit = entry_price - atr * 3
                
                signal = Signal.create_entry(
                    strategy_id=self.config.strategy_id,
                    strategy_name=self.config.name,
                    symbol=bar.symbol,
                    direction=Direction.SHORT,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=min(0.85, (adx / 50) * (volume_ratio / 2)),
                    position_size_pct=self.config.risk_per_trade,
                    timeframe=bar.timeframe,
                    reasoning=f"Momentum: ROC={momentum:.4f}, RSI={rsi:.1f}, ADX={adx:.1f}, VolRatio={volume_ratio:.2f}",
                )
                signals.append(signal)
        
        return signals
    
    def _rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _adx(self, df, period: int = 14) -> np.ndarray:
        """Calculate ADX."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        tr1 = high - low
        tr2 = np.abs(high - close.shift())
        tr3 = np.abs(low - close.shift())
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (-minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(period).mean()
    
    def _atr(self, df, period: int = 14):
        """Calculate ATR."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        tr1 = high - low
        tr2 = np.abs(high - close.shift())
        tr3 = np.abs(low - close.shift())
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        return tr.rolling(period).mean()
    
    def _bars_to_dataframe(self, bars: deque) -> np.ndarray:
        """Convert bars to structured array."""
        import polars as pl
        data = []
        for bar in bars:
            data.append({
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            })
        return pl.DataFrame(data)
_original_create_strategy = create_strategy

def create_strategy(strategy_type: StrategyType, config: StrategyConfig) -> BaseStrategy:
    """Factory function to create strategies by type."""
    style_strategies = {
        StrategyType.SCALPING: ScalpingStrategy,
        StrategyType.DAY_TRADING: DayTradingStrategy,
        StrategyType.SWING_TRADING: SwingTradingStrategy,
        StrategyType.POSITION_TRADING: PositionTradingStrategy,
    }
    
    advanced_strategies = {
        StrategyType.NEWS_BASED: NewsBasedTradingStrategy,
        StrategyType.PAIRS_TRADING: PairsTradingStrategy,
        StrategyType.MOMENTUM: MomentumTradingStrategy,
    }
    
    if strategy_type in style_strategies:
        return style_strategies[strategy_type](config)
    
    if strategy_type in advanced_strategies:
        return advanced_strategies[strategy_type](config)
    
    return _original_create_strategy(strategy_type, config)
