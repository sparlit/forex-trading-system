"""
Elite Autonomous Quantum Trading System - Autonomous Decision Engine
Zero-user-input decision making engine for fully autonomous trading.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np

from src.infra.config.settings import settings
from src.risk.risk_circuit_breaker import circuit_breaker_manager
from src.strategy.session_manager import session_manager

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of autonomous decisions."""
    ENTRY = "entry"
    EXIT = "exit"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"
    ADJUST_SL = "adjust_sl"
    ADJUST_TP = "adjust_tp"
    HEDGE = "hedge"
    REBALANCE = "rebalance"
    RISK_REDUCTION = "risk_reduction"
    PORTFOLIO_OPTIMIZE = "portfolio_optimize"


class DecisionConfidence(Enum):
    """Confidence levels for decisions."""
    VERY_LOW = 0.1
    LOW = 0.3
    MEDIUM = 0.5
    HIGH = 0.7
    VERY_HIGH = 0.9


@dataclass
class AutonomousDecision:
    """Represents an autonomous trading decision."""
    decision_id: str
    decision_type: DecisionType
    symbol: str
    confidence: float
    reasoning: str
    parameters: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    executed: bool = False
    result: dict[str, Any] | None = None


@dataclass
class MarketContext:
    """Current market context for decision making."""
    symbol: str
    regime: str
    trend: str
    volatility: float
    liquidity: float
    sentiment: float
    session: str
    time_to_session_end: timedelta
    correlation_risk: float
    portfolio_exposure: float


@dataclass
class DecisionContext:
    """Context for decision making."""
    timestamp: datetime
    symbol: str
    market_data: Any
    prediction: Any
    analysis: Any
    selection: Any
    account_balance: float
    risk_limit: float


@dataclass
class TradingDecision:
    """Represents a trading decision."""
    decision_id: str
    symbol: str
    direction: str  # "long", "short", "market_make"
    size: float
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    metadata: dict[str, Any]


