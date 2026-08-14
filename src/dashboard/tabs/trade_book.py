"""
Trade Book tab — Standalone top-level view of all trades.
Uses multiprocessing.Pool for parallel feature computation across trade entries.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

try:
    from multiprocessing import Pool, cpu_count
    MP_OK = True
except ImportError:
    MP_OK = False


# ── Multiprocessing helper ──────────────────────────────────────────────────
def _compute_trade_features(trade_row: dict[str, Any]) -> dict[str, Any]:
    """Compute per-trade features in parallel (one trade per worker)."""
    pnl = float(trade_row.get("pnl", 0.0))
    entry = float(trade_row.get("entry_price", 1.0))
    current = float(trade_row.get("current_price", entry))
    vol = float(trade_row.get("volume", 0.0))
    duration_min = float(trade_row.get("duration_min", 0.0))

    pnl_pips = (current - entry) * 10000 if entry > 0 else 0
    pnl_pct = (pnl / max(1.0, vol * entry * 100000)) * 100
    pnl_per_min = pnl / max(1.0, duration_min)
    notional = vol * entry * 100000

    return {
        "pnl_pips": round(pnl_pips, 1),
        "pnl_pct": round(pnl_pct, 4),
        "pnl_per_min": round(pnl_per_min, 6),
        "notional": round(notional, 2),
        "pnl_status": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAK-EVEN"),
    }


def _parallel_enrich(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich a batch of trades using multiprocessing."""
    if not MP_OK or len(trades) < 4:
        # Single-process fallback for small batches
        return [_compute_trade_features(t) for t in trades]
    try:
        with Pool(min(cpu_count(), 4)) as pool:
            features = pool.map(_compute_trade_features, trades)
        return features
    except Exception:
        return [_compute_trade_features(t) for t in trades]


def _synthetic_trades() -> list[dict[str, Any]]:
    """Generate a synthetic trade book for the UI."""
    now = datetime.now(timezone.utc)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD", "SPY", "AAPL"]
    trades = []
    for i in range(48):
        sym = symbols[i % len(symbols)]
        side = "BUY" if i % 2 == 0 else "SELL"
        entry = 1.0850 + (i % 7) * 0.001
        current = entry + ((-1) ** i) * (0.0005 + (i % 5) * 0.0002)
        vol = round(0.05 + (i % 4) * 0.15, 2)
        pnl = (current - entry) * vol * 100000 if side == "BUY" else (entry - current) * vol * 100000
        duration = (i % 240) + 1
        t_open = now - timedelta(minutes=duration)
        trades.append({
            "ticket": 100001 + i,
            "symbol": sym,
            "side": side,
            "entry_price": round(entry, 5),
            "current_price": round(current, 5),
            "volume": vol,
            "pnl": round(pnl, 2),
            "duration_min": duration,
            "time_open": t_open.strftime("%H:%M:%S"),
            "broker": "MT5" if i % 3 == 0 else ("Binance" if "BTC" in sym or "ETH" in sym else "IBKR"),
            "status": "OPEN" if i % 4 != 0 else "CLOSED",
            "magic": 60022138 + (i % 3),
        })
    return trades


def _df_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def render_trade_book_tab() -> None:
    """Render standalone Trade Book tab."""
    st.header("📚 Trade Book")

    raw_trades = _synthetic_trades()
    with st.spinner("Computing trade features in parallel..."):
        features = _parallel_enrich(raw_trades)

    enriched: list[dict[str, Any]] = []
    for trade, feat in zip(raw_trades, features):
        enriched.append({**trade, **feat})
    df = pd.DataFrame(enriched)

    # ── Summary metrics ───────────────────────────────────────────────
    cols = st.columns(5)
    with cols[0]:
        st.metric("Total Trades", len(df), help=f"Using {cpu_count()} CPU cores" if MP_OK else "Single-process")
    with cols[1]:
        st.metric("Open", len(df[df["status"] == "OPEN"]))
    with cols[2]:
        st.metric("Closed", len(df[df["status"] == "CLOSED"]))
    with cols[3]:
        st.metric("Total PnL", f"${df['pnl'].sum():,.2f}",
                  delta=f"{df['pnl'].sum():+.2f}")
    with cols[4]:
        win_rate = (len(df[df["pnl"] > 0]) / max(1, len(df))) * 100
        st.metric("Win Rate", f"{win_rate:.1f}%")

    st.markdown("---")

    # ── Filters ───────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        sym_filter = st.multiselect("Symbols", sorted(df["symbol"].unique().tolist()))
    with fc2:
        side_filter = st.multiselect("Side", ["BUY", "SELL"])
    with fc3:
        status_filter = st.multiselect("Status", ["OPEN", "CLOSED"])
    with fc4:
        broker_filter = st.multiselect("Broker", sorted(df["broker"].unique().tolist()))

    view = df.copy()
    if sym_filter:
        view = view[view["symbol"].isin(sym_filter)]
    if side_filter:
        view = view[view["side"].isin(side_filter)]
    if status_filter:
        view = view[view["status"].isin(status_filter)]
    if broker_filter:
        view = view[view["broker"].isin(broker_filter)]

    # ── Table ─────────────────────────────────────────────────────────
    st.dataframe(
        view[["ticket", "symbol", "side", "entry_price", "current_price",
              "volume", "pnl", "pnl_pct", "pnl_pips", "duration_min",
              "status", "broker", "time_open", "pnl_status"]],
        use_container_width=True, hide_index=True,
    )

    # ── Export ────────────────────────────────────────────────────────
    st.download_button(
        "⬇️ Export Trade Book CSV",
        _df_to_csv(view),
        file_name=f"trade_book_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    # ── Charts ────────────────────────────────────────────────────────
    if PLOTLY_OK and not view.empty:
        st.markdown("### PnL Distribution by Symbol")
        fig = px.bar(view.groupby("symbol")["pnl"].sum().reset_index(),
                     x="symbol", y="pnl",
                     color="pnl",
                     color_continuous_scale=["#f85149", "#d29922", "#3fb950"],
                     title="Cumulative PnL per Symbol")
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
