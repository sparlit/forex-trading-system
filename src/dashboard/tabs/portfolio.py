'''
Portfolio tab – total equity, allocation by asset class, correlation matrix,
Markowitz efficient frontier, Black-Litterman adjusted weights, portfolio VaR,
sector & currency exposure, and position-level attribution table.
'''

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# --------------------------------------------------------------------------- #
# Seed universe of holdings
# --------------------------------------------------------------------------- #
_UNIVERSE = [
    {"symbol": "EURUSD", "asset_class": "FX",        "sector": "Major",     "ccy": "EUR", "weight": 0.18, "pnl":  1_240.0},
    {"symbol": "USDJPY", "asset_class": "FX",        "sector": "Major",     "ccy": "JPY", "weight": 0.10, "pnl":   -420.0},
    {"symbol": "GBPUSD", "asset_class": "FX",        "sector": "Major",     "ccy": "GBP", "weight": 0.07, "pnl":    310.0},
    {"symbol": "XAUUSD", "asset_class": "Metals",    "sector": "Precious",  "ccy": "USD", "weight": 0.14, "pnl":  2_010.0},
    {"symbol": "BTCUSD", "asset_class": "Crypto",    "sector": "L1",        "ccy": "USD", "weight": 0.12, "pnl": -1_120.0},
    {"symbol": "ETHUSD", "asset_class": "Crypto",    "sector": "L1",        "ccy": "USD", "weight": 0.06, "pnl":    680.0},
    {"symbol": "SPY",    "asset_class": "Equity",    "sector": "Index",     "ccy": "USD", "weight": 0.15, "pnl":  1_790.0},
    {"symbol": "QQQ",    "asset_class": "Equity",    "sector": "Tech",      "ccy": "USD", "weight": 0.10, "pnl":    920.0},
    {"symbol": "AAPL",   "asset_class": "Equity",    "sector": "Tech",      "ccy": "USD", "weight": 0.05, "pnl":    140.0},
    {"symbol": "COPPER", "asset_class": "Commodity", "sector": "Industrial","ccy": "USD", "weight": 0.03, "pnl":    -85.0},
]


# --------------------------------------------------------------------------- #
# Math helpers
# --------------------------------------------------------------------------- #
def _returns_matrix(n: int, periods: int = 250, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0003, scale=0.012, size=(periods, n))


def _correlation_matrix(rets: np.ndarray) -> np.ndarray:
    return np.corrcoef(rets.T)


def _markowitz_frontier(rets: np.ndarray, n_points: int = 40) -> pd.DataFrame:
    """Mean-variance frontier — long-only, Dirichlet-sampled weights."""
    mu = rets.mean(axis=0) * 252
    cov = np.cov(rets.T) * 252
    rows = []
    for _ in range(n_points):
        w = np.random.dirichlet(np.ones(len(mu)))
        port_ret = float(w @ mu)
        port_vol = float(np.sqrt(w @ cov @ w))
        rows.append({
            "return": port_ret,
            "vol": port_vol,
            "sharpe": port_ret / max(port_vol, 1e-9),
            "weights": w,
        })
    return pd.DataFrame(rows).sort_values("vol").reset_index(drop=True)


def _black_litterman(rets: np.ndarray, view_strength: float = 0.5) -> np.ndarray:
    """Simplified BL — shrink prior μ toward historical mean with Ω scaling."""
    mu = rets.mean(axis=0) * 252
    prior = np.full_like(mu, mu.mean())
    cov = np.cov(rets.T) * 252
    n = len(mu)
    omega = np.eye(n) * float(np.diag(cov).mean()) * (1.0 - view_strength)
    p = np.eye(n)
    q = mu
    tau = 0.05
    try:
        ts_inv = np.linalg.inv(tau * cov)
        o_inv = np.linalg.inv(omega)
        m_inv = ts_inv + p.T @ o_inv @ p
        mu_bl = np.linalg.inv(m_inv) @ (ts_inv @ prior + p.T @ o_inv @ q)
    except np.linalg.LinAlgError:
        mu_bl = 0.5 * (mu + prior)
    sigma = np.sqrt(np.diag(cov))
    score = np.exp(mu_bl / np.maximum(sigma, 1e-9))
    weights = score / score.sum()
    return weights


