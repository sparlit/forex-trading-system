"""

Market Regime Detection
=======================

Detects market regimes (trending, ranging, volatile, etc.) to enable
adaptive strategy selection and risk management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import numpy as np
import polars as pl
from loguru import logger

from src.data.models import Bar


def _utc_now() -> datetime:
    return datetime.now(UTC)



class RegimeType(str, Enum):
    """Market regime types."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    BREAKOUT = "breakout"
    MEAN_REVERTING = "mean_reverting"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RegimeInfo:
    """Information about detected regime."""
    regime: RegimeType
    confidence: float
    strength: float  # 0-1, how strong the regime is
    duration: int  # bars in current regime
    characteristics: dict[str, float]
    timestamp: datetime = field(default_factory=_utc_now)


class MarketRegimeDetector:
    """
    Detects market regimes using multiple methods:
    - ADX for trend strength
    - Bollinger Band width for volatility
    - Hurst exponent for mean reversion vs trend
    - Price action patterns
    - Volume analysis
    """
    
    def __init__(
        self,
        lookback: int = 100,
        adx_threshold: float = 25.0,
        bb_width_threshold: float = 0.02,
        hurst_trend_threshold: float = 0.55,
        hurst_mean_revert_threshold: float = 0.45,
    ):
        self.lookback = lookback
        self.adx_threshold = adx_threshold
        self.bb_width_threshold = bb_width_threshold
        self.hurst_trend_threshold = hurst_trend_threshold
        self.hurst_mean_revert_threshold = hurst_mean_revert_threshold
        
        # State
        self._current_regime: RegimeInfo | None = None
        self._regime_history: list[RegimeInfo] = []
        self._regime_duration = 0
        
    def bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        """Convert bars to polars DataFrame."""
        if not bars:
            return pl.DataFrame()
        
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
    
    def calculate_adx(self, df: pl.DataFrame, period: int = 14) -> float:
        """Calculate Average Directional Index."""
        if len(df) < period * 2:
            return 0.0
        
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()
        
        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        
        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smooth
        atr = np.convolve(tr, np.ones(period)/period, mode='valid')
        plus_di = 100 * np.convolve(plus_dm, np.ones(period)/period, mode='valid') / atr
        minus_di = 100 * np.convolve(minus_dm, np.ones(period)/period, mode='valid') / atr
        
        # ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = np.convolve(dx, np.ones(period)/period, mode='valid')
        
        return float(adx[-1]) if len(adx) > 0 else 0.0
    
    def calculate_bollinger_width(self, df: pl.DataFrame, period: int = 20, std_dev: float = 2.0) -> float:
        """Calculate Bollinger Band width as % of price."""
        if len(df) < period:
            return 0.0
        
        close = df["close"].to_numpy()
        sma = np.convolve(close, np.ones(period)/period, mode='valid')
        std = np.array([np.std(close[i:i+period]) for i in range(len(close)-period+1)])
        
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        width = (upper - lower) / sma
        
        return float(width[-1]) if len(width) > 0 else 0.0
    
    def calculate_hurst_exponent(self, df: pl.DataFrame, max_lag: int = 20) -> float:
        """Calculate Hurst exponent to detect trend vs mean reversion."""
        if len(df) < max_lag * 2:
            return 0.5
        
        close = df["close"].to_numpy()
        returns = np.diff(np.log(close))
        
        if len(returns) < max_lag:
            return 0.5
        
        lags = range(2, min(max_lag, len(returns)//2))
        tau = [np.sqrt(np.std(np.subtract(returns[lag:], returns[:-lag]))) for lag in lags]
        
        if len(tau) < 2:
            return 0.5
        
        # Linear regression on log-log plot
        poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        hurst = poly[0] * 2.0
        
        return float(np.clip(hurst, 0, 1))
    
    def detect_price_action_regime(self, df: pl.DataFrame) -> tuple[RegimeType, float]:
        """Detect regime from price action patterns."""
        if len(df) < 20:
            return RegimeType.UNKNOWN, 0.0
        
        close = df["close"].to_numpy()
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        
        # Recent returns
        returns = np.diff(np.log(close[-20:]))
        cum_return = np.sum(returns)
        volatility = np.std(returns)
        
        # Higher highs / lower lows
        recent_highs = high[-10:]
        recent_lows = low[-10:]
        
        higher_highs = np.sum(np.diff(recent_highs) > 0)
        lower_lows = np.sum(np.diff(recent_lows) < 0)
        
        # Determine regime
        if cum_return > 2 * volatility and higher_highs >= 6:
            return RegimeType.TRENDING_UP, min(1.0, abs(cum_return) / (volatility + 1e-6))
        elif cum_return < -2 * volatility and lower_lows >= 6:
            return RegimeType.TRENDING_DOWN, min(1.0, abs(cum_return) / (volatility + 1e-6))
        elif volatility > 0.015:  # High volatility
            return RegimeType.VOLATILE, min(1.0, volatility * 50)
        else:
            return RegimeType.RANGING, 0.5
    
    async def detect_regime(self, bars: list[Bar]) -> RegimeType:
        """
        Detect current market regime from bars.
        Returns the most likely regime type.
        """
        if len(bars) < self.lookback:
            return RegimeType.UNKNOWN
        
        df = self.bars_to_dataframe(bars[-self.lookback:])
        if df.is_empty():
            return RegimeType.UNKNOWN
        
        # Calculate indicators
        adx = self.calculate_adx(df)
        bb_width = self.calculate_bollinger_width(df)
        hurst = self.calculate_hurst_exponent(df)
        price_regime, price_confidence = self.detect_price_action_regime(df)
        
        # Combine signals for final decision
        regime_scores = {
            RegimeType.TRENDING_UP: 0.0,
            RegimeType.TRENDING_DOWN: 0.0,
            RegimeType.RANGING: 0.0,
            RegimeType.VOLATILE: 0.0,
            RegimeType.MEAN_REVERTING: 0.0,
        }
        
        # ADX-based trend detection
        if adx > self.adx_threshold:
            if price_regime in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN):
                regime_scores[price_regime] += 0.4 * (adx / 50.0)
            else:
                # ADX high but price action unclear - could be volatile trending
                regime_scores[RegimeType.VOLATILE] += 0.3
        
        # Bollinger Band width for volatility
        if bb_width > self.bb_width_threshold:
            regime_scores[RegimeType.VOLATILE] += 0.3 * min(1.0, bb_width / 0.05)
        else:
            regime_scores[RegimeType.LOW_VOLATILITY] += 0.2
        
        # Hurst exponent
        if hurst > self.hurst_trend_threshold:
            # Trending
            if price_regime == RegimeType.TRENDING_UP:
                regime_scores[RegimeType.TRENDING_UP] += 0.3
            elif price_regime == RegimeType.TRENDING_DOWN:
                regime_scores[RegimeType.TRENDING_DOWN] += 0.3
            else:
                regime_scores[RegimeType.TRENDING_UP] += 0.15
                regime_scores[RegimeType.TRENDING_DOWN] += 0.15
        elif hurst < self.hurst_mean_revert_threshold:
            regime_scores[RegimeType.MEAN_REVERTING] += 0.3
        else:
            regime_scores[RegimeType.RANGING] += 0.2
        
        # Price action confirmation
        if price_regime != RegimeType.UNKNOWN:
            regime_scores[price_regime] += 0.3 * price_confidence
        
        # Select best regime
        best_regime = max(regime_scores, key=regime_scores.get)
        confidence = regime_scores[best_regime]
        
        # Update state
        if self._current_regime and self._current_regime.regime == best_regime:
            self._regime_duration += 1
        else:
            self._regime_duration = 1
        
        regime_info = RegimeInfo(
            regime=best_regime,
            confidence=confidence,
            strength=confidence,
            duration=self._regime_duration,
            characteristics={
                "adx": adx,
                "bb_width": bb_width,
                "hurst": hurst,
                "price_regime": price_regime.value,
                "price_confidence": price_confidence,
            },
            timestamp=datetime.now(UTC),
        )
        
        self._current_regime = regime_info
        self._regime_history.append(regime_info)
        
        # Keep history bounded
        if len(self._regime_history) > 1000:
            self._regime_history = self._regime_history[-500:]
        
        logger.debug(f"Regime detected: {best_regime.value} (confidence: {confidence:.2f}, ADX: {adx:.1f}, Hurst: {hurst:.2f})")
        
        return best_regime
    
    def get_current_regime(self) -> RegimeInfo | None:
        """Get current regime info."""
        return self._current_regime
    
    def get_regime_history(self) -> list[RegimeInfo]:
        """Get regime history."""
        return self._regime_history.copy()
    
    def should_use_strategy(self, strategy_type: str) -> float:
        """
        Get suitability score for a strategy type in current regime.
        Returns 0-1 score.
        """
        if not self._current_regime:
            return 0.5
        
        regime = self._current_regime.regime
        confidence = self._current_regime.confidence
        
        suitability = {
            "trend_following": {
                RegimeType.TRENDING_UP: 0.9,
                RegimeType.TRENDING_DOWN: 0.9,
                RegimeType.RANGING: 0.2,
                RegimeType.VOLATILE: 0.5,
                RegimeType.MEAN_REVERTING: 0.1,
            },
            "mean_reversion": {
                RegimeType.TRENDING_UP: 0.1,
                RegimeType.TRENDING_DOWN: 0.1,
                RegimeType.RANGING: 0.9,
                RegimeType.VOLATILE: 0.3,
                RegimeType.MEAN_REVERTING: 0.95,
            },
            "breakout": {
                RegimeType.TRENDING_UP: 0.6,
                RegimeType.TRENDING_DOWN: 0.6,
                RegimeType.RANGING: 0.7,
                RegimeType.VOLATILE: 0.8,
                RegimeType.MEAN_REVERTING: 0.3,
            },
            "ensemble_ml": {
                RegimeType.TRENDING_UP: 0.8,
                RegimeType.TRENDING_DOWN: 0.8,
                RegimeType.RANGING: 0.7,
                RegimeType.VOLATILE: 0.9,
                RegimeType.MEAN_REVERTING: 0.8,
            },
        }
        
        base_score = suitability.get(strategy_type, {}).get(regime, 0.5)
        return base_score * confidence + 0.5 * (1 - confidence)