class AutonomousDecisionEngine:
    """
    Fully autonomous decision engine that makes trading decisions
    without any user input or intervention.
    """

    def __init__(self):
        self.decisions: dict[str, AutonomousDecision] = {}
        self.decision_history: list[AutonomousDecision] = []
        self.active_symbols: set[str] = set()
        self.decision_interval = timedelta(seconds=30)
        self.last_decision_time: dict[str, datetime] = {}
        self.min_confidence_threshold = 0.6
        self.max_decisions_per_symbol = 5
        self.decision_cooldown = timedelta(minutes=5)

        # ML models for decision making
        self.regime_classifier = None
        self.sentiment_analyzer = None
        self.volatility_predictor = None
        self.correlation_monitor = None

        # Risk parameters
        self.max_portfolio_risk = settings.risk_max_portfolio_risk
        self.max_drawdown = settings.risk_max_drawdown
        self.max_correlation = settings.risk_max_correlation

        logger.info("Autonomous Decision Engine initialized")

    async def initialize(self) -> None:
        """Initialize the decision engine and load ML models."""
        await self._load_models()
        await self._initialize_session_tracking()
        logger.info("Decision Engine fully initialized")

    async def _load_models(self) -> None:
        """Load ML models for decision making."""
        try:
            # In production, load actual trained models
            # self.regime_classifier = await load_model("regime_classifier")
            # self.sentiment_analyzer = await load_model("sentiment_analyzer")
            # self.volatility_predictor = await load_model("volatility_predictor")
            logger.info("ML models loaded (placeholder)")
        except Exception as e:
            logger.warning(f"Could not load ML models: {e}")

    async def _initialize_session_tracking(self) -> None:
        """Initialize session tracking for session-aware decisions."""
        session_info = await session_manager.get_session_info()
        logger.info(f"Session tracking initialized: {session_info}")

    async def analyze_market_context(self, symbol: str) -> MarketContext:
        """Analyze current market context for a symbol."""
        # Get regime
        regime_info = await session_manager.get_session_info()
        regime = regime_info.get("primary_mode", "unknown")

        # Get market data (placeholder)
        volatility = 0.01  # placeholder
        liquidity = 0.8  # placeholder
        sentiment = 0.0  # placeholder

        # Get session info
        session_info = await session_manager.get_session_info()
        session = session_info.get("primary_mode", "unknown")
        time_to_session_end = timedelta(hours=4)  # placeholder

        # Get correlation risk
        correlation_risk = 0.3  # placeholder

        # Get portfolio exposure
        portfolio_exposure = 0.2  # placeholder

        return MarketContext(
            symbol=symbol,
            regime=regime,
            trend="bullish",  # placeholder
            volatility=volatility,
            liquidity=liquidity,
            sentiment=sentiment,
            session=session,
            time_to_session_end=time_to_session_end,
            correlation_risk=correlation_risk,
            portfolio_exposure=portfolio_exposure
        )

    async def evaluate_entry_decision(self, symbol: str, context: MarketContext) -> AutonomousDecision | None:
        """Evaluate whether to enter a position."""
        # Check if we already have too many decisions for this symbol
        recent_decisions = [
            d for d in self.decision_history
            if d.symbol == symbol and d.timestamp > datetime.now(UTC) - timedelta(hours=1)
        ]
        if len(recent_decisions) >= self.max_decisions_per_symbol:
            return None

        # Check cooldown
        if symbol in self.last_decision_time:
            if datetime.now(UTC) - self.last_decision_time[symbol] < self.decision_cooldown:
                return None

        # Check risk limits
        if not await self._check_risk_limits(symbol):
            return None

        # Check circuit breakers
        if circuit_breaker_manager.is_any_open():
            return None

        # Calculate confidence based on multiple factors
        confidence = self._calculate_entry_confidence(context)

        if confidence < self.min_confidence_threshold:
            return None

        # Determine position size using Kelly criterion
        position_size = self._calculate_position_size(context, confidence)

        # Determine stop loss and take profit
        sl, tp = self._calculate_sl_tp(context, position_size)

        decision = AutonomousDecision(
            decision_id=f"entry_{symbol}_{datetime.now(UTC).timestamp()}",
            decision_type=DecisionType.ENTRY,
            symbol=symbol,
            confidence=confidence,
            reasoning=self._generate_entry_reasoning(context, confidence),
            parameters={
                "side": "buy" if context.trend == "bullish" else "sell",
                "size": position_size,
                "entry_price": None,  # Market order
                "stop_loss": sl,
                "take_profit": tp,
                "leverage": 1.0,
                "order_type": "market",
            },
            expires_at=datetime.now(UTC) + timedelta(minutes=30)
        )

        return decision

    async def evaluate_exit_decision(self, symbol: str, context: MarketContext) -> AutonomousDecision | None:
        """Evaluate whether to exit a position."""
        # Check if position exists
        # In production, check actual position
        position_exists = True  # placeholder

        if not position_exists:
            return None

        # Check for exit signals
        exit_signals = self._evaluate_exit_signals(context)
        if not exit_signals:
            return None

        confidence = 0.8  # High confidence for exits

        decision = AutonomousDecision(
            decision_id=f"exit_{symbol}_{datetime.now(UTC).timestamp()}",
            decision_type=DecisionType.EXIT,
            symbol=symbol,
            confidence=confidence,
            reasoning=f"Exit signals triggered: {', '.join(exit_signals)}",
            parameters={
                "side": "close",
                "size": "100%",
                "order_type": "market",
            },
            expires_at=datetime.now(UTC) + timedelta(minutes=5)
        )

        return decision

    async def evaluate_risk_reduction(self, symbol: str, context: MarketContext) -> AutonomousDecision | None:
        """Evaluate whether to reduce risk."""
        # Check portfolio risk
        portfolio_risk = await self._calculate_portfolio_risk()

        if portfolio_risk > self.max_portfolio_risk * 0.8:
            # Reduce position size
            return AutonomousDecision(
                decision_id=f"risk_reduce_{symbol}_{datetime.now(UTC).timestamp()}",
                decision_type=DecisionType.RISK_REDUCTION,
                symbol=symbol,
                confidence=0.9,
                reasoning=f"Portfolio risk at {portfolio_risk:.2%}, reducing exposure",
                parameters={
                    "action": "reduce",
                    "reduction_pct": 0.5,
                    "order_type": "market",
                },
                expires_at=datetime.now(UTC) + timedelta(minutes=10)
            )

        return None

    async def evaluate_portfolio_optimization(self) -> AutonomousDecision | None:
        """Evaluate portfolio rebalancing."""
        # Run portfolio optimization
        # In production, run Markowitz optimization
        needs_rebalance = True  # placeholder

        if needs_rebalance:
            return AutonomousDecision(
                decision_id=f"rebalance_{datetime.now(UTC).timestamp()}",
                decision_type=DecisionType.PORTFOLIO_OPTIMIZE,
                symbol="PORTFOLIO",
                confidence=0.7,
                reasoning="Portfolio drift detected, rebalancing to optimal weights",
                parameters={
                    "action": "rebalance",
                    "target_weights": {},  # computed by optimizer
                    "threshold": 0.05,
                },
                expires_at=datetime.now(UTC) + timedelta(hours=1)
            )

        return None

    def _calculate_entry_confidence(self, context: MarketContext) -> float:
        """Calculate confidence for entry decision."""
        confidence = 0.5  # Base confidence

        # Regime alignment
        if context.regime == "trending" and context.trend == "bullish":
            confidence += 0.2
        elif context.regime == "ranging":
            confidence -= 0.1

        # Volatility check
        if 0.005 < context.volatility < 0.02:
            confidence += 0.1
        elif context.volatility > 0.03:
            confidence -= 0.2

        # Liquidity check
        if context.liquidity > 0.7:
            confidence += 0.1
        elif context.liquidity < 0.3:
            confidence -= 0.2

        # Sentiment alignment
        if context.sentiment > 0.2 and context.trend == "bullish" or context.sentiment < -0.2 and context.trend == "bearish":
            confidence += 0.1

        # Session timing
        if context.time_to_session_end > timedelta(hours=2):
            confidence += 0.05

        # Correlation risk
        if context.correlation_risk < 0.5:
            confidence += 0.05

        return max(0.0, min(1.0, confidence))

    def _calculate_position_size(self, context: MarketContext, confidence: float) -> float:
        """Calculate position size using Kelly criterion."""
        # Simplified Kelly: f = (bp - q) / b
        # where b = odds, p = win probability, q = 1-p
        win_prob = confidence
        loss_prob = 1 - confidence
        avg_win = 0.02  # 2% average win
        avg_loss = 0.01  # 1% average loss
        odds = avg_win / avg_loss if avg_loss > 0 else 2

        kelly_fraction = (odds * win_prob - loss_prob) / odds
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%

        # Apply confidence scaling
        position_size = kelly_fraction * confidence

        # Apply risk limits
        max_size = settings.risk_max_position_size_pct
        position_size = min(position_size, max_size)

        return position_size

    def _calculate_sl_tp(self, context: MarketContext, position_size: float) -> tuple:
        """Calculate stop loss and take profit."""
        atr = context.volatility * 100  # Approximate ATR
        sl_distance = atr * 2  # 2 ATR stop loss
        tp_distance = atr * 3  # 3 ATR take profit (1:1.5 RR)

        return sl_distance, tp_distance

    def _generate_entry_reasoning(self, context: MarketContext, confidence: float) -> str:
        """Generate human-readable reasoning for entry."""
        reasons = [
            f"Regime: {context.regime}",
            f"Trend: {context.trend}",
            f"Volatility: {context.volatility:.4f}",
            f"Liquidity: {context.liquidity:.2f}",
            f"Confidence: {confidence:.2f}",
        ]
        return "; ".join(reasons)

    def _evaluate_exit_signals(self, context: MarketContext) -> list[str]:
        """Evaluate exit signals."""
        signals = []

        # Trend reversal
        if context.trend == "bearish":
            signals.append("trend_reversal")

        # Volatility spike
        if context.volatility > 0.03:
            signals.append("volatility_spike")

        # Session end approaching
        if context.time_to_session_end < timedelta(minutes=30):
            signals.append("session_end")

        # Correlation risk
        if context.correlation_risk > 0.7:
            signals.append("correlation_risk")

        # Sentiment shift
        if context.sentiment < -0.5:
            signals.append("sentiment_shift")

        return signals

    async def _check_risk_limits(self, symbol: str) -> bool:
        """Check if risk limits allow new position."""
        # Check portfolio risk
        portfolio_risk = await self._calculate_portfolio_risk()
        if portfolio_risk > self.max_portfolio_risk:
            return False

        # Check drawdown
        # In production, check actual drawdown
        current_drawdown = 0.05  # placeholder
        if current_drawdown > self.max_drawdown * 0.8:
            return False

        # Check correlation
        correlation = 0.3  # placeholder
        if correlation > self.max_correlation:
            return False

        return True

    async def _calculate_portfolio_risk(self) -> float:
        """Calculate current portfolio risk."""
        # Placeholder - in production, calculate actual portfolio VaR
        return 0.015  # 1.5% portfolio risk

    async def execute_decision(self, decision: AutonomousDecision) -> bool:
        """Execute an autonomous decision."""
        try:
            # In production, send order to execution engine
            logger.info(f"Executing decision: {decision.decision_id} for {decision.symbol}")

            # Simulate execution
            decision.executed = True
            decision.result = {
                "status": "filled",
                "fill_price": 1.0,  # placeholder
                "fill_size": decision.parameters.get("size"),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            self.decision_history.append(decision)
            self.last_decision_time[decision.symbol] = datetime.now(UTC)

            logger.info(f"Decision executed successfully: {decision.decision_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to execute decision {decision.decision_id}: {e}")
            decision.result = {"status": "failed", "error": str(e)}
            return False

    async def run_decision_cycle(self) -> list[AutonomousDecision]:
        """Run a complete decision cycle for all active symbols."""
        executed_decisions = []

        # Get active symbols
        symbols = self.active_symbols or {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"}

        for symbol in symbols:
            try:
                # Analyze market context
                context = await self.analyze_market_context(symbol)

                # Evaluate all decision types
                decisions = []

                # Entry decision
                entry = await self.evaluate_entry_decision(symbol, context)
                if entry:
                    decisions.append(entry)

                # Exit decision
                exit_dec = await self.evaluate_exit_decision(symbol, context)
                if exit_dec:
                    decisions.append(exit_dec)

                # Risk reduction
                risk_red = await self.evaluate_risk_reduction(symbol, context)
                if risk_red:
                    decisions.append(risk_red)

                # Execute decisions (highest confidence first)
                decisions.sort(key=lambda d: d.confidence, reverse=True)

                for decision in decisions:
                    if await self.execute_decision(decision):
                        executed_decisions.append(decision)

            except Exception as e:
                logger.error(f"Error in decision cycle for {symbol}: {e}")

        # Portfolio-level decisions
        portfolio_opt = await self.evaluate_portfolio_optimization()
        if portfolio_opt:
            await self.execute_decision(portfolio_opt)
            executed_decisions.append(portfolio_opt)

        return executed_decisions

    async def start_autonomous_loop(self, interval: int = 30) -> None:
        """Start the autonomous decision loop."""
        logger.info(f"Starting autonomous decision loop with {interval}s interval")

        while True:
            try:
                await self.run_decision_cycle()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Autonomous loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in autonomous loop: {e}")
                await asyncio.sleep(interval)

    def get_decision_stats(self) -> dict[str, Any]:
        """Get statistics about decisions."""
        total = len(self.decision_history)
        executed = sum(1 for d in self.decision_history if d.executed)
        by_type = {}
        for d in self.decision_history:
            by_type[d.decision_type.value] = by_type.get(d.decision_type.value, 0) + 1

        avg_confidence = np.mean([d.confidence for d in self.decision_history]) if self.decision_history else 0

        return {
            "total_decisions": total,
            "executed": executed,
            "success_rate": executed / total if total > 0 else 0,
            "by_type": by_type,
            "avg_confidence": avg_confidence,
            "active_symbols": list(self.active_symbols),
        }


# Global instance
decision_engine = AutonomousDecisionEngine()