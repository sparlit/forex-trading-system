from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from numba import jit


@dataclass
class IndicatorResult:
    """Container for indicator values."""
    name: str
    values: np.ndarray
    params: dict


class TechnicalIndicators:
    """High-performance technical indicators using Numba and Polars."""

    @staticmethod
    @jit(nopython=True, cache=True)
    def sma_numba(data: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average - Numba optimized."""
        n = len(data)
        result = np.full(n, np.nan)
        if n < period:
            return result

        # First valid value
        result[period - 1] = np.mean(data[:period])

        # Rolling calculation
        for i in range(period, n):
            result[i] = result[i - 1] + (data[i] - data[i - period]) / period

        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def ema_numba(data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average - Numba optimized."""
        n = len(data)
        result = np.full(n, np.nan)
        if n == 0:
            return result

        alpha = 2.0 / (period + 1.0)
        result[0] = data[0]

        for i in range(1, n):
            result[i] = alpha * data[i] + (1.0 - alpha) * result[i - 1]

        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def rsi_numba(data: np.ndarray, period: int = 14) -> np.ndarray:
        """RSI - Numba optimized."""
        n = len(data)
        result = np.full(n, np.nan)
        if n < period + 1:
            return result

        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # Initial average
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        if avg_loss == 0:
            result[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[period] = 100.0 - (100.0 / (1.0 + rs))

        # Rolling
        for i in range(period + 1, n):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

            if avg_loss == 0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))

        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def bollinger_bands_numba(data: np.ndarray, period: int = 20, std_dev: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Bollinger Bands - Numba optimized."""
        n = len(data)
        upper = np.full(n, np.nan)
        middle = np.full(n, np.nan)
        lower = np.full(n, np.nan)

        if n < period:
            return upper, middle, lower

        for i in range(period - 1, n):
            window = data[i - period + 1:i + 1]
            mean = np.mean(window)
            std = np.std(window)
            middle[i] = mean
            upper[i] = mean + std_dev * std
            lower[i] = mean - std_dev * std

        return upper, middle, lower

    @staticmethod
    @jit(nopython=True, cache=True)
    def atr_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """ATR - Numba optimized."""
        n = len(close)
        result = np.full(n, np.nan)
        if n < 2:
            return result

        tr = np.zeros(n)
        tr[0] = high[0] - low[0]

        for i in range(1, n):
            tr1 = high[i] - low[i]
            tr2 = abs(high[i] - close[i - 1])
            tr3 = abs(low[i] - close[i - 1])
            tr[i] = max(tr1, tr2, tr3)

        # Initial ATR
        result[period - 1] = np.mean(tr[:period])

        # Rolling
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period

        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def macd_numba(data: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD - Numba optimized."""
        ema_fast = TechnicalIndicators.ema_numba(data, fast)
        ema_slow = TechnicalIndicators.ema_numba(data, slow)
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.ema_numba(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    @jit(nopython=True, cache=True)
    def stochastic_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14, smooth: int = 3) -> tuple[np.ndarray, np.ndarray]:
        """Stochastic - Numba optimized."""
        n = len(close)
        k = np.full(n, np.nan)
        d = np.full(n, np.nan)

        if n < period:
            return k, d

        for i in range(period - 1, n):
            window_high = high[i - period + 1:i + 1]
            window_low = low[i - period + 1:i + 1]
            highest = np.max(window_high)
            lowest = np.min(window_low)

            if highest != lowest:
                k[i] = 100.0 * (close[i] - lowest) / (highest - lowest)
            else:
                k[i] = 50.0

        # Smooth K to get D
        valid_k = k[period - 1:]
        if len(valid_k) >= smooth:
            d_vals = TechnicalIndicators.sma_numba(valid_k, smooth)
            d[period - 1 + smooth - 1:] = d_vals[smooth - 1:]

        return k, d

    @staticmethod
    @jit(nopython=True, cache=True)
    def adx_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """ADX - Numba optimized."""
        n = len(close)
        plus_di = np.full(n, np.nan)
        minus_di = np.full(n, np.nan)
        adx = np.full(n, np.nan)

        if n < period + 1:
            return plus_di, minus_di, adx

        # Calculate +DM, -DM, TR
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        tr = np.zeros(n)

        tr[0] = high[0] - low[0]

        for i in range(1, n):
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]

            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            else:
                plus_dm[i] = 0.0

            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            else:
                minus_dm[i] = 0.0

            tr1 = high[i] - low[i]
            tr2 = abs(high[i] - close[i - 1])
            tr3 = abs(low[i] - close[i - 1])
            tr[i] = max(tr1, tr2, tr3)

        # Smooth with Wilder's smoothing
        atr = np.zeros(n)
        plus_dm_smooth = np.zeros(n)
        minus_dm_smooth = np.zeros(n)

        atr[period - 1] = np.mean(tr[:period])
        plus_dm_smooth[period - 1] = np.mean(plus_dm[:period])
        minus_dm_smooth[period - 1] = np.mean(minus_dm[:period])

        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
            plus_dm_smooth[i] = (plus_dm_smooth[i - 1] * (period - 1) + plus_dm[i]) / period
            minus_dm_smooth[i] = (minus_dm_smooth[i - 1] * (period - 1) + minus_dm[i]) / period

        for i in range(period - 1, n):
            if atr[i] > 0:
                plus_di[i] = 100.0 * plus_dm_smooth[i] / atr[i]
                minus_di[i] = 100.0 * minus_dm_smooth[i] / atr[i]

        # DX and ADX
        dx = np.full(n, np.nan)
        for i in range(period - 1, n):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

        adx[2 * period - 2] = np.mean(dx[period - 1:2 * period - 1])
        for i in range(2 * period - 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return plus_di, minus_di, adx

    @staticmethod
    @jit(nopython=True, cache=True)
    def ichimoku_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Ichimoku Cloud - Numba optimized."""
        n = len(close)
        tenkan = np.full(n, np.nan)
        kijun = np.full(n, np.nan)
        senkou_a = np.full(n, np.nan)
        senkou_b = np.full(n, np.nan)
        chikou = np.full(n, np.nan)

        # Tenkan-sen (9 period)
        for i in range(8, n):
            tenkan[i] = (np.max(high[i - 8:i + 1]) + np.min(low[i - 8:i + 1])) / 2

        # Kijun-sen (26 period)
        for i in range(25, n):
            kijun[i] = (np.max(high[i - 25:i + 1]) + np.min(low[i - 25:i + 1])) / 2

        # Senkou Span A (shifted 26)
        for i in range(25, n - 26):
            senkou_a[i + 26] = (tenkan[i] + kijun[i]) / 2

        # Senkou Span B (52 period, shifted 26)
        for i in range(51, n - 26):
            senkou_b[i + 26] = (np.max(high[i - 51:i + 1]) + np.min(low[i - 51:i + 1])) / 2

        # Chikou Span (shifted -26)
        for i in range(26, n):
            chikou[i - 26] = close[i]

        return tenkan, kijun, senkou_a, senkou_b, chikou

    @staticmethod
    def add_all_indicators_polars(df: pl.DataFrame) -> pl.DataFrame:
        """Add all indicators using Polars expressions (vectorized)."""
        return df.with_columns([
            # Moving Averages
            pl.col("close").rolling_mean(window_size=10).alias("sma_10"),
            pl.col("close").rolling_mean(window_size=20).alias("sma_20"),
            pl.col("close").rolling_mean(window_size=50).alias("sma_50"),
            pl.col("close").rolling_mean(window_size=100).alias("sma_100"),
            pl.col("close").rolling_mean(window_size=200).alias("sma_200"),

            pl.col("close").ewm_mean(span=10).alias("ema_10"),
            pl.col("close").ewm_mean(span=20).alias("ema_20"),
            pl.col("close").ewm_mean(span=50).alias("ema_50"),
            pl.col("close").ewm_mean(span=100).alias("ema_100"),

            # RSI
                        (100 - 100 / (1 + (
                            pl.col("close").diff().clip(lower_bound=0).rolling_mean(window_size=14) /
                            (-pl.col("close").diff()).clip(lower_bound=0).rolling_mean(window_size=14)
                        ))).alias("rsi_14"),

            # Bollinger Bands
            pl.col("close").rolling_mean(window_size=20).alias("bb_middle_20"),
            (pl.col("close").rolling_mean(window_size=20) +
             2 * pl.col("close").rolling_std(window_size=20)).alias("bb_upper_20"),
            (pl.col("close").rolling_mean(window_size=20) -
             2 * pl.col("close").rolling_std(window_size=20)).alias("bb_lower_20"),

            # MACD
            (pl.col("close").ewm_mean(span=12) - pl.col("close").ewm_mean(span=26)).alias("macd"),
            (pl.col("close").ewm_mean(span=12) - pl.col("close").ewm_mean(span=26)).ewm_mean(span=9).alias("macd_signal"),

            # ATR
            pl.max_horizontal([
                pl.col("high") - pl.col("low"),
                (pl.col("high") - pl.col("close").shift(1)).abs(),
                (pl.col("low") - pl.col("close").shift(1)).abs(),
            ]).rolling_mean(window_size=14).alias("atr_14"),

            # Stochastic
            (100 * (pl.col("close") - pl.col("low").rolling_min(window_size=14)) /
             (pl.col("high").rolling_max(window_size=14) - pl.col("low").rolling_min(window_size=14))).alias("stoch_k_14"),

            # ADX components
            # Plus DM
            pl.when(
                (pl.col("high") - pl.col("high").shift(1) > pl.col("low").shift(1) - pl.col("low")) &
                (pl.col("high") - pl.col("high").shift(1) > 0)
            ).then(pl.col("high") - pl.col("high").shift(1)).otherwise(0).rolling_mean(window_size=14).alias("plus_dm_14"),

            # Minus DM
            pl.when(
                (pl.col("low").shift(1) - pl.col("low") > pl.col("high") - pl.col("high").shift(1)) &
                (pl.col("low").shift(1) - pl.col("low") > 0)
            ).then(pl.col("low").shift(1) - pl.col("low")).otherwise(0).rolling_mean(window_size=14).alias("minus_dm_14"),
        ])


# Pattern Recognition
class CandlestickPatterns:
    """Candlestick pattern detection."""

    @staticmethod
    @jit(nopython=True, cache=True)
    def doji(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, threshold: float = 0.1) -> np.ndarray:
        """Doji pattern detection."""
        n = len(open_)
        result = np.zeros(n, dtype=np.bool_)
        for i in range(n):
            body = abs(close[i] - open_[i])
            range_ = high[i] - low[i]
            if range_ > 0 and body / range_ <= threshold:
                result[i] = True
        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def hammer(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """Hammer pattern detection."""
        n = len(open_)
        result = np.zeros(n, dtype=np.bool_)
        for i in range(n):
            body = abs(close[i] - open_[i])
            lower_wick = min(open_[i], close[i]) - low[i]
            upper_wick = high[i] - max(open_[i], close[i])
            range_ = high[i] - low[i]

            if range_ > 0 and lower_wick > 2 * body and upper_wick < 0.1 * range_:
                result[i] = True
        return result

    @staticmethod
    @jit(nopython=True, cache=True)
    def engulfing(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
        """Bullish/Bearish Engulfing pattern."""
        n = len(open_)
        result = np.zeros(n, dtype=np.int8)  # 1 = bullish, -1 = bearish, 0 = none
        for i in range(1, n):
            abs(close[i - 1] - open_[i - 1])
            abs(close[i] - open_[i])

            # Bullish engulfing
            if close[i - 1] < open_[i - 1] and close[i] > open_[i]:
                if open_[i] < close[i - 1] and close[i] > open_[i - 1]:
                    result[i] = 1

            # Bearish engulfing
            elif close[i - 1] > open_[i - 1] and close[i] < open_[i]:
                if open_[i] > close[i - 1] and close[i] < open_[i - 1]:
                    result[i] = -1
        return result

    @staticmethod
    def detect_all_patterns(df: pl.DataFrame) -> pl.DataFrame:
        """Detect all candlestick patterns using Polars."""
        open_ = df["open"].to_numpy()
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()

        doji = CandlestickPatterns.doji(open_, high, low, close)
        hammer = CandlestickPatterns.hammer(open_, high, low, close)
        engulfing = CandlestickPatterns.engulfing(open_, close)

        return df.with_columns([
            pl.Series("pattern_doji", doji),
            pl.Series("pattern_hammer", hammer),
            pl.Series("pattern_engulfing", engulfing),
        ])


# Market Regime Detection
class MarketRegime:
    """Market regime detection using HMM and volatility."""

    @staticmethod
    def detect_regime_hmm(returns: np.ndarray, n_states: int = 3) -> np.ndarray:
        """Detect regime using Hidden Markov Model (requires hmmlearn)."""
        try:
            from hmmlearn import hmm
            model = hmm.GaussianHMM(n_components=n_states, covariance_type="full", n_iter=100)
            model.fit(returns.reshape(-1, 1))
            return model.predict(returns.reshape(-1, 1))
        except ImportError:
            # Fallback: simple volatility-based regime
            return MarketRegime.detect_regime_volatility(returns)

    @staticmethod
    def detect_regime_volatility(returns: np.ndarray, window: int = 20) -> np.ndarray:
        """Simple volatility-based regime detection."""
        vol = pd.Series(returns).rolling(window).std().values
        vol_median = np.nanmedian(vol)

        regimes = np.zeros(len(returns), dtype=np.int8)
        regimes[vol > vol_median * 1.5] = 2  # High volatility
        regimes[vol < vol_median * 0.5] = 0  # Low volatility
        regimes[(vol >= vol_median * 0.5) & (vol <= vol_median * 1.5)] = 1  # Normal

        return regimes

    @staticmethod
    def get_regime_name(regime: int) -> str:
        """Get regime name."""
        names = {0: "LOW_VOL", 1: "NORMAL", 2: "HIGH_VOL", 3: "TRENDING", 4: "RANGING"}
        return names.get(regime, f"UNKNOWN_{regime}")


import pandas as pd