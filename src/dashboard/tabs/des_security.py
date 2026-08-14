"""
DES Security tab — Detailed Security specifications & contract parameters.

Vibrant slate-gray/cyan theme. Three sections:
    (a) Security Specs table — instrument metadata & margin/leverage.
    (b) Greeks calculator — Black-Scholes for options (delta, gamma, theta, vega, rho).
    (c) Contract parameters reference table for futures.

Falls back to synthetic data so the page renders even when the live
InstrumentRegistry / OptionsService is unavailable.
"""

from __future__ import annotations

import math
import os
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


# --------------------------------------------------------------------------- #
# Theme — slate-gray + cyan
# --------------------------------------------------------------------------- #

_THEME = {
    "bg": "#0e1117",
    "panel": "#1a2030",
    "panel2": "#11182a",
    "text": "#e6f7ff",
    "muted": "#8aa0b4",
    "primary": "#22d3ee",        # cyan
    "secondary": "#06b6d4",
    "accent": "#67e8f9",
    "warn": "#fbbf24",
    "danger": "#f87171",
    "ok": "#34d399",
}


# --------------------------------------------------------------------------- #
# Black-Scholes Greeks (pure-python, no scipy required)
# --------------------------------------------------------------------------- #


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict[str, float]:
    """Return price + Greeks (delta, gamma, theta, vega, rho).

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiry in years.
        r: Risk-free rate (e.g. 0.05 = 5%).
        sigma: Implied volatility (e.g. 0.20 = 20%).
        option_type: 'call' or 'put'.

    Returns:
        Dictionary with keys: price, delta, gamma, theta, vega, rho.
    """
    if T <= 0 or sigma <= 0:
        # At expiry
        if option_type == "call":
            price = max(S - K, 0.0)
        else:
            price = max(K - S, 0.0)
        return {
            "price": price,
            "delta": 1.0 if (option_type == "call" and S > K) else -1.0 if (option_type == "put" and S < K) else 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
        }

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    if option_type == "call":
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta = (
            -(S * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
        ) / 365.0
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2) / 100.0
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = -_norm_cdf(-d1)
        theta = (
            -(S * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
            + r * K * math.exp(-r * T) * _norm_cdf(-d2)
        ) / 365.0
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100.0

    gamma = _norm_pdf(d1) / (S * sigma * sqrt_T)
    vega = S * _norm_pdf(d1) * sqrt_T / 100.0

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "rho": rho,
    }


# --------------------------------------------------------------------------- #
# Synthetic data
# --------------------------------------------------------------------------- #


def _security_specs() -> pd.DataFrame:
    rows = [
        {
            "instrument": "EURUSD",
            "exchange": "FX_IDC",
            "contract_size": 100000,
            "tick_size": 0.00001,
            "tick_value": 1.00,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "margin_pct": 1.0,
            "leverage": "1:100",
            "trading_hours": "Sun 22:00 - Fri 22:00",
            "settlement_type": "Spot (T+2)",
        },
        {
            "instrument": "GBPUSD",
            "exchange": "FX_IDC",
            "contract_size": 100000,
            "tick_size": 0.00001,
            "tick_value": 1.00,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "margin_pct": 1.0,
            "leverage": "1:100",
            "trading_hours": "Sun 22:00 - Fri 22:00",
            "settlement_type": "Spot (T+2)",
        },
        {
            "instrument": "USDJPY",
            "exchange": "FX_IDC",
            "contract_size": 100000,
            "tick_size": 0.001,
            "tick_value": 0.67,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "margin_pct": 1.0,
            "leverage": "1:100",
            "trading_hours": "Sun 22:00 - Fri 22:00",
            "settlement_type": "Spot (T+2)",
        },
        {
            "instrument": "XAUUSD",
            "exchange": "COMEX",
            "contract_size": 100,
            "tick_size": 0.01,
            "tick_value": 1.00,
            "min_lot": 0.01,
            "max_lot": 50.0,
            "margin_pct": 2.0,
            "leverage": "1:50",
            "trading_hours": "Sun 18:00 - Fri 17:00",
            "settlement_type": "Physical",
        },
        {
            "instrument": "WTI Crude",
            "exchange": "NYMEX",
            "contract_size": 1000,
            "tick_size": 0.01,
            "tick_value": 10.00,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "margin_pct": 5.0,
            "leverage": "1:20",
            "trading_hours": "Sun 18:00 - Fri 17:00",
            "settlement_type": "Physical",
        },
        {
            "instrument": "BTCUSD",
            "exchange": "CME",
            "contract_size": 1,
            "tick_size": 5.0,
            "tick_value": 5.00,
            "min_lot": 0.001,
            "max_lot": 100.0,
            "margin_pct": 10.0,
            "leverage": "1:10",
            "trading_hours": "24/7",
            "settlement_type": "Cash",
        },
        {
            "instrument": "SPX500",
            "exchange": "CBOE",
            "contract_size": 50,
            "tick_size": 0.01,
            "tick_value": 0.50,
            "min_lot": 0.1,
            "max_lot": 50.0,
            "margin_pct": 5.0,
            "leverage": "1:20",
            "trading_hours": "Mon-Fri 09:30-16:00 ET",
            "settlement_type": "Cash",
        },
    ]
    return pd.DataFrame(rows)


