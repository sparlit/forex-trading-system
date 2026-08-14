"""
Execution Logger tab — full lifecycle log of every order event.

Displays timestamped submit/modify/cancel/fill events with latency,
TCA score, and slippage. Supports symbol + action filtering, CSV
export, and a latency-distribution histogram.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import numpy as np
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
    from src.execution.audit_log import ExecutionAuditLog  # type: ignore
except Exception:  # pragma: no cover
    ExecutionAuditLog = None  # type: ignore[assignment,misc]

try:
    import plotly.express as px  # type: ignore
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False


# --------------------------------------------------------------------------- #
# Placeholder data
# --------------------------------------------------------------------------- #


def _exec_log(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]
    actions = ["submit", "modify", "cancel", "fill"]
    actions_w = [0.30, 0.20, 0.10, 0.40]
    brokers = ["MT5-Demo", "MT5-Live", "Binance", "Coinbase"]

    base = datetime.now(UTC)
    rows = []
    for i in range(n):
        ts = base - timedelta(seconds=i * rng.integers(2, 30))
        sym = str(rng.choice(symbols))
        act = str(rng.choice(actions, p=actions_w))
        price = float(round(rng.uniform(1.05, 1.30), 5))
        qty = float(rng.choice([0.05, 0.10, 0.20, 0.30, 0.50, 1.00]))
        broker = str(rng.choice(brokers))
        latency = int(rng.integers(8, 320))
        tca = float(round(rng.uniform(-0.6, 0.9), 3))
        slippage = float(round(rng.normal(0.0, 0.6), 3))  # pips
        rows.append({
            "timestamp":  ts.strftime("%Y-%m-%d %H:%M:%S"),
            "order_id":   f"ORD-{540_000 + i:06d}",
            "symbol":     sym,
            "action":     act,
            "price":      price,
            "quantity":   qty,
            "broker":     broker,
            "latency_ms": latency,
            "tca_score":  tca,
            "slippage":   slippage,
        })
    return pd.DataFrame(rows)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #


def render_execution_logger_tab() -> None:
    """Render the execution log with filters, export, and histogram."""
    st.header("📜 Execution Logger")
    st.caption(
        "Full order-event audit trail with latency, TCA score, and slippage. "
        "Use the filters below to narrow the view."
    )

    df = _exec_log()

    # ---- Filters ---------------------------------------------------------- #
    f1, f2, f3 = st.columns([1, 2, 1])
    symbol_filter = f1.selectbox(
        "Symbol",
        options=["(all)"] + sorted(df["symbol"].unique().tolist()),
        index=0,
    )
    action_filter = f2.multiselect(
        "Action",
        options=sorted(df["action"].unique().tolist()),
        default=sorted(df["action"].unique().tolist()),
    )
    broker_filter = f3.selectbox(
        "Broker",
        options=["(all)"] + sorted(df["broker"].unique().tolist()),
        index=0,
    )

    view = df.copy()
    if symbol_filter != "(all)":
        view = view[view["symbol"] == symbol_filter]
    if action_filter:
        view = view[view["action"].isin(action_filter)]
    if broker_filter != "(all)":
        view = view[view["broker"] == broker_filter]

    st.caption(f"Showing {len(view)} of {len(df)} events.")

    # ---- Top KPI strip ---------------------------------------------------- #
    if len(view):
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Events", len(view))
        k2.metric("Avg latency", f"{view['latency_ms'].mean():.0f} ms")
        k3.metric("p95 latency", f"{view['latency_ms'].quantile(0.95):.0f} ms")
        k4.metric("Avg TCA", f"{view['tca_score'].mean():+.3f}")
        k5.metric("Avg slippage", f"{view['slippage'].mean():+.3f} pips")

    # ---- Table ------------------------------------------------------------ #
    st.subheader("Event log")
    st.dataframe(view, use_container_width=True, hide_index=True, height=420)

    # ---- Export ----------------------------------------------------------- #
    csv = _csv_bytes(view)
    st.download_button(
        "⬇️ Export filtered log to CSV",
        data=csv,
        file_name=f"execution_log_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
    )

    st.divider()

    # ---- Latency distribution -------------------------------------------- #
    st.subheader("Latency distribution")
    if _HAS_PLOTLY and len(view):
        fig = px.histogram(
            view,
            x="latency_ms",
            nbins=30,
            color="action",
            marginal="box",
            title="Latency by action (ms)",
            labels={"latency_ms": "Latency (ms)"},
        )
        fig.update_layout(barmode="overlay", height=380)
        fig.update_traces(opacity=0.65)
        st.plotly_chart(fig, use_container_width=True)

        # Slippage scatter vs latency
        st.subheader("Slippage vs latency (by broker)")
        fig2 = px.scatter(
            view,
            x="latency_ms", y="slippage",
            color="broker", symbol="action",
            hover_data=["order_id", "symbol", "price"],
            labels={"latency_ms": "Latency (ms)", "slippage": "Slippage (pips)"},
        )
        fig2.update_layout(height=380)
        st.plotly_chart(fig2, use_container_width=True)
    elif len(view):
        st.bar_chart(view["latency_ms"].value_counts(bins=20).sort_index())
    else:
        st.info("No events match the current filters.")
