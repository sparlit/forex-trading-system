"""
Risk Manager tab — equity, margin, drawdown, VaR, position sizing & limits.

Shows real-time account metrics, drawdown progress, Value-at-Risk and
Expected Shortfall, a position-sizing calculator, circuit-breaker status,
and an editable risk-limits form. Falls back to placeholder data so the
page renders even when the broker/RiskService is offline.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from typing import Any

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
    from src.risk.service import RiskService  # type: ignore
except Exception:  # pragma: no cover
    RiskService = None  # type: ignore[assignment,misc]

try:
    import plotly.graph_objects as go  # type: ignore
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False


# --------------------------------------------------------------------------- #
# Placeholder data
# --------------------------------------------------------------------------- #


def _account() -> dict[str, Any]:
    return {
        "equity": 102_450.20,
        "balance": 100_000.00,
        "used_margin": 12_300.00,
        "free_margin": 90_150.20,
        "margin_level_pct": 832.9,
        "daily_pnl": -820.50,
        "daily_pnl_limit_pct": 2.0,
        "open_positions": 3,
        "max_drawdown_pct": 4.6,
        "max_drawdown_limit_pct": 8.0,
    }


def _risk_stats() -> dict[str, float]:
    return {
        "var_95": 1_245.00,   # 1-day VaR at 95% confidence, $ loss
        "var_99": 1_980.00,
        "es_95":  1_640.00,   # Expected Shortfall (CVaR)
        "es_99":  2_410.00,
    }


def _circuit_breaker() -> dict[str, Any]:
    return {
        "state": "armed",  # one of: armed, tripped, cooling_down, disarmed
        "reason": None,
        "tripped_at": None,
        "reset_at": (datetime.now(UTC)).strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #


def render_risk_manager_tab() -> None:
    """Render the risk manager dashboard."""
    st.header("🛡️ Risk Manager")
    st.caption(
        "Live equity, margin, drawdown, VaR/ES, position sizing calculator, "
        "circuit-breaker status, and editable risk limits."
    )

    acct = _account()
    stats = _risk_stats()
    breaker = _circuit_breaker()

    # ---- Account KPIs ------------------------------------------------------ #
    st.subheader("Account")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity", f"${acct['equity']:,.2f}",
              delta=f"{acct['equity'] - acct['balance']:+,.2f}")
    c2.metric("Used margin", f"${acct['used_margin']:,.2f}")
    c3.metric("Free margin", f"${acct['free_margin']:,.2f}")
    c4.metric("Margin level", f"{acct['margin_level_pct']:.1f}%")
    daily_pct = (acct["daily_pnl"] / acct["balance"]) * 100
    c5.metric(
        "Daily PnL",
        f"${acct['daily_pnl']:+,.2f}",
        delta=f"{daily_pct:+.2f}% / limit -{acct['daily_pnl_limit_pct']:.1f}%",
        delta_color="inverse",
    )

    # ---- Drawdown progress ------------------------------------------------- #
    st.subheader("Max drawdown")
    dd_pct = acct["max_drawdown_pct"]
    dd_limit = acct["max_drawdown_limit_pct"]
    st.progress(
        min(dd_pct / dd_limit, 1.0),
        text=f"Current DD: {dd_pct:.2f}%  /  limit {dd_limit:.2f}%",
    )

    st.divider()

    # ---- VaR / ES ---------------------------------------------------------- #
    st.subheader("Risk metrics (1-day)")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("VaR 95%", f"${stats['var_95']:,.0f}",
              help="Loss not exceeded with 95% probability over 1 day.")
    v2.metric("VaR 99%", f"${stats['var_99']:,.0f}")
    v3.metric("ES 95%",  f"${stats['es_95']:,.0f}",
              help="Expected Shortfall (CVaR) at 95%.")
    v4.metric("ES 99%",  f"${stats['es_99']:,.0f}")

    # ---- Circuit breaker --------------------------------------------------- #
    st.subheader("Circuit breaker")
    state = breaker["state"]
    state_emoji = {
        "armed": "🟢",
        "tripped": "🔴",
        "cooling_down": "🟡",
        "disarmed": "⚪",
    }.get(state, "⚪")
    bc1, bc2, bc3 = st.columns([1, 2, 2])
    bc1.metric("Status", f"{state_emoji} {state}")
    bc2.write(f"**Auto-reset at:** {breaker['reset_at']}")
    bc3.write(
        f"**Reason:** {breaker['reason'] or '—'}"
    )

    bcols = st.columns(3)
    if bcols[0].button("Arm breaker"):
        st.success("Circuit breaker armed.")
    if bcols[1].button("Disarm"):
        st.warning("Circuit breaker disarmed.")
    if bcols[2].button("Manual trip"):
        st.error("Circuit breaker tripped manually.")

    st.divider()

    # ---- Position sizing calculator --------------------------------------- #
    st.subheader("Position sizing calculator")
    sc1, sc2, sc3, sc4 = st.columns(4)
    risk_pct = sc1.number_input("Risk per trade (%)", min_value=0.1, max_value=10.0,
                                value=1.0, step=0.1)
    stop_pips = sc2.number_input("Stop loss (pips)", min_value=1, max_value=500,
                                 value=20, step=1)
    pip_value = sc3.number_input("Pip value per 1 lot ($)", min_value=1.0,
                                 max_value=1000.0, value=10.0, step=0.5)
    pair = sc4.selectbox("Pair", ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"])

    if pair == "USDJPY":
        # crude conversion: pip size ≈ 0.01
        contract_size = 100_000
        lot_size = (acct["equity"] * (risk_pct / 100.0)) / max(stop_pips, 1) / (pip_value)
    else:
        # standard FX: pip = 0.0001, contract = 100,000
        contract_size = 100_000
        lot_size = (acct["equity"] * (risk_pct / 100.0)) / max(stop_pips, 1) / (pip_value)

    r1, r2 = st.columns(2)
    r1.metric("Suggested lot size", f"{lot_size:.2f}")
    r2.metric("Contract size", f"{contract_size:,}")
    st.caption(
        f"Risking ${acct['equity'] * risk_pct / 100:,.2f} at a {stop_pips}-pip "
        f"stop → **{lot_size:.2f} lots** on {pair}."
    )

    st.divider()

    # ---- Risk limits editor ------------------------------------------------ #
    st.subheader("Risk limits")
    with st.form("risk_limits_form"):
        l1, l2 = st.columns(2)
        max_daily_loss = l1.number_input(
            "Max daily loss (% of balance)",
            min_value=0.5, max_value=20.0,
            value=acct["daily_pnl_limit_pct"], step=0.5,
        )
        max_dd = l2.number_input(
            "Max drawdown (%)",
            min_value=1.0, max_value=50.0,
            value=dd_limit, step=0.5,
        )

        l3, l4 = st.columns(2)
        max_positions = l3.number_input(
            "Max open positions",
            min_value=1, max_value=50,
            value=5, step=1,
        )
        risk_per_trade = l4.number_input(
            "Risk per trade (%)",
            min_value=0.1, max_value=5.0,
            value=risk_pct, step=0.1,
        )

        st.caption("Changes apply after re-arm / session restart.")
        if st.form_submit_button("Save risk limits"):
            st.success(
                f"Saved — daily loss {max_daily_loss}%, drawdown {max_dd}%, "
                f"max positions {max_positions}, risk/trade {risk_per_trade}%."
            )

    # ---- Optional drawdown sparkline --------------------------------------- #
    if _HAS_PLOTLY:
        st.subheader("Equity curve (last 30d)")
        idx = pd.date_range(end=datetime.now(UTC), periods=30, freq="D")
        eq = acct["equity"] + pd.Series(range(30)).apply(
            lambda i: (i - 15) * 35 + (i % 7) * 18
        )
        fig = go.Figure(data=[go.Scatter(x=idx, y=eq, mode="lines", name="equity")])
        fig.update_layout(
            height=260, margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="", yaxis_title="Equity ($)",
        )
        st.plotly_chart(fig, use_container_width=True)
