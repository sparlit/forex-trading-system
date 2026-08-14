"""
Elite Autonomous Quantum Trading System - Comprehensive Strategy Suite (Part 2)
Additional Strategy Implementations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from src.data.models import MarketData, Signal, SignalType, Timeframe
from src.strategies.comprehensive_strategies import (
    StrategyCategory,
    StrategyMetadata,
    TradingStyle,
    register_strategy,
)
from src.strategy.base import BaseStrategy, StrategyConfig
from src.strategy.technical.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


# ============================================================
# ADDITIONAL STRATEGY IMPLEMENTATIONS
# ============================================================

# 2. EMA CROSSOVER STRATEGY
@dataclass
class EMACrossoverConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    atr_period: int = 14
    atr_multiplier: float = 2.0
    trend_filter_period: int = 200


class EMACrossoverStrategy(BaseStrategy):
    """EMA Crossover Strategy - Trend Following"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ema_config = EMACrossoverConfig(**config.parameters.get("ema_crossover", {}))
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.H1, Timeframe.H4, Timeframe.D1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []
        
        for symbol in self.required_symbols:
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)
            bars_h4 = market_data.get_bars(symbol, Timeframe.H4)
            bars_d1 = market_data.get_bars(symbol, Timeframe.D1)
            
            if not all([bars_h1, bars_h4, bars_d1]):
                continue
            if len(bars_d1) < 200 or len(bars_h4) < 50 or len(bars_h1) < 50:
                continue
            
            # D1: Trend filter
            d1_closes = np.array([b.close for b in bars_d1])
            trend_ema = pd.Series(d1_closes).ewm(span=200).mean().iloc[-1]
            current_price = d1_closes[-1]
            trend_up = current_price > trend_ema
            
            # H4: MACD for momentum
            h4_closes = np.array([b.close for b in bars_h4])
            ema_fast_h4 = pd.Series(h4_closes).ewm(span=self.ema_config.fast_period).mean().iloc[-1]
            ema_slow_h4 = pd.Series(h4_closes).ewm(span=self.ema_config.slow_period).mean().iloc[-1]
            macd_h4 = ema_fast_h4 - ema_slow_h4
            _signal_h4 = pd.Series([macd_h4]).ewm(span=self.ema_config.signal_period).mean().iloc[-1]
            
            # H1: Entry timing
            h1_closes = np.array([b.close for b in bars_h1])
            ema_fast_h1 = pd.Series(h1_closes).ewm(span=self.ema_config.fast_period).mean().iloc[-1]
            ema_slow_h1 = pd.Series(h1_closes).ewm(span=self.ema_config.slow_period).mean().iloc[-1]
            macd_h1 = ema_fast_h1 - ema_slow_h1
            signal_h1 = pd.Series([macd_h1]).ewm(span=self.ema_config.signal_period).mean().iloc[-1]
            
            # ATR for stops
            h1_bars = market_data.get_bars(symbol, Timeframe.H1)
            atr = TechnicalIndicators.atr(
                np.array([b.high for b in h1_bars]),
                np.array([b.low for b in h1_bars]),
                np.array([b.close for b in h1_bars]),
                self.ema_config.atr_period
            )[-1]
            
            # Long: MACD crosses above signal on H1, H4 MACD > 0, trend up
            if (macd_h1 > signal_h1 and macd_h4 > 0 and trend_up):
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=0.75,
                    entry_price=h1_closes[-1],
                    stop_loss=h1_closes[-1] - atr * 2.0,
                    take_profit=h1_closes[-1] + atr * 3.0,
                    metadata={"trend_up": trend_up, "macd_h4": macd_h4, "strategy": "ema_crossover"}
                )
                signals.append(signal)
            
            # Short: MACD crosses below signal, H4 MACD < 0, trend down
            elif (macd_h1 < signal_h1 and macd_h4 < 0 and not trend_up):
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=0.75,
                    entry_price=h1_closes[-1],
                    stop_loss=h1_closes[-1] + atr * 2.0,
                    take_profit=h1_closes[-1] - atr * 3.0,
                    metadata={"trend_up": trend_up, "macd_h4": macd_h4, "strategy": "ema_crossover"}
                )
                signals.append(signal)
        
        return signals


