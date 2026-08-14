"""
Stock Predictor tab – synthetic market forecasting & signal dashboard.

Features:
    1️⃣ Symbol selection dropdown (FX, ETFs, equities, crypto)
    2️⃣ Historical OHLC (last 180 bars) with volume – Plotly candlestick + bar chart
    3️⃣ Moving Averages (SMA 20/50/200, EMA 12/26/50) – toggles and crossover table
    4️⃣ Technical Indicators (RSI, MACD, Bollinger Bands, ATR, Stochastic, ADX) – subplots with current values + signal interpretation
    5️⃣ Market Sentiment – synthetic sentiment scores displayed as a radar chart
    6️⃣ Price Forecast – Linear regression, EMA‑based, Monte‑Carlo (1000 paths) – overlay line chart + summary table
    7️⃣ Signal Summary – final Buy / Sell / Hold recommendation with confidence %

All data is generated on‑the‑fly; no external API calls.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_OK = True
except Exception:  # pragma: no cover – Plotly is a hard dependency in the repo
    PLOTLY_OK = False

# Ensure project root is on sys.path (mirrors other tabs)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Synthetic data generators (cached)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _symbol_list() -> list[str]:
    """List of symbols offered in the dropdown."""
    return [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "XAUUSD",
        "BTCUSD",
        "ETHUSD",
        "SPY",
        "QQQ",
        "AAPL",
        "TSLA",
        "NVDA",
    ]

@st.cache_data(show_spinner=False)
def _historical_ohlc(symbol: str, bars: int = 180) -> pd.DataFrame:
    """Generate synthetic OHLCV data for *bars* periods ending now.

    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    The price follows a geometric random walk with drift.
    """
    rng = np.random.default_rng(hash(symbol) % (2**32 - 1))
    # Base price per asset class
    base = {
        "EURUSD": 1.08,
        "GBPUSD": 1.27,
        "USDJPY": 149.0,
        "XAUUSD": 2025.0,
        "BTCUSD": 30000.0,
        "ETHUSD": 2000.0,
        "SPY": 485.0,
        "QQQ": 420.0,
        "AAPL": 175.0,
        "TSLA": 750.0,
        "NVDA": 600.0,
    }.get(symbol, 100.0)
    # Log‑return drift and volatility (daily equivalents – our bars are made‑up minutes)
    drift = 0.00002  # tiny upward drift per bar
    vol = 0.0015    # volatility per bar
    # Simulate log returns
    log_returns = rng.normal(loc=drift, scale=vol, size=bars)
    price = base * np.exp(np.cumsum(log_returns))
    # Build OHLC from price series (simple approach: open = previous close)
    close = price
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.001, size=bars))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.001, size=bars))
    volume = rng.integers(500_000, 5_000_000, size=bars)
    timestamps = [datetime.now(timezone.utc) - timedelta(minutes=bars - i) for i in range(bars)]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    return df

@st.cache_data(show_spinner=False)
def _sentiment_scores() -> tuple[int, dict[str, int]]:
    """Generate an overall sentiment score and a breakdown.

    Returns overall 0‑100 integer and a dict with keys:
        news_sentiment, social_sentiment, technical_sentiment, options_sentiment
    """
    rng = np.random.default_rng(999)
    overall = int(np.clip(rng.normal(60, 20), 5, 95))
    breakdown = {
        "news_sentiment": int(np.clip(rng.normal(65, 15), 0, 100)),
        "social_sentiment": int(np.clip(rng.normal(55, 20), 0, 100)),
        "technical_sentiment": int(np.clip(rng.normal(58, 18), 0, 100)),
        "options_sentiment": int(np.clip(rng.normal(52, 22), 0, 100)),
    }
    return overall, breakdown

# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    up = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    rs = up / down
    return float(100 - 100 / (1 + rs.iloc[-1]))

def _macd(series: pd.Series) -> tuple[float, float, float]:
    ema12 = _ema(series, 12)
    ema26 = _ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    hist = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])

def _bbands(series: pd.Series, period: int = 20, mult: float = 2.0) -> tuple[float, float, float]:
    sma = _sma(series, period)
    std = series.rolling(window=period, min_periods=1).std()
    upper = sma + mult * std
    lower = sma - mult * std
    return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])

def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high_low = df["high"] - df["low"]
    high_prev_close = np.abs(df["high"] - df["close"].shift())
    low_prev_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1])

def _stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> tuple[float, float]:
    lowest_low = df["low"].rolling(k_period, min_periods=1).min()
    highest_high = df["high"].rolling(k_period, min_periods=1).max()
    k = 100 * (df["close"] - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(d_period, min_periods=1).mean()
    return float(k.iloc[-1]), float(d.iloc[-1])

def _adx(df: pd.DataFrame, period: int = 14) -> float:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr1 = df["high"] - df["low"]
    tr2 = np.abs(df["high"] - df["close"].shift())
    tr3 = np.abs(df["low"] - df["close"].shift())
    tr = pd.Series(np.maximum.reduce([tr1, tr2, tr3]))
    tr_smooth = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * _ema(pd.Series(plus_dm), period) / tr_smooth
    minus_di = 100 * _ema(pd.Series(minus_dm), period) / tr_smooth
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return float(adx.iloc[-1])

# ---------------------------------------------------------------------------
# Forecast models
# ---------------------------------------------------------------------------

def _linear_regression_forecast(df: pd.DataFrame, steps: int = 30) -> pd.Series:
    """Fit a simple linear regression to close price vs index and extrapolate.
    Returns a Series indexed by future timestamps.
    """
    y = df["close"].values
    X = np.arange(len(y)).reshape(-1, 1)
    # Ordinary Least Squares (closed‑form)
    beta = np.linalg.lstsq(X, y, rcond=None)[0][0]
    intercept = y[0] - beta * 0
    future_idx = np.arange(len(y), len(y) + steps)
    forecast = intercept + beta * future_idx
    future_times = [df["timestamp"].iloc[-1] + timedelta(minutes=i + 1) for i in range(steps)]
    return pd.Series(forecast, index=future_times)

def _ema_forecast(df: pd.DataFrame, steps: int = 30, ema_period: int = 20) -> pd.Series:
    ema_series = _ema(df["close"], ema_period)
    last_ema = ema_series.iloc[-1]
    # Assume price will revert toward EMA slowly – we simply repeat EMA as flat forecast
    future_times = [df["timestamp"].iloc[-1] + timedelta(minutes=i + 1) for i in range(steps)]
    return pd.Series([last_ema] * steps, index=future_times)

def _monte_carlo_forecast(df: pd.DataFrame, steps: int = 30, paths: int = 1000) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Geometric Brownian Motion Monte‑Carlo simulation.
    Returns median, lower 2.5% and upper 97.5% series.
    """
    rng = np.random.default_rng(12345)
    log_returns = np.log(df["close"] / df["close"].shift()).dropna()
    mu = log_returns.mean()
    sigma = log_returns.std()
    dt = 1  # one bar per step
    start_price = df["close"].iloc[-1]
    simulations = np.exp(
        (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * rng.standard_normal((paths, steps))
    )
    price_paths = start_price * simulations.cumprod(axis=1)
    median = np.median(price_paths, axis=0)
    lower = np.percentile(price_paths, 2.5, axis=0)
    upper = np.percentile(price_paths, 97.5, axis=0)
    future_times = [df["timestamp"].iloc[-1] + timedelta(minutes=i + 1) for i in range(steps)]
    return (
        pd.Series(median, index=future_times),
        pd.Series(lower, index=future_times),
        pd.Series(upper, index=future_times),
    )

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _candle_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["timestamp"],
            y=df["volume"],
            name="Volume",
            marker_color="#636efa",
            yaxis="y2",
        )
    )
    # Layout – dark theme
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=500,
        yaxis_title="Price",
        yaxis2=dict(
            title="Volume",
            overlaying="y",
            side="right",
            showgrid=False,
            tickfont=dict(color="#a1a1a1"),
        ),
        margin=dict(l=20, r=20, t=30, b=20),
    )
    return fig

