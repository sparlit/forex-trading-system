'''Overnight safety tab – exposure, gap risk, weekend checks, margin simulation, auto-close, swap rates, session gap.'''

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

def _max_overnight_exposure() -> float:
    # Placeholder static value
    return 25000.0

def _gap_risk_table() -> pd.DataFrame:
    data = [
        {"symbol": "EURUSD", "avg_gap_pips": 5.2, "max_gap_pips": 20, "risk_level": "low"},
        {"symbol": "GBPJPY", "avg_gap_pips": 12.8, "max_gap_pips": 45, "risk_level": "high"},
    ]
    return pd.DataFrame(data)

def _weekend_positions() -> pd.DataFrame:
    data = [
        {"symbol": "AUDUSD", "size": 100000, "direction": "long"},
        {"symbol": "USDCAD", "size": 50000, "direction": "short"},
    ]
    return pd.DataFrame(data)

def _margin_call_simulation(equity: float, projected: float) -> dict[str, Any]:
    return {"current_equity": equity, "projected_equity": projected, "margin_call": projected < 0.2 * equity}

def _swap_rates() -> pd.DataFrame:
    data = [
        {"symbol": "EURUSD", "swap_long": -0.2, "swap_short": 0.3},
        {"symbol": "GBPUSD", "swap_long": -0.1, "swap_short": 0.25},
    ]
    return pd.DataFrame(data)


def _rollover_cost_preview() -> pd.DataFrame:
    """Per-night rollover cost = swap × position size × nights held."""
    nights = st.session_state.get("ov_nights", 1)
    st.session_state["ov_nights"] = nights
    rows = [
        {"symbol": "EURUSD", "lots": 0.50, "swap_pts": -0.20, "nights": nights,
         "cost_usd": round(-0.20 * 0.50 * nights, 2)},
        {"symbol": "GBPUSD", "lots": 0.30, "swap_pts": -0.10, "nights": nights,
         "cost_usd": round(-0.10 * 0.30 * nights, 2)},
    ]
    return pd.DataFrame(rows)


def _session_gap() -> pd.DataFrame:
    """Real countdown to next illiquid-window transition."""
    from datetime import time as _time
    from datetime import timedelta as _td
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon ... 6=Sun
    # Next 22:00 UTC if currently before it on a weekday
    target = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now.time() >= _time(22, 0):
        target = target + _td(days=1)
    # If Friday and currently before 22:00 → weekend illiquidity starts
    label = "Daily illiquid window starts (22:00 UTC)"
    if weekday == 4 and now.time() < _time(22, 0):
        label = "Weekend illiquidity (Fri 22:00 UTC)"
    # If weekend → next liquidity resume is Monday 00:00 UTC
    if weekday >= 5:
        days_to_mon = (7 - weekday) % 7 or 7
        target = (now + _td(days=days_to_mon)).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "Liquidity resumes (Mon 00:00 UTC)"
    delta = target - now
    return pd.DataFrame([{
        "transition": label,
        "eta_hms": str(delta).split(".")[0],
        "now_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
    }])


def _illiquid_hours_check() -> pd.DataFrame:
    """Show which positions would still be open during the illiquid window."""
    illiquid = [
        ("EURUSD", "yes"), ("XAUUSD", "yes"), ("BTCUSD", "yes"),
    ]
    return pd.DataFrame(illiquid, columns=["symbol", "open_during_illiquid_hours"])

def render_overnight_tab() -> None:
    st.title("\u23F0 Overnight Safety")
    st.metric("Max Overnight Exposure", f"${_max_overnight_exposure():,.0f}")

    st.subheader("Gap Risk Assessment")
    st.dataframe(_gap_risk_table(), hide_index=True, use_container_width=True)

    st.subheader("Weekend Position Check")
    st.dataframe(_weekend_positions(), hide_index=True, use_container_width=True)

    st.subheader("Margin Call Simulation")
    equity = st.slider("Current Equity ($)", 0, 200000, 100000, step=1000)
    projected = st.slider("Projected Equity ($)", 0, 200000, 90000, step=1000)
    sim = _margin_call_simulation(equity, projected)
    st.metric("Current Equity", f"${sim['current_equity']:,}")
    st.metric("Projected Equity", f"${sim['projected_equity']:,}")
    st.metric("Margin Call?", "YES" if sim['margin_call'] else "NO")

    st.subheader("Auto-Close At Time")
    enabled = st.checkbox("Enable auto-close", value=False)
    if enabled:
        close_time = st.time_input("Close time", value=datetime.now().time())
        st.success(f"Auto-close scheduled at {close_time.isoformat()}")

    st.subheader("Rollover Swap Rates")
    st.dataframe(_swap_rates(), hide_index=True, use_container_width=True)

    st.subheader("Rollover Cost Preview")
    nights = st.slider("Nights held", 1, 14, 1, key="ov_nights_slider")
    st.session_state["ov_nights"] = nights
    df = _rollover_cost_preview()
    df["nights"] = nights
    st.dataframe(df, hide_index=True, use_container_width=True)

    st.subheader("Session Gap Countdown")
    st.dataframe(_session_gap(), hide_index=True, use_container_width=True)

    st.subheader("Positions Open During Illiquid Hours")
    st.dataframe(_illiquid_hours_check(), hide_index=True, use_container_width=True)