# 3. MACD MOMENTUM STRATEGY
@dataclass
class MACDMomentumConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    histogram_threshold: float = 0.0
    atr_period: int = 14
    atr_multiplier: float = 2.0


class MACDMomentumStrategy(BaseStrategy):
    """MACD Momentum Confluence - Trend Following / Momentum"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.macd_config = MACDMomentumConfig(**config.parameters.get("macd_momentum", {}))
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []
        
        for symbol in self.required_symbols:
            bars_m15 = market_data.get_bars(symbol, Timeframe.M15)
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)
            bars_h4 = market_data.get_bars(symbol, Timeframe.H4)
            
            if not all([bars_m15, bars_h1, bars_h4]):
                continue
            
            closes_h4 = np.array([b.close for b in bars_h4])
            closes_h1 = np.array([b.close for b in bars_h1])
            closes_m15 = np.array([b.close for b in bars_m15])
            
            if len(closes_h4) < 50 or len(closes_h1) < 50 or len(closes_m15) < 50:
                continue
            
            # Multi-timeframe MACD
            for timeframe, closes, period_fast, period_slow, period_signal in [
                (Timeframe.H4, closes_h4, 12, 26, 9),
                (Timeframe.H1, closes_h1, 12, 26, 9),
                (Timeframe.M15, closes_m15, 12, 26, 9)
            ]:
                ema_fast = pd.Series(closes).ewm(span=period_fast).mean().iloc[-1]
                ema_slow = pd.Series(closes).ewm(span=period_slow).mean().iloc[-1]
                macd = ema_fast - ema_slow
                _signal = pd.Series([macd]).ewm(span=period_signal).mean().iloc[-1]
                _histogram = macd - _signal
            
            # Get H4 MACD
            ema_fast_h4 = pd.Series(closes_h4).ewm(span=12).mean().iloc[-1]
            ema_slow_h4 = pd.Series(closes_h4).ewm(span=26).mean().iloc[-1]
            macd_h4 = ema_fast_h4 - ema_slow_h4
            signal_h4 = pd.Series([macd_h4]).ewm(span=9).mean().iloc[-1]
            hist_h4 = macd_h4 - signal_h4
            
            # Get H1 MACD
            ema_fast_h1 = pd.Series(closes_h1).ewm(span=12).mean().iloc[-1]
            ema_slow_h1 = pd.Series(closes_h1).ewm(span=26).mean().iloc[-1]
            macd_h1 = ema_fast_h1 - ema_slow_h1
            signal_h1 = pd.Series([macd_h1]).ewm(span=9).mean().iloc[-1]
            hist_h1 = macd_h1 - signal_h1
            
            # Get M15 MACD
            ema_fast_m15 = pd.Series(closes_m15).ewm(span=12).mean().iloc[-1]
            ema_slow_m15 = pd.Series(closes_m15).ewm(span=26).mean().iloc[-1]
            macd_m15 = ema_fast_m15 - ema_slow_m15
            signal_m15 = pd.Series([macd_m15]).ewm(span=9).mean().iloc[-1]
            hist_m15 = macd_m15 - signal_m15
            
            current_price = closes_m15[-1]
            
            # ATR for stops
            m15_bars = market_data.get_bars(symbol, Timeframe.M15)
            atr = TechnicalIndicators.atr(
                np.array([b.high for b in m15_bars]),
                np.array([b.low for b in m15_bars]),
                np.array([b.close for b in m15_bars]),
                14
            )[-1]
            
            # Confluence: All three timeframes aligned
            if (macd_h4 > signal_h4 and macd_h1 > signal_h1 and macd_m15 > signal_m15 and
                hist_h4 > 0 and hist_h1 > 0 and hist_m15 > 0):
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M15,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=0.85,
                    entry_price=current_price,
                    stop_loss=current_price - atr * 2.0,
                    take_profit=current_price + atr * 3.0,
                    metadata={
                        "macd_h4": macd_h4, "macd_h1": macd_h1, "macd_m15": macd_m15,
                        "confluence": "triple_timeframe_bullish", "strategy": "macd_momentum"
                    }
                )
                signals.append(signal)
            
            elif (macd_h4 < signal_h4 and macd_h1 < signal_h1 and macd_m15 < signal_m15 and
                  hist_h4 < 0 and hist_h1 < 0 and hist_m15 < 0):
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M15,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=0.85,
                    entry_price=current_price,
                    stop_loss=current_price + atr * 2.0,
                    take_profit=current_price - atr * 3.0,
                    metadata={
                        "macd_h4": macd_h4, "macd_h1": macd_h1, "macd_m15": macd_m15,
                        "confluence": "triple_timeframe_bearish", "strategy": "macd_momentum"
                    }
                )
                signals.append(signal)
        
        return signals


# 4. BOLLINGER BANDS + RSI MEAN REVERSION
@dataclass
class BollingerRSIConfig:
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    bb_squeeze_threshold: float = 0.05


class BollingerRSIStrategy(BaseStrategy):
    """Bollinger Bands + RSI Mean Reversion"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.bb_config = BollingerRSIConfig(**config.parameters.get("bollinger_rsi", {}))
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M5, Timeframe.M15, Timeframe.H1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "XAUUSD"])
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []
        
        for symbol in self.required_symbols:
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)
            if not bars_h1 or len(bars_h1) < 50:
                continue
            
            closes = np.array([b.close for b in bars_h1])
            
            # Bollinger Bands
            _bb_period = self.bb_config.bb_period
            _bb_std = self.bb_config.bb_std
            bb_middle = pd.Series(closes).rolling(self.bb_config.bb_period).mean().iloc[-1]
            bb_std_val = pd.Series(closes).rolling(self.bb_config.bb_period).std().iloc[-1]
            bb_upper = bb_middle + (bb_std_val * self.bb_config.bb_std)
            bb_lower = bb_middle - (bb_std_val * self.bb_config.bb_std)
            
            # RSI
            rsi = TechnicalIndicators.rsi(closes, self.bb_config.rsi_period)[-1]
            
            # BB Squeeze check
            bb_width = (bb_upper - bb_lower) / bb_middle
            squeeze = bb_width < self.bb_config.bb_squeeze_threshold
            
            current_price = closes[-1]
            
            # Long: Price at lower band + RSI oversold
            if current_price <= bb_lower and rsi <= self.bb_config.rsi_oversold:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=0.7,
                    entry_price=current_price,
                    stop_loss=current_price * 0.98,
                    take_profit=bb_middle,
                    metadata={
                        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_middle": bb_middle,
                        "rsi": rsi, "squeeze": squeeze, "strategy": "bollinger_rsi"
                    }
                )
                signals.append(signal)
            
            # Short: Price at upper band + RSI overbought
            elif current_price >= bb_upper and rsi >= self.bb_config.rsi_overbought:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=0.7,
                    entry_price=current_price,
                    stop_loss=current_price * 1.02,
                    take_profit=bb_middle,
                    metadata={
                        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_middle": bb_middle,
                        "rsi": rsi, "squeeze": squeeze, "strategy": "bollinger_rsi"
                    }
                )
                signals.append(signal)
        
        return signals