def _portfolio_var(rets: np.ndarray, weights: np.ndarray, conf: float) -> float:
    port = rets @ weights
    return float(-np.quantile(port, 1 - conf))


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
def _overview_panel() -> None:
    st.markdown("#### 💰 Portfolio Overview")
    df = pd.DataFrame(_UNIVERSE)
    eq = float(st.session_state.get("pf_total_equity", 100_000.0))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Equity", f"${eq:,.0f}")
    c2.metric("Positions", len(df))
    c3.metric("Gross Weight", f"{df['weight'].sum():.2f}")
    c4.metric("Daily PnL", f"${df['pnl'].sum():+,.0f}")


def _allocation_panel() -> None:
    st.markdown("#### 🥧 Allocation by Asset Class")
    df = pd.DataFrame(_UNIVERSE)
    by_class = df.groupby("asset_class")["weight"].sum().reset_index()
    fig = px.pie(by_class, names="asset_class", values="weight", hole=0.45,
                 color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320,
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font_color="#e0e0e0")
    st.plotly_chart(fig, use_container_width=True)


def _correlation_panel() -> None:
    st.markdown("#### 🔥 Correlation Matrix")
    rets = _returns_matrix(len(_UNIVERSE))
    corr = _correlation_matrix(rets)
    labels = [u["symbol"] for u in _UNIVERSE]
    fig = go.Figure(data=go.Heatmap(
        z=corr, x=labels, y=labels,
        colorscale="RdBu", zmin=-1, zmax=1,
        text=np.round(corr, 2), texttemplate="%{text}",
    ))
    fig.update_layout(height=420, margin=dict(t=10, b=10),
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font_color="#e0e0e0")
    st.plotly_chart(fig, use_container_width=True)


def _efficient_frontier_panel() -> None:
    st.markdown("#### 📈 Markowitz Efficient Frontier")
    rets = _returns_matrix(len(_UNIVERSE))
    frontier = _markowitz_frontier(rets)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frontier["vol"] * 100, y=frontier["return"] * 100,
        mode="markers",
        marker=dict(color=frontier["sharpe"], colorscale="Viridis",
                    size=8, colorbar=dict(title="Sharpe")),
        hovertemplate="Vol: %{x:.2f}%<br>Return: %{y:.2f}%<extra></extra>",
    ))
    if not frontier.empty:
        i = int(frontier["sharpe"].idxmax())
        fig.add_trace(go.Scatter(
            x=[frontier.loc[i, "vol"] * 100],
            y=[frontier.loc[i, "return"] * 100],
            mode="markers+text", marker=dict(size=14, color="#3fb950"),
            text=["Max Sharpe"], textposition="top center",
        ))
    fig.update_layout(
        xaxis_title="Volatility (%)", yaxis_title="Expected Return (%)",
        height=380, margin=dict(t=10, b=10),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font_color="#e0e0e0",
    )
    st.plotly_chart(fig, use_container_width=True)


def _black_litterman_panel() -> None:
    st.markdown("#### 🧮 Black-Litterman Adjusted Weights")
    strength = st.slider(
        "View strength (0 = prior, 1 = pure views)",
        0.0, 1.0,
        float(st.session_state.get("pf_bl_view_strength", 0.5)), 0.05,
        key="pf_bl_slider",
    )
    st.session_state["pf_bl_view_strength"] = strength
    rets = _returns_matrix(len(_UNIVERSE))
    w = _black_litterman(rets, strength)
    df = pd.DataFrame({
        "Symbol": [u["symbol"] for u in _UNIVERSE],
        "BL Weight": np.round(w, 4),
    })
    fig = px.bar(df, x="Symbol", y="BL Weight", color="BL Weight",
                 color_continuous_scale="Teal")
    fig.update_layout(height=320, margin=dict(t=10, b=10),
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font_color="#e0e0e0", yaxis_title="Weight")
    st.plotly_chart(fig, use_container_width=True)


