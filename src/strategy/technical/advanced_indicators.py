"""
Advanced technical indicators (pure numpy / pandas).

Implemented as static methods on ``AdvancedIndicators``.  Only ``numpy`` and
``pandas`` are imported; no external finance libraries are used.
All inputs are assumed to be 1‑D arrays of equal length.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _to_array(x, dtype: type = float) -> np.ndarray:
    """Convert input to a contiguous 1‑D ``np.ndarray``.

    ``x`` can be a list, pandas Series, or numpy array.
    """
    return np.ascontiguousarray(np.asarray(x, dtype=dtype))


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average.

    The first value is the series first element; the result is the same length
    as ``series`` with ``np.nan`` only for ``period`` <= 0 (which is not a valid
    use case).
    """
    n = len(series)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    alpha = 2.0 / (period + 1.0)
    out[0] = series[0]
    for i in range(1, n):
        out[i] = alpha * series[i] + (1.0 - alpha) * out[i - 1]
    return out


def _sma(series: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average (center‑aligned, first valid at ``period-1``)."""
    n = len(series)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out
    csum = np.cumsum(np.insert(series, 0, 0.0))
    out[period - 1 :] = (csum[period:] - csum[:-period]) / period
    return out


def _wma(series: np.ndarray, period: int) -> np.ndarray:
    """Weighted moving average with linear weights 1..period."""
    n = len(series)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out
    weights = np.arange(1, period + 1, dtype=float)
    wsum = weights.sum()
    for i in range(period - 1, n):
        out[i] = np.dot(series[i - period + 1 : i + 1], weights) / wsum
    return out


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    return tr


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = _true_range(high, low, close)
    n = len(tr)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out
    out[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out

# ---------------------------------------------------------------------------
# Indicator class
# ---------------------------------------------------------------------------

class AdvancedIndicators:
    """Collection of higher‑level technical indicators.

    All methods are static and accept raw ``np.ndarray`` inputs.  ``pandas`` is
    used only where its convenience outweighs a pure‑numpy implementation (e.g.
    regression).  The goal is clarity rather than ultra‑high performance.
    """

    # ---------------------------------------------------------------------
    # Ichimoku Cloud
    # ---------------------------------------------------------------------
    @staticmethod
    def ichimoku_cloud(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
        displacement: int = 26,
    ) -> dict:
        """Return Ichimoku components.

        ``tenkan`` – conversion line, ``kijun`` – baseline, ``senkou_a`` – leading
        span A, ``senkou_b`` – leading span B, ``chikou`` – lagging span.
        """
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        n = len(close)
        # Conversion and baseline are simple SMAs of the median price.
        median = (high + low) / 2.0
        tenkan = _sma(median, tenkan_period)
        kijun = _sma(median, kijun_period)
        senkou_a_raw = (tenkan + kijun) / 2.0
        senkou_b_raw = _sma(median, senkou_b_period)
        # Shift forward by displacement.
        senkou_a = np.full(n, np.nan, dtype=float)
        senkou_b = np.full(n, np.nan, dtype=float)
        if displacement < n:
            valid_a = ~np.isnan(senkou_a_raw)
            idx_a = np.where(valid_a)[0]
            if len(idx_a) > 0:
                end = min(n, idx_a[-1] + displacement + 1)
                senkou_a[idx_a + displacement] = senkou_a_raw[idx_a]
            valid_b = ~np.isnan(senkou_b_raw)
            idx_b = np.where(valid_b)[0]
            if len(idx_b) > 0:
                senkou_b[idx_b + displacement] = senkou_b_raw[idx_b]
        # Lagging span (chikou) is close shifted backward.
        chikou = np.full(n, np.nan, dtype=float)
        if displacement < n:
            chikou[: n - displacement] = close[displacement:]
        return {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "chikou": chikou,
        }

    # ---------------------------------------------------------------------
    # SuperTrend
    # ---------------------------------------------------------------------
    @staticmethod
    def supertrend(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 10,
        multiplier: float = 3.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """SuperTrend – returns ``trend`` (+1/-1) and ``stop`` series."""
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        n = len(close)
        atr = _atr(high, low, close, period)
        hl2 = (high + low) / 2.0
        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr
        trend = np.zeros(n, dtype=float)
        stop = np.full(n, np.nan, dtype=float)
        # Initialise at first valid ATR
        start = period - 1
        trend[start] = 1.0
        stop[start] = lower[start]
        for i in range(start + 1, n):
            prev_stop = stop[i - 1]
            # Adjust bands to avoid whipsaw
            if close[i - 1] > prev_stop:
                ub = min(upper[i], upper[i - 1])
                lb = lower[i]
            else:
                ub = upper[i]
                lb = max(lower[i], lower[i - 1])
            if trend[i - 1] == 1.0:
                if close[i] < lb:
                    trend[i] = -1.0
                    stop[i] = ub
                else:
                    trend[i] = 1.0
                    stop[i] = lb
            else:
                if close[i] > ub:
                    trend[i] = 1.0
                    stop[i] = lb
                else:
                    trend[i] = -1.0
                    stop[i] = ub
        return trend, stop

    # ---------------------------------------------------------------------
    # Hull Moving Average
    # ---------------------------------------------------------------------
    @staticmethod
    def hull_moving_average(close: np.ndarray, period: int = 14) -> np.ndarray:
        """Hull Moving Average (HMA)."""
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        half = max(int(period / 2), 1)
        sqrt_p = max(int(np.sqrt(period)), 1)
        wma_half = _wma(close, half)
        wma_full = _wma(close, period)
        diff = 2.0 * wma_half - wma_full
        out = _wma(diff, sqrt_p)
        return out

    # ---------------------------------------------------------------------
    # Williams %R
    # ---------------------------------------------------------------------
    @staticmethod
    def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            hh = np.max(high[i - period + 1 : i + 1])
            ll = np.min(low[i - period + 1 : i + 1])
            out[i] = -100.0 * (hh - close[i]) / (hh - ll) if hh != ll else 0.0
        return out

    # ---------------------------------------------------------------------
    # Commodity Channel Index (CCI)
    # ---------------------------------------------------------------------
    @staticmethod
    def commodity_channel_index(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        tp = (high + low + close) / 3.0
        sma = _sma(tp, period)
        md = np.full_like(tp, np.nan)
        for i in range(period - 1, len(tp)):
            md[i] = np.mean(np.abs(tp[i - period + 1 : i + 1] - sma[i]))
        cci = (tp - sma) / (0.015 * md)
        return cci

    # ---------------------------------------------------------------------
    # Keltner Channel
    # ---------------------------------------------------------------------
    @staticmethod
    def keltner_channel(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 20,
        multiplier: float = 2.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        ema = _ema(close, period)
        tr = _true_range(high, low, close)
        atr = _sma(tr, period)  # simple ATR for ease
        middle = ema
        upper = ema + multiplier * atr
        lower = ema - multiplier * atr
        return upper, middle, lower

    # ---------------------------------------------------------------------
    # Elder Impulse System (EMA + MACD)
    # ---------------------------------------------------------------------
    @staticmethod
    def elder_impulse(
        close: np.ndarray,
        ema_period: int = 13,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
    ) -> np.ndarray:
        close = _to_array(close)
        ema = _ema(close, ema_period)
        macd_line = _ema(close, macd_fast) - _ema(close, macd_slow)
        signal = _ema(macd_line, macd_signal)
        # 1 = bullish, -1 = bearish, 0 = neutral
        signals = np.zeros_like(close, dtype=int)
        for i in range(1, len(close)):
            ema_up = ema[i] > ema[i - 1]
            macd_up = macd_line[i] > signal[i]
            if ema_up and macd_up:
                signals[i] = 1
            elif not ema_up and not macd_up:
                signals[i] = -1
            else:
                signals[i] = 0
        return signals

    # ---------------------------------------------------------------------
    # Center of Gravity (COG)
    # ---------------------------------------------------------------------
    @staticmethod
    def center_of_gravity(close: np.ndarray, period: int = 10) -> np.ndarray:
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            window = close[i - period + 1 : i + 1]
            weights = np.arange(1, period + 1)
            denom = window.sum()
            out[i] = (weights @ window) / denom if denom != 0 else np.nan
        return out

    # ---------------------------------------------------------------------
    # Relative Vigor Index (RVI)
    # ---------------------------------------------------------------------
    @staticmethod
    def relative_vigor_index(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 10) -> np.ndarray:
        o = _to_array(open_)
        h = _to_array(high)
        l = _to_array(low)
        c = _to_array(close)
        n = len(c)
        rvi = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            num = np.mean((c[i - period + 1 : i + 1] - o[i - period + 1 : i + 1]) / (h[i - period + 1 : i + 1] - l[i - period + 1 : i + 1]))
            den = np.mean((c[i - period + 1 : i + 1] - o[i - period + 1 : i + 1]) / (h[i - period + 1 : i + 1] - l[i - period + 1 : i + 1]))
            rvi[i] = num  # simplified – typical RVI uses SMA of numerator/denominator separately
        return rvi

    # ---------------------------------------------------------------------
    # Ultimate Oscillator
    # ---------------------------------------------------------------------
    @staticmethod
    def ultimate_oscillator(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period1: int = 7,
        period2: int = 14,
        period3: int = 28,
    ) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        bp = close - np.minimum(low, np.concatenate(([close[0]], close[:-1])))
        tr = _true_range(high, low, close)
        def avg(b, t, p):
            return np.convolve(b, np.ones(p), "valid") / np.convolve(t, np.ones(p), "valid")
        av1 = avg(bp, tr, period1)
        av2 = avg(bp, tr, period2)
        av3 = avg(bp, tr, period3)
        # Pad to original length
        pad = len(close) - len(av3)
        uo = np.full_like(close, np.nan, dtype=float)
        uo[pad:] = 100.0 * (4 * av1 + 2 * av2 + av3) / 7.0
        return uo

    # ---------------------------------------------------------------------
    # Chaikin Money Flow (CMF)
    # ---------------------------------------------------------------------
    @staticmethod
    def chaikin_money_flow(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 20) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        vol = _to_array(volume)
        mfv = ((close - low) - (high - close)) / (high - low + 1e-9) * vol
        cmf = np.full_like(close, np.nan, dtype=float)
        for i in range(period - 1, len(close)):
            cmf[i] = mfv[i - period + 1 : i + 1].sum() / vol[i - period + 1 : i + 1].sum()
        return cmf

    # ---------------------------------------------------------------------
    # Detrended Price Oscillator (DPO)
    # ---------------------------------------------------------------------
    @staticmethod
    def detrended_price_oscillator(close: np.ndarray, period: int = 20) -> np.ndarray:
        close = _to_array(close)
        lag = int(period / 2) + 1
        sma = _sma(close, period)
        dpo = np.full_like(close, np.nan, dtype=float)
        for i in range(lag, len(close)):
            dpo[i] = close[i - lag] - sma[i]
        return dpo

    # ---------------------------------------------------------------------
    # True Strength Index (TSI)
    # ---------------------------------------------------------------------
    @staticmethod
    def true_strength_index(close: np.ndarray, r: int = 25, s: int = 13) -> np.ndarray:
        close = _to_array(close)
        diff = np.diff(close, prepend=close[0])
        def double_ema(series, period):
            return _ema(_ema(series, period), period)
        ema1 = double_ema(diff, r)
        ema2 = double_ema(np.abs(diff), r)
        tsi = np.full_like(close, np.nan, dtype=float)
        tsi[r * 2 - 2 :] = ema1[r - 1 :] / ema2[r - 1 :]
        tsi = _ema(tsi, s)
        return tsi

    # ---------------------------------------------------------------------
    # Money Flow Index (MFI)
    # ---------------------------------------------------------------------
    @staticmethod
    def money_flow_index(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        vol = _to_array(volume)
        typical = (high + low + close) / 3.0
        mf = typical * vol
        pos = np.zeros_like(mf)
        neg = np.zeros_like(mf)
        for i in range(1, len(close)):
            if typical[i] > typical[i - 1]:
                pos[i] = mf[i]
            elif typical[i] < typical[i - 1]:
                neg[i] = mf[i]
        mfi = np.full_like(close, np.nan, dtype=float)
        for i in range(period, len(close)):
            pos_sum = pos[i - period + 1 : i + 1].sum()
            neg_sum = neg[i - period + 1 : i + 1].sum()
            if neg_sum == 0:
                mfi[i] = 100.0
            else:
                mfr = pos_sum / neg_sum
                mfi[i] = 100.0 - (100.0 / (1.0 + mfr))
        return mfi

    # ---------------------------------------------------------------------
    # Aroon
    # ---------------------------------------------------------------------
    @staticmethod
    def aroon(high: np.ndarray, low: np.ndarray, period: int = 25) -> tuple[np.ndarray, np.ndarray]:
        high = _to_array(high)
        low = _to_array(low)
        n = len(high)
        up = np.full(n, np.nan, dtype=float)
        down = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            window_high = high[i - period + 1 : i + 1]
            window_low = low[i - period + 1 : i + 1]
            days_since_max = period - np.argmax(window_high)
            days_since_min = period - np.argmin(window_low)
            up[i] = 100.0 * (period - days_since_max) / period
            down[i] = 100.0 * (period - days_since_min) / period
        return up, down

    # ---------------------------------------------------------------------
    # Heikin-Ashi
    # ---------------------------------------------------------------------
    @staticmethod
    def heikin_ashi(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        o = _to_array(open_)
        h = _to_array(high)
        l = _to_array(low)
        c = _to_array(close)
        n = len(c)
        ha_close = (o + h + l + c) / 4.0
        ha_open = np.full(n, np.nan, dtype=float)
        ha_open[0] = (o[0] + c[0]) / 2.0
        for i in range(1, n):
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
        ha_high = np.maximum.reduce([h, ha_open, ha_close])
        ha_low = np.minimum.reduce([l, ha_open, ha_close])
        return ha_open, ha_high, ha_low, ha_close

    # ---------------------------------------------------------------------
    # Chande Momentum Oscillator (CMO)
    # ---------------------------------------------------------------------
    @staticmethod
    def chande_momentum_oscillator(close: np.ndarray, period: int = 14) -> np.ndarray:
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        diff = np.diff(close, prepend=close[0])
        for i in range(period - 1, n):
            up = np.sum(diff[i - period + 1 : i + 1][diff[i - period + 1 : i + 1] > 0])
            down = -np.sum(diff[i - period + 1 : i + 1][diff[i - period + 1 : i + 1] < 0])
            denom = up + down
            out[i] = (up - down) / denom * 100.0 if denom != 0 else 0.0
        return out

    # ---------------------------------------------------------------------
    # VWAP
    # ---------------------------------------------------------------------
    @staticmethod
    def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        vol = _to_array(volume)
        tp = (high + low + close) / 3.0
        cum_tp_vol = np.cumsum(tp * vol)
        cum_vol = np.cumsum(vol)
        return cum_tp_vol / cum_vol

    # ---------------------------------------------------------------------
    # Parabolic SAR
    # ---------------------------------------------------------------------
    @staticmethod
    def parabolic_sar(high: np.ndarray, low: np.ndarray, step: float = 0.02, max_step: float = 0.2) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        n = len(high)
        sar = np.full(n, np.nan, dtype=float)
        # Initialise trend as uptrend
        is_up = True
        af = step
        ep = low[0]
        sar[0] = low[0]
        for i in range(1, n):
            prev_sar = sar[i - 1]
            if is_up:
                sar[i] = prev_sar + af * (ep - prev_sar)
                if low[i] < sar[i]:
                    # Switch to downtrend
                    is_up = False
                    sar[i] = ep
                    af = step
                    ep = high[i]
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + step, max_step)
            else:
                sar[i] = prev_sar + af * (ep - prev_sar)
                if high[i] > sar[i]:
                    # Switch to uptrend
                    is_up = True
                    sar[i] = ep
                    af = step
                    ep = low[i]
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + step, max_step)
        return sar

    # ---------------------------------------------------------------------
    # ADX
    # ---------------------------------------------------------------------
    @staticmethod
    def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        tr = _true_range(high, low, close)
        plus_dm = np.diff(high, prepend=high[0])
        minus_dm = -np.diff(low, prepend=low[0])
        plus_dm[plus_dm < 0] = 0.0
        minus_dm[minus_dm < 0] = 0.0
        tr_smooth = _sma(tr, period)
        plus_smooth = _sma(plus_dm, period)
        minus_smooth = _sma(minus_dm, period)
        plus_di = 100.0 * plus_smooth / tr_smooth
        minus_di = 100.0 * minus_smooth / tr_smooth
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)
        adx = _sma(dx, period)
        return adx

    # ---------------------------------------------------------------------
    # Linear Regression Slope
    # ---------------------------------------------------------------------
    @staticmethod
    def linear_regression_slope(close: np.ndarray, period: int = 14) -> np.ndarray:
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        x = np.arange(period)
        x_mean = x.mean()
        denom = np.sum((x - x_mean) ** 2)
        for i in range(period - 1, n):
            y = close[i - period + 1 : i + 1]
            y_mean = y.mean()
            num = np.sum((x - x_mean) * (y - y_mean))
            out[i] = num / denom if denom != 0 else np.nan
        return out

    # ---------------------------------------------------------------------
    # R-squared of linear regression
    # ---------------------------------------------------------------------
    @staticmethod
    def r_squared(close: np.ndarray, period: int = 14) -> np.ndarray:
        close = _to_array(close)
        n = len(close)
        out = np.full(n, np.nan, dtype=float)
        x = np.arange(period)
        x_mean = x.mean()
        denom = np.sum((x - x_mean) ** 2)
        for i in range(period - 1, n):
            y = close[i - period + 1 : i + 1]
            y_mean = y.mean()
            num = np.sum((x - x_mean) * (y - y_mean))
            slope = num / denom if denom != 0 else 0.0
            intercept = y_mean - slope * x_mean
            y_pred = slope * x + intercept
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y_mean) ** 2)
            out[i] = 1.0 - ss_res / ss_tot if ss_tot != 0 else np.nan
        return out

    # ---------------------------------------------------------------------
    # Coppock Curve
    # ---------------------------------------------------------------------
    @staticmethod
    def coppock_curve(close: np.ndarray, roc1: int = 14, roc2: int = 11, wma: int = 10) -> np.ndarray:
        close = _to_array(close)
        roc1_arr = (close[roc1:] - close[:-roc1]) / close[:-roc1]
        roc2_arr = (close[roc2:] - close[:-roc2]) / close[:-roc2]
        min_len = min(len(roc1_arr), len(roc2_arr))
        cci = roc1_arr[-min_len:] + roc2_arr[-min_len:]
        # Pad to original length with nan
        out = np.full_like(close, np.nan, dtype=float)
        if len(cci) >= wma:
            out[-len(cci) :] = _wma(cci, wma)
        return out

    # ---------------------------------------------------------------------
    # Stochastic Oscillator
    # ---------------------------------------------------------------------
    @staticmethod
    def stochastic_oscillator(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        k_period: int = 14,
        d_period: int = 3,
    ) -> tuple[np.ndarray, np.ndarray]:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        n = len(close)
        k = np.full(n, np.nan, dtype=float)
        for i in range(k_period - 1, n):
            hh = np.max(high[i - k_period + 1 : i + 1])
            ll = np.min(low[i - k_period + 1 : i + 1])
            k[i] = 100.0 * (close[i] - ll) / (hh - ll) if hh != ll else 0.0
        d = _sma(k, d_period)
        return k, d

    # ---------------------------------------------------------------------
    # Pivot Points (standard)
    # ---------------------------------------------------------------------
    @staticmethod
    def pivot_points(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> dict:
        high = _to_array(high)
        low = _to_array(low)
        close = _to_array(close)
        pp = (high + low + close) / 3.0
        r1 = 2 * pp - low
        r2 = pp + (high - low)
        r3 = high + 2 * (pp - low)
        s1 = 2 * pp - high
        s2 = pp - (high - low)
        s3 = low - 2 * (high - pp)
        return {
            "pp": pp,
            "r1": r1,
            "r2": r2,
            "r3": r3,
            "s1": s1,
            "s2": s2,
            "s3": s3,
        }

    # ---------------------------------------------------------------------
    # Donchian Channel
    # ---------------------------------------------------------------------
    @staticmethod
    def donchian_channel(high: np.ndarray, low: np.ndarray, period: int = 20) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        high = _to_array(high)
        low = _to_array(low)
        n = len(high)
        upper = np.full(n, np.nan, dtype=float)
        lower = np.full(n, np.nan, dtype=float)
        middle = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            upper[i] = np.max(high[i - period + 1 : i + 1])
            lower[i] = np.min(low[i - period + 1 : i + 1])
            middle[i] = (upper[i] + lower[i]) / 2.0
        return upper, middle, lower

    # ---------------------------------------------------------------------
    # Awesome Oscillator
    # ---------------------------------------------------------------------
    @staticmethod
    def awesome_oscillator(high: np.ndarray, low: np.ndarray, fast: int = 5, slow: int = 34) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        median = (high + low) / 2.0
        sma_fast = _sma(median, fast)
        sma_slow = _sma(median, slow)
        return sma_fast - sma_slow

    # ---------------------------------------------------------------------
    # Accelerator Oscillator
    # ---------------------------------------------------------------------
    @staticmethod
    def accelerator_oscillator(high: np.ndarray, low: np.ndarray, fast: int = 5, slow: int = 34) -> np.ndarray:
        ao = AdvancedIndicators.awesome_oscillator(high, low, fast, slow)
        sma_ao = _sma(ao, 5)
        return ao - sma_ao

    # ---------------------------------------------------------------------
    # Fractal Indicator (simple version – high/low fractals)
    # ---------------------------------------------------------------------
    @staticmethod
    def fractal_indicator(high: np.ndarray, low: np.ndarray, period: int = 5) -> np.ndarray:
        high = _to_array(high)
        low = _to_array(low)
        n = len(high)
        out = np.full(n, np.nan, dtype=float)
        half = period // 2
        for i in range(half, n - half):
            window_h = high[i - half : i + half + 1]
            window_l = low[i - half : i + half + 1]
            if high[i] == np.max(window_h):
                out[i] = 1.0  # bullish fractal
            elif low[i] == np.min(window_l):
                out[i] = -1.0  # bearish fractal
        return out

    # ---------------------------------------------------------------------
    # Alligator (Jaw, Teeth, Lips) – uses SMAs
    # ---------------------------------------------------------------------
    @staticmethod
    def alligator(high: np.ndarray, low: np.ndarray, jaw: int = 13, teeth: int = 8, lips: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        median = (high + low) / 2.0
        jaw_sma = _sma(median, jaw)
        teeth_sma = _sma(median, teeth)
        lips_sma = _sma(median, lips)
        # Apply displacement of 8 for all components (standard) – shift forward.
        displacement = 8
        n = len(median)
        def shift(arr):
            shifted = np.full(n, np.nan, dtype=float)
            if displacement < n:
                shifted[displacement:] = arr[:-displacement]
            return shifted
        return shift(jaw_sma), shift(teeth_sma), shift(lips_sma)

    # ---------------------------------------------------------------------
    # Gator Oscillator – derived from Alligator
    # ---------------------------------------------------------------------
    @staticmethod
    def gator_oscillator(high: np.ndarray, low: np.ndarray) -> np.ndarray:
        jaw, teeth, lips = AdvancedIndicators.alligator(high, low)
        # Gap between jaw and teeth plus lips
        gap_jaw_teeth = np.abs(jaw - teeth)
        gap_teeth_lips = np.abs(teeth - lips)
        return gap_jaw_teeth + gap_teeth_lips