# 5. MACRO CARRY TRADE
@dataclass
class CarryTradeConfig:
    min_carry_bps: float = 50.0
    max_leverage: float = 3.0
    rebalance_frequency: str = "weekly"
    correlation_filter: float = 0.7
    vol_target: float = 0.10
    max_drawdown_pct: float = 0.05


class CarryTradeStrategy(BaseStrategy):
    """Macro Carry Trade - Earn swap/rollover income"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.carry_config = CarryTradeConfig(**config.parameters.get("carry_trade", {}))
        self.carry_data: dict[str, float] = {}
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.D1]
    
    @property
    def required_symbols(self) -> list[str]:
        return [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
            "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
        ]
    
    async def update_carry_data(self):
        """Update carry/interest rate differential data"""
        # Approximate annualized carry (would fetch from central bank APIs in production)
        self.carry_data = {
            "EURUSD": -0.015, "GBPUSD": 0.012, "USDJPY": 0.045,
            "USDCHF": -0.010, "AUDUSD": 0.035, "USDCAD": 0.015,
            "NZDUSD": 0.040, "EURGBP": -0.025, "EURJPY": 0.030, "GBPJPY": 0.055
        }
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        await self.update_carry_data()
        signals = []
        
        for symbol in self.required_symbols:
            bars = market_data.get_bars(symbol, Timeframe.D1)
            if not bars or len(bars) < 50:
                continue
            
            closes = np.array([b.close for b in bars])
            carry = self.carry_data.get(symbol, 0.0)
            
            if abs(carry) < self.carry_config.min_carry_bps / 10000:
                continue
            
            # Volatility for position sizing
            returns = np.diff(np.log(closes[-20:]))
            vol = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0.20
            if vol == 0:
                continue
            
            # Position sizing: target portfolio vol
            carry_weight = min(abs(carry) / 0.05, 1.0)
            position_size = (self.carry_config.vol_target / vol) * carry_weight
            position_size = min(position_size, self.carry_config.max_leverage / len(self.required_symbols))
            
            current_price = closes[-1]
            
            # Long if positive carry (earn swap)
            if carry > 0:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.D1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(carry * 100, 1.0),
                    entry_price=current_price,
                    stop_loss=current_price * 0.95,
                    take_profit=current_price * 1.10,
                    metadata={
                        "carry_bps": carry * 10000,
                        "volatility": vol,
                        "position_size": position_size,
                        "strategy": "carry_trade"
                    }
                )
                signals.append(signal)
            
            # Short if negative carry (earn by being short)
            elif carry < 0:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.D1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(abs(carry) * 100, 1.0),
                    entry_price=current_price,
                    stop_loss=current_price * 1.05,
                    take_profit=current_price * 0.90,
                    metadata={
                        "carry_bps": carry * 10000,
                        "volatility": vol,
                        "position_size": position_size,
                        "strategy": "carry_trade"
                    }
                )
                signals.append(signal)
        
        return signals


# 6. CRYPTO FUNDING RATE ARBITRAGE
@dataclass
class FundingRateArbConfig:
    min_funding_rate: float = 0.0001  # 0.01% per 8h
    max_leverage: float = 5.0
    basis_threshold: float = 0.005  # 0.5% annualized
    max_position_size: float = 0.1
    rebalance_hours: int = 8


class FundingRateArbStrategy(BaseStrategy):
    """Crypto Funding Rate Arbitrage (Cash and Carry)"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.funding_config = FundingRateArbConfig(**config.parameters.get("funding_rate_arb", {}))
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return ["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "DOTUSD"]
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []
        
        for symbol in self.required_symbols:
            # Fetch funding rate from external API (placeholder)
            funding_rate = await self._fetch_funding_rate(symbol)
            spot_price = await self._get_spot_price(market_data, symbol)
            futures_price = await self._get_futures_price(symbol)
            
            if funding_rate is None or spot_price is None:
                continue
            
            # Annualized funding rate
            annualized_funding = funding_rate * (365 * 3)  # 3 payments per day
            
            # Basis trade: if futures > spot + threshold, short futures + long spot
            if futures_price and spot_price:
                basis = (futures_price - spot_price) / spot_price
                annualized_basis = basis * (365 / 90)  # Assuming quarterly futures
                
                # Cash and carry: long spot, short futures when basis > threshold
                if annualized_basis > self.funding_config.basis_threshold:
                    signal = Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe.H1,
                        signal_type=SignalType.ENTRY_LONG,
                        direction="long",
                        strength=0.8,
                        entry_price=market_data.get_latest_price(symbol) or 0,
                        stop_loss=0,  # Hedged position
                        take_profit=0,
                        metadata={
                            "funding_rate": funding_rate,
                            "annualized_funding": annualized_funding,
                            "basis": basis,
                            "annualized_basis": annualized_basis,
                            "strategy": "funding_rate_arb"
                        }
                    )
                    signals.append(signal)
        
        return signals
    
    async def _fetch_funding_rate(self, symbol: str) -> float | None:
        """Fetch funding rate from exchange API"""
        # Placeholder - would call exchange API
        return 0.0001
    
    async def _get_spot_price(self, market_data: MarketData, symbol: str) -> float | None:
        bars = market_data.get_bars(symbol, Timeframe.H1)
        if bars:
            return bars[-1].close
        return None
    
    async def _get_futures_price(self, symbol: str) -> float | None:
        """Fetch futures price from exchange"""
        return None