def _var_panel() -> None:
    st.markdown("#### ⚠️ Portfolio Value-at-Risk")
    rets = _returns_matrix(len(_UNIVERSE))
    eq = float(st.session_state.get("pf_total_equity", 100_000.0))
    w = _black_litterman(rets)
    var95 = _portfolio_var(rets, w, 0.95) * eq
    var99 = _portfolio_var(rets, w, 0.99) * eq
    c1, c2, c3 = st.columns(3)
    c1.metric("VaR 95% (1d)", f"${var95:,.0f}")
    c2.metric("VaR 99% (1d)", f"${var99:,.0f}")
    c3.metric("As % of equity", f"{-var95 / eq * 100:.2f}%")


def _exposures_panel() -> None:
    st.markdown("#### 🌍 Sector & Currency Exposure")
    df = pd.DataFrame(_UNIVERSE)
    c1, c2 = st.columns(2)
    with c1:
        sec = df.groupby("sector")["weight"].sum().reset_index()
        fig = px.bar(sec, x="sector", y="weight", color="weight",
                     color_continuous_scale="Blues", title="Sector")
        fig.update_layout(height=280, margin=dict(t=30, b=10),
                          paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                          font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        cur = df.groupby("ccy")["weight"].sum().reset_index()
        fig = px.bar(cur, x="ccy", y="weight", color="weight",
                     color_continuous_scale="Oranges", title="Currency")
        fig.update_layout(height=280, margin=dict(t=30, b=10),
                          paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                          font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)


def _attribution_panel() -> None:
    st.markdown("#### 📋 Position-Level Attribution")
    df = pd.DataFrame(_UNIVERSE)
    eq = float(st.session_state.get("pf_total_equity", 100_000.0))
    df["notional_usd"] = (df["weight"] * eq).round(0)
    df["pnl"] = df["pnl"].round(2)
    st.dataframe(
        df[["symbol", "asset_class", "sector", "ccy", "weight", "notional_usd", "pnl"]],
        use_container_width=True, hide_index=True,
    )


def _position_book_panel() -> None:
    """Original position-book view kept for backwards compatibility."""
    data = [
        {"symbol": "EURUSD", "side": "long",  "volume": 100000, "entry": 1.0800, "current": 1.0850, "pnl":  500, "pnl_pct":  0.5, "duration": "2h"},
        {"symbol": "GBPJPY", "side": "short", "volume":  50000, "entry": 152.30, "current": 151.00, "pnl": -650, "pnl_pct": -1.3, "duration": "30m"},
    ]
    df = pd.DataFrame(data)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.metric("Total PnL", f"${df['pnl'].sum():,.2f}")


def _funds_summary_panel() -> None:
    summary = {
        "cash_balance": 15000.0,
        "total_equity": 100000.0,
        "margin_used": 20000.0,
        "available_margin": 80000.0,
        "buying_power": 250000.0,
    }
    col1, col2, col3 = st.columns(3)
    col1.metric("Cash Balance",     f"${summary['cash_balance']:,.2f}")
    col2.metric("Total Equity",     f"${summary['total_equity']:,.2f}")
    col3.metric("Margin Used",      f"${summary['margin_used']:,.2f}")
    col4, col5 = st.columns(2)
    col4.metric("Available Margin", f"${summary['available_margin']:,.2f}")
    col5.metric("Buying Power",     f"${summary['buying_power']:,.2f}")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render_portfolio_tab() -> None:
    st.title("\U0001F4B0 Portfolio")
    _overview_panel()
    st.markdown("---")
    _allocation_panel()
    st.markdown("---")
    _correlation_panel()
    st.markdown("---")
    _efficient_frontier_panel()
    st.markdown("---")
    _black_litterman_panel()
    st.markdown("---")
    _var_panel()
    st.markdown("---")
    _exposures_panel()
    st.markdown("---")
    _attribution_panel()
    st.markdown("---")
    with st.expander("📒 Detailed Position Book"):
        _position_book_panel()
    with st.expander("💵 Funds Summary"):
        _funds_summary_panel()
