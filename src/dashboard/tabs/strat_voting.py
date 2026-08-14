"""
Strategy Voting tab — Strategy Voting weight matrix & dynamic state transitions.

Vibrant crimson/red theme. Three sections:
    (a) Strategy Voting Matrix with votes, consensus, weight, state, win rate, sharpe.
    (b) Dynamic State Transitions timeline (plotly) for last 24h.
    (c) Weight allocation pie chart for capital distribution across active strategies.

Falls back to synthetic data when StrategyEngine is unavailable.
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
    "panel": "#1a080c",
    "panel2": "#12070b",
    "text": "#ffe4e6",
    "muted": "#f9a8d4",
    "primary": "#dc2626",        # bright crimson
    "secondary": "#ef4444",
    "accent": "#fca5a5",
    "warn": "#fbbf24",
    "danger": "#b91c1c",
    "ok": "#34d399",
}


def _strategy_voting_matrix() -> pd.DataFrame:
    rng = random.Random(123)
    strategies = [
        ("Trend_Follower", "trend"),
        ("Mean_Reversion", "mean_rev"),
        ("MOM_Alpha", "momentum"),
        ("Stat_Arb", "stat_arb"),
        ("News_Breakout", "news"),
        ("Carry_Trade", "carry"),
        ("FX_Rate_Model", "fx"),
        ("Macro_Spread", "macro"),
        ("Liquidity_Provider", "liq"),
        ("Option_Vega", "options"),
        ("Volatility_Squeeze", "vol_squeeze"),
        ("Quant_Fundamental", "fundamental"),
        ("Sentiment_Scoring", "sentiment"),
        ("Arb_Calibration", "arb"),
        ("Risk_Parity", "risk"),
    ]
    rows = []
    for name, cat in strategies:
        votes_bullish = rng.randint(50, 300)
        votes_bearish = rng.randint(20, 250)
        votes_neutral = rng.randint(0, 80)
        total = votes_bullish + votes_bearish + votes_neutral
        consensus = "Bullish" if votes_bullish > votes_bearish else "Bearish" if votes_bearish > votes_bullish else "Neutral"
        weight_pct = round(rng.uniform(0.5, 12.0), 2)
        state = rng.choice(["active", "paused", "cooling_down"])
        win_rate = round(rng.uniform(45.0, 68.0), 2)
        sharpe = round(rng.uniform(0.3, 1.7), 2)
        rows.append({
            "strategy_name": name,
            "category": cat,
            "votes_bullish": votes_bullish,
            "votes_bearish": votes_bearish,
            "votes_neutral": votes_neutral,
            "consensus": consensus,
            "weight_pct": weight_pct,
            "state": state,
            "last_signal": (datetime.now(UTC) - timedelta(minutes=rng.randint(5, 120))).strftime("%Y-%m-%d %H:%M"),
            "win_rate_pct": win_rate,
            "sharpe": sharpe,
        })
    return pd.DataFrame(rows)


def _state_transitions(df: pd.DataFrame) -> pd.DataFrame:
    """Create a synthetic timeline of state changes for each strategy over 24h."""
    now = datetime.now(UTC)
    records = []
    for _, row in df.iterrows():
        name = row["strategy_name"]
        # generate 3-5 random transitions in the last 24h
        n = random.randint(3, 5)
        timestamps = sorted([now - timedelta(hours=random.uniform(0, 24)) for _ in range(n)])
        # cycle through possible states
        possible = ["active", "paused", "cooling_down"]
        for ts in timestamps:
            state = random.choice(possible)
            records.append({"timestamp": ts, "strategy": name, "state": state})
    return pd.DataFrame(records)


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .strat-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .strat-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .state-pill {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .state-active {{ background: {_THEME['ok']}33; color: {_THEME['ok']}; border: 1px solid {_THEME['ok']}; }}
        .state-paused {{ background: {_THEME['warn']}33; color: {_THEME['warn']}; border: 1px solid {_THEME['warn']}; }}
        .state-cooling {{ background: {_THEME['danger']}33; color: {_THEME['danger']}; border: 1px solid {_THEME['danger']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _state_pill(state: str) -> str:
    cls = {
        "active": "state-active",
        "paused": "state-paused",
        "cooling_down": "state-cooling",
    }.get(state, "state-paused")
    return f'<span class="state-pill {cls}">{state.replace("_", " ").title()}</span>'


def render_strat_voting_tab() -> None:
    """Render the Strategy Voting tab."""
    _inject_css()
    st.markdown(
        f"""
        <div class="strat-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">📝 Strategy Voting — Weights & State Transitions</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Matrix of voting signals, consensus, and dynamic capital allocation.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    voting = _strategy_voting_matrix()

    # KPIs
    cols = st.columns(3)
    cols[0].metric("Total Strategies", len(voting))
    cols[1].metric("Active", (voting["state"] == "active").sum())
    cols[2].metric("Total Weight %", round(voting["weight_pct"].sum(), 2))

    st.divider()

    # ---- (a) Strategy Voting Matrix ----
    st.markdown("### (a) Strategy Voting Matrix")
    # Add state pill column
    voting_display = voting.copy()
    voting_display["state_pill"] = voting_display["state"].apply(_state_pill)
    st.dataframe(
        voting_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "state": None,
            "state_pill": st.column_config.TextColumn("State"),
            "strategy_name": st.column_config.TextColumn("Strategy", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "votes_bullish": st.column_config.NumberColumn("Bullish", format="%d"),
            "votes_bearish": st.column_config.NumberColumn("Bearish", format="%d"),
            "votes_neutral": st.column_config.NumberColumn("Neutral", format="%d"),
            "consensus": st.column_config.TextColumn("Consensus", width="small"),
            "weight_pct": st.column_config.NumberColumn("Weight %", format="%.2f"),
            "last_signal": st.column_config.TextColumn("Last Signal", width="medium"),
            "win_rate_pct": st.column_config.NumberColumn("Win %", format="%.2f"),
            "sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f"),
        },
    )

    st.divider()

    # ---- (b) Dynamic State Transitions ----
    st.markdown("### (b) Dynamic State Transitions (last 24h)")
    if _HAS_PLOTLY:
        transitions = _state_transitions(voting)
        fig = go.Figure()
        for strat, sub in transitions.groupby("strategy"):
            fig.add_trace(
                go.Scatter(
                    x=sub["timestamp"],
                    y=[strat] * len(sub),
                    mode="markers+lines",
                    name=strat,
                    marker=dict(size=8, symbol="circle", color=_THEME["primary"]),
                    line=dict(width=2, dash="dot", color=_THEME["secondary"]),
                )
            )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=460,
            margin=dict(l=20, r=20, t=40, b=20),
            title="Strategy State Changes (24h)",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- (c) Weight Allocation Pie Chart ----
    st.markdown("### (c) Capital Allocation by Weight (active only)")
    active = voting[voting["state"] == "active"]
    if not active.empty and _HAS_PLOTLY:
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=active["strategy_name"],
                    values=active["weight_pct"],
                    hole=0.35,
                    marker=dict(colors=[_THEME["primary"]] * len(active)),
                    textinfo="label+percent",
                )
            ]
        )
        fig.update_traces(textfont=dict(color=_THEME["text"]))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=440,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • Synthetic data."
    )