# Register new strategies
register_strategy(StrategyMetadata(
    name="ema_crossover",
    category=StrategyCategory.TREND_FOLLOWING,
    trading_style=TradingStyle.SWING_TRADING,
    description="EMA Crossover with multi-timeframe confirmation",
    required_timeframes=[Timeframe.H1, Timeframe.H4, Timeframe.D1],
    required_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
    min_holding_period=timedelta(hours=4),
    max_holding_period=timedelta(days=30),
    typical_win_rate=0.55,
    typical_risk_reward=2.0,
    complexity=3,
    capital_efficiency=0.7,
    slippage_sensitivity=0.3
))

register_strategy(StrategyMetadata(
    name="macd_momentum",
    category=StrategyCategory.MOMENTUM,
    trading_style=TradingStyle.DAY_TRADING,
    description="MACD Momentum Confluence - Triple timeframe MACD alignment",
    required_timeframes=[Timeframe.M15, Timeframe.H1, Timeframe.H4],
    required_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
    min_holding_period=timedelta(minutes=15),
    max_holding_period=timedelta(hours=4),
    typical_win_rate=0.60,
    typical_risk_reward=2.5,
    complexity=4,
    capital_efficiency=0.8,
    slippage_sensitivity=0.4
))

register_strategy(StrategyMetadata(
    name="bollinger_rsi",
    category=StrategyCategory.MEAN_REVERSION,
    trading_style=TradingStyle.SCALPING,
    description="Bollinger Bands + RSI Mean Reversion",
    required_timeframes=[Timeframe.M5, Timeframe.M15, Timeframe.H1],
    required_symbols=["EURUSD", "GBPUSD", "XAUUSD"],
    min_holding_period=timedelta(minutes=5),
    max_holding_period=timedelta(hours=2),
    typical_win_rate=0.65,
    typical_risk_reward=1.5,
    complexity=3,
    capital_efficiency=0.6,
    slippage_sensitivity=0.5
))

