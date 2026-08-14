"""
Market tab — Exchange Messages, Market Movers, Scanners, Fundamentals, Corporate Actions
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False


def _exchange_messages() -> pd.DataFrame:
    """Simulated exchange messages/announcements feed."""
    now = datetime.now(timezone.utc)
    return pd.DataFrame([
        {"timestamp": (now - timedelta(minutes=2)).strftime("%H:%M:%S"),
         "exchange": "FX", "message": "High volatility expected — Fed minutes release in 30min", "impact": "High"},
        {"timestamp": (now - timedelta(minutes=15)).strftime("%H:%M:%S"),
         "exchange": "CME", "message": "Margin requirement increase for NG futures", "impact": "Medium"},
        {"timestamp": (now - timedelta(minutes=35)).strftime("%H:%M:%S"),
         "exchange": "NYSE", "message": "Circuit breaker test scheduled for close", "impact": "Low"},
        {"timestamp": (now - timedelta(hours=1)).strftime("%H:%M:%S"),
         "exchange": "CRYPTO", "message": "BTC funding rate flipped negative on Binance", "impact": "Medium"},
        {"timestamp": (now - timedelta(hours=2)).strftime("%H:%M:%S"),
         "exchange": "LSE", "message": "Auction period uncrossing in 5 minutes", "impact": "Low"},
        {"timestamp": (now - timedelta(hours=3)).strftime("%H:%M:%S"),
         "exchange": "TSE", "message": "Break announcement — lunch session starts", "impact": "Low"},
    ])


def _market_movers() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (gainers, losers, active) DataFrames."""
    gainers = pd.DataFrame([
        {"symbol": "SOLUSD", "price": 185.5, "change_pct": +8.2, "volume": "2.4M"},
        {"symbol": "AUDJPY", "price": 99.45, "change_pct": +2.7, "volume": "1.1M"},
        {"symbol": "GBPUSD", "price": 1.2685, "change_pct": +2.1, "volume": "3.2M"},
        {"symbol": "ETHUSD", "price": 3568.0, "change_pct": +1.8, "volume": "8.5M"},
        {"symbol": "SPY", "price": 485.2, "change_pct": +0.9, "volume": "12M"},
    ], columns=["symbol", "price", "change_pct", "volume"])

    losers = pd.DataFrame([
        {"symbol": "XAUUSD", "price": 2025.0, "change_pct": -1.5, "volume": "5.1M"},
        {"symbol": "USDJPY", "price": 149.10, "change_pct": -1.2, "volume": "4.0M"},
        {"symbol": "BTCUSD", "price": 64200.0, "change_pct": -1.1, "volume": "18M"},
        {"symbol": "EURUSD", "price": 1.0820, "change_pct": -0.8, "volume": "6.2M"},
        {"symbol": "QQQ", "price": 418.8, "change_pct": -0.3, "volume": "9.5M"},
    ], columns=["symbol", "price", "change_pct", "volume"])

    active = pd.DataFrame([
        {"symbol": "BTCUSD", "price": 64200.0, "change_pct": -1.1, "volume": "18M"},
        {"symbol": "ETHUSD", "price": 3568.0, "change_pct": +1.8, "volume": "8.5M"},
        {"symbol": "EURUSD", "price": 1.0820, "change_pct": -0.8, "volume": "6.2M"},
        {"symbol": "AAPL", "price": 193.5, "change_pct": +0.4, "volume": "5.8M"},
        {"symbol": "XAUUSD", "price": 2025.0, "change_pct": -1.5, "volume": "5.1M"},
    ], columns=["symbol", "price", "change_pct", "volume"])

    return gainers, losers, active


def _scanners(selected_scan: str) -> pd.DataFrame:
    """Predefined scan results based on selection."""
    scans = {
        "RSI Oversold (RSI<30)": pd.DataFrame([
            {"symbol": "USDJPY", "rsi": 25.3, "price": 149.10, "signal": "Oversold"},
            {"symbol": "XAUUSD", "rsi": 28.7, "price": 2025.0, "signal": "Oversold"},
            {"symbol": "AUDUSD", "rsi": 22.1, "price": 0.6510, "signal": "Oversold"},
        ]),
        "MACD Bullish Crossover": pd.DataFrame([
            {"symbol": "GBPUSD", "macd_line": 0.0012, "signal_line": 0.0008, "price": 1.2685,
             "signal": "Bullish cross"},
            {"symbol": "ETHUSD", "macd_line": 12.5, "signal_line": 10.2, "price": 3568.0,
             "signal": "Bullish cross"},
        ]),
        "Volume Spike (>3x avg)": pd.DataFrame([
            {"symbol": "SOLUSD", "current_vol": "2.4M", "avg_vol": "0.6M", "multiple": 4.0,
             "signal": "4x volume spike"},
            {"symbol": "BTCUSD", "current_vol": "18M", "avg_vol": "7.5M", "multiple": 2.4,
             "signal": "2.4x volume spike"},
        ]),
        "Gap Up (>1%)": pd.DataFrame([
            {"symbol": "SOLUSD", "gap_pct": 8.2, "prev_close": 171.5, "current": 185.5,
             "signal": "Gap up"},
            {"symbol": "AUDJPY", "gap_pct": 2.7, "prev_close": 96.8, "current": 99.45,
             "signal": "Gap up"},
        ]),
        "Gap Down (<-1%)": pd.DataFrame([
            {"symbol": "XAUUSD", "gap_pct": -1.5, "prev_close": 2055.0, "current": 2025.0,
             "signal": "Gap down"},
            {"symbol": "USDJPY", "gap_pct": -1.2, "prev_close": 150.9, "current": 149.10,
             "signal": "Gap down"},
        ]),
    }
    return scans.get(selected_scan, scans["RSI Oversold (RSI<30)"])


