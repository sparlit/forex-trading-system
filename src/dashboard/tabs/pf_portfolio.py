"""
Portfolio tab — Position book, holdings, and funds overview.

Vibrant emerald/gold theme. Three sub-tabs via st.tabs:
    (a) Position Book sortable by PnL.
    (b) Holdings with allocation pie chart.
    (c) Funds ledger with total equity metric.

Synthetic fallback.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import UTC, datetime

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
    "panel": "#0b1b0c",
    "panel2": "#08170a",
    "text": "#d1fae5",
    "muted": "#86efac",
    "primary": "#10b981",        # emerald
    "secondary": "#34d399",
    "accent": "#6ee7b7",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "ok": "#22c55e",
}


def _positions() -> pd.DataFrame:
    rows = []
    now = datetime.now(UTC)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "SPX500", "NDX100"]
    for sym in symbols:
        side = random.choice(["LONG", "SHORT"])
        vol = random.choice([0.01, 0.05, 0.1, 0.2, 0.5, 1.0])
        avg_price = round(random.uniform(0.8, 1.5), 5) if "USD" in sym else round(random.uniform(50, 1500), 2)
        cur_price = avg_price * (1 + random.uniform(-0.03, 0.04))
        market_val = vol * cur_price * (100000 if "USD" in sym else 1)
        unreal = (cur_price - avg_price) * vol * (100000 if "USD" in sym else 1)
        change_pct = ((cur_price - avg_price) / avg_price) * 100
        margin_used = round(random.uniform(100, 2000), 2)
        rows.append({
            "symbol": sym,
            "side": side,
            "volume": vol,
            "avg_price": avg_price,
            "current_price": cur_price,
            "market_value": market_val,
            "unrealized_pnl": unreal,
            "change_pct": change_pct,
            "margin_used": margin_used,
        })
    return pd.DataFrame(rows)


def _holdings() -> pd.DataFrame:
    asset_classes = ["Equity", "Commodity", "Crypto", "Forex"]
    rows = []
    for i in range(12):
        asset = random.choice(asset_classes)
        symbol = random.choice(["AAPL", "MSFT", "GOOG", "TSLA", "GLD", "SLV", "BTC", "ETH", "EURUSD", "GBPUSD"])
        qty = random.choice([10, 25, 50, 100, 250, 500])
        avg_cost = round(random.uniform(20, 1500), 2)
        market_val = qty * avg_cost * random.uniform(0.95, 1.10)
        weight = round(random.uniform(0.5, 8.0), 2)
        beta = round(random.uniform(0.5, 1.5), 2)
        sector = random.choice(["Technology", "Energy", "Financials", "Consumer", "Materials"])
        rows.append({
            "asset_class": asset,
            "symbol": symbol,
            "quantity": qty,
            "avg_cost": avg_cost,
            "market_value": market_val,
            "weight_pct": weight,
            "beta": beta,
            "sector": sector,
        })
    return pd.DataFrame(rows)


def _funds() -> pd.DataFrame:
    rows = []
    accounts = ["primary", "secondary", "demo"]
    for acc in accounts:
        currency = random.choice(["USD", "EUR", "GBP"])
        balance = round(random.uniform(50000, 250000), 2)
        avail = balance * random.uniform(0.6, 0.95)
        locked = balance - avail
        free_pnl = round(random.uniform(-5000, 8000), 2)
        unreal = round(random.uniform(-3000, 6000), 2)
        rows.append({
            "account": acc,
            "currency": currency,
            "balance": balance,
            "available_margin": avail,
            "locked_margin": locked,
            "free_pnl": free_pnl,
            "unrealized_pnl": unreal,
        })
    return pd.DataFrame(rows)


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .pf-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
        }}
        .pf-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .equity-metric {{
            font-size: 1.4rem; font-weight: 600; color: {_THEME['primary']};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_pf_portfolio_tab() -> None:
    """Render the Portfolio tab with three sub-tabs."""
    _inject_css()
    st.markdown(
        f"""
        <div class="pf-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">💰 Portfolio Overview — Positions, Holdings, Funds</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Position book, asset holdings, and free ledger funds with visualizations.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    tab_pos, tab_hold, tab_funds = st.tabs(["Positions", "Holdings", "Funds"])

    # ---- (a) Position Book ----
    with tab_pos:
        st.markdown("### (a) Position Book")
        df_pos = _positions()
        # Sorting control
        sort_col = st.selectbox("Sort by", options=df_pos.columns, index=list(df_pos.columns).index("unrealized_pnl"))
        asc = st.checkbox("Ascending", value=False)
        df_sorted = df_pos.sort_values(by=sort_col, ascending=asc)
        st.dataframe(
            df_sorted,
            hide_index=True,
            use_container_width=True,
            column_config={
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "side": st.column_config.TextColumn("Side", width="small"),
                "volume": st.column_config.NumberColumn("Vol", format="%.3f"),
                "avg_price": st.column_config.NumberColumn("Avg $", format="%.5f"),
                "current_price": st.column_config.NumberColumn("Current $", format="%.5f"),
                "market_value": st.column_config.NumberColumn("Market $", format="%.2f"),
                "unrealized_pnl": st.column_config.NumberColumn("Unreal PnL", format="%.2f"),
                "change_pct": st.column_config.NumberColumn("% Change", format="%.2f%%"),
                "margin_used": st.column_config.NumberColumn("Margin $", format="%.2f"),
            },
        )

    # ---- (b) Holdings ----
    with tab_hold:
        st.markdown("### (b) Asset Holdings")
        df_hold = _holdings()
        st.dataframe(
            df_hold,
            hide_index=True,
            use_container_width=True,
            column_config={
                "asset_class": st.column_config.TextColumn("Class", width="small"),
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "quantity": st.column_config.NumberColumn("Qty", format="%d"),
                "avg_cost": st.column_config.NumberColumn("Avg Cost", format="%.2f"),
                "market_value": st.column_config.NumberColumn("Market $", format="%.2f"),
                "weight_pct": st.column_config.ProgressColumn("Weight %", min_value=0, max_value=10, format="%.1f%%"),
                "beta": st.column_config.NumberColumn("Beta", format="%.2f"),
                "sector": st.column_config.TextColumn("Sector", width="medium"),
            },
        )
        if _HAS_PLOTLY:
            # Allocation pie chart by weight
            fig = go.Figure(data=[go.Pie(labels=df_hold["symbol"], values=df_hold["weight_pct"], hole=0.3)])
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor=_THEME["bg"],
                plot_bgcolor=_THEME["panel2"],
                font_color=_THEME["text"],
                height=380,
                margin=dict(l=20, r=20, t=40, b=20),
                title="Holdings Allocation by Weight",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ---- (c) Funds ----
    with tab_funds:
        st.markdown("### (c) Funds Ledger")
        df_fund = _funds()
        # Compute total equity across accounts (balance + free PnL + unrealized)
        df_fund["total_equity"] = df_fund["balance"] + df_fund["free_pnl"] + df_fund["unrealized_pnl"]
        total_eq = df_fund["total_equity"].sum()
        st.markdown(f"<div class='equity-metric'>Total Equity: ${total_eq:,.2f}</div>", unsafe_allow_html=True)
        st.dataframe(
            df_fund,
            hide_index=True,
            use_container_width=True,
            column_config={
                "account": st.column_config.TextColumn("Account", width="small"),
                "currency": st.column_config.TextColumn("CCY", width="small"),
                "balance": st.column_config.NumberColumn("Balance", format="$.2f"),
                "available_margin": st.column_config.NumberColumn("Avail. Margin", format="$.2f"),
                "locked_margin": st.column_config.NumberColumn("Locked Margin", format="$.2f"),
                "free_pnl": st.column_config.NumberColumn("Free PnL", format="$.2f"),
                "unrealized_pnl": st.column_config.NumberColumn("Unreal PnL", format="$.2f"),
                "total_equity": st.column_config.NumberColumn("Total Eq", format="$.2f"),
            },
        )

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} \u2022 Synthetic portfolio data."
    )