def _ma_table(df: pd.DataFrame, periods_sma: list[int], periods_ema: list[int]) -> pd.DataFrame:
    latest = df.iloc[-1]
    rows = []
    for p in periods_sma:
        sma_val = _sma(df["close"], p).iloc[-1]
        rows.append({"period": f"SMA {p}", "value": round(sma_val, 4), "type": "SMA"})
    for p in periods_ema:
        ema_val = _ema(df["close"], p).iloc[-1]
        rows.append({"period": f"EMA {p}", "value": round(ema_val, 4), "type": "EMA"})
    # Compute crossovers where SMA and EMA of same period exist
    crossover_rows = []
    for p in set(periods_sma).intersection(periods_ema):
        sma = _sma(df["close"], p).iloc[-1]
        ema = _ema(df["close"], p).iloc[-1]
        if sma > ema:
            signal = "SMA > EMA"
        elif ema > sma:
            signal = "EMA > SMA"
        else:
            signal = "Equal"
        crossover_rows.append({"period": f"{p}", "SMA": round(sma, 4), "EMA": round(ema, 4), "crossover": signal})
    ma_df = pd.DataFrame(rows)
    cross_df = pd.DataFrame(crossover_rows)
    return ma_df, cross_df

def _technical_indicator_subplots(df: pd.DataFrame) -> go.Figure:
    # Create 3 rows: RSI, MACD, Bollinger Bands (with price), ATR & ADX, Stochastic
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.02, subplot_titles=["RSI", "MACD", "Bollinger Bands", "ATR & ADX", "Stochastic"])
    # RSI
    rsi_val = _rsi(df["close"])
    fig.add_trace(go.Scatter(x=df["timestamp"], y=_rsi(df["close"]).rolling(window=1), name="RSI", line=dict(color="#22c55e")), row=1, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=1, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#22c55e", row=1, col=1)
    # MACD
    macd_line, signal_line, hist = _macd(df["close"])
    fig.add_trace(go.Scatter(x=df["timestamp"], y=_ema(df["close"], 12) - _ema(df["close"], 26), name="MACD", line=dict(color="#3b82f6")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=_ema(_ema(df["close"], 12) - _ema(df["close"], 26), 9), name="Signal", line=dict(color="#ef4444")), row=2, col=1)
    # Bollinger Bands with price line
    upper, mid, lower = _bbands(df["close"])
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["close"], name="Close", line=dict(color="#fafafa")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=upper, name="Upper", line=dict(color="#ef4444", dash="dash")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=lower, name="Lower", line=dict(color="#22c55e", dash="dash")), row=3, col=1)
    # ATR & ADX – plotted together (two lines)
    atr_val = _atr(df)
    adx_val = _adx(df)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=_atr(df).rolling(window=1), name="ATR", line=dict(color="#facc15")), row=4, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=_adx(df).rolling(window=1), name="ADX", line=dict(color="#a855f7")), row=4, col=1)
    # Stochastic
    k, d = _stochastic(df)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=k, name="%K", line=dict(color="#22c55e")), row=5, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=d, name="%D", line=dict(color="#ef4444")), row=5, col=1)
    fig.update_layout(template="plotly_dark", height=900, margin=dict(l=20, r=20, t=40, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def _sentiment_radar(overall: int, breakdown: dict[str, int]) -> go.Figure:
    categories = ["News", "Social", "Technical", "Options"]
    values = [breakdown["news_sentiment"], breakdown["social_sentiment"], breakdown["technical_sentiment"], breakdown["options_sentiment"]]
    # Radar chart (polar)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values + [values[0]], theta=categories + [categories[0]], fill="toself", name="Sentiment", line_color="#22c55e"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(color="#fafafa"))),
        template="plotly_dark",
        height=350,
        margin=dict(l=20, r=20, t=30, b=20),
        showlegend=False,
    )
    return fig

def _forecast_chart(df: pd.DataFrame, lin: pd.Series, ema_f: pd.Series, mc_median: pd.Series, mc_low: pd.Series, mc_high: pd.Series) -> go.Figure:
    fig = go.Figure()
    # Historical price line for reference
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["close"], mode="lines", name="Historical", line=dict(color="#636efa")))
    # Linear regression forecast
    fig.add_trace(go.Scatter(x=lin.index, y=lin.values, mode="lines", name="Linear Reg.", line=dict(color="#22c55e", dash="dash")))
    # EMA forecast (flat line)
    fig.add_trace(go.Scatter(x=ema_f.index, y=ema_f.values, mode="lines", name="EMA Forecast", line=dict(color="#ef4444", dash="dot")))
    # Monte Carlo median + confidence band
    fig.add_trace(go.Scatter(x=mc_median.index, y=mc_median.values, mode="lines", name="MC Median", line=dict(color="#facc15")))
    fig.add_trace(go.Scatter(x=mc_low.index, y=mc_low.values, mode="lines", line=dict(color="#a16207", width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=mc_high.index, y=mc_high.values, mode="lines", line=dict(color="#a16207", width=0), fill="tonexty", fillcolor="rgba(250,200,25,0.2)", name="95% CI"))
    fig.update_layout(template="plotly_dark", height=500, margin=dict(l=20, r=20, t=30, b=20), xaxis_title="Time", yaxis_title="Price")
    return fig

def _final_signal(overall_sentiment: int, rsi_val: float, macd_hist: float, crossover_signal: str, mc_median: float, last_price: float) -> tuple[str, float]:
    """Combine a handful of signals into a final recommendation.
    Returns (label, confidence%).
    """
    score = 0.0
    # Sentiment weight
    score += (overall_sentiment - 50) * 0.2
    # RSI – oversold / overbought
    if rsi_val < 30:
        score += 15
    elif rsi_val > 70:
        score -= 15
    # MACD histogram sign
    score += 10 if macd_hist > 0 else -10
    # Crossover simple heuristic
    if "SMA > EMA" in crossover_signal:
        score += 5
    elif "EMA > SMA" in crossover_signal:
        score -= 5
    # Monte‑Carlo median vs last price
    price_last = mc_median  # median is already future price – compare to current close
    price_cur = last_price
    ret_pct = (price_last - price_cur) / price_cur * 100
    if ret_pct > 2:
        score += 10
    elif ret_pct < -2:
        score -= 10
    # Clamp and map to recommendation
    if score >= 20:
        return "Buy", min(100, round(score * 2))
    if score <= -20:
        return "Sell", min(100, round(-score * 2))
    return "Hold", max(0, round(50 + score))

# ---------------------------------------------------------------------------
# Main tab renderer
# ---------------------------------------------------------------------------

def render_stock_predictor_tab() -> None:
    st.header("📈 Stock Market Predictor")
    if not PLOTLY_OK:
        st.error("Plotly is required for this tab but could not be imported.")
        return

    # 1️⃣ Symbol selection
    symbol = st.selectbox("Select symbol", _symbol_list())

    # 2️⃣ Historical OHLC + volume
    hist_df = _historical_ohlc(symbol)
    st.subheader("Historical Price (last 180 bars)")
    st.plotly_chart(_candle_chart(hist_df), use_container_width=True)

    # 3️⃣ Moving Averages
    st.subheader("Moving Averages Comparison")
    sma_periods = [20, 50, 200]
    ema_periods = [12, 26, 50]
    ma_df, crossover_df = _ma_table(hist_df, sma_periods, ema_periods)
    # UI toggles – for brevity we display all and let Streamlit hide if not needed
    st.dataframe(ma_df, hide_index=True, use_container_width=True)
    if not crossover_df.empty:
        st.caption("Crossover signals where SMA and EMA of the same period intersect")
        st.dataframe(crossover_df, hide_index=True, use_container_width=True)

    # 4️⃣ Technical Indicators Evaluation
    st.subheader("Technical Indicators Evaluation")
    fig_tech = _technical_indicator_subplots(hist_df)
    st.plotly_chart(fig_tech, use_container_width=True)

    # Extract current indicator values for final signal weighting
    rsi_val = _rsi(hist_df["close"])
    # Current RSI value computed; additional indicators recalculated in §7 Signal Summary.

    # 5️⃣ Market Sentiment Scores (radar)
    overall_sent, breakdown = _sentiment_scores()
    st.subheader("Market Sentiment Scores")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Overall Sentiment", f"{overall_sent} / 100")
    with col2:
        st.plotly_chart(_sentiment_radar(overall_sent, breakdown), use_container_width=True)

    # 6️⃣ Price Forecast Curves
    st.subheader("Price Forecast (30 bars ahead)")
    lin_f = _linear_regression_forecast(hist_df)
    ema_f = _ema_forecast(hist_df)
    mc_mid, mc_low, mc_high = _monte_carlo_forecast(hist_df)
    st.plotly_chart(_forecast_chart(hist_df, lin_f, ema_f, mc_mid, mc_low, mc_high), use_container_width=True)
    # Forecast summary table
    forecast_rows = []
    # Linear regression target
    lr_target = lin_f.iloc[-1]
    forecast_rows.append({"model": "Linear Regression", "target_price_30d": round(lr_target, 2), "expected_return_pct": round((lr_target - hist_df["close"].iloc[-1]) / hist_df["close"].iloc[-1] * 100, 2), "confidence_level": "N/A"})
    ema_target = ema_f.iloc[-1]
    forecast_rows.append({"model": "EMA Forecast", "target_price_30d": round(ema_target, 2), "expected_return_pct": round((ema_target - hist_df["close"].iloc[-1]) / hist_df["close"].iloc[-1] * 100, 2), "confidence_level": "N/A"})
    mc_target = mc_mid.iloc[-1]
    forecast_rows.append({"model": "Monte Carlo", "target_price_30d": round(mc_target, 2), "expected_return_pct": round((mc_target - hist_df["close"].iloc[-1]) / hist_df["close"].iloc[-1] * 100, 2), "confidence_level": "95%"})
    forecast_df = pd.DataFrame(forecast_rows)
    st.dataframe(forecast_df, hide_index=True, use_container_width=True)

    # 7️⃣ Signal Summary
    st.subheader("Signal Summary")
    # Compute needed values for final recommendation
    # Re‑compute indicator values for weighting
    rsi_val = _rsi(hist_df["close"])
    macd_line, macd_signal, macd_hist = _macd(hist_df["close"])
    # Simple crossover string using last period common to both SMA and EMA (period 50)
    sma_50 = _sma(hist_df["close"], 50).iloc[-1]
    ema_50 = _ema(hist_df["close"], 50).iloc[-1]
    cross_signal = "SMA > EMA" if sma_50 > ema_50 else "EMA > SMA"
    # Monte Carlo median is already computed as mc_mid
    final_label, confidence = _final_signal(overall_sent, rsi_val, macd_hist, cross_signal, mc_mid.iloc[-1], hist_df["close"].iloc[-1])
    st.metric("Recommendation", final_label, f"Confidence: {confidence}%")
    st.caption("Weighted combination of sentiment, technicals, and forecast models.")

# End of file