def _fundamentals() -> pd.DataFrame:
    """Company fundamental data."""
    return pd.DataFrame([
        {"symbol": "AAPL", "pe_ratio": 32.5, "eps": 5.97, "market_cap": "3.0T",
         "dividend_yield": 0.52, "debt_to_equity": 1.95, "roe": 156.0},
        {"symbol": "SPY", "pe_ratio": 24.8, "eps": 19.35, "market_cap": "—",
         "dividend_yield": 1.42, "debt_to_equity": 0.0, "roe": 0.0},
        {"symbol": "QQQ", "pe_ratio": 28.1, "eps": 14.94, "market_cap": "—",
         "dividend_yield": 0.78, "debt_to_equity": 0.0, "roe": 0.0},
        {"symbol": "BTCUSD", "pe_ratio": "—", "eps": "—", "market_cap": "1.25T",
         "dividend_yield": 0.0, "debt_to_equity": "—", "roe": "—"},
        {"symbol": "ETHUSD", "pe_ratio": "—", "eps": "—", "market_cap": "430B",
         "dividend_yield": 0.0, "debt_to_equity": "—", "roe": "—"},
    ])


def _corporate_actions() -> pd.DataFrame:
    """Corporate actions feed."""
    now = datetime.now(timezone.utc)
    return pd.DataFrame([
        {"symbol": "AAPL", "action": "Dividend", "ex_date": (now + timedelta(days=5)).date(),
         "record_date": (now + timedelta(days=6)).date(), "details": "$0.24/share quarterly"},
        {"symbol": "SPY", "action": "Rebalance", "ex_date": (now + timedelta(days=14)).date(),
         "record_date": (now + timedelta(days=15)).date(), "details": "Q quarterly rebalance"},
        {"symbol": "QQQ", "action": "Rebalance", "ex_date": now.date(),
         "record_date": (now + timedelta(days=1)).date(), "details": "Annual reconstitution"},
        {"symbol": "BTCUSD", "action": "Halving", "ex_date": "2028-04-01",
         "record_date": "—", "details": "Next BTC halving event"},
    ])


def render_market_tab() -> None:
    """Render the Market tab with 5 sub-tabs."""
    st.header("📈 Market")

    sub_exchange, sub_movers, sub_scanners, sub_fundamentals, sub_corp = st.tabs([
        "📨 Exchange Messages", "🚀 Market Movers", "🔍 Scanners",
        "📊 Fundamentals", "🏛️ Corporate Actions"
    ])

    # ── Exchange Messages ──
    with sub_exchange:
        msgs = _exchange_messages()
        st.dataframe(msgs, use_container_width=True, hide_index=True)
        if PLOTLY_OK:
            impact_counts = msgs["impact"].value_counts()
            fig = go.Figure(data=[go.Bar(x=impact_counts.index, y=impact_counts.values,
                                         marker_color=["#f85149", "#d29922", "#3fb950"][:len(impact_counts)])])
            fig.update_layout(title="Message Impact Distribution",
                              template="plotly_dark", height=300)
            st.plotly_chart(fig, use_container_width=True)

    # ── Market Movers ──
    with sub_movers:
        gainers, losers, active = _market_movers()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("🟢 Top Gainers")
            st.dataframe(gainers, use_container_width=True, hide_index=True)
        with col2:
            st.subheader("🔴 Top Losers")
            st.dataframe(losers, use_container_width=True, hide_index=True)
        with col3:
            st.subheader("📈 Most Active")
            st.dataframe(active, use_container_width=True, hide_index=True)

        if PLOTLY_OK:
            combined = pd.concat([gainers.assign(cat="Gain"), losers.assign(cat="Loss")])
            fig = go.Figure(data=[go.Bar(
                x=combined["symbol"], y=combined["change_pct"],
                marker_color=["#3fb950" if v > 0 else "#f85149" for v in combined["change_pct"]],
                text=combined["change_pct"], textposition="outside"
            )])
            fig.update_layout(title="Daily Movers", xaxis_title="Symbol",
                              yaxis_title="Change %", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

    # ── Scanners ──
    with sub_scanners:
        scan_options = [
            "RSI Oversold (RSI<30)", "MACD Bullish Crossover",
            "Volume Spike (>3x avg)", "Gap Up (>1%)", "Gap Down (<-1%)"
        ]
        sel = st.selectbox("Select scan", scan_options)
        results = _scanners(sel)
        st.dataframe(results, use_container_width=True, hide_index=True)

    # ── Fundamentals ──
    with sub_fundamentals:
        st.dataframe(_fundamentals(), use_container_width=True, hide_index=True)

    # ── Corporate Actions ──
    with sub_corp:
        st.dataframe(_corporate_actions(), use_container_width=True, hide_index=True)
