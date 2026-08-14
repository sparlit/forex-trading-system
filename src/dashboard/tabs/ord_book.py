"""
Order Book tab — Order Book, Trade Book, Spread/Multi-leg, and Trigger Orders.

Vibrant blue/cyan theme. Four sub-tabs using st.tabs.
    (a) Order Book: pending/working orders.
    (b) Trade Book: filled orders.
    (c) Spread/Multi-leg: multi-leg order details.
    (d) Trigger Orders: conditional orders.

Synthetic data, per-sub-tab Cancel All button.
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

_THEME = {
    "bg": "#0e1117",
    "panel": "#0b1c28",
    "panel2": "#081822",
    "text": "#e0f2fe",
    "muted": "#93c5fd",
    "primary": "#0284c7",        # vibrant blue
    "secondary": "#06b6d4",
    "accent": "#38bdf8",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "ok": "#34d399",
}


# --------------------------------------------------------------------------- #
# Synthetic data generators
# --------------------------------------------------------------------------- #


def _order_book() -> pd.DataFrame:
    now = datetime.now(UTC)
    rows = []
    for i in range(12):
        ticket = f"OB{i+1001}"
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
        side = random.choice(["BUY", "SELL"])
        ord_type = random.choice(["LIMIT", "STOP", "STOP_LIMIT"])
        volume = random.choice([0.01, 0.05, 0.1, 0.2, 0.5, 1.0])
        price = round(random.uniform(0.8, 1.5), 5) if "USD" in symbol else round(random.uniform(50, 1500), 2)
        status = random.choice(["PENDING", "WORKING", "PARTIAL"])
        valid_until = (now + timedelta(minutes=random.randint(30, 480))).strftime("%Y-%m-%d %H:%M")
        broker = random.choice(["IB", "MT5", "Binance", "Coinbase"])
        rows.append({
            "ticket": ticket,
            "symbol": symbol,
            "side": side,
            "type": ord_type,
            "volume": volume,
            "price": price,
            "status": status,
            "valid_until": valid_until,
            "broker": broker,
        })
    return pd.DataFrame(rows)


def _trade_book() -> pd.DataFrame:
    now = datetime.now(UTC)
    rows = []
    for i in range(15):
        ticket = f"TB{i+2001}"
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
        side = random.choice(["BUY", "SELL"])
        volume = random.choice([0.01, 0.05, 0.1, 0.2, 0.5, 1.0])
        fill_price = round(random.uniform(0.8, 1.5), 5) if "USD" in symbol else round(random.uniform(50, 1500), 2)
        fill_time = (now - timedelta(minutes=random.randint(1, 720))).strftime("%Y-%m-%d %H:%M")
        broker = random.choice(["IB", "MT5", "Binance", "Coinbase"])
        commission = round(random.uniform(0.0, 2.5), 2)
        slippage = round(random.uniform(0.0, 0.5), 3)
        rows.append({
            "ticket": ticket,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "fill_price": fill_price,
            "fill_time": fill_time,
            "broker": broker,
            "commission": commission,
            "slippage_pips": slippage,
        })
    return pd.DataFrame(rows)


def _spread_multi_leg() -> pd.DataFrame:
    rows = []
    for i in range(6):
        name = f"SpreadStrategy_{i+1}"
        legs = []
        for leg_idx in range(random.randint(2, 4)):
            leg_symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
            leg_side = random.choice(["BUY", "SELL"])
            leg_volume = random.choice([0.01, 0.05, 0.1])
            legs.append({"symbol": leg_symbol, "side": leg_side, "volume": leg_volume})
        net_price = round(sum(l["volume"] * random.uniform(0.8, 1.5) for l in legs), 5)
        max_profit = round(random.uniform(50, 200), 2)
        max_loss = -round(random.uniform(30, 150), 2)
        breakeven = round(net_price + random.uniform(-5, 5), 5)
        margin_required = round(random.uniform(1000, 5000), 2)
        rows.append({
            "strategy_name": name,
            "legs": legs,
            "net_price": net_price,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "breakeven": breakeven,
            "margin_required": margin_required,
        })
    return pd.DataFrame(rows)


def _trigger_orders() -> pd.DataFrame:
    now = datetime.now(UTC)
    rows = []
    for i in range(10):
        cond = random.choice([
            "price > SMA(20)",
            "price < EMA(21)",
            "vol > 1M", 
            "rsi(14) > 70", 
            "time == 09:30", 
        ])
        action = random.choice(["Buy", "Sell", "Close", "Cancel"])
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
        side = random.choice(["BUY", "SELL"])
        volume = random.choice([0.01, 0.05, 0.1])
        price = round(random.uniform(0.8, 1.5), 5) if "USD" in symbol else round(random.uniform(50, 1500), 2)
        status = random.choice(["ACTIVE", "TRIGGERED", "CANCELLED"])
        created = (now - timedelta(minutes=random.randint(0, 1200))).strftime("%Y-%m-%d %H:%M")
        expires = (now + timedelta(hours=random.randint(1, 12))).strftime("%Y-%m-%d %H:%M")
        rows.append({
            "trigger_condition": cond,
            "action": action,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": price,
            "status": status,
            "created": created,
            "expires": expires,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .ord-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
        }}
        .ord-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 12px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_ord_book_tab() -> None:
    """Render the Order Book tab with four sub‑tabs."""
    _inject_css()
    st.markdown(
        f"""
        <div class="ord-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">⚙️ Order Book & Trade Management</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Live view of pending orders, filled trades, multi‑leg spreads and conditional triggers.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_order, tab_trade, tab_spread, tab_trigger = st.tabs(["Order Book", "Trade Book", "Spread / Multi‑leg", "Trigger Orders"])

    # ---- (a) Order Book ----
    with tab_order:
        st.markdown("### Pending / Working Orders")
        df_ob = _order_book()
        st.dataframe(
            df_ob,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticket": st.column_config.TextColumn("Ticket", width="small"),
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "side": st.column_config.TextColumn("Side", width="small"),
                "type": st.column_config.TextColumn("Type", width="small"),
                "volume": st.column_config.NumberColumn("Vol", format="%.3f"),
                "price": st.column_config.NumberColumn("Price", format="%.5f"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "valid_until": st.column_config.TextColumn("Valid Until", width="medium"),
                "broker": st.column_config.TextColumn("Broker", width="small"),
            },
        )
        if st.button("Cancel All Orders", key="cancel_all_ob"):
            st.warning("⚠️ All pending orders would be sent cancellation requests (simulated).")

    # ---- (b) Trade Book ----
    with tab_trade:
        st.markdown("### Filled Trade History")
        df_tb = _trade_book()
        st.dataframe(
            df_tb,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticket": st.column_config.TextColumn("Ticket", width="small"),
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "side": st.column_config.TextColumn("Side", width="small"),
                "volume": st.column_config.NumberColumn("Vol", format="%.3f"),
                "fill_price": st.column_config.NumberColumn("Fill Price", format="%.5f"),
                "fill_time": st.column_config.TextColumn("Fill Time", width="medium"),
                "broker": st.column_config.TextColumn("Broker", width="small"),
                "commission": st.column_config.NumberColumn("Comm.", format="%.2f"),
                "slippage_pips": st.column_config.NumberColumn("Slippage (pips)", format="%.3f"),
            },
        )
        if st.button("Clear Trade History", key="clear_trade"):
            st.info("🔹 In a real system this would purge the local cache – here it simply re‑generates synthetic data.")

    # ---- (c) Spread / Multi‑leg ----
    with tab_spread:
        st.markdown("### Multi‑Leg Spread Strategies")
        df_spread = _spread_multi_leg()
        # Render as expandable rows showing leg details
        for idx, row in df_spread.iterrows():
            with st.expander(f"{row['strategy_name']} – Net {row['net_price']:.5f}"):
                st.write(f"**Max Profit:** ${row['max_profit']:.2f}")
                st.write(f"**Max Loss:** ${row['max_loss']:.2f}")
                st.write(f"**Breakeven:** {row['breakeven']:.5f}")
                st.write(f"**Margin Required:** ${row['margin_required']:.2f}")
                st.subheader("Legs")
                legs_df = pd.DataFrame(row["legs"])
                st.table(legs_df)
        if st.button("Cancel All Spread Orders", key="cancel_spread"):
            st.warning("⚠️ All multi‑leg orders would be cancelled (simulated).")

    # ---- (d) Trigger Orders ----
    with tab_trigger:
        st.markdown("### Conditional Trigger Orders")
        df_trig = _trigger_orders()
        st.dataframe(
            df_trig,
            use_container_width=True,
            hide_index=True,
            column_config={
                "trigger_condition": st.column_config.TextColumn("Condition", width="large"),
                "action": st.column_config.TextColumn("Action", width="small"),
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "side": st.column_config.TextColumn("Side", width="small"),
                "volume": st.column_config.NumberColumn("Vol", format="%.3f"),
                "price": st.column_config.NumberColumn("Price", format="%.5f"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "created": st.column_config.TextColumn("Created", width="medium"),
                "expires": st.column_config.TextColumn("Expires", width="medium"),
            },
        )
        if st.button("Deactivate All Triggers", key="deact_trig"):
            st.warning("⚠️ All trigger orders would be set to INACTIVE (simulated).")

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} – synthetic order data."
    )