def _contract_params() -> pd.DataFrame:
    rows = [
        {
            "contract": "ES (E-mini S&P 500)",
            "expiry": "Mar 2026",
            "last_trade_date": "2026-03-20",
            "first_notice": "2026-03-13",
            "settlement_method": "Cash",
            "tick_value": 12.50,
        },
        {
            "contract": "NQ (E-mini Nasdaq-100)",
            "expiry": "Mar 2026",
            "last_trade_date": "2026-03-20",
            "first_notice": "2026-03-13",
            "settlement_method": "Cash",
            "tick_value": 5.00,
        },
        {
            "contract": "CL (WTI Crude)",
            "expiry": "Apr 2026",
            "last_trade_date": "2026-03-20",
            "first_notice": "2026-03-13",
            "settlement_method": "Physical",
            "tick_value": 10.00,
        },
        {
            "contract": "GC (Gold)",
            "expiry": "Apr 2026",
            "last_trade_date": "2026-03-27",
            "first_notice": "2026-03-25",
            "settlement_method": "Physical",
            "tick_value": 10.00,
        },
        {
            "contract": "SI (Silver)",
            "expiry": "Apr 2026",
            "last_trade_date": "2026-03-27",
            "first_notice": "2026-03-25",
            "settlement_method": "Physical",
            "tick_value": 25.00,
        },
        {
            "contract": "ZB (30Y T-Bond)",
            "expiry": "Mar 2026",
            "last_trade_date": "2026-03-20",
            "first_notice": "2026-03-13",
            "settlement_method": "Physical",
            "tick_value": 31.25,
        },
        {
            "contract": "6E (Euro FX)",
            "expiry": "Mar 2026",
            "last_trade_date": "2026-03-16",
            "first_notice": "2026-03-13",
            "settlement_method": "Physical",
            "tick_value": 12.50,
        },
        {
            "contract": "BTC Futures",
            "expiry": "Mar 2026",
            "last_trade_date": "2026-03-27",
            "first_notice": "n/a",
            "settlement_method": "Cash",
            "tick_value": 25.00,
        },
    ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .des-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}33;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 12px { _THEME['primary']}11;
        }}
        .des-header {{
            background: linear-gradient(90deg, {_THEME['primary']}22, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .des-metric {{
            background: {_THEME['panel']};
            border: 1px solid {_THEME['primary']}44;
            padding: 10px 14px;
            border-radius: 8px;
            text-align: center;
        }}
        .des-metric-label {{ color: {_THEME['muted']}; font-size: 11px; text-transform: uppercase; }}
        .des-metric-value {{ color: {_THEME['primary']}; font-size: 18px; font-weight: 700; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_des_security_tab() -> None:
    """Render the DES Security tab."""
    _inject_css()

    st.markdown(
        f"""
        <div class="des-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">🔐 DES Security — Instrument Specifications & Contract Reference</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Detailed security specifications, options Greeks calculator, and futures contract reference.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- (a) Security Specs ----
    st.markdown("### (a) Security Specifications")
    specs = _security_specs()
    st.dataframe(
        specs,
        use_container_width=True,
        hide_index=True,
        column_config={
            "instrument": st.column_config.TextColumn("Instrument", width="medium"),
            "exchange": st.column_config.TextColumn("Exchange", width="small"),
            "contract_size": st.column_config.NumberColumn("Contract Size", format="%d"),
            "tick_size": st.column_config.NumberColumn("Tick Size", format="%.5f"),
            "tick_value": st.column_config.NumberColumn("Tick Value ($)", format="%.2f"),
            "min_lot": st.column_config.NumberColumn("Min Lot", format="%.3f"),
            "max_lot": st.column_config.NumberColumn("Max Lot", format="%.1f"),
            "margin_pct": st.column_config.NumberColumn("Margin %", format="%.1f%%"),
            "leverage": st.column_config.TextColumn("Leverage", width="small"),
            "trading_hours": st.column_config.TextColumn("Trading Hours", width="medium"),
            "settlement_type": st.column_config.TextColumn("Settlement", width="medium"),
        },
    )

    st.divider()

    # ---- (b) Greeks Calculator ----
    st.markdown("### (b) Options Greeks Calculator (Black-Scholes)")

    col1, col2, col3 = st.columns(3)
    with col1:
        spot = st.number_input("Spot Price (S)", min_value=0.01, value=100.0, step=1.0, key="des_spot")
        strike = st.number_input("Strike Price (K)", min_value=0.01, value=100.0, step=1.0, key="des_strike")
    with col2:
        days_to_expiry = st.number_input(
            "Days to Expiry", min_value=1, max_value=730, value=30, step=1, key="des_days"
        )
        vol_pct = st.number_input(
            "Implied Vol %", min_value=1.0, max_value=500.0, value=25.0, step=1.0, key="des_vol"
        )
    with col3:
        rate_pct = st.number_input(
            "Risk-Free Rate %", min_value=0.0, max_value=20.0, value=4.5, step=0.1, key="des_rate"
        )
        option_type = st.selectbox("Option Type", ["call", "put"], key="des_opt_type")

    T = max(days_to_expiry, 1) / 365.0
    sigma = vol_pct / 100.0
    r = rate_pct / 100.0
    greeks = black_scholes_greeks(spot, strike, T, r, sigma, option_type)

    g_cols = st.columns(6)
    greek_items = [
        ("Price", f"${greeks['price']:.4f}"),
        ("Delta", f"{greeks['delta']:.4f}"),
        ("Gamma", f"{greeks['gamma']:.5f}"),
        ("Theta", f"{greeks['theta']:.4f}"),
        ("Vega", f"{greeks['vega']:.4f}"),
        ("Rho", f"{greeks['rho']:.4f}"),
    ]
    for col, (label, value) in zip(g_cols, greek_items, strict=False):
        with col:
            st.markdown(
                f"""
                <div class="des-metric">
                    <div class="des-metric-label">{label}</div>
                    <div class="des-metric-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Greeks bar chart
    if _HAS_PLOTLY:
        fig = go.Figure()
        keys = ["delta", "gamma", "theta", "vega", "rho"]
        values = [greeks[k] for k in keys]
        colors = [_THEME["primary"], _THEME["accent"], _THEME["warn"], _THEME["ok"], _THEME["secondary"]]
        fig.add_trace(
            go.Bar(
                x=[k.upper() for k in keys],
                y=values,
                marker_color=colors,
                text=[f"{v:.4f}" for v in values],
                textposition="outside",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            title="Options Greeks",
            height=320,
            margin=dict(l=20, r=20, t=40, b=20),
            yaxis=dict(gridcolor=_THEME["panel"]),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- (c) Contract Parameters Reference ----
    st.markdown("### (c) Futures Contract Parameters Reference")
    contracts = _contract_params()
    st.dataframe(
        contracts,
        use_container_width=True,
        hide_index=True,
        column_config={
            "contract": st.column_config.TextColumn("Contract", width="medium"),
            "expiry": st.column_config.TextColumn("Expiry", width="small"),
            "last_trade_date": st.column_config.TextColumn("Last Trade Date", width="medium"),
            "first_notice": st.column_config.TextColumn("First Notice", width="medium"),
            "settlement_method": st.column_config.TextColumn("Settlement", width="small"),
            "tick_value": st.column_config.NumberColumn("Tick Value ($)", format="%.2f"),
        },
    )

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • "
        "All values synthetic and for display only."
    )
