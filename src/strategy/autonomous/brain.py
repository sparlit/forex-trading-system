"""
Autonomous Trading Brain
=========================

The central decision-making engine for fully autonomous trading.
This module integrates all components: market analysis, strategy selection,
risk management, position sizing, and trade execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from loguru import logger

from src.data.models import (
    Bar,
    Direction,
    OrderSide,
    OrderType,
    Position,
    Signal,
    Symbol,
    Tick,
    Timeframe,
)
from src.execution.order_manager import Order, OrderManager
from src.infra.config.settings import settings
from src.risk.portfolio_risk import PortfolioRiskManager
from src.risk.position_sizer import PositionSizer
from src.strategy.base.strategy import BaseStrategy, StrategyConfig, StrategyRegistry
from src.strategy.market_regime import MarketRegimeDetector, RegimeType
from src.strategy.ml.next_candle_predictor import (
    CandlePrediction,
    NextCandleConfig,
    NextCandlePredictor,
)
from src.strategy.ml.strategies import (
    BreakoutStrategy,
    EnsembleStrategy,
    MeanReversionStrategy,
    TrendFollowingStrategy,
)
from src.strategy.session_manager import session_manager


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BrainState(str, Enum):
    """State of the autonomous brain."""
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    DECIDING = "deciding"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass(slots=True)
class MarketContext:
    """Current market context for decision making."""
    timestamp: datetime
    symbols: dict[str, Symbol]
    ticks: dict[str, Tick]
    bars: dict[str, list[Bar]]  # symbol -> recent bars
    positions: dict[str, Position]
    account_balance: float
    account_equity: float
    free_margin: float
    margin_level: float
    regime: RegimeType | None = None
    volatility: dict[str, float] = field(default_factory=dict)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)


@dataclass(slots=True)
class TradingDecision:
    """A complete trading decision with all parameters."""
    symbol: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    confidence: float
    strategy_id: str
    reasoning: str
    risk_reward_ratio: float
    expected_value: float
    max_risk_pct: float
    timestamp: datetime = field(default_factory=_utc_now)


class AutonomousBrain:
    """
    The central autonomous trading brain.
    
    This class orchestrates the entire trading process:
    1. Market data ingestion and analysis
    2. Market regime detection
    3. Strategy selection and signal generation
    4. Risk assessment and position sizing
    5. Trade execution and monitoring
    6. Continuous learning and adaptation
    """
    
    def __init__(
        self,
        order_manager: OrderManager,
        risk_manager: PortfolioRiskManager,
        position_sizer: PositionSizer,
        symbols: list[str] | None = None,
    ):
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.position_sizer = position_sizer
        self.symbols = symbols or []
        
        # State
        self.state = BrainState.INITIALIZING
        self._running = False
        self._main_task: asyncio.Task | None = None
        self._market_context: MarketContext | None = None
        
        # Components
        self.regime_detector = MarketRegimeDetector()
        self.strategy_registry = StrategyRegistry()
        self.active_strategies: dict[str, BaseStrategy] = {}
        
        # Performance tracking
        self.decisions_made = 0
        self.trades_executed = 0
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        self.max_daily_drawdown = 0.0
        self.session_start = datetime.now(UTC)
        
        # Risk limits
        self.max_daily_loss = settings.risk_daily_loss_limit
        self.max_drawdown = settings.risk_max_drawdown
        self.max_portfolio_risk = settings.risk_max_portfolio_risk
        
        # Callbacks
        self.on_decision: Callable[[TradingDecision], None] | None = None
        self.on_trade: Callable[[Order], None] | None = None
        self.on_error: Callable[[Exception], None] | None = None
        

        # Next Candle Predictor
        self.next_candle_predictor = NextCandlePredictor()
        self.next_candle_config = NextCandleConfig()
        self.next_candle_predictions: dict[str, CandlePrediction] = {}
        self.prediction_feedback_loop_active = True
        
        # Initialize strategies
        self._init_strategies()
        
    def _init_strategies(self) -> None:
        """Initialize all available strategies."""
        # ML Ensemble Strategy
        ensemble_config = StrategyConfig(
            strategy_id="ensemble_ml",
            name="Ensemble ML Strategy",
            description="ML ensemble combining multiple models",
            asset_classes=["forex", "metals", "crypto"],
            timeframes=[Timeframe.M15, Timeframe.H1, Timeframe.H4],
            symbols=self.symbols,
            parameters={
                "lookback": 100,
                "prediction_horizon": 10,
                "hidden_size": 128,
                "num_layers": 2,
                "dropout": 0.2,
                "learning_rate": 0.001,
            },
            min_confidence=0.65,
            risk_per_trade=0.02,
        )
        self.active_strategies["ensemble_ml"] = EnsembleStrategy(ensemble_config)
        
        # Trend Following Strategy
        trend_config = StrategyConfig(
            strategy_id="trend_following",
            name="Trend Following Strategy",
            description="EMA crossover with ADX filter",
            asset_classes=["forex", "metals", "indices"],
            timeframes=[Timeframe.H1, Timeframe.H4, Timeframe.D1],
            symbols=self.symbols,
            parameters={
                "fast_ema": 20,
                "slow_ema": 50,
                "adx_threshold": 20,
                "atr_multiplier": 2.0,
            },
            min_confidence=0.6,
            risk_per_trade=0.015,
        )
        self.active_strategies["trend_following"] = TrendFollowingStrategy(trend_config)
        
        # Mean Reversion Strategy
        mean_rev_config = StrategyConfig(
            strategy_id="mean_reversion",
            name="Mean Reversion Strategy",
            description="Bollinger Bands + RSI mean reversion",
            asset_classes=["forex", "crypto"],
            timeframes=[Timeframe.M15, Timeframe.H1, Timeframe.H4],
            symbols=self.symbols,
            parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
            },
            min_confidence=0.55,
            risk_per_trade=0.015,
        )
        self.active_strategies["mean_reversion"] = MeanReversionStrategy(mean_rev_config)
        
        # Breakout Strategy
        breakout_config = StrategyConfig(
            strategy_id="breakout",
            name="Breakout Strategy",
            description="Donchian channel breakout with volume filter",
            asset_classes=["forex", "crypto", "metals"],
            timeframes=[Timeframe.H1, Timeframe.H4],
            symbols=self.symbols,
            parameters={
                "channel_period": 20,
                "volume_threshold": 1.5,
                "atr_filter": True,
            },
            min_confidence=0.6,
            risk_per_trade=0.02,
        )
        self.active_strategies["breakout"] = BreakoutStrategy(breakout_config)
        
        logger.info(f"Initialized {len(self.active_strategies)} strategies")
    
    async def start(self) -> None:
        """Start the autonomous trading brain."""
        if self._running:
            logger.warning("Brain already running")
            return
            
        self._running = True
        self.state = BrainState.ANALYZING
        self.session_start = datetime.now(UTC)
        
        # Initialize all strategies
        for strategy_id, strategy in self.active_strategies.items():
            try:
                await strategy.initialize()
                logger.info(f"Strategy {strategy_id} initialized")
            except Exception as e:
                logger.error(f"Failed to initialize {strategy_id}: {e}")
                if self.on_error:
                    self.on_error(e)
        
        # Start main loop
        self._main_task = asyncio.create_task(self._main_loop())
        logger.info("Autonomous brain started")
    
    async def stop(self) -> None:
        """Stop the autonomous trading brain."""
        self._running = False
        self.state = BrainState.STOPPING
        
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                raise NotImplementedError("Not implemented")
        
        # Close all positions if needed
        await self._close_all_positions()
        
        logger.info("Autonomous brain stopped")
    
    async def pause(self) -> None:
        """Pause the brain (keep positions, stop new trades)."""
        self._running = False
        self.state = BrainState.PAUSED
        logger.info("Autonomous brain paused")
    
    async def resume(self) -> None:
        """Resume the brain."""
        if not self._running:
            self._running = True
            self.state = BrainState.ANALYZING
            self._main_task = asyncio.create_task(self._main_loop())
            logger.info("Autonomous brain resumed")
    
    async def _main_loop(self) -> None:
        """Main autonomous trading loop."""
        while self._running:
            try:
                cycle_start = datetime.now(UTC)
                
                # 1. Analyze market
                self.state = BrainState.ANALYZING
                await self._analyze_market()
                
                # 2. Check risk limits
                if not await self._check_risk_limits():
                    logger.warning("Risk limits exceeded, pausing new trades")
                    await asyncio.sleep(60)
                    continue
                
                # 3. Make decisions
                self.state = BrainState.DECIDING
                decisions = await self._make_decisions()
                
                # 4. Execute decisions
                if decisions:
                    self.state = BrainState.EXECUTING
                    await self._execute_decisions(decisions)
                
                # 5. Monitor existing positions
                self.state = BrainState.MONITORING
                await self._monitor_positions()
                
                # 6. Update performance metrics
                await self._update_performance()
                
                # Sleep until next cycle (1 minute default)
                cycle_time = (datetime.now(UTC) - cycle_start).total_seconds()
                sleep_time = max(1, 60 - cycle_time)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                if self.on_error:
                    self.on_error(e)
                await asyncio.sleep(10)  # Brief pause before retry
    
    async def _analyze_market(self) -> None:
        """Analyze current market conditions with next candle prediction and session awareness."""
        # Update session information
        session_info = await session_manager.update()
        self._current_session_info = session_info
        
        # Dynamic symbol selection based on active session
        recommended_pairs = session_info.get("recommended_pairs", [])
        active_session_mode = session_info.get("primary_mode", "standby")
        
        # Update symbols based on active session
        if active_session_mode != "standby" and recommended_pairs:
            # Use session-recommended pairs, but filter by configured symbols
            session_symbols = [s for s in recommended_pairs if s in self.symbols]
            if session_symbols:
                self._active_session_symbols = session_symbols
                logger.info(f"Session mode: {session_info.get('primary_mode')}, Active symbols: {session_symbols}")
            else:
                # Fallback to configured symbols
                self._active_session_symbols = self.symbols
        else:
            # No active session, use crypto if available or all symbols
            self._active_session_symbols = self.symbols
        
        # This would fetch real data from MT5/CCXT providers
        # For now, we simulate the structure
        self._market_context = MarketContext(
            timestamp=datetime.now(UTC),
            symbols={},
            ticks={},
            bars={},
            positions={},
            account_balance=100000.0,
            account_equity=100000.0,
            free_margin=100000.0,
            margin_level=1000.0,
        )
        
        # Detect market regime
        if self._market_context.bars:
            primary_symbol = self._active_session_symbols[0] if self._active_session_symbols else "EURUSD"
            if primary_symbol in self._market_context.bars:
                bars = self._market_context.bars[primary_symbol]
                if len(bars) >= 50:
                    regime = await self.regime_detector.detect_regime(bars)
                    self._market_context.regime = regime
                    logger.debug(f"Detected regime: {regime.value}")
        
        # Calculate volatility and correlations
        await self._calculate_market_metrics()
        
        # Next candle prediction for active symbols
        if self._active_session_symbols and self.prediction_feedback_loop_active:
            await self._predict_next_candles()

    async def _predict_next_candles(self) -> None:
        """Generate next candle predictions for session-active symbols."""
        try:
            # Initialize predictor if not done
            if not hasattr(self, 'next_candle_predictor') or self.next_candle_predictor is None:
                self.next_candle_predictor = NextCandlePredictor()
                # Use session-aware symbols
                symbols_to_predict = getattr(self, '_active_session_symbols', self.symbols)
                await self.next_candle_predictor.initialize(symbols_to_predict)
            
            symbols_to_predict = getattr(self, '_active_session_symbols', self.symbols)
            
            for symbol in symbols_to_predict:
                if symbol in self._market_context.bars:
                    bars = self._market_context.bars[symbol]
                    if len(bars) >= self.next_candle_config.lookback:
                        # Get latest bar for prediction
                        latest_bar = bars[-1]
                        
                        # Predict next candle
                        prediction = await self.next_candle_predictor.predict_next_candle(latest_bar)
                        if prediction:
                            self.next_candle_predictions[symbol] = prediction
                            
                            # Log high-confidence predictions
                            if prediction.direction_confidence >= self.next_candle_config.confidence_threshold:
                                logger.info(
                                    f"Next candle prediction for {symbol}: "
                                    f"{prediction.direction.value} (conf={prediction.direction_confidence:.2f}, "
                                    f"prob={prediction.direction_probability:.2f})"
                                )
            
            # Self-correction feedback loop
            if hasattr(self, 'next_candle_predictor') and self.next_candle_predictor:
                # Update with actual bars for learning
                symbols_to_predict = getattr(self, '_active_session_symbols', self.symbols)
                for symbol in symbols_to_predict:
                    if symbol in self._market_context.bars:
                        latest_bar = self._market_context.bars[symbol][-1]
                        self.next_candle_predictor.update_with_actual(latest_bar)
                
                # Process self-correction for all predictions
                for symbol, prediction in self.next_candle_predictions.items():
                    await self.next_candle_predictor._self_correct(prediction)
                    
        except Exception as e:
            logger.error(f"Next candle prediction error: {e}")
    
    async def _calculate_market_metrics(self) -> None:
        """Calculate volatility, correlations, etc."""
        # Placeholder for real implementation
    
    async def _check_risk_limits(self) -> bool:
        """Check if we're within risk limits."""
        # Daily loss limit
        if self.daily_pnl < -self.max_daily_loss * self._market_context.account_balance:
            logger.warning(f"Daily loss limit exceeded: {self.daily_pnl}")
            return False
        
        # Max drawdown
        if self.max_daily_drawdown > self.max_drawdown:
            logger.warning(f"Max drawdown exceeded: {self.max_daily_drawdown}")
            return False
        
        # Portfolio risk
        portfolio_risk = await self.risk_manager.calculate_portfolio_risk(
            self._market_context.positions,
            self._market_context.symbols,
        )
        if portfolio_risk > self.max_portfolio_risk:
            logger.warning(f"Portfolio risk exceeded: {portfolio_risk}")
            return False
        
        return True
    
    async def _make_decisions(self) -> list[TradingDecision]:
        """Generate trading decisions from all strategies."""
        all_decisions = []
        
        for strategy_id, strategy in self.active_strategies.items():
            if not strategy.is_active:
                continue
            
            try:
                # Get signals from strategy
                signals = await strategy.generate_signals(self._market_context)
                
                for signal in signals:
                    # Convert signal to decision
                    decision = await self._signal_to_decision(signal, strategy_id)
                    if decision and await self._validate_decision(decision):
                        all_decisions.append(decision)
                        
            except Exception as e:
                logger.error(f"Error generating signals for {strategy_id}: {e}")
                if self.on_error:
                    self.on_error(e)
        
        # Rank and filter decisions
        all_decisions.sort(key=lambda d: d.expected_value, reverse=True)
        
        # Limit concurrent signals
        max_signals = settings.strategy_max_concurrent_signals
        return all_decisions[:max_signals]
    
    async def _signal_to_decision(
        self, 
        signal: Signal, 
        strategy_id: str
    ) -> TradingDecision | None:
        """Convert a signal to a complete trading decision."""
        # Get current market price
        tick = self._market_context.ticks.get(signal.symbol)
        if not tick:
            return None
        
        entry_price = tick.ask if signal.direction == Direction.LONG else tick.bid
        
        # Calculate position size
        volume = await self.position_sizer.calculate_size(
            symbol=signal.symbol,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            account_balance=self._market_context.account_balance,
            risk_pct=self.active_strategies[strategy_id].config.risk_per_trade,
        )
        
        if volume <= 0:
            return None
        
        # Calculate risk/reward
        risk = abs(entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        # Expected value calculation
        win_rate = self.active_strategies[strategy_id].performance.win_rate or 0.5
        expected_value = (win_rate * reward) - ((1 - win_rate) * risk)
        
        return TradingDecision(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            volume=volume,
            confidence=signal.confidence,
            strategy_id=strategy_id,
            reasoning=signal.reasoning or f"Signal from {strategy_id}",
            risk_reward_ratio=risk_reward,
            expected_value=expected_value,
            max_risk_pct=self.active_strategies[strategy_id].config.risk_per_trade,
        )
    
    async def _validate_decision(self, decision: TradingDecision) -> bool:
        """Validate a trading decision against risk rules."""
        # Minimum risk/reward
        if decision.risk_reward_ratio < 1.5:
            return False
        
        # Minimum expected value
        if decision.expected_value <= 0:
            return False
        
        # Confidence threshold
        strategy = self.active_strategies[decision.strategy_id]
        if decision.confidence < strategy.config.min_confidence:
            return False
        
        # Check correlation with existing positions
        # (placeholder - would check actual correlations)
        
        # Check max positions per strategy
        strategy_positions = sum(
            1 for p in self._market_context.positions.values()
            if p.strategy_id == decision.strategy_id
        )
        if strategy_positions >= strategy.config.max_positions:
            return False
        
        return True
    
    async def _execute_decisions(self, decisions: list[TradingDecision]) -> None:
        """Execute validated trading decisions."""
        for decision in decisions:
            try:
                # Create order
                order = Order(
                    symbol=decision.symbol,
                    side=OrderSide.BUY if decision.direction == Direction.LONG else OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=decision.volume,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                    strategy_id=decision.strategy_id,
                    metadata={
                        "confidence": decision.confidence,
                        "reasoning": decision.reasoning,
                        "expected_value": decision.expected_value,
                    }
                )
                
                # Place order
                result = await self.order_manager.place_order(order)
                
                if result and result.status in ["filled", "partial"]:
                    self.trades_executed += 1
                    self.decisions_made += 1
                    
                    if self.on_trade:
                        self.on_trade(result)
                    
                    logger.info(
                        f"Executed: {decision.symbol} {decision.direction.value} "
                        f"{decision.volume} lots @ {decision.entry_price} "
                        f"(SL: {decision.stop_loss}, TP: {decision.take_profit})"
                    )
                else:
                    logger.warning(f"Order failed or pending: {result}")
                    
            except Exception as e:
                logger.error(f"Error executing decision: {e}")
                if self.on_error:
                    self.on_error(e)
    
    async def _monitor_positions(self) -> None:
        """Monitor and manage existing positions."""
        # Check for stop loss / take profit hits
        # Update trailing stops
        # Check for regime changes that invalidate positions
        
        for position in self._market_context.positions.values():
            # Update unrealized PnL
            tick = self._market_context.ticks.get(position.symbol)
            if tick:
                raise NotImplementedError("Not implemented")
                # Update position PnL
        
        # Check daily PnL
        await self._update_daily_pnl()
    
    async def _update_daily_pnl(self) -> None:
        """Update daily PnL tracking."""
        # Calculate current daily PnL
        # Update max drawdown
    
    async def _update_performance(self) -> None:
        """Update performance metrics."""
        # Update strategy performance
        for strategy in self.active_strategies.values():
            await strategy.update_performance()
    
    async def _close_all_positions(self) -> None:
        """Close all open positions."""
        for position in self._market_context.positions.values():
            try:
                order = Order(
                    symbol=position.symbol,
                    side=OrderSide.SELL if position.side == "buy" else OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=position.volume,
                    strategy_id=position.strategy_id,
                    metadata={"reason": "brain_shutdown"}
                )
                await self.order_manager.place_order(order)
            except Exception as e:
                logger.error(f"Error closing position {position.symbol}: {e}")
    
    def get_status(self) -> dict[str, Any]:
        """Get current brain status."""
        return {
            "state": self.state.value,
            "running": self._running,
            "session_duration": str(datetime.now(UTC) - self.session_start),
            "strategies_active": len(self.active_strategies),
            "decisions_made": self.decisions_made,
            "trades_executed": self.trades_executed,
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "max_drawdown": self.max_daily_drawdown,
            "current_regime": self._market_context.regime.value if self._market_context and self._market_context.regime else None,
            "open_positions": len(self._market_context.positions) if self._market_context else 0,
        }


# Factory function
async def create_autonomous_brain(
    order_manager: OrderManager,
    risk_manager: PortfolioRiskManager,
    position_sizer: PositionSizer,
    symbols: list[str] | None = None,
) -> AutonomousBrain:
    """Create and initialize an autonomous trading brain."""
    brain = AutonomousBrain(
        order_manager=order_manager,
        risk_manager=risk_manager,
        position_sizer=position_sizer,
        symbols=symbols,
    )
    await brain.start()
    return brain
