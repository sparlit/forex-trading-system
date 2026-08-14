"""
Elite Autonomous Quantum Trading System - Autonomous Selection Engine
Complete automatic selection of method, style, strategy, session, and symbols.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.brain.analysis_brain import AnalysisResult
from src.brain.next_candle_predictor import PredictionResult
from src.strategies import (
    AutoStrategySelector,
    AutoStyleSelector,
    TradingStyle,
)
from src.strategy.session_manager import (
    TradingSession,
    session_manager,
)

logger = logging.getLogger(__name__)


class TradingMethod(Enum):
    """Trading methods."""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"
    CARRY_TRADE = "carry_trade"
    ARBITRAGE = "arbitrage"
    ORDER_FLOW = "order_flow"
    PATTERN = "pattern"
    STATISTICAL = "statistical"
    MACRO = "macro"
    FUNDING_RATE = "funding_rate"
    MARKET_MAKING = "market_making"
    EVENT_DRIVEN = "event_driven"
    INTERMARKET = "intermarket"
    VOLATILITY = "volatility"
    SEASONAL = "seasonal"
    ALTERNATIVE_DATA = "alternative_data"
    HIGH_FREQUENCY = "high_frequency"
    QUANTITATIVE = "quantitative"


@dataclass
class SelectionContext:
    """Context for selection decisions."""
    timestamp: datetime
    active_sessions: dict[str, TradingSession]
    active_symbols: set[str]
    market_regime: str
    volatility: float
    volume: float
    spread: float
    account_size: float
    risk_tolerance: float
    max_positions: int
    current_positions: int
    performance_metrics: dict[str, float]
    prediction: PredictionResult | None = None
    analysis: AnalysisResult | None = None


@dataclass
class SelectionResult:
    """Result of automatic selection."""
    method: TradingMethod
    style: TradingStyle
    strategy: str
    session: str
    symbols: list[str]
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AutonomousSelectionEngine:
    """
    Complete autonomous selection engine.
    Automatically selects method, style, strategy, session, and symbols.
    """
    
    def __init__(self):
        self.strategy_selector = AutoStrategySelector()
        self.style_selector = AutoStyleSelector()
        self.session_manager = session_manager
        
        # Method preferences by regime
        self.regime_method_preferences = {
            "trending_up": [TradingMethod.TREND_FOLLOWING, TradingMethod.MOMENTUM, TradingMethod.BREAKOUT],
            "trending_down": [TradingMethod.TREND_FOLLOWING, TradingMethod.MOMENTUM, TradingMethod.BREAKOUT],
            "ranging": [TradingMethod.MEAN_REVERSION, TradingMethod.PATTERN, TradingMethod.STATISTICAL],
            "volatile": [TradingMethod.VOLATILITY, TradingMethod.BREAKOUT, TradingMethod.ARBITRAGE],
            "low_volatility": [TradingMethod.CARRY_TRADE, TradingMethod.MEAN_REVERSION, TradingMethod.MARKET_MAKING],
            "high_volatility": [TradingMethod.BREAKOUT, TradingMethod.MOMENTUM, TradingMethod.VOLATILITY],
        }
        
        # Method preferences by style
        self.style_method_preferences = {
            TradingStyle.HIGH_FREQUENCY: [TradingMethod.MARKET_MAKING, TradingMethod.HIGH_FREQUENCY, TradingMethod.ARBITRAGE],
            TradingStyle.SCALPING: [TradingMethod.ORDER_FLOW, TradingMethod.PATTERN, TradingMethod.HIGH_FREQUENCY],
            TradingStyle.DAY_TRADING: [TradingMethod.MOMENTUM, TradingMethod.BREAKOUT, TradingMethod.PATTERN],
            TradingStyle.SWING_TRADING: [TradingMethod.TREND_FOLLOWING, TradingMethod.MEAN_REVERSION, TradingMethod.MACRO],
            TradingStyle.POSITION_TRADING: [TradingMethod.CARRY_TRADE, TradingMethod.MACRO, TradingMethod.FUNDING_RATE],
        }
        
        # Performance tracking
        self.selection_performance: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        logger.info("AutonomousSelectionEngine initialized")
    
    async def initialize(self):
        """Initialize the selection engine."""
        await self.session_manager.initialize()
        logger.info("AutonomousSelectionEngine fully initialized")
    
    async def select_all(self, context: SelectionContext) -> SelectionResult:
        """Perform complete autonomous selection."""
        
        # 1. Select trading session
        session = self._select_session(context)
        
        # 2. Select tradable symbols for session
        symbols = self._select_symbols(context, session)
        
        # 3. Select trading style
        style = self._select_style(context)
        
        # 4. Select trading method
        method = self._select_method(context, style)
        
        # 5. Select strategy
        strategy = self._select_strategy(context, method, style, symbols)
        
        # Calculate confidence
        confidence = self._calculate_confidence(context, method, style, strategy, symbols)
        
        # Build reasoning
        reasoning = self._build_reasoning(context, method, style, strategy, session, symbols)
        
        return SelectionResult(
            method=method,
            style=style,
            strategy=strategy,
            session=session,
            symbols=symbols,
            confidence=confidence,
            reasoning=reasoning,
            metadata={
                "regime": context.market_regime,
                "volatility": context.volatility,
                "active_sessions": list(context.active_sessions.keys()),
                "account_size": context.account_size,
                "risk_tolerance": context.risk_tolerance,
            }
        )
    
    def _select_session(self, context: SelectionContext) -> str:
        """Select the most relevant active session."""
        if not context.active_sessions:
            # Default to crypto 24/7
            return "crypto_24_7"
        
        # Priority: overlap sessions > major sessions > minor sessions
        priority_order = [
            "london_newyork_overlap",
            "tokyo_london_overlap",
            "sydney_tokyo_overlap",
            "london",
            "new_york",
            "tokyo",
            "frankfurt",
            "sydney",
            "hong_kong",
            "singapore",
            "crypto_24_7",
        ]
        
        for session_name in priority_order:
            if session_name in context.active_sessions:
                return session_name
        
        # Return first active session
        return next(iter(context.active_sessions.keys()))
    
    def _select_symbols(self, context: SelectionContext, session: str) -> list[str]:
        """Select optimal symbols for the session."""
        session_obj = self.session_manager.get_session_by_name(session)
        if not session_obj:
            return list(context.active_symbols)[:10]
        
        # Get session's major symbols
        session_symbols = session_obj.major_symbols
        
        # Filter by active symbols
        available = [s for s in session_symbols if s in context.active_symbols]
        
        # If not enough, add from active symbols
        if len(available) < 5:
            for s in context.active_symbols:
                if s not in available:
                    available.append(s)
                if len(available) >= 10:
                    break
        
        return available[:10]
    
    def _select_style(self, context: SelectionContext) -> TradingStyle:
        """Select optimal trading style."""
        return self.style_selector.select_style(
            symbol=next(iter(context.active_symbols)) if context.active_symbols else "EURUSD",
            volatility=context.volatility,
            session=context.active_sessions.keys().__iter__().__next__() if context.active_sessions else "crypto_24_7",
            account_size=context.account_size,
            risk_tolerance=context.risk_tolerance,
            time_available_hours=4.0  # Default
        )
    
    def _select_method(self, context: SelectionContext, style: TradingStyle) -> TradingMethod:
        """Select optimal trading method."""
        regime = context.market_regime
        
        # Get candidates from regime
        regime_methods = self.regime_method_preferences.get(regime, [])
        
        # Get candidates from style
        style_methods = self.style_method_preferences.get(style, [])
        
        # Intersection
        candidates = set(regime_methods) & set(style_methods)
        if not candidates:
            candidates = set(regime_methods) | set(style_methods)
        if not candidates:
            candidates = {TradingMethod.TREND_FOLLOWING, TradingMethod.MEAN_REVERSION}
        
        # Rank by performance
        best_method = None
        best_score = -1
        
        for method in candidates:
            score = self.selection_performance.get(regime, {}).get(method.value, 0.5)
            if score > best_score:
                best_score = score
                best_method = method
        
        return best_method or TradingMethod.TREND_FOLLOWING
    
    def _select_strategy(self, context: SelectionContext, method: TradingMethod, 
                         style: TradingStyle, symbols: list[str]) -> str:
        """Select optimal strategy."""
        primary_symbol = symbols[0] if symbols else "EURUSD"
        
        strategies = self.strategy_selector.select_strategies(
            symbol=primary_symbol,
            regime=context.market_regime,
            style=style,
            market_context={
                "volatility": context.volatility,
                "volume": context.volume,
                "spread": context.spread,
                "method": method.value,
            },
            max_strategies=1
        )
        
        return strategies[0] if strategies else "donchian_breakout"
    
    def _calculate_confidence(self, context: SelectionContext, method: TradingMethod,
                              style: TradingStyle, strategy: str, symbols: list[str]) -> float:
        """Calculate confidence in selection."""
        confidence = 0.5
        
        # Regime alignment
        regime_methods = self.regime_method_preferences.get(context.market_regime, [])
        if method in regime_methods:
            confidence += 0.15
        
        # Style alignment
        style_methods = self.style_method_preferences.get(style, [])
        if method in style_methods:
            confidence += 0.15
        
        # Performance history
        perf = self.selection_performance.get(context.market_regime, {}).get(method.value, 0.5)
        confidence += (perf - 0.5) * 0.3
        
        # Symbol coverage
        if len(symbols) >= 5:
            confidence += 0.1
        
        # Prediction confidence
        if context.prediction and context.prediction.confidence > 0.7:
            confidence += 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _build_reasoning(self, context: SelectionContext, method: TradingMethod,
                         style: TradingStyle, strategy: str, session: str, symbols: list[str]) -> str:
        """Build human-readable reasoning."""
        return (
            f"Selected {method.value} method for {context.market_regime} regime "
            f"with {style.value} style. Strategy: {strategy}. "
            f"Active session: {session}. Symbols: {', '.join(symbols[:5])}. "
            f"Volatility: {context.volatility:.4f}, Account: ${context.account_size:,.0f}"
        )
    
    def update_performance(self, regime: str, method: TradingMethod, pnl: float):
        """Update performance tracking."""
        current = self.selection_performance[regime].get(method.value, 0.5)
        self.selection_performance[regime][method.value] = 0.9 * current + 0.1 * max(0, min(1, 0.5 + pnl / 1000))


# Global instance
selection_engine = AutonomousSelectionEngine()