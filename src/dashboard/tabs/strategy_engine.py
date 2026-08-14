"""
Strategy Engine tab — registry, auto-selection, weights, performance.

Displays every registered strategy with its stats, the meta-controller's
auto-selection result and rationale, a weight-allocation pie chart, and a
manual override control. Uses plotly when available, falling back to
plain Streamlit bars.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from src.infra.config.settings import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

try:
    import plotly.express as px  # type: ignore
    import plotly.graph_objects as go  # type: ignore
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False


# --------------------------------------------------------------------------- #
# Placeholder data — keep field names identical to the strategy registry
# --------------------------------------------------------------------------- #


def _strategies() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"name": "ema_cross_m15",   "category": "trend",      "style": "EMA 8/21 cross",
             "win_rate": 0.58, "pnl": 4210.55, "sharpe": 1.42, "max_dd": -4.8, "active": True},
            {"name": "rsi_meanrev_h1",  "category": "meanrev",    "style": "RSI(14) reversion",
             "win_rate": 0.61, "pnl": 3120.10, "sharpe": 1.18, "max_dd": -3.2, "active": True},
            {"name": "breakout_atr_m5", "category": "breakout",   "style": "ATR breakout",
             "win_rate": 0.47, "pnl": -980.40, "sharpe": 0.21, "max_dd": -7.5, "active": False},
            {"name": "news_sentiment",  "category": "sentiment",  "style": "LLM-news classifier",
             "win_rate": 0.54, "pnl": 1875.22, "sharpe": 0.92, "max_dd": -5.1, "active": True},
            {"name": "carry_trade_h4",  "category": "macro",      "style": "Carry + swap",
             "win_rate": 0.63, "pnl": 2640.00, "sharpe": 1.05, "max_dd": -2.9, "active": True},
            {"name": "vwap_reversion",  "category": "meanrev",    "style": "VWAP touch",
             "win_rate": 0.52, "pnl": 410.80,  "sharpe": 0.55, "max_dd": -3.6, "active": False},
        ]
    )


def _weights() -> dict[str, float]:
    return {
        "ema_cross_m15":   0.30,
        "rsi_meanrev_h1":  0.20,
        "news_sentiment":  0.15,
        "carry_trade_h4":  0.20,
        "breakout_atr_m5": 0.05,
        "vwap_reversion":  0.10,
    }


def _selection_result() -> dict[str, Any]:
    return {
        "selected": "ema_cross_m15",
        "reason": (
            "Highest 30-day Sharpe (1.42) under current regime (ADX>25, "
            "VIX<18). News classifier confidence degraded after CPI release."
        ),
        "regime": "trending",
        "score": 0.87,
        "decided_at": (datetime.now(UTC) - timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #


def render_strategy_engine_tab() -> None:
    """Render the strategy registry / auto-selection / override tab."""
    st.header("🧠 Strategy Engine")
    st.caption(
        "Registered strategies, the meta-controller's pick, weight allocation, "
        "and a manual override switch."
    )

    df = _strategies()
    sel = _selection_result()
    weights = _weights()

    # ---- Auto-selection banner -------------------------------------------- #
    st.subheader("Auto-selection result")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected strategy", sel["selected"])
    c2.metric("Regime", sel["regime"])
    c3.metric("Confidence score", f"{sel['score']:.2f}")
    c4.metric("Decided at (UTC)", sel["decided_at"])
    st.info(f"💡 **Why:** {sel['reason']}")

    # ---- Manual override --------------------------------------------------- #
    st.subheader("Manual override")
    ovr_col, btn_col = st.columns([3, 1])
    override_choice = ovr_col.selectbox(
        "Force a strategy (bypasses meta-controller)",
        options=["(auto)"] + df["name"].tolist(),
        index=0,
    )
    if btn_col.button("Apply override"):
        if override_choice == "(auto)":
            st.success("Auto-selection re-enabled.")
        else:
            st.success(f"Manual override set to **{override_choice}** (placeholder).")

    st.divider()

    # ---- Strategy table --------------------------------------------------- #
    st.subheader("Registered strategies")
    st.dataframe(
        df.style.format({
            "win_rate": "{:.0%}",
            "pnl": "{:+,.2f}",
            "sharpe": "{:.2f}",
            "max_dd": "{:+.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # ---- Weight allocation + perf comparison ----------------------------- #
    chart_col, perf_col = st.columns(2)

    with chart_col:
        st.subheader("Weight allocation")
        if _HAS_PLOTLY:
            w_df = pd.DataFrame(
                {"strategy": list(weights.keys()), "weight": list(weights.values())}
            )
            fig = px.pie(
                w_df, names="strategy", values="weight", hole=0.45,
                title="Current strategy weights"
            )
            fig.update_traces(textposition="inside", textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(pd.DataFrame({"weight": weights}))

    with perf_col:
        st.subheader("Performance comparison (PnL)")
        if _HAS_PLOTLY:
            p_df = df.sort_values("pnl", ascending=False)
            fig2 = go.Figure(
                data=[go.Bar(
                    x=p_df["name"], y=p_df["pnl"],
                    marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in p_df["pnl"]],
                )]
            )
            fig2.update_layout(title="Cumulative PnL by strategy", xaxis_title="", yaxis_title="PnL")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.bar_chart(df.set_index("name")[["pnl"]])

    # ---- Sharpe comparison ------------------------------------------------ #
    st.subheader("Sharpe / drawdown scatter")
    if _HAS_PLOTLY:
        fig3 = px.scatter(
            df, x="max_dd", y="sharpe", size="pnl", color="active",
            hover_name="name", text="name",
            labels={"max_dd": "Max drawdown (%)", "sharpe": "Sharpe ratio"},
            title="Risk/return map",
        )
        fig3.update_traces(textposition="top center")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.dataframe(df[["name", "sharpe", "max_dd"]], use_container_width=True, hide_index=True)
