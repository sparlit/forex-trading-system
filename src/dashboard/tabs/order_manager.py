"""
Order Manager tab — order book, trade book, spread/multi-leg, trigger orders.

Four sub-tabs covering the full order lifecycle:
  1. Order Book — pending orders with cancel-all
  2. Trade Book — fills from today
  3. Spread / Multi-leg — leg builder + existing spreads
  4. Trigger Orders — conditional orders + create form
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

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
    from src.execution.order_router import OrderRouter  # type: ignore
except Exception:  # pragma: no cover
    OrderRouter = None  # type: ignore[assignment,misc]


# --------------------------------------------------------------------------- #
# Placeholder data — field names mirror a typical OMS
# --------------------------------------------------------------------------- #


def _order_book() -> pd.DataFrame:
    base = datetime.now(UTC)
    return pd.DataFrame(
        [
            {"ticket": 550_001, "symbol": "EURUSD", "side": "BUY",  "type": "LIMIT",
             "volume": 0.50, "price": 1.08450, "sl": 1.08200, "tp": 1.08950,
             "status": "pending", "time": (base - timedelta(minutes=2)).strftime("%H:%M:%S"),
             "broker": "MT5-Demo"},
            {"ticket": 550_002, "symbol": "GBPUSD", "side": "SELL", "type": "STOP",
             "volume": 0.30, "price": 1.27200, "sl": 1.27500, "tp": 1.26600,
             "status": "pending", "time": (base - timedelta(minutes=5)).strftime("%H:%M:%S"),
             "broker": "MT5-Demo"},
            {"ticket": 550_003, "symbol": "USDJPY", "side": "BUY",  "type": "LIMIT",
             "volume": 0.20, "price": 149.250, "sl": 148.900, "tp": 149.950,
             "status": "pending", "time": (base - timedelta(minutes=9)).strftime("%H:%M:%S"),
             "broker": "MT5-Live"},
            {"ticket": 550_004, "symbol": "XAUUSD", "side": "BUY",  "type": "MARKET",
             "volume": 0.10, "price": 2345.10, "sl": 2330.00, "tp": 2380.00,
             "status": "working", "time": (base - timedelta(seconds=12)).strftime("%H:%M:%S"),
             "broker": "MT5-Live"},
        ]
    )


def _trade_book() -> pd.DataFrame:
    base = datetime.now(UTC)
    return pd.DataFrame(
        [
            {"ticket": 540_998, "symbol": "EURUSD", "side": "BUY",  "fill_price": 1.08620,
             "volume": 0.50, "pnl": +85.00, "time": (base - timedelta(hours=1)).strftime("%H:%M:%S")},
            {"ticket": 540_999, "symbol": "GBPUSD", "side": "SELL", "fill_price": 1.26940,
             "volume": 0.30, "pnl": -42.50, "time": (base - timedelta(hours=2, minutes=15)).strftime("%H:%M:%S")},
            {"ticket": 541_000, "symbol": "USDJPY", "side": "BUY",  "fill_price": 149.110,
             "volume": 0.20, "pnl": +24.10, "time": (base - timedelta(hours=3, minutes=40)).strftime("%H:%M:%S")},
            {"ticket": 541_001, "symbol": "XAUUSD", "side": "SELL", "fill_price": 2351.40,
             "volume": 0.05, "pnl": -18.20, "time": (base - timedelta(hours=5)).strftime("%H:%M:%S")},
        ]
    )


def _spread_orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": "SP-001", "leg1": "BUY  EURUSD 0.30 @1.0860",
             "leg2": "SELL GBPUSD 0.30 @1.2700",
             "spread_target": 0.0184, "spread_current": 0.0182,
             "status": "armed", "filled_legs": "0/2"},
            {"id": "SP-002", "leg1": "SELL USDJPY 0.20 @149.30",
             "leg2": "BUY  EURUSD 0.20 @1.0855",
             "spread_target": 148.245, "spread_current": 148.260,
             "status": "partial", "filled_legs": "1/2"},
        ]
    )


def _trigger_orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trigger_type": "price_above", "trigger_price": 1.09500, "symbol": "EURUSD",
             "action": "BUY 0.50 MKT", "volume": 0.50, "status": "armed"},
            {"trigger_type": "price_below", "trigger_price": 1.26000, "symbol": "GBPUSD",
             "action": "SELL 0.30 MKT", "volume": 0.30, "status": "armed"},
            {"trigger_type": "time_at",     "trigger_price": "13:30 UTC", "symbol": "USDJPY",
             "action": "CLOSE_ALL",     "volume": 0,    "status": "armed"},
            {"trigger_type": "spread_above","trigger_price": 0.0185, "symbol": "EURUSD-GBPUSD",
             "action": "OPEN_SPREAD",   "volume": 0.30, "status": "tripped"},
        ]
    )


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #


def render_order_manager_tab() -> None:
    """Render the Order Manager with 4 sub-tabs."""
    st.header("📋 Order Manager")
    st.caption("Live and historical orders across brokers.")

    sub = st.tabs(["Order Book", "Trade Book", "Spread / Multi-leg", "Trigger Orders"])

    # ---------- Order Book ---------------------------------------------- #
    with sub[0]:
        st.subheader("Pending orders")
        ob = _order_book()
        ctop = st.columns([1, 1, 1, 5])
        if ctop[0].button("Cancel all", type="primary"):
            st.error(f"Cancel-all issued for {len(ob)} orders (placeholder).")
        if ctop[1].button("Flatten symbols"):
            st.warning("Flatten request queued (placeholder).")
        if ctop[2].button("Refresh"):
            st.rerun()

        st.dataframe(ob, use_container_width=True, hide_index=True)

        st.markdown("**Per-order actions**")
        for _, row in ob.iterrows():
            c = st.columns([2, 2, 2, 2, 1])
            c[0].write(f"`{row['ticket']}` **{row['symbol']}** {row['side']}")
            c[1].write(f"{row['type']} @ {row['price']}")
            c[2].write(f"vol {row['volume']}  SL {row['sl']}  TP {row['tp']}")
            c[3].write(f"status: *{row['status']}*  broker: {row['broker']}")
            if c[4].button("Cancel", key=f"cancel_{row['ticket']}"):
                st.warning(f"Order {row['ticket']} cancelled (placeholder).")

    # ---------- Trade Book ---------------------------------------------- #
    with sub[1]:
        st.subheader("Filled orders — today")
        tb = _trade_book()
        totals = st.columns(3)
        totals[0].metric("Fills today", len(tb))
        totals[1].metric("Realised PnL",
                         f"${tb['pnl'].sum():+,.2f}")
        totals[2].metric("Volume (lots)",
                         f"{tb['volume'].sum():.2f}")
        st.dataframe(tb, use_container_width=True, hide_index=True)

    # ---------- Spread / Multi-leg -------------------------------------- #
    with sub[2]:
        st.subheader("Multi-leg order builder")
        with st.form("spread_builder"):
            r1c1, r1c2, r1c3, r1c4 = st.columns(4)
            leg1_sym = r1c1.selectbox("Leg 1 symbol",
                                      ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
                                      key="leg1_sym")
            leg1_side = r1c2.selectbox("Leg 1 side", ["BUY", "SELL"], key="leg1_side")
            leg1_vol = r1c3.number_input("Leg 1 volume", 0.01, 5.0, 0.30, 0.01, key="leg1_vol")
            leg1_price = r1c4.number_input("Leg 1 price", 0.0, 5000.0, 1.0850, 0.0001, key="leg1_price")

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            leg2_sym = r2c1.selectbox("Leg 2 symbol",
                                      ["GBPUSD", "EURUSD", "USDJPY", "AUDUSD"],
                                      index=1, key="leg2_sym")
            leg2_side = r2c2.selectbox("Leg 2 side", ["BUY", "SELL"], index=1, key="leg2_side")
            leg2_vol = r2c3.number_input("Leg 2 volume", 0.01, 5.0, 0.30, 0.01, key="leg2_vol")
            leg2_price = r2c4.number_input("Leg 2 price", 0.0, 5000.0, 1.2700, 0.0001, key="leg2_price")

            tgt = st.number_input("Spread target (quote-currency units)",
                                  min_value=-10.0, max_value=10.0, value=0.0184, step=0.0001)
            ttl = st.slider("Time-in-force (min)", 1, 60, 15)
            if st.form_submit_button("Submit spread order"):
                st.success(
                    f"Spread order queued — {leg1_side} {leg1_vol} {leg1_sym}@{leg1_price} "
                    f"+ {leg2_side} {leg2_vol} {leg2_sym}@{leg2_price} target={tgt} ttl={ttl}m."
                )

        st.divider()
        st.subheader("Existing spread orders")
        st.dataframe(_spread_orders(), use_container_width=True, hide_index=True)

    # ---------- Trigger Orders ------------------------------------------ #
    with sub[3]:
        st.subheader("Conditional / trigger orders")
        st.dataframe(_trigger_orders(), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Create trigger order")
        with st.form("trigger_create"):
            ttype = st.selectbox(
                "Trigger type",
                ["price_above", "price_below", "time_at", "spread_above", "spread_below"],
            )
            tsym = st.selectbox("Symbol", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
            tact = st.selectbox(
                "Action",
                ["BUY MKT", "SELL MKT", "CLOSE_ALL", "OPEN_SPREAD", "CANCEL_ALL_PENDING"],
            )
            tvol = st.number_input("Volume", 0.0, 10.0, 0.30, 0.01)
            tprice = st.text_input("Trigger value (price or HH:MM)", value="1.09500")
            submitted = st.form_submit_button("Arm trigger")
            if submitted:
                st.success(
                    f"Trigger armed — {ttype} {tprice} on {tsym} → {tact} vol {tvol}."
                )
