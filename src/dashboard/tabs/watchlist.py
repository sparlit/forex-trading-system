'''Watchlist tab – symbols table and heatmap visualisation.'''

from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

def _load_watchlist() -> pd.DataFrame:
    # Placeholder static watchlist – in reality would load from DB or file
    data = [
        {"symbol": "EURUSD", "last": 1.0850, "change_pct": 0.12, "volume": 1200000, "bid": 1.0849, "ask": 1.0851, "spread": 0.0002, "asset_class": "forex"},
        {"symbol": "AAPL", "last": 175.3, "change_pct": -0.45, "volume": 8000000, "bid": 175.2, "ask": 175.4, "spread": 0.2, "asset_class": "equity"},
        {"symbol": "BTCUSD", "last": 30000, "change_pct": 2.5, "volume": 35000, "bid": 29990, "ask": 30010, "spread": 20, "asset_class": "crypto"},
    ]
    return pd.DataFrame(data)

def _heatmap(df: pd.DataFrame) -> go.Figure:
    # Use a scatter plot with marker size proportional to volume, color to change_pct
    fig = go.Figure(
        data=go.Scatter(
            x=df["symbol"],
            y=[0] * len(df),  # flat y for heatmap style
            mode="markers",
            marker=dict(
                size=df["volume"] / df["volume"].max() * 60 + 10,
                color=df["change_pct"],
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title="% change"),
            ),
            text=df.apply(lambda r: f"{r['symbol']}: {r['last']:.4f} ({r['change_pct']:+.2f}%)", axis=1),
        )
    )
    fig.update_layout(showlegend=False, yaxis_visible=False, xaxis_title="Symbol")
    return fig

def render_watchlist_tab() -> None:
    st.title("\U0001F310 Watchlist")
    df = _load_watchlist()

    filter_class = st.multiselect("Asset class filter", options=df["asset_class"].unique(), default=list(df["asset_class"].unique()))
    filtered = df[df["asset_class"].isin(filter_class)]

    st.subheader("Symbol Table")
    st.dataframe(filtered.drop(columns=["asset_class"]), hide_index=True, use_container_width=True)

    st.subheader("Heatmap")
    st.plotly_chart(_heatmap(filtered), use_container_width=True)

    # Add / remove controls (simulated)
    st.subheader("Manage Watchlist")
    new_symbol = st.text_input("Add symbol (e.g., USDCAD)")
    if st.button("Add") and new_symbol:
        st.success(f"Added {new_symbol} (simulation).")
    remove_symbol = st.selectbox("Remove symbol", options=filtered["symbol"].tolist())
    if st.button("Remove"):
        st.warning(f"Removed {remove_symbol} (simulation).")
