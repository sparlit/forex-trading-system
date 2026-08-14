"""
Built-in Strategy Implementations
- Trend Following (multi-timeframe)
- Mean Reversion (statistical arbitrage)
- Carry Trade
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.models import Bar, MarketData, Signal, SignalType, Timeframe
from src.strategy.base import BaseStrategy, StrategyConfig

logger = logging.getLogger(__name__)


# ============================================================
# TREND FOLLOWING STRATEGY
# ============================================================

@dataclass
class TrendConfig:
    fast_ema: int = 12
    slow_ema: int = 26
    signal_ema: int = 9
    atr_period: int = 14
    atr_multiplier: float = 2.0
    trend_filter_period: int = 200  # Long-term trend filter
    min_trend_strength: float = 0.02
    use_volume_filter: bool = True
    volume_ma_period: int = 20


class TrendFollowingStrategy(BaseStrategy):
    """
    Multi-timeframe trend following strategy using EMA crossover with ATR stops.
    Uses higher timeframe for trend direction, lower timeframe for entries.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.trend_config = TrendConfig(**config.parameters.get("trend", {}))
        
        # State
        self.ema_fast: dict[str, float] = {}
        self.ema_slow: dict[str, float] = {}
        self.ema_signal: dict[str, float] = {}
        self.atr: dict[str, float] = {}
        self.trend_ma: dict[str, float] = {}
        self.prev_macd: dict[str, float] = {}
        self.prev_signal: dict[str, float] = {}
        
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", [])
    
    def get_required_indicators(self) -> list[str]:
        return ["ema", "atr", "macd", "volume_sma"]
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate EMA using pandas for accuracy"""
        if len(prices) < period:
            return prices[-1] if len(prices) > 0 else 0.0
        return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]
    
    def _calculate_atr(self, bars: list[Bar], period: int) -> float:
        """Calculate Average True Range"""
        if len(bars) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, min(len(bars), period + 1)):
            high = bars[-i].high
            low = bars[-i].low
            prev_close = bars[-i-1].close if i < len(bars) else bars[-i].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        return np.mean(true_ranges) if true_ranges else 0.0
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        """Generate trend following signals"""
        signals = []
        
        for symbol in self.required_symbols:
            # Get data for each timeframe
            bars_h4 = market_data.get_bars(symbol, Timeframe.H4)
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)
            bars_m15 = market_data.get_bars(symbol, Timeframe.M15)
            
            if not bars_h4 or not bars_h1 or not bars_m15:
                continue
            
            # Need enough bars for calculations
            if len(bars_h4) < max(self.trend_config.trend_filter_period, 50):
                continue
            if len(bars_h1) < max(self.trend_config.slow_ema, self.trend_config.atr_period) + 10:
                continue
            if len(bars_m15) < self.trend_config.fast_ema + 10:
                continue
            
            # Extract prices
            h4_closes = np.array([b.close for b in bars_h4])
            h1_closes = np.array([b.close for b in bars_h1])
            m15_closes = np.array([b.close for b in bars_m15])
            
            # H4: Trend filter (200 MA)
            trend_ma = self._calculate_ema(h4_closes, self.trend_config.trend_filter_period)
            current_price = h1_closes[-1]
            trend_direction = 1 if current_price > trend_ma else -1
            trend_strength = abs(current_price - trend_ma) / trend_ma
            
            if trend_strength < self.trend_config.min_trend_strength:
                continue  # No clear trend
            
            # H1: MACD for momentum
            ema_fast_h1 = self._calculate_ema(h1_closes, self.trend_config.fast_ema)
            ema_slow_h1 = self._calculate_ema(h1_closes, self.trend_config.slow_ema)
            macd_h1 = ema_fast_h1 - ema_slow_h1
            signal_h1 = self._calculate_ema(np.array([macd_h1]), self.trend_config.signal_ema)
            
            # M15: Entry timing
            ema_fast_m15 = self._calculate_ema(m15_closes, self.trend_config.fast_ema)
            ema_slow_m15 = self._calculate_ema(m15_closes, self.trend_config.slow_ema)
            macd_m15 = ema_fast_m15 - ema_slow_m15
            
            # ATR for stops
            h1_bars = market_data.get_bars(symbol, Timeframe.H1)
            atr = self._calculate_atr(h1_bars, self.trend_config.atr_period)
            
            # Volume filter
            if self.trend_config.use_volume_filter:
                h1_volumes = np.array([b.volume for b in h1_bars[-self.trend_config.volume_ma_period:]])
                vol_sma = np.mean(h1_volumes) if len(h1_volumes) > 0 else 0
                current_vol = h1_bars[-1].volume
                if vol_sma > 0 and current_vol < vol_sma * 0.5:
                    continue  # Low volume
            
            # Check MACD crossover on M15 aligned with H1 trend
            prev_macd = self.prev_macd.get(symbol, 0)
            prev_signal_val = self.prev_signal.get(symbol, 0)
            
            # Long signal: MACD crosses above signal, trend is up
            if (macd_m15 > signal_h1 and prev_macd <= prev_signal_val and 
                trend_direction == 1 and macd_h1 > 0):
                
                entry_price = m15_closes[-1]
                stop_loss = entry_price - (atr * self.trend_config.atr_multiplier)
                take_profit = entry_price + (atr * self.trend_config.atr_multiplier * 2)
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M15,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(trend_strength * 10, 1.0),
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "trend_direction": trend_direction,
                        "trend_strength": trend_strength,
                        "atr": atr,
                        "macd_h1": macd_h1,
                        "macd_m15": macd_m15,
                        "timeframe_alignment": "H4 trend, H1 momentum, M15 entry"
                    }
                )
                
                signals.append(signal)
                await self.on_signal_generated(signal)
            
            # Short signal: MACD crosses below signal, trend is down
            elif (macd_m15 < signal_h1 and prev_macd >= prev_signal_val and 
                  trend_direction == -1 and macd_h1 < 0):
                
                entry_price = m15_closes[-1]
                stop_loss = entry_price + (atr * self.trend_config.atr_multiplier)
                take_profit = entry_price - (atr * self.trend_config.atr_multiplier * 2)
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M15,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(trend_strength * 10, 1.0),
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "trend_direction": trend_direction,
                        "trend_strength": trend_strength,
                        "atr": atr,
                        "macd_h1": macd_h1,
                        "macd_m15": macd_m15,
                        "timeframe_alignment": "H4 trend, H1 momentum, M15 entry"
                    }
                )
                
                signals.append(signal)
                await self.on_signal_generated(signal)
            
            # Update previous values
            self.prev_macd[symbol] = macd_m15
            self.prev_signal[symbol] = signal_h1
        
        return signals
    
    def get_required_indicators(self) -> list[str]:
        return ["ema", "atr", "macd", "volume_sma"]


# ============================================================
# MEAN REVERSION STRATEGY
# ============================================================

@dataclass
class MeanReversionConfig:
    lookback_period: int = 20
    entry_zscore: float = 2.0
    exit_zscore: float = 0.5
    stop_zscore: float = 3.0
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    bb_period: int = 20
    bb_std: float = 2.0
    min_half_life: int = 5
    max_half_life: int = 50
    cooldown_bars: int = 10


class MeanReversionStrategy(BaseStrategy):
    """
    Statistical mean reversion using Bollinger Bands and Z-score.
    Trades pairs and single assets when they deviate from mean.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.mr_config = MeanReversionConfig(**config.parameters.get("mean_reversion", {}))
        
        # State
        self.bb_upper: dict[str, float] = {}
        self.bb_lower: dict[str, float] = {}
        self.bb_middle: dict[str, float] = {}
        self.zscore: dict[str, float] = {}
        self.half_life: dict[str, float] = {}
        self.cooldown: dict[str, int] = {}
        self.in_position: dict[str, bool] = {}
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.H1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", [])
    
    def get_required_indicators(self) -> list[str]:
        return ["bbands", "zscore", "rsi", "half_life"]
    
    def _calculate_bollinger(self, prices: np.ndarray, period: int, std_mult: float) -> tuple:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return 0.0, 0.0, 0.0
        
        sma = pd.Series(prices).rolling(period).mean().iloc[-1]
        std = pd.Series(prices).rolling(period).std().iloc[-1]
        
        upper = sma + (std * std_mult)
        lower = sma - (std * std_mult)
        
        return upper, sma, lower
    
    def _calculate_zscore(self, prices: np.ndarray, period: int) -> float:
        """Calculate Z-score of current price"""
        if len(prices) < period:
            return 0.0
        
        recent = prices[-period:]
        mean = np.mean(recent)
        std = np.std(recent)
        
        if std == 0:
            return 0.0
        
        return (prices[-1] - mean) / std
    
    def _calculate_half_life(self, prices: np.ndarray) -> float:
        """Calculate half-life of mean reversion (Ornstein-Uhlenbeck)"""
        if len(prices) < 20:
            return 0.0
        
        # Simple OLS: y_t = alpha + beta * y_{t-1} + epsilon
        y = prices[1:]
        x = prices[:-1]
        
        if len(x) < 10:
            return 0.0
        
        beta = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
        
        if beta <= 0 or beta >= 1:
            return 0.0
        
        half_life = -np.log(2) / np.log(beta)
        return max(1, min(half_life, 100))
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []
        
        for symbol in self.required_symbols:
            bars = market_data.get_bars(symbol, Timeframe.H1)
            if not bars or len(bars) < self.mr_config.lookback_period + 20:
                continue
            
            closes = np.array([b.close for b in bars])
            
            # Calculate indicators
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger(
                closes, self.mr_config.bb_period, self.mr_config.bb_std
            )
            zscore = self._calculate_zscore(closes, self.mr_config.lookback_period)
            half_life = self._calculate_half_life(closes)
            
            # Check half-life is in valid range
            if half_life < self.mr_config.min_half_life or half_life > self.mr_config.max_half_life:
                continue
            
            # Update state
            self.bb_upper[symbol] = bb_upper
            self.bb_lower[symbol] = bb_lower
            self.bb_middle[symbol] = bb_middle
            self.zscore[symbol] = zscore
            self.half_life[symbol] = half_life
            
            # Cooldown
            if self.cooldown.get(symbol, 0) > 0:
                self.cooldown[symbol] -= 1
                continue
            
            current_price = closes[-1]
            in_pos = self.in_position.get(symbol, False)
            
            # Long entry: price below lower band, zscore < -2
            if (not in_pos and zscore <= -self.mr_config.entry_zscore and 
                current_price <= bb_lower):
                
                entry_price = current_price
                stop_loss = entry_price * (1 - 0.02)  # 2% stop
                take_profit = bb_middle  # Target middle band
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "zscore": zscore,
                        "bb_upper": bb_upper,
                        "bb_middle": bb_middle,
                        "bb_lower": bb_lower,
                        "half_life": half_life,
                        "strategy_type": "mean_reversion"
                    }
                )
                
                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = True
                self.cooldown[symbol] = self.mr_config.cooldown_bars
            
            # Short entry: price above upper band, zscore > 2
            elif (not in_pos and zscore >= self.mr_config.entry_zscore and 
                  current_price >= bb_upper):
                
                entry_price = current_price
                stop_loss = entry_price * (1 + 0.02)
                take_profit = bb_middle
                
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "zscore": zscore,
                        "bb_upper": bb_upper,
                        "bb_middle": bb_middle,
                        "bb_lower": bb_lower,
                        "half_life": half_life,
                        "strategy_type": "mean_reversion"
                    }
                )
                
                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = True
                self.cooldown[symbol] = self.mr_config.cooldown_bars
            
            # Exit long: zscore returns to mean
            elif in_pos and zscore >= -self.mr_config.exit_zscore:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.EXIT_LONG,
                    direction="flat",
                    strength=1.0,
                    entry_price=closes[-1],
                    metadata={"exit_reason": "zscore_mean_reversion"}
                )
                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = False
            
            # Exit short
            elif in_pos and zscore <= self.mr_config.exit_zscore:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.EXIT_SHORT,
                    direction="flat",
                    strength=1.0,
                    entry_price=closes[-1],
                    metadata={"exit_reason": "zscore_mean_reversion"}
                )
                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = False
            
            # Stop loss: zscore exceeds stop threshold
            elif in_pos and abs(zscore) >= self.mr_config.stop_zscore:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.STOP_LOSS,
                    direction="flat",
                    strength=1.0,
                    entry_price=closes[-1],
                    metadata={"exit_reason": "zscore_stop_loss"}
                )
                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = False
                self.cooldown[symbol] = self.mr_config.cooldown_bars * 2
        
        return signals
    
    def get_required_indicators(self) -> list[str]:
        return ["bbands", "zscore", "rsi", "half_life"]


