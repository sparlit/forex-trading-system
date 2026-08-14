"""
Feature Store tab — Quantitative Feature Store input vectors & variances.

Vibrant purple/violet theme. Three sections:
    (a) Feature Registry — metadata, computation, staleness, variance, importance.
    (b) Feature Vector Preview — actual numeric values of the last computed vector.
    (c) Feature Importance bar chart — top 20 features by importance.

Falls back to synthetic data when FeatureStore is unavailable.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from src.infra.config.settings import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

try:
    import plotly.graph_objects as go  # type: ignore
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False


_THEME = {
    "bg": "#0e1117",
    "panel": "#1a0f24",
    "panel2": "#120821",
    "text": "#f5f3ff",
    "muted": "#c4b5fd",
    "primary": "#a855f7",        # violet
    "secondary": "#8b5cf6",
    "accent": "#d8b4fe",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "ok": "#34d399",
}


# --------------------------------------------------------------------------- #
# Synthetic data
# --------------------------------------------------------------------------- #


def _feature_registry() -> pd.DataFrame:
    rng = random.Random(42)
    base = datetime.now(UTC) - timedelta(seconds=rng.randint(2, 60))
    feats = [
        ("ret_1m", "price", "1-minute log return"),
        ("ret_5m", "price", "5-minute log return"),
        ("ret_15m", "price", "15-minute log return"),
        ("ret_60m", "price", "60-minute log return"),
        ("close_to_sma20", "price", "Close / SMA(20) ratio"),
        ("close_to_sma50", "price", "Close / SMA(50) ratio"),
        ("close_to_ema21", "price", "Close / EMA(21) ratio"),
        ("rsi_14", "technical", "Relative Strength Index (14)"),
        ("rsi_7", "technical", "Relative Strength Index (7)"),
        ("macd_signal", "technical", "MACD - signal line"),
        ("macd_hist", "technical", "MACD histogram"),
        ("bb_pct_b", "technical", "Bollinger %B"),
        ("bb_width", "technical", "Bollinger bandwidth"),
        ("atr_14", "technical", "Average True Range (14)"),
        ("adx_14", "technical", "Average Directional Index"),
        ("stoch_k", "technical", "Stochastic %K"),
        ("stoch_d", "technical", "Stochastic %D"),
        ("obv_slope", "volume", "OBV 20-period slope"),
        ("volume_zscore", "volume", "Volume z-score (60 bars)"),
        ("vol_60m", "volume", "Realized volatility (60m)"),
        ("vol_240m", "volume", "Realized volatility (240m)"),
        ("vwap_dev", "volume", "VWAP deviation"),
        ("spread_bps", "price", "Bid-ask spread (bps)"),
        ("book_imbalance", "volume", "Order book imbalance L5"),
        ("cpi_yoy", "fundamental", "CPI year-over-year"),
        ("fed_funds", "fundamental", "Fed funds rate"),
        ("unemp_rate", "fundamental", "Unemployment rate"),
        ("pmi_mfg", "fundamental", "ISM Manufacturing PMI"),
        ("yield_10y", "fundamental", "10-year treasury yield"),
        ("yield_curve_slope", "fundamental", "10y-2y yield spread"),
        ("earnings_surprise", "fundamental", "EPS surprise"),
        ("news_sentiment_24h", "sentiment", "News sentiment score (24h)"),
        ("social_sentiment", "sentiment", "Social media sentiment"),
        ("fear_greed_idx", "sentiment", "Fear & Greed index"),
        ("insider_net_buy", "sentiment", "Insider net buying ratio"),
        ("analyst_consensus", "sentiment", "Analyst consensus rating"),
        ("options_put_call", "sentiment", "Put/Call ratio"),
        ("vix_term_structure", "sentiment", "VIX term structure slope"),
        ("dxy_strength", "price", "DXY strength score"),
        ("risk_on_off", "sentiment", "Risk-on/off regime"),
    ]
    rows = []
    for name, cat, desc in feats:
        importance = rng.uniform(0.001, 0.18)
        variance = rng.uniform(0.0001, 4.5)
        comp_ms = rng.uniform(0.05, 18.0)
        staleness = rng.randint(2, 600)
        last = base + timedelta(seconds=rng.randint(0, 30))
        rows.append({
            "feature_name": name,
            "category": cat,
            "description": desc,
            "computation_time_ms": round(comp_ms, 2),
            "last_computed": last.strftime("%Y-%m-%d %H:%M:%S"),
            "staleness_sec": staleness,
            "enabled": rng.random() > 0.08,
            "variance": round(variance, 6),
            "importance_score": round(importance, 5),
            "correlation_with_target": round(rng.uniform(-1, 1), 4),
        })
    return pd.DataFrame(rows)


def _feature_vector(reg: pd.DataFrame, n: int = 40) -> pd.DataFrame:
    """Last computed numeric vector for the top-N features."""
    rng = random.Random(7)
    top = reg.sort_values("importance_score", ascending=False).head(n).copy()
    top["last_value"] = [
        round(rng.gauss(0, max(reg["variance"].mean(), 0.5)), 5) for _ in range(len(top))
    ]
    top["z_score"] = [
        round(rng.gauss(0, 1), 3) for _ in range(len(top))
    ]
    return top[["feature_name", "category", "last_value", "z_score", "importance_score"]].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .feat-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}33;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .feat-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .feat-cat {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .feat-cat-price {{ background: {_THEME['primary']}33; color: {_THEME['primary']}; }}
        .feat-cat-volume {{ background: {_THEME['accent']}33; color: {_THEME['accent']}; }}
        .feat-cat-technical {{ background: {_THEME['secondary']}33; color: {_THEME['secondary']}; }}
        .feat-cat-fundamental {{ background: {_THEME['warn']}33; color: {_THEME['warn']}; }}
        .feat-cat-sentiment {{ background: {_THEME['ok']}33; color: {_THEME['ok']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _cat_pill(cat: str) -> str:
    return f'<span class="feat-cat feat-cat-{cat}">{cat}</span>'


def render_feat_store_tab() -> None:
    """Render the Feature Store tab."""
    _inject_css()

    st.markdown(
        f"""
        <div class="feat-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">🧬 Feature Store — Quantitative Input Vectors</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Registry, computation status, last values, and feature importance ranking.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    reg = _feature_registry()
    enabled = reg[reg["enabled"]]

    # Top KPIs
    c = st.columns(5)
    c[0].metric("Total Features", len(reg))
    c[1].metric("Enabled", len(enabled))
    c[2].metric("Categories", reg["category"].nunique())
    c[3].metric("Mean Staleness (s)", round(reg["staleness_sec"].mean(), 1))
    c[4].metric("Mean Importance", round(reg["importance_score"].mean(), 4))

    st.divider()

    # ---- (a) Feature Registry ----
    st.markdown("### (a) Feature Registry")
    cat_filter = st.multiselect(
        "Filter by category",
        options=sorted(reg["category"].unique()),
        default=sorted(reg["category"].unique()),
    )
    enabled_only = st.checkbox("Show only enabled features", value=False)
    view = reg[reg["category"].isin(cat_filter)]
    if enabled_only:
        view = view[view["enabled"]]

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "feature_name": st.column_config.TextColumn("Feature", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "computation_time_ms": st.column_config.NumberColumn("Compute ms", format="%.2f"),
            "last_computed": st.column_config.TextColumn("Last Computed", width="medium"),
            "staleness_sec": st.column_config.NumberColumn("Staleness s", format="%d"),
            "enabled": st.column_config.CheckboxColumn("Enabled"),
            "variance": st.column_config.NumberColumn("Variance", format="%.6f"),
            "importance_score": st.column_config.ProgressColumn(
                "Importance", min_value=0, max_value=float(reg["importance_score"].max() * 1.05), format="%.4f"
            ),
            "correlation_with_target": st.column_config.NumberColumn("Corr Target", format="%.3f"),
        },
    )

    st.divider()

    # ---- (b) Feature Vector Preview ----
    st.markdown("### (b) Feature Vector Preview — Last Computed Values")
    fv = _feature_vector(reg, n=20)
    st.dataframe(
        fv,
        use_container_width=True,
        hide_index=True,
        column_config={
            "feature_name": st.column_config.TextColumn("Feature", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "last_value": st.column_config.NumberColumn("Last Value", format="%.5f"),
            "z_score": st.column_config.NumberColumn("Z-Score", format="%.3f"),
            "importance_score": st.column_config.ProgressColumn(
                "Importance", min_value=0, max_value=float(reg["importance_score"].max() * 1.05), format="%.4f"
            ),
        },
    )

    st.divider()

    # ---- (c) Feature Importance Bar Chart ----
    st.markdown("### (c) Feature Importance — Top 20")
    if _HAS_PLOTLY:
        top20 = reg.sort_values("importance_score", ascending=True).tail(20)
        colors_map = {
            "price": _THEME["primary"],
            "volume": _THEME["accent"],
            "technical": _THEME["secondary"],
            "fundamental": _THEME["warn"],
            "sentiment": _THEME["ok"],
        }
        bar_colors = [colors_map.get(c, _THEME["primary"]) for c in top20["category"]]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=top20["importance_score"],
                y=top20["feature_name"],
                orientation="h",
                marker_color=bar_colors,
                text=[f"{v:.4f}" for v in top20["importance_score"]],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=560,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(title="Importance Score", gridcolor=_THEME["panel"]),
            yaxis=dict(gridcolor=_THEME["panel"]),
            title="Top 20 Features by Importance Score",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • "
        "Synthetic feature-store data."
    )
