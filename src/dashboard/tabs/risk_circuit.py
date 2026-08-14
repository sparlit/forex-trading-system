"""
Risk Circuit tab — Circuit breakers, VaR boundaries, and stop protection models.

Vibrant deep-red/orange theme. Four sections:
    (a) Risk gauges (Equity at Risk, Daily PnL, Margin Level, Max Drawdown).
    (b) VaR analysis table.
    (c) Circuit breaker status table.
    (d) Stop protection models table.

Synthetic data fallback.
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
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False

_THEME = {
    "bg": "#0e1117",
    "panel": "#1a080c",
    "panel2": "#12070b",
    "text": "#ffe4e6",
    "muted": "#fca5a5",
    "primary": "#b91c1c",        # deep red
    "secondary": "#dc2626",
    "accent": "#fbbf24",
    "warn": "#f59e0b",
    "danger": "#ef4444",
    "ok": "#34d399",
}


def _risk_gauges() -> dict[str, float]:
    return {
        "equity_at_risk_pct": random.uniform(0.5, 3.2),
        "daily_pnl_pct": random.uniform(-2.5, 2.8),
        "margin_level_pct": random.uniform(45, 120),
        "max_drawdown_pct": random.uniform(5, 22),
    }


def _var_analysis() -> pd.DataFrame:
    rows = [
        {"var_95_1d": 42_000, "var_99_1d": 68_000, "expected_shortfall_95": 55_000, "expected_shortfall_99": 80_000, "var_historical": 48_500, "var_montecarlo": 51_200, "currency": "USD"},
        {"var_95_1d": 37_500, "var_99_1d": 60_300, "expected_shortfall_95": 49_800, "expected_shortfall_99": 72_400, "var_historical": 42_100, "var_montecarlo": 45_900, "currency": "EUR"},
    ]
    return pd.DataFrame(rows)


def _circuit_breakers() -> pd.DataFrame:
    rows = []
    names = ["EquityATR", "DailyPnL", "MarginLevel", "Drawdown"]
    for name in names:
        threshold = random.uniform(1.0, 5.0)
        current = threshold * random.uniform(0.5, 1.3)
        status = "green" if current < threshold else "amber" if current < threshold * 1.2 else "red"
        action = random.choice(["take_profit", "stop", "trailing", "emergency"])
        rows.append({
            "breaker_name": name,
            "threshold": f"{threshold:.2f}%",
            "current_value": f"{current:.2f}%",
            "status": status,
            "action": action,
        })
    return pd.DataFrame(rows)


def _stop_protection_models() -> pd.DataFrame:
    rows = []
    positions = ["Long EURUSD", "Short GBPUSD", "Long XAUUSD", "Short BTCUSD"]
    for pos in positions:
        price = random.uniform(0.8, 1.5)
        sl = price - random.uniform(0.02, 0.07)
        tp = price + random.uniform(0.03, 0.09)
        sl_pips = int((price - sl) * 10000)
        sl_pct = (price - sl) / price * 100
        trailing = random.choice([True, False])
        atr_sl = sl - random.uniform(0.001, 0.005) if trailing else None
        rows.append({
            "position": pos,
            "current_price": round(price, 5),
            "sl_price": round(sl, 5),
            "tp_price": round(tp, 5),
            "sl_distance_pips": sl_pips,
            "sl_distance_pct": round(sl_pct, 3),
            "trailing_active": trailing,
            "atr_based_sl": round(atr_sl, 5) if atr_sl else "N/A",
        })
    return pd.DataFrame(rows)


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .risk-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .risk-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .gauge {{
            font-size: 24px; font-weight: 600; color: {_THEME['primary']};
        }}
        .status-green {{ color: {_THEME['ok']}; font-weight: 600; }}
        .status-amber {{ color: {_THEME['warn']}; font-weight: 600; }}
        .status-red {{ color: {_THEME['danger']}; font-weight: 600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_span(status: str) -> str:
    mapping = {"green": "status-green", "amber": "status-amber", "red": "status-red"}
    cls = mapping.get(status, "status-amber")
    return f'<span class="{cls}">{status.title()}</span>'


def render_risk_circuit_tab() -> None:
    """Render the Risk Circuit tab."""
    _inject_css()
    st.markdown(
        f"""
        <div class="risk-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">💨 Risk Circuit — VaR, Breakers & Stops</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Real-time risk gauges, VaR analysis, circuit breaker status, and stop‑loss models.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- (a) Gauges ----
    st.markdown("### (a) Risk Gauges")
    gauges = _risk_gauges()
    cols = st.columns(4)
    def _gauge(label, value, fmt="{:.2f}%"):
        st.markdown(f"<div class='gauge'>{label}<br>{fmt.format(value)}</div>", unsafe_allow_html=True)
    _gauge("Equity @ Risk", gauges["equity_at_risk_pct"], "{:.2f}%")
    _gauge("Daily PnL", gauges["daily_pnl_pct"], "{:.2f}%")
    _gauge("Margin Level", gauges["margin_level_pct"], "{:.1f}%")
    _gauge("Max Drawdown", gauges["max_drawdown_pct"], "{:.2f}%")

    st.divider()

    # ---- (b) VaR Analysis ----
    st.markdown("### (b) VaR Analysis")
    var_df = _var_analysis()
    st.dataframe(
        var_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "var_95_1d": st.column_config.NumberColumn("VaR 95% (1d)", format="$%,.0f"),
            "var_99_1d": st.column_config.NumberColumn("VaR 99% (1d)", format="$%,.0f"),
            "expected_shortfall_95": st.column_config.NumberColumn("ES 95%", format="$%,.0f"),
            "expected_shortfall_99": st.column_config.NumberColumn("ES 99%", format="$%,.0f"),
            "var_historical": st.column_config.NumberColumn("Historical VaR", format="$%,.0f"),
            "var_montecarlo": st.column_config.NumberColumn("Monte Carlo VaR", format="$%,.0f"),
            "currency": st.column_config.TextColumn("CCY"),
        },
    )

    st.divider()

    # ---- (c) Circuit Breaker Status ----
    st.markdown("### (c) Circuit Breaker Status")
    cb = _circuit_breakers()
    cb_display = cb.copy()
    cb_display["status_span"] = cb_display["status"].apply(_status_span)
    st.dataframe(
        cb_display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "status": None,
            "status_span": st.column_config.TextColumn("Status"),
            "breaker_name": st.column_config.TextColumn("Breaker", width="medium"),
            "threshold": st.column_config.TextColumn("Threshold"),
            "current_value": st.column_config.TextColumn("Current"),
            "action": st.column_config.TextColumn("Action", width="small"),
        },
    )

    st.divider()

    # ---- (d) Stop Protection Models ----
    st.markdown("### (d) Stop Protection Models")
    sp = _stop_protection_models()
    st.dataframe(
        sp,
        hide_index=True,
        use_container_width=True,
        column_config={
            "position": st.column_config.TextColumn("Position", width="medium"),
            "current_price": st.column_config.NumberColumn("Price", format="%.5f"),
            "sl_price": st.column_config.NumberColumn("SL", format="%.5f"),
            "tp_price": st.column_config.NumberColumn("TP", format="%.5f"),
            "sl_distance_pips": st.column_config.NumberColumn("SL Pips", format="%d"),
            "sl_distance_pct": st.column_config.NumberColumn("SL %", format="%.3f%%"),
            "trailing_active": st.column_config.CheckboxColumn("Trailing"),
            "atr_based_sl": st.column_config.TextColumn("ATR‑SL"),
        },
    )

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • Synthetic risk data."
    )