# ============================================================
# CARRY TRADE STRATEGY
# ============================================================

@dataclass
class CarryConfig:
    min_carry_bps: float = 50.0  # Minimum 50 bps annual carry
    max_leverage: float = 3.0
    rebalance_frequency: str = "weekly"
    correlation_filter: float = 0.7
    vol_target: float = 0.10  # 10% annual vol target
    max_drawdown_pct: float = 0.05


class CarryTradeStrategy(BaseStrategy):
    """
    Carry trade strategy - earns swap/rollover income.
    Goes long high-yield currencies, short low-yield currencies.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.carry_config = CarryConfig(**config.parameters.get("carry", {}))
        
        # Currency yield data (would come from central bank data)
        self.carry_data: dict[str, float] = {}
        self.positions: dict[str, dict] = {}
    
    @property
    def required_timeframes(self) -> list:
        return [Timeframe.D1]
    
    @property
    def required_symbols(self) -> list[str]:
        # Major FX pairs
        return [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", 
            "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
        ]
    
    def get_required_indicators(self) -> list[str]:
        return ["swap_rates", "volatility", "correlation"]
    
    async def update_carry_data(self):
        """Update carry/interest rate data from external source"""
        # This would fetch from central bank APIs or data providers
        # For now, use static approximate values (annualized %)
        self.carry_data = {
            "EURUSD": -0.015,   # EUR negative, USD positive
            "GBPUSD": 0.012,    # GBP positive vs USD
            "USDJPY": 0.045,    # JPY negative, USD positive
            "USDCHF": -0.010,   # CHF negative
            "AUDUSD": 0.035,    # AUD positive
            "USDCAD": 0.015,    # CAD slightly positive
            "NZDUSD": 0.040,    # NZD positive
            "EURGBP": -0.025,
            "EURJPY": 0.030,
            "GBPJPY": 0.055,
        }
    
    def _calculate_volatility(self, prices: np.ndarray, period: int = 20) -> float:
        """Calculate annualized volatility"""
        if len(prices) < period:
            return 0.20  # Default 20%
        
        returns = np.diff(np.log(prices[-period:]))
        return np.std(returns) * np.sqrt(252)
    
    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        await self.update_carry_data()
        signals = []
        
        # Get daily bars for all symbols
        for symbol in self.required_symbols:
            bars = market_data.get_bars(symbol, Timeframe.D1)
            if not bars or len(bars) < 50:
                continue
            
            closes = np.array([b.close for b in bars])
            carry = self.carry_data.get(symbol, 0.0)
            
            # Filter by minimum carry
            if abs(carry) < self.carry_config.min_carry_bps / 10000:
                continue
            
            # Calculate volatility for position sizing
            vol = self._calculate_volatility(closes)
            if vol == 0:
                continue
            
            # Position sizing: target portfolio vol
            # Size = target_vol / asset_vol * carry_weight
            carry_weight = min(abs(carry) / 0.05, 1.0)  # Cap at 5% carry
            position_size = (self.carry_config.vol_target / vol) * carry_weight
            position_size = min(position_size, self.carry_config.max_leverage / len(self.required_symbols))
            
            # Check correlation with existing positions
            # (simplified - would need full correlation matrix)
            
            current_price = closes[-1]
            
            # Long if positive carry
            if carry > 0:
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.D1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(carry * 100, 1.0),
                    entry_price=current_price,
                    stop_loss=current_price * 0.95,  # 5% stop
                    take_profit=current_price * 1.10,
                    metadata={
                        "carry_bps": carry * 10000,
                        "volatility": vol,
                        "position_size": position_size,
                        "strategy_type": "carry_trade"
                    }
                )
                signals.append(signal)
                await self.on_signal_generated(signal)
            
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
                        "strategy_type": "carry_trade"
                    }
                )
                signals.append(signal)
                await self.on_signal_generated(signal)
        
        return signals
    
    def get_required_indicators(self) -> list[str]:
        return ["swap_rates", "volatility", "correlation"]


# ============================================================
# STRATEGY FACTORY
# ============================================================

def create_trend_following(config: StrategyConfig) -> BaseStrategy:
    return TrendFollowingStrategy(config)


def create_mean_reversion(config: StrategyConfig) -> BaseStrategy:
    return MeanReversionStrategy(config)


def create_carry_trade(config: StrategyConfig) -> BaseStrategy:
    return CarryTradeStrategy(config)



# ============================================================
# BREAKOUT STRATEGY
# ============================================================

@dataclass
class BreakoutConfig:
    lookback_period: int = 20
    breakout_threshold: float = 0.001  # 0.1% breakout
    volume_multiplier: float = 1.5
    atr_period: int = 14
    atr_multiplier_sl: float = 2.0
    atr_multiplier_tp: float = 3.0
    donchian_period: int = 20
    min_consolidation_bars: int = 5
    max_consolidation_bars: int = 50
    false_breakout_filter: bool = True
    retest_confirmation: bool = True


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy using Donchian channels and volume confirmation.
    Trades breakouts from consolidation ranges with volume confirmation.
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.breakout_config = BreakoutConfig(**config.parameters.get("breakout", {}))

        # State
        self.donchian_upper: dict[str, float] = {}
        self.donchian_lower: dict[str, float] = {}
        self.donchian_middle: dict[str, float] = {}
        self.consolidation_bars: dict[str, int] = {}
        self.in_position: dict[str, bool] = {}
        self.entry_price: dict[str, float] = {}
        self.consolidation_detected: dict[str, bool] = {}
        self.pending_retest: dict[str, dict] = {}

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.H1, Timeframe.H4]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", [])

    def get_required_indicators(self) -> list[str]:
        return ["donchian", "atr", "volume_sma", "adx"]

    def _calculate_donchian(self, bars: list[Bar], period: int) -> tuple:
        """Calculate Donchian Channels"""
        if len(bars) < period:
            return 0.0, 0.0, 0.0

        highs = np.array([b.high for b in bars[-period:]])
        lows = np.array([b.low for b in bars[-period:]])

        upper = np.max(highs)
        lower = np.min(lows)
        middle = (upper + lower) / 2

        return upper, middle, lower

    def _calculate_atr(self, bars: list[Bar], period: int) -> float:
        """Calculate Average True Range"""
        if len(bars) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(1, min(len(bars), period + 1)):
            high = bars[-i].high
            low = bars[-i].low
            prev_close = bars[-i-1].close if i < len(bars) else bars[-i].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        return np.mean(true_ranges) if true_ranges else 0.0

    def _calculate_adx(self, bars: list[Bar], period: int = 14) -> float:
        """Calculate Average Directional Index"""
        if len(bars) < period * 2:
            return 0.0

        high = np.array([b.high for b in bars])
        low = np.array([b.low for b in bars])
        close = np.array([b.close for b in bars])

        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )

        # Plus/Minus Directional Movement
        plus_dm = np.maximum(high[1:] - high[:-1], 0)
        minus_dm = np.maximum(low[:-1] - low[1:], 0)

        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

        # Smoothed values
        atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().iloc[-1]
        plus_di = 100 * pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean().iloc[-1] / atr if atr > 0 else 0
        minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean().iloc[-1] / atr if atr > 0 else 0

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        adx = pd.Series([dx]).ewm(alpha=1/period, adjust=False).mean().iloc[-1]

        return adx

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []

        for symbol in self.required_symbols:
            bars_h4 = market_data.get_bars(symbol, Timeframe.H4)
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)

            if not bars_h4 or not bars_h1:
                continue

            if len(bars_h4) < self.breakout_config.donchian_period + 10:
                continue
            if len(bars_h1) < self.breakout_config.lookback_period + 10:
                continue

            # Calculate Donchian channels on H4
            dc_upper_h4, dc_middle_h4, dc_lower_h4 = self._calculate_donchian(
                bars_h4, self.breakout_config.donchian_period
            )

            # Calculate Donchian channels on H1 for entry timing
            dc_upper_h1, _dc_middle_h1, dc_lower_h1 = self._calculate_donchian(
                bars_h1, self.breakout_config.lookback_period
            )

            # Calculate ATR for stops
            h1_bars = market_data.get_bars(symbol, Timeframe.H1)
            atr = self._calculate_atr(h1_bars, self.breakout_config.atr_period)

            # Calculate ADX for trend strength
            adx = self._calculate_adx(bars_h1)

            # Volume confirmation
            h1_volumes = np.array([b.volume for b in h1_bars[-20:]])
            vol_sma = np.mean(h1_volumes) if len(h1_volumes) > 0 else 0
            current_vol = h1_bars[-1].volume
            _volume_confirmed = current_vol > vol_sma * self.breakout_config.volume_multiplier if vol_sma > 0 else False

            current_price = bars_h1[-1].close

            # Check consolidation
            dc_width = (dc_upper_h4 - dc_lower_h4) / dc_middle_h4
            is_consolidating = dc_width < 0.02  # Less than 2% range

            if is_consolidating:
                self.consolidation_bars[symbol] = self.consolidation_bars.get(symbol, 0) + 1
            else:
                self.consolidation_bars[symbol] = 0

            consolidation_bars = self.consolidation_bars.get(symbol, 0)
            min_bars = self.breakout_config.min_consolidation_bars
            max_bars = self.breakout_config.max_consolidation_bars

            # Check if consolidation is valid
            valid_consolidation = min_bars <= consolidation_bars <= max_bars

            # Volume confirmation for breakout
            current_vol = h1_bars[-1].volume
            vol_sma_20 = np.mean([b.volume for b in h1_bars[-20:]]) if len(h1_bars) >= 20 else 0
            volume_spike = current_vol > vol_sma_20 * self.breakout_config.volume_multiplier if vol_sma_20 > 0 else False

            _current_high = bars_h1[-1].high
            _current_low = bars_h1[-1].low

            # Long breakout: price breaks above Donchian upper
            long_breakout = (
                current_price > dc_upper_h1 * (1 + self.breakout_config.breakout_threshold) and
                valid_consolidation and
                volume_spike and
                not self.in_position.get(symbol, False)
            )

            # Short breakout: price breaks below Donchian lower
            short_breakout = (
                current_price < dc_lower_h1 * (1 - self.breakout_config.breakout_threshold) and
                valid_consolidation and
                volume_spike and
                not self.in_position.get(symbol, False)
            )

            # False breakout filter: check if price quickly reverses
            if self.breakout_config.false_breakout_filter:
                _prev_close = h1_bars[-2].close if len(h1_bars) > 1 else current_price
                if long_breakout and current_price < dc_upper_h1:
                    long_breakout = False
                if short_breakout and current_price > dc_lower_h1:
                    short_breakout = False

            # Retest confirmation
            if self.breakout_config.retest_confirmation:
                if long_breakout and symbol not in self.pending_retest:
                    self.pending_retest[symbol] = {"direction": "long", "level": dc_upper_h1}
                    long_breakout = False  # Wait for retest
                elif short_breakout and symbol not in self.pending_retest:
                    self.pending_retest[symbol] = {"direction": "short", "level": dc_lower_h1}
                    short_breakout = False  # Wait for retest

            # Check retest confirmation
            if symbol in self.pending_retest:
                pending = self.pending_retest[symbol]
                if pending["direction"] == "long" and current_price <= pending["level"] * 1.001 and current_price >= pending["level"] * 0.999:
                    long_breakout = True
                    del self.pending_retest[symbol]
                elif pending["direction"] == "short" and current_price >= pending["level"] * 0.999 and current_price <= pending["level"] * 1.001:
                    short_breakout = True
                    del self.pending_retest[symbol]

            # Long signal
            if long_breakout:
                entry_price = current_price
                stop_loss = entry_price - (atr * self.breakout_config.atr_multiplier_sl)
                take_profit = entry_price + (atr * self.breakout_config.atr_multiplier_tp)

                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(adx / 50, 1.0) if adx > 0 else 0.7,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "dc_upper": dc_upper_h1,
                        "dc_lower": dc_lower_h1,
                        "dc_middle": (dc_upper_h1 + dc_lower_h1) / 2,
                        "atr": atr,
                        "adx": adx,
                        "consolidation_bars": self.consolidation_bars.get(symbol, 0),
                        "dc_width_pct": dc_width * 100,
                        "volume_confirmed": True,
                        "strategy_type": "breakout"
                    }
                )

                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = True
                self.entry_price[symbol] = entry_price

            # Short signal
            elif short_breakout:
                entry_price = current_price
                stop_loss = entry_price + (atr * self.breakout_config.atr_multiplier_sl)
                take_profit = entry_price - (atr * self.breakout_config.atr_multiplier_tp)

                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(adx / 50, 1.0) if adx > 0 else 0.7,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "dc_upper": dc_upper_h1,
                        "dc_lower": dc_lower_h1,
                        "dc_middle": (dc_upper_h1 + dc_lower_h1) / 2,
                        "atr": atr,
                        "adx": adx,
                        "consolidation_bars": self.consolidation_bars.get(symbol, 0),
                        "dc_width_pct": dc_width * 100,
                        "volume_confirmed": True,
                        "strategy_type": "breakout"
                    }
                )

                signals.append(signal)
                await self.on_signal_generated(signal)
                self.in_position[symbol] = True
                self.entry_price[symbol] = entry_price

            # Exit logic for existing positions
            elif self.in_position.get(symbol, False):
                entry = self.entry_price.get(symbol, 0)
                if entry > 0:
                    # Trail stop using ATR
                    _trail_sl = atr * 1.5
                    current_pnl = current_price - entry if current_price > entry else entry - current_price

                    # Update stop loss if price moved favorably
                    # This is simplified - in production would track actual stop orders
                    if current_pnl > atr * 2:
                        pass  # Trailing stop logic would go here

        return signals

    def get_required_indicators(self) -> list[str]:
        return ["donchian", "atr", "volume_sma", "adx"]


def create_breakout(config: StrategyConfig) -> BaseStrategy:
    return BreakoutStrategy(config)


STRATEGY_FACTORIES = {
    "trend_following": create_trend_following,
    "mean_reversion": create_mean_reversion,
    "carry_trade": create_carry_trade,
    "breakout": create_breakout,
}