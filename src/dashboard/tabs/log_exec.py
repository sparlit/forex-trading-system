"""
Log Execution tab — Direct execution logs and database transaction logs.

Vibrant amber/gold theme. Two sections:
    (a) Execution Log with filtering and CSV export.
    (b) Database Transaction Log.

Synthetic data fallback.
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
    "panel": "#1a0e08",
    "panel2": "#120b07",
    "text": "#fef3c7",
    "muted": "#d9a558",
    "primary": "#fbbf24",        # amber
    "secondary": "#fcd34d",
    "accent": "#fbbf24",
    "warn": "#f59e0b",
    "danger": "#ef4444",
    "ok": "#34d399",
}


# --------------------------------------------------------------------------- #
# Synthetic data generators
# --------------------------------------------------------------------------- #


def _execution_log() -> pd.DataFrame:
    now = datetime.now(UTC)
    actions = ["NEW", "MOD", "CXL", "FILL", "PARTIAL_FILL"]
    rows = []
    for i in range(120):
        ts = (now - timedelta(seconds=random.randint(0, 86400))).strftime("%Y-%m-%d %H:%M:%S")
        order_id = f"ORD{random.randint(1000,9999)}"
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])
        action = random.choice(actions)
        price = round(random.uniform(0.8, 1.5), 5) if "USD" in symbol else round(random.uniform(50, 1500), 2)
        qty = random.choice([0.01, 0.05, 0.1, 0.2, 0.5, 1.0])
        broker = random.choice(["IB", "MT5", "Binance", "Coinbase"])
        latency = round(random.uniform(0.5, 25.4), 2)
        tca = round(random.uniform(0.0, 1.2), 3)
        slippage = round(random.uniform(0.0, 2.4), 2)
        rejection = "" if action != "CXL" else random.choice(["Insufficient margin", "Invalid price", "Network timeout"])
        rows.append({
            "timestamp": ts,
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": qty,
            "broker": broker,
            "latency_ms": latency,
            "tca_score": tca,
            "slippage_bps": slippage,
            "rejection_reason": rejection,
        })
    return pd.DataFrame(rows)


def _db_transactions() -> pd.DataFrame:
    now = datetime.now(UTC)
    ops = ["INSERT", "UPDATE", "DELETE"]
    rows = []
    for i in range(80):
        ts = (now - timedelta(seconds=random.randint(0, 86400))).strftime("%Y-%m-%d %H:%M:%S")
        tx_id = f"TX{random.randint(2000,9999)}"
        table = random.choice(["orders", "trades", "positions", "account", "risk_limits"])
        op = random.choice(ops)
        rows_affected = random.randint(1, 150)
        exec_ms = round(random.uniform(0.2, 16.8), 2)
        user = random.choice(["system", "admin", "scheduler", "engine"])
        checksum = f"{random.getrandbits(64):016x}"
        rows.append({
            "tx_id": tx_id,
            "table_affected": table,
            "operation": op,
            "rows_affected": rows_affected,
            "execution_time_ms": exec_ms,
            "timestamp": ts,
            "user": user,
            "checksum": checksum,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .log-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .log-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['secondary']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 10px 14px;
            border-radius: 8px;
            margin-bottom: 8px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_log_exec_tab() -> None:
    """Render the Execution + DB Log tab."""
    _inject_css()
    st.markdown(
        f"""
        <div class="log-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">⏱ Log Execution — Orders & DB Transactions</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Detailed execution trace with filtering and CSV export, and audit‑trail DB transaction log.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- (a) Execution Log ----
    st.markdown("### (a) Execution Log")
    exec_df = _execution_log()
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        action_filter = st.multiselect("Action", options=exec_df["action"].unique(), default=list(exec_df["action"].unique()))
    with col2:
        symbol_filter = st.multiselect("Symbol", options=exec_df["symbol"].unique(), default=list(exec_df["symbol"].unique()))
    with col3:
        date_range = st.date_input("Date range", [], help="Select one or two dates to filter.")
    filtered = exec_df[exec_df["action"].isin(action_filter) & exec_df["symbol"].isin(symbol_filter)]
    if isinstance(date_range, list) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[ (pd.to_datetime(filtered["timestamp"]).dt.date >= start) & (pd.to_datetime(filtered["timestamp"]).dt.date <= end) ]
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp": st.column_config.TextColumn("Time", width="medium"),
            "order_id": st.column_config.TextColumn("Order ID", width="small"),
            "symbol": st.column_config.TextColumn("Symbol", width="small"),
            "action": st.column_config.TextColumn("Action", width="small"),
            "price": st.column_config.NumberColumn("Price", format="%.5f"),
            "quantity": st.column_config.NumberColumn("Qty", format="%.3f"),
            "broker": st.column_config.TextColumn("Broker", width="small"),
            "latency_ms": st.column_config.NumberColumn("Latency ms", format="%.2f"),
            "tca_score": st.column_config.NumberColumn("TCA", format="%.3f"),
            "slippage_bps": st.column_config.NumberColumn("Slippage bps", format="%.2f"),
            "rejection_reason": st.column_config.TextColumn("Rejection", width="medium"),
        },
    )
    csv = filtered.to_csv(index=False)
    st.download_button(label="Download CSV", data=csv, file_name="execution_log.csv", mime="text/csv")

    st.divider()

    # ---- (b) Database Transaction Log ----
    st.markdown("### (b) Database Transaction Log")
    db_df = _db_transactions()
    st.dataframe(
        db_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "tx_id": st.column_config.TextColumn("Tx ID", width="small"),
            "table_affected": st.column_config.TextColumn("Table", width="small"),
            "operation": st.column_config.TextColumn("Op", width="small"),
            "rows_affected": st.column_config.NumberColumn("Rows", format="%d"),
            "execution_time_ms": st.column_config.NumberColumn("Exec ms", format="%.2f"),
            "timestamp": st.column_config.TextColumn("Time", width="medium"),
            "user": st.column_config.TextColumn("User", width="small"),
            "checksum": st.column_config.TextColumn("Checksum", width="medium"),
        },
    )
    db_csv = db_df.to_csv(index=False)
    st.download_button(label="Download DB Log CSV", data=db_csv, file_name="db_transactions.csv", mime="text/csv")

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • Synthetic logs."
    )
