"""Sentiment tab — Deep Market Sentiment Analyzer.

Covers:
  * Overall Sentiment Gauge (0–100, red→yellow→green)
  * News Sentiment (RSS / feed headlines, color-coded)
  * Social Media Sentiment (Twitter / Reddit)
  * Fear & Greed Index with 7d / 30d sparklines
  * Put/Call Ratio with interpretation
  * VIX / Volatility Index with regime indicator
  * Sentiment vs Price Divergence scanner
  * Central Bank Sentiment (Fed / ECB / BoJ / BoE)

All data is synthetic and generated in-page. No external API calls.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:  # pragma: no cover
    PLOTLY_OK = False

# Ensure project root is on sys.path for optional imports
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ────────────────────────────────────────────────────────────────────────────
# Synthetic data generators
# ────────────────────────────────────────────────────────────────────────────

_NEWS_SOURCES = [
    "Reuters", "Bloomberg", "CNBC", "WSJ", "FT",
    "MarketWatch", "Investing.com", "FXStreet", "DailyFX", "CoinDesk",
]

_NEWS_HEADLINE_TEMPLATES = [
    "{sym} rallies on stronger-than-expected {driver}",
    "{sym} drops as {driver} fuels recession fears",
    "Analysts upgrade {sym} citing robust {driver}",
    "{sym} consolidates ahead of central bank decision",
    "Hawkish comments lift USD; {sym} slips",
    "Risk-on mood boosts {sym} to multi-week highs",
    "{sym} breaks key support as {driver} disappoints",
    "Bullish technical setup forming in {sym}",
    "{sym} trades range-bound amid thin liquidity",
    "Geopolitical tensions weigh on {sym}",
    "Strong earnings push {sym} higher",
    "Weak macro data pressures {sym} lower",
    "{sym} options activity signals caution among traders",
    "Volatility spike drags {sym} to session lows",
    "Positive momentum continues for {sym}",
    "Profit-taking caps gains in {sym}",
    "{sym} eyes breakout as institutional flow picks up",
    "Dollar strength sends {sym} lower across the board",
    "Commodity rally lifts {sym} to fresh tops",
    "Risk-off tone keeps {sym} under pressure",
]

_NEWS_DRIVERS = [
    "CPI print", "jobs report", "PMI data", "GDP release",
    "retail sales", "rate decision", "geopolitical headlines",
    "earnings beat", "trade balance", "consumer confidence",
]

_NEWS_ENTITIES = [
    "Fed", "ECB", "BoJ", "BoE", "Powell", "Lagarde",
    "Ueda", "Bailey", "inflation", "yields", "Treasury",
    "China", "OPEC", "BlackRock",
]

_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
    "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "SPX", "NDX", "USOIL",
]


def _seed_rng() -> random.Random:
    """Return a seed-stable RNG so repeated renders show consistent values."""
    seed = int(st.session_state.get("sentiment_seed", 42))
    return random.Random(seed)


def _overall_score() -> int:
    """Overall market sentiment score in [0, 100] (50 = neutral)."""
    rng = _seed_rng()
    # Slight positive bias to mimic typical mid-cycle market
    return int(np.clip(rng.gauss(58, 18), 5, 95))


def _classify_overall(score: int) -> tuple[str, str]:
    """Return (label, hex color) for an overall sentiment score."""
    if score >= 70:
        return "Extreme Greed", "#16a34a"
    if score >= 55:
        return "Bullish", "#22c55e"
    if score >= 46:
        return "Neutral", "#eab308"
    if score >= 30:
        return "Bearish", "#ef4444"
    return "Extreme Fear", "#991b1b"


def _news_sentiment() -> pd.DataFrame:
    """Synthetic RSS / news-headline sentiment table."""
    rng = _seed_rng()
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for i in range(20):
        sym = rng.choice(_SYMBOLS)
        headline = rng.choice(_NEWS_HEADLINE_TEMPLATES).format(
            sym=sym, driver=rng.choice(_NEWS_DRIVERS),
        )
        score = round(rng.uniform(-1.0, 1.0), 3)
        n_entities = rng.randint(1, 4)
        entities = ", ".join(rng.sample(_NEWS_ENTITIES, n_entities))
        ts = (now - timedelta(minutes=rng.randint(1, 240))).strftime("%Y-%m-%d %H:%M")
        rows.append({
            "source": rng.choice(_NEWS_SOURCES),
            "headline": headline,
            "sentiment_score": score,
            "entities_mentioned": entities,
            "timestamp": ts,
        })
    df = pd.DataFrame(rows).sort_values("timestamp", ascending=False).reset_index(drop=True)
    return df


def _social_sentiment() -> pd.DataFrame:
    """Synthetic Twitter / Reddit sentiment per symbol."""
    rng = _seed_rng()
    platforms = ["Twitter/X", "Reddit", "StockTwits"]
    rows: list[dict[str, Any]] = []
    for sym in _SYMBOLS[:12]:
        for platform in platforms:
            sentiment = round(rng.uniform(-1.0, 1.0), 2)
            mentions = rng.randint(120, 18_500)
            trend_pct = round(rng.gauss(0, 25), 1)
            rows.append({
                "platform": platform,
                "symbol": sym,
                "sentiment": sentiment,
                "mentions": mentions,
                "volume_trend": f"{trend_pct:+.1f}%",
            })
    return pd.DataFrame(rows)


def _fear_greed_history(days: int) -> pd.DataFrame:
    """Return synthetic Fear & Greed history for the last ``days`` days."""
    rng = random.Random(7)  # separate, stable series for the F&G history
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=i) for i in range(days, -1, -1)]
    base = 50
    values = []
    cur = base
    for _ in dates:
        cur = cur + rng.gauss(0, 6)
        cur = max(5, min(95, cur))
        # ``round`` already returns an int when used without ndigits; extra int() is redundant (RUF046)
        values.append(round(cur))
    return pd.DataFrame({"date": dates, "value": values})


def _fear_greed_current() -> int:
    return int(_fear_greed_history(0)["value"].iloc[-1])


def _put_call_ratio() -> float:
    rng = _seed_rng()
    return round(rng.gauss(0.85, 0.18), 3)


def _vix_value() -> float:
    rng = _seed_rng()
    return round(rng.gauss(18.5, 4.5), 2)


def _divergence_table() -> pd.DataFrame:
    """Symbols where sentiment diverges from price action over the last 7d."""
    rng = _seed_rng()
    rows: list[dict[str, Any]] = []
    for sym in _SYMBOLS:
        price_trend = round(rng.gauss(0, 3.5), 2)  # % change over 7d
        sentiment = round(rng.uniform(-1, 1), 2)

        divergence = ""
        action = ""
        # Bullish divergence: price weak, sentiment strong
        if price_trend < -1.0 and sentiment > 0.35:
            divergence = "Bullish divergence"
            action = "Watch for reversal long"
        # Bearish divergence: price strong, sentiment weak
        elif price_trend > 1.0 and sentiment < -0.35:
            divergence = "Bearish divergence"
            action = "Consider trim / short bias"
        # Confirmation
        elif (price_trend > 0 and sentiment > 0) or (price_trend < 0 and sentiment < 0):
            divergence = "Aligned"
            action = "Hold / trend-follow"
        else:
            divergence = "Neutral"
            action = "No clear edge"

        rows.append({
            "symbol": sym,
            "price_trend_7d": price_trend,
            "sentiment_score": sentiment,
            "divergence_type": divergence,
            "action_hint": action,
        })
    df = pd.DataFrame(rows)
    # Only keep rows that show some divergence or are aligned-confirmed interesting
    df = df[df["divergence_type"].isin(["Bullish divergence", "Bearish divergence", "Aligned"])]
    return df.reset_index(drop=True)


def _central_bank_sentiment() -> pd.DataFrame:
    """Synthetic hawkish/dovish stance per central bank based on recent statements."""
    rng = _seed_rng()
    data = [
        {
            "central_bank": "Federal Reserve (Fed)",
            "recent_statement": (
                "Inflation remains elevated; further policy firming may be appropriate "
                "if data warrants."
            ),
            "stance_score": round(rng.uniform(0.55, 0.95), 2),
            "next_meeting": (datetime.now(timezone.utc) + timedelta(days=12)).strftime("%Y-%m-%d"),
            "rate_path": "Hiking bias",
        },
        {
            "central_bank": "European Central Bank (ECB)",
            "recent_statement": (
                "Disinflation is proceeding; we will calibrate policy meeting by meeting."
            ),
            "stance_score": round(rng.uniform(0.20, 0.55), 2),
            "next_meeting": (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%d"),
            "rate_path": "Data-dependent",
        },
        {
            "central_bank": "Bank of Japan (BoJ)",
            "recent_statement": (
                "Patience remains appropriate; accommodative monetary framework continues."
            ),
            "stance_score": round(rng.uniform(-0.85, -0.20), 2),
            "next_meeting": (datetime.now(timezone.utc) + timedelta(days=28)).strftime("%Y-%m-%d"),
            "rate_path": "Dovish / easing bias",
        },
        {
            "central_bank": "Bank of England (BoE)",
            "recent_statement": (
                "Services inflation persists; policy needs to remain restrictive for long enough."
            ),
            "stance_score": round(rng.uniform(0.40, 0.80), 2),
            "next_meeting": (datetime.now(timezone.utc) + timedelta(days=18)).strftime("%Y-%m-%d"),
            "rate_path": "Hold / hike bias",
        },
    ]
    df = pd.DataFrame(data)
    df["stance_label"] = df["stance_score"].apply(_stance_label)
    return df


def _stance_label(score: float) -> str:
    if score >= 0.6:
        return "Hawkish"
    if score >= 0.2:
        return "Mildly Hawkish"
    if score >= -0.2:
        return "Neutral"
    if score >= -0.6:
        return "Mildly Dovish"
    return "Dovish"


def _vix_regime(vix: float) -> tuple[str, str]:
    if vix < 15:
        return "Low Volatility", "#16a34a"
    if vix < 25:
        return "Normal Volatility", "#eab308"
    return "High Volatility (Stressed)", "#ef4444"


def _pc_interpretation(pc: float) -> tuple[str, str]:
    if pc < 0.7:
        return "Bullish (heavy call buying)", "#16a34a"
    if pc > 1.0:
        return "Bearish (heavy put buying)", "#ef4444"
    return "Neutral", "#eab308"


# ────────────────────────────────────────────────────────────────────────────
# Plotly helpers
# ────────────────────────────────────────────────────────────────────────────

def _gauge(
    value: float,
    title: str,
    *,
    vmin: float = 0,
    vmax: float = 100,
    steps: list[dict[str, Any]] | None = None,
    threshold: float | None = None,
) -> go.Figure | None:
    """Build a dark-themed Plotly gauge. Returns None if Plotly is unavailable."""
    if not PLOTLY_OK:
        return None

    if steps is None:
        steps = [
            {"range": [0, 30], "color": "#7f1d1d"},
            {"range": [30, 45], "color": "#ef4444"},
            {"range": [45, 55], "color": "#eab308"},
            {"range": [55, 70], "color": "#84cc16"},
            {"range": [70, 100], "color": "#16a34a"},
        ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        number={"font": {"color": "#fafafa", "size": 48}, "valueformat": ".1f"},
        delta={"reference": (vmin + vmax) / 2, "increasing": {"color": "#22c55e"}, "decreasing": {"color": "#ef4444"}},
        title={"text": title, "font": {"color": "#fafafa", "size": 18}},
        gauge={
            "axis": {"range": [vmin, vmax], "tickcolor": "#fafafa", "tickfont": {"color": "#fafafa"}},
            "bar": {"color": "#fafafa", "thickness": 0.18},
            "bgcolor": "#0e1117",
            "borderwidth": 0,
            "steps": steps,
            "threshold": (
                {
                    "line": {"color": "#fafafa", "width": 4},
                    "thickness": 0.85,
                    "value": threshold,
                }
                if threshold is not None
                else None
            ),
        },
    ))

    fig.update_layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font={"color": "#fafafa"},
        height=320,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig


def _sparkline(series: pd.Series, color: str = "#22c55e") -> go.Figure | None:
    if not PLOTLY_OK:
        return None
    fig = go.Figure(go.Scatter(
        x=list(range(len(series))),
        y=series.values,
        mode="lines",
        line={"color": color, "width": 2},
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.15)",
        hoverinfo="y",
    ))
    fig.update_layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font={"color": "#fafafa"},
        height=80,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        xaxis={"visible": False},
        yaxis={"visible": False, "fixedrange": True},
        showlegend=False,
    )
    return fig


def _styled_dataframe(df: pd.DataFrame, score_col: str | None = None) -> pd.io.formats.style.Styler:
    """Return a Styler that color-codes a sentiment column if present."""
    if score_col is None or score_col not in df.columns:
        return df.style  # type: ignore[return-value]

    def _color(val: float) -> str:
        if pd.isna(val):
            return ""
        if val > 0.2:
            return "color: #22c55e; font-weight: 600;"
        if val < -0.2:
            return "color: #ef4444; font-weight: 600;"
        return "color: #eab308;"

    return df.style.map(_color, subset=[score_col])


# ────────────────────────────────────────────────────────────────────────────
# Section renderers
# ────────────────────────────────────────────────────────────────────────────

def _render_overall_gauge(score: int) -> None:
    label, color = _classify_overall(score)
    st.subheader("📊 Overall Market Sentiment")
    cols = st.columns([2, 1])
    with cols[0]:
        fig = _gauge(score, "Composite Sentiment Score (0–100)")
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.progress(score / 100.0, text=f"{score} / 100")
    with cols[1]:
        st.markdown("### Sentiment Label")
        st.markdown(
            f"<div style='background:{color};color:#0e1117;padding:18px;border-radius:10px;"
            f"text-align:center;font-weight:700;font-size:1.5rem;'>{label}</div>",
            unsafe_allow_html=True,
        )
        st.metric("Score", f"{score} / 100")
        delta = score - 50
        st.metric("vs Neutral (50)", f"{delta:+d}")
        st.caption(
            "Score blends news, social, volatility, breadth and central-bank tone. "
            "Higher = greedier."
        )


def _render_news() -> None:
    df = _news_sentiment()
    st.subheader("📰 News Sentiment (RSS / Headlines)")
    st.caption(
        "Top 20 headlines scored from -1 (most bearish) to +1 (most bullish). "
        "Color-coded green/red/yellow by score."
    )

    # Summary metrics
    avg_score = df["sentiment_score"].mean()
    pos = (df["sentiment_score"] > 0.2).sum()
    neg = (df["sentiment_score"] < -0.2).sum()
    neu = len(df) - pos - neg
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg Score", f"{avg_score:+.2f}")
    m2.metric("🟢 Positive", int(pos))
    m3.metric("🟡 Neutral", int(neu))
    m4.metric("🔴 Negative", int(neg))

    st.dataframe(
        _styled_dataframe(df, score_col="sentiment_score"),
        hide_index=True,
        use_container_width=True,
        height=420,
    )


def _render_social() -> None:
    df = _social_sentiment()
    st.subheader("💬 Social Media Sentiment")
    st.caption("Per-platform sentiment for trending symbols.")

    # Aggregate across platforms per symbol for quick read
    agg = (
        df.groupby("symbol")
        .agg(
            avg_sentiment=("sentiment", "mean"),
            total_mentions=("mentions", "sum"),
        )
        .round(3)
        .sort_values("avg_sentiment", ascending=False)
        .reset_index()
    )
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### Per-symbol summary")
        st.dataframe(
            _styled_dataframe(agg, score_col="avg_sentiment"),
            hide_index=True,
            use_container_width=True,
            height=380,
        )
    with c2:
        st.markdown("##### Per-platform detail")
        st.dataframe(
            _styled_dataframe(df, score_col="sentiment"),
            hide_index=True,
            use_container_width=True,
            height=380,
        )


def _render_fear_greed() -> None:
    current = _fear_greed_current()
    history = _fear_greed_history(30)
    last7 = history.tail(8)  # last 7d + today
    avg7 = last7["value"].mean()
    avg30 = history["value"].mean()

    st.subheader("😱 Fear & Greed Index")
    cols = st.columns([2, 1])
    with cols[0]:
        fig = _gauge(
            current,
            "Fear & Greed (0 = Extreme Fear, 100 = Extreme Greed)",
            threshold=current,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
    with cols[1]:
        st.metric("Current", f"{current}", f"{current - avg7:+.1f} vs 7d avg")
        st.metric("7-day Avg", f"{avg7:.1f}")
        st.metric("30-day Avg", f"{avg30:.1f}")
        st.caption(
            "Built from momentum, breadth, options put/call, junk demand, "
            "and safe-haven flows."
        )

    st.markdown("##### Historical Trend (last 30 days)")
    spark_cols = st.columns([1, 4, 1])
    with spark_cols[0]:
        st.markdown("**7d**")
    with spark_cols[1]:
        fig7 = _sparkline(last7["value"], color="#22c55e")
        if fig7 is not None:
            st.plotly_chart(fig7, use_container_width=True)
    with spark_cols[2]:
        st.markdown(f"<span style='font-size:1.2rem;font-weight:600'>{last7['value'].iloc[-1]}</span>",
                    unsafe_allow_html=True)

    full_cols = st.columns([1, 4, 1])
    with full_cols[0]:
        st.markdown("**30d**")
    with full_cols[1]:
        fig30 = _sparkline(history["value"], color="#3b82f6")
        if fig30 is not None:
            st.plotly_chart(fig30, use_container_width=True)
    with full_cols[2]:
        st.markdown(f"<span style='font-size:1.2rem;font-weight:600'>{history['value'].iloc[-1]}</span>",
                    unsafe_allow_html=True)


def _render_put_call() -> None:
    pc = _put_call_ratio()
    label, color = _pc_interpretation(pc)
    st.subheader("📉 Put/Call Ratio")
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = _gauge(
            pc,
            "Put / Call Ratio (Equity Options, 5-day MA)",
            vmin=0.4,
            vmax=1.4,
            steps=[
                {"range": [0.4, 0.7], "color": "#16a34a"},
                {"range": [0.7, 1.0], "color": "#eab308"},
                {"range": [1.0, 1.4], "color": "#ef4444"},
            ],
            threshold=pc,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.metric("Current", f"{pc:.2f}")
        st.markdown(
            f"<div style='background:{color};color:#0e1117;padding:12px;border-radius:8px;"
            f"text-align:center;font-weight:700;'>{label}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "**Interpretation:**\n"
            "- `< 0.7` → bullish (more calls than puts)\n"
            "- `0.7 – 1.0` → neutral / mixed positioning\n"
            "- `> 1.0` → bearish / hedging heavy"
        )


def _render_vix() -> None:
    vix = _vix_value()
    label, color = _vix_regime(vix)
    st.subheader("⚡ VIX / Volatility Index")
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = _gauge(
            vix,
            "VIX Index (CBOE)",
            vmin=8,
            vmax=45,
            steps=[
                {"range": [8, 15], "color": "#16a34a"},
                {"range": [15, 25], "color": "#eab308"},
                {"range": [25, 45], "color": "#ef4444"},
            ],
            threshold=vix,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.metric("Current VIX", f"{vix:.2f}")
        st.markdown(
            f"<div style='background:{color};color:#0e1117;padding:12px;border-radius:8px;"
            f"text-align:center;font-weight:700;'>{label}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "**Regimes:**\n"
            "- `< 15` → Low volatility / complacent\n"
            "- `15 – 25` → Normal\n"
            "- `> 25` → High volatility / risk-off"
        )


def _render_divergence() -> None:
    df = _divergence_table()
    st.subheader("🔀 Sentiment vs Price Divergence")
    st.caption(
        "Symbols where 7-day price trend disagrees with composite sentiment. "
        "Watch for mean-reversion or trend-continuation setups."
    )

    bull = (df["divergence_type"] == "Bullish divergence").sum()
    bear = (df["divergence_type"] == "Bearish divergence").sum()
    aligned = (df["divergence_type"] == "Aligned").sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Bullish Divergence", int(bull))
    m2.metric("🔴 Bearish Divergence", int(bear))
    m3.metric("⚪ Aligned", int(aligned))

    styled = (
        df.style
        .map(
            lambda v: "color: #22c55e; font-weight: 600;" if v == "Bullish divergence"
            else "color: #ef4444; font-weight: 600;" if v == "Bearish divergence"
            else "color: #94a3b8;",
            subset=["divergence_type"],
        )
        .map(
            lambda v: "color: #22c55e;" if isinstance(v, (int, float)) and v > 0.2
            else "color: #ef4444;" if isinstance(v, (int, float)) and v < -0.2
            else "color: #eab308;",
            subset=["sentiment_score"],
        )
        .map(
            lambda v: "color: #22c55e; font-weight: 600;" if isinstance(v, (int, float)) and v > 0
            else "color: #ef4444; font-weight: 600;" if isinstance(v, (int, float)) and v < 0
            else "",
            subset=["price_trend_7d"],
        )
    )
    st.dataframe(styled, hide_index=True, use_container_width=True, height=420)


def _render_central_banks() -> None:
    df = _central_bank_sentiment()
    st.subheader("🏛️ Central Bank Sentiment")
    st.caption(
        "Composite stance score (negative = dovish, positive = hawkish) derived "
        "from the most recent official statements."
    )

    for _, row in df.iterrows():
        score = row["stance_score"]
        label = row["stance_label"]
        if score >= 0.6:
            color = "#ef4444"  # hawkish → red
        elif score >= 0.2:
            color = "#f97316"
        elif score >= -0.2:
            color = "#eab308"
        elif score >= -0.6:
            color = "#84cc16"
        else:
            color = "#22c55e"  # dovish → green

        with st.expander(
            f"{row['central_bank']}  •  {label}  ({score:+.2f})",
            expanded=False,
        ):
            st.markdown(
                f"<div style='background:{color};color:#0e1117;padding:8px 12px;"
                f"border-radius:6px;display:inline-block;font-weight:700;'>{label}</div>",
                unsafe_allow_html=True,
            )
            st.markdown("**Most recent statement (excerpt):**")
            st.info(row["recent_statement"])
            cm1, cm2 = st.columns(2)
            cm1.metric("Stance Score", f"{score:+.2f}", help="-1 = Dovish, +1 = Hawkish")
            cm2.metric("Next Meeting", row["next_meeting"])
            st.caption(f"**Rate path bias:** {row['rate_path']}")

    # Comparative table
    st.markdown("##### Comparative Overview")
    tbl = df[["central_bank", "stance_label", "stance_score", "next_meeting", "rate_path"]]
    st.dataframe(
        tbl.style.map(
            lambda v: "color: #ef4444; font-weight: 600;" if isinstance(v, (int, float)) and v >= 0.6
            else "color: #22c55e; font-weight: 600;" if isinstance(v, (int, float)) and v <= -0.6
            else "color: #fafafa;",
            subset=["stance_score"],
        ),
        hide_index=True,
        use_container_width=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────────────────────────

def render_sentiment_tab() -> None:
    """Render the Deep Market Sentiment Analyzer dashboard tab."""
    st.header("🧠 Deep Market Sentiment Analyzer")
    st.caption(
        "Multi-source sentiment dashboard: news, social, volatility, derivatives, "
        "and central-bank tone. All values are synthesized for demonstration — "
        "no external API calls are made."
    )

    # Re-seed button lets users regenerate the synthetic dataset on demand
    ctrl_cols = st.columns([3, 1, 1])
    with ctrl_cols[0]:
        st.write("")  # spacer
    with ctrl_cols[1]:
        if st.button("🔄 Regenerate", use_container_width=True):
            st.session_state["sentiment_seed"] = (
                datetime.now(timezone.utc).timestamp().__int__()
            )
            st.rerun()
    with ctrl_cols[2]:
        st.write("")

    # Compute headline numbers once so sub-sections stay consistent
    score = _overall_score()

    sub_overall, sub_news, sub_social, sub_fg, sub_pc, sub_vix, sub_div, sub_cb = st.tabs([
        "📊 Overall",
        "📰 News",
        "💬 Social",
        "😱 Fear & Greed",
        "📉 Put/Call",
        "⚡ VIX",
        "🔀 Divergence",
        "🏛️ Central Banks",
    ])

    with sub_overall:
        _render_overall_gauge(score)

    with sub_news:
        _render_news()

    with sub_social:
        _render_social()

    with sub_fg:
        _render_fear_greed()

    with sub_pc:
        _render_put_call()

    with sub_vix:
        _render_vix()

    with sub_div:
        _render_divergence()

    with sub_cb:
        _render_central_banks()


__all__ = ["render_sentiment_tab"]