register_strategy(StrategyMetadata(
    name="carry_trade",
    category=StrategyCategory.CARRY_TRADE,
    trading_style=TradingStyle.POSITION_TRADING,
    description="Macro Carry Trade - Interest rate differential harvesting",
    required_timeframes=[Timeframe.D1],
    required_symbols=["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"],
    min_holding_period=timedelta(days=7),
    max_holding_period=timedelta(days=90),
    typical_win_rate=0.55,
    typical_risk_reward=1.8,
    complexity=4,
    capital_efficiency=0.8,
    slippage_sensitivity=0.2
))

register_strategy(StrategyMetadata(
    name="funding_rate_arb",
    category=StrategyCategory.FUNDING_RATE,
    trading_style=TradingStyle.DAY_TRADING,
    description="Crypto Funding Rate Arbitrage (Cash and Carry)",
    required_timeframes=[Timeframe.H1, Timeframe.H4],
    required_symbols=["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "DOTUSD"],
    min_holding_period=timedelta(hours=8),
    max_holding_period=timedelta(days=30),
    typical_win_rate=0.70,
    typical_risk_reward=3.0,
    complexity=5,
    capital_efficiency=0.9,
    slippage_sensitivity=0.3
))

# Export new strategies
__all__ = [
    "BollingerRSIStrategy",
    "CarryTradeStrategy",
    "EMACrossoverStrategy",
    "FundingRateArbStrategy",
    "MACDMomentumStrategy",
]