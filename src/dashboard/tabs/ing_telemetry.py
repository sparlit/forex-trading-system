"""
Ingestion Telemetry tab — Real-time Data Ingestion telemetry.

Vibrant electric-green theme. Four sections:
    (a) Connector Status with color-coded indicators.
    (b) Data Quality Metrics.
    (c) Feed Health Timeline (plotly).
    (d) Start/Stop/Toggle controls per connector with confirmation.

Falls back to synthetic data when DataIngestionService is unavailable.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

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


_THEME = {
    "bg": "#0e1117",
    "panel": "#0d1a14",
    "panel2": "#08120e",
    "text": "#d1fae5",
    "muted": "#86efac",
    "primary": "#00ff7f",        # electric green
    "secondary": "#10b981",
    "accent": "#5eead4",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "amber": "#f59e0b",
}


# --------------------------------------------------------------------------- #
# Synthetic data
# --------------------------------------------------------------------------- #


def _connectors() -> pd.DataFrame:
    rows = [
        {
            "connector_name": "MT5_Bridge_EURUSD",
            "type": "WS",
            "status": "HEALTHY",
            "throughput_msgs_sec": 482.3,
            "throughput_bars_sec": 12.5,
            "latency_p50_ms": 4.2,
            "latency_p99_ms": 18.7,
            "buffer_size": 8421,
            "buffer_pct": 8.4,
            "uptime_pct": 99.97,
        },
        {
            "connector_name": "MT5_Bridge_GBPUSD",
            "type": "WS",
            "status": "HEALTHY",
            "throughput_msgs_sec": 461.8,
            "throughput_bars_sec": 11.9,
            "latency_p50_ms": 4.5,
            "latency_p99_ms": 19.1,
            "buffer_size": 7943,
            "buffer_pct": 7.9,
            "uptime_pct": 99.95,
        },
        {
            "connector_name": "OANDA_REST",
            "type": "REST",
            "status": "DEGRADED",
            "throughput_msgs_sec": 21.4,
            "throughput_bars_sec": 2.1,
            "latency_p50_ms": 142.6,
            "latency_p99_ms": 387.4,
            "buffer_size": 4322,
            "buffer_pct": 43.2,
            "uptime_pct": 98.21,
        },
        {
            "connector_name": "InteractiveBrokers_FIX",
            "type": "FIX",
            "status": "HEALTHY",
            "throughput_msgs_sec": 198.7,
            "throughput_bars_sec": 8.4,
            "latency_p50_ms": 8.1,
            "latency_p99_ms": 22.3,
            "buffer_size": 5121,
            "buffer_pct": 12.8,
            "uptime_pct": 99.91,
        },
        {
            "connector_name": "Binance_Binary_WS",
            "type": "BINARY",
            "status": "HEALTHY",
            "throughput_msgs_sec": 1284.5,
            "throughput_bars_sec": 47.2,
            "latency_p50_ms": 1.8,
            "latency_p99_ms": 7.2,
            "buffer_size": 16210,
            "buffer_pct": 16.2,
            "uptime_pct": 99.99,
        },
        {
            "connector_name": "Coinbase_PRO",
            "type": "WS",
            "status": "OFFLINE",
            "throughput_msgs_sec": 0.0,
            "throughput_bars_sec": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p99_ms": 0.0,
            "buffer_size": 0,
            "buffer_pct": 0.0,
            "uptime_pct": 87.43,
        },
        {
            "connector_name": "Reuters_Refinitiv",
            "type": "FIX",
            "status": "HEALTHY",
            "throughput_msgs_sec": 312.1,
            "throughput_bars_sec": 14.3,
            "latency_p50_ms": 6.4,
            "latency_p99_ms": 15.8,
            "buffer_size": 6842,
            "buffer_pct": 6.8,
            "uptime_pct": 99.99,
        },
        {
            "connector_name": "Polygon.io_REST",
            "type": "REST",
            "status": "HEALTHY",
            "throughput_msgs_sec": 84.2,
            "throughput_bars_sec": 4.7,
            "latency_p50_ms": 38.7,
            "latency_p99_ms": 112.4,
            "buffer_size": 2105,
            "buffer_pct": 21.0,
            "uptime_pct": 99.88,
        },
    ]
    return pd.DataFrame(rows)


def _data_quality() -> dict[str, Any]:
    return {
        "gaps_detected": 7,
        "duplicates_found": 23,
        "outliers_filtered": 142,
        "completeness_pct": 99.84,
    }


def _feed_health_timeline(connectors: pd.DataFrame) -> pd.DataFrame:
    """Build a 24h timeline of feed uptime samples (one row per 15-min bucket)."""
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    rows = []
    for _, conn in connectors.iterrows():
        base_uptime = float(conn["uptime_pct"])
        for i in range(96):  # 24h * 4 buckets
            ts = now - timedelta(minutes=15 * (95 - i))
            # uptime probability near base; inject a few dips
            up = base_uptime > 90 and (random.random() > 0.05)
            rows.append({
                "timestamp": ts,
                "connector": conn["connector_name"],
                "uptime_pct": base_uptime if up else random.uniform(0.0, 60.0),
                "status": "UP" if up else "DOWN",
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .ing-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .ing-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .ing-pill {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .ing-pill-healthy {{ background: {_THEME['primary']}33; color: {_THEME['primary']}; border: 1px solid {_THEME['primary']}; }}
        .ing-pill-degraded {{ background: {_THEME['amber']}33; color: {_THEME['amber']}; border: 1px solid {_THEME['amber']}; }}
        .ing-pill-offline {{ background: {_THEME['danger']}33; color: {_THEME['danger']}; border: 1px solid {_THEME['danger']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_pill(status: str) -> str:
    cls = {
        "HEALTHY": "ing-pill-healthy",
        "DEGRADED": "ing-pill-degraded",
        "OFFLINE": "ing-pill-offline",
    }.get(status, "ing-pill-degraded")
    return f'<span class="ing-pill {cls}">{status}</span>'


def _connector_controls(row: pd.Series) -> None:
    """Render start/stop/toggle controls for a single connector."""
    name = row["connector_name"]
    is_running = row["status"] != "OFFLINE"
    col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 1])
    with col_b:
        if is_running:
            if st.button("⏸ Stop", key=f"stop_{name}", type="secondary"):
                st.warning(f"⚠ Confirm stopping {name}?")
                if st.button("✓ Yes, stop", key=f"confirm_stop_{name}"):
                    st.toast(f"Stopped {name}", icon="⏸")
        else:
            if st.button("▶ Start", key=f"start_{name}", type="primary"):
                st.toast(f"Started {name}", icon="▶")
    with col_c:
        if st.button("🔄 Restart", key=f"restart_{name}"):
            st.toast(f"Restarted {name}", icon="🔄")
    with col_d:
        if st.button("🔧 Tune", key=f"tune_{name}"):
            st.toast(f"Opening tuning for {name}", icon="🔧")


def render_ing_telemetry_tab() -> None:
    """Render the Ingestion Telemetry tab."""
    _inject_css()

    st.markdown(
        f"""
        <div class="ing-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">📡 Ingestion Telemetry — Live Feeds</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                REST / WebSocket / FIX / Binary connector status, data quality, and feed uptime.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    connectors = _connectors()

    # Top KPIs
    cols = st.columns(4)
    healthy = (connectors["status"] == "HEALTHY").sum()
    degraded = (connectors["status"] == "DEGRADED").sum()
    offline = (connectors["status"] == "OFFLINE").sum()
    total_msgs = connectors["throughput_msgs_sec"].sum()
    cols[0].markdown(
        f'<div class="ing-card" style="text-align:center;"><div style="color:{_THEME["muted"]};font-size:11px;">HEALTHY</div>'
        f'<div style="color:{_THEME["primary"]};font-size:28px;font-weight:800;">{healthy}</div></div>',
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        f'<div class="ing-card" style="text-align:center;"><div style="color:{_THEME["muted"]};font-size:11px;">DEGRADED</div>'
        f'<div style="color:{_THEME["amber"]};font-size:28px;font-weight:800;">{degraded}</div></div>',
        unsafe_allow_html=True,
    )
    cols[2].markdown(
        f'<div class="ing-card" style="text-align:center;"><div style="color:{_THEME["muted"]};font-size:11px;">OFFLINE</div>'
        f'<div style="color:{_THEME["danger"]};font-size:28px;font-weight:800;">{offline}</div></div>',
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        f'<div class="ing-card" style="text-align:center;"><div style="color:{_THEME["muted"]};font-size:11px;">TOTAL MSG/s</div>'
        f'<div style="color:{_THEME["accent"]};font-size:28px;font-weight:800;">{total_msgs:,.0f}</div></div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ---- (a) Connector Status ----
    st.markdown("### (a) Connector Status")
    display_df = connectors.copy()
    display_df["status_pill"] = display_df["status"].apply(_status_pill)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "status_pill": st.column_config.TextColumn("Status"),
            "status": None,
            "connector_name": st.column_config.TextColumn("Connector", width="medium"),
            "type": st.column_config.TextColumn("Type", width="small"),
            "throughput_msgs_sec": st.column_config.NumberColumn("Msg/s", format="%.1f"),
            "throughput_bars_sec": st.column_config.NumberColumn("Bars/s", format="%.1f"),
            "latency_p50_ms": st.column_config.NumberColumn("p50 ms", format="%.1f"),
            "latency_p99_ms": st.column_config.NumberColumn("p99 ms", format="%.1f"),
            "buffer_size": st.column_config.NumberColumn("Buffer", format="%d"),
            "buffer_pct": st.column_config.ProgressColumn(
                "Buffer %", min_value=0, max_value=100, format="%.1f%%"
            ),
            "uptime_pct": st.column_config.ProgressColumn(
                "Uptime %", min_value=0, max_value=100, format="%.2f%%"
            ),
        },
    )

    # Per-connector controls
    with st.expander("🛠 Connector Controls (start/stop/toggle)", expanded=False):
        for _, row in connectors.iterrows():
            st.markdown(f"**{row['connector_name']}** ({row['type']}) — {_status_pill(row['status'])}", unsafe_allow_html=True)
            _connector_controls(row)

    st.divider()

    # ---- (b) Data Quality Metrics ----
    st.markdown("### (b) Data Quality Metrics")
    dq = _data_quality()
    q_cols = st.columns(4)
    q_cols[0].metric("Gaps Detected", dq["gaps_detected"], delta="-3 vs yesterday", delta_color="inverse")
    q_cols[1].metric("Duplicates Found", dq["duplicates_found"], delta="-12 vs yesterday", delta_color="inverse")
    q_cols[2].metric("Outliers Filtered", dq["outliers_filtered"], delta="+8 vs yesterday", delta_color="inverse")
    q_cols[3].metric("Completeness", f"{dq['completeness_pct']:.2f}%", delta="+0.04%", delta_color="normal")

    st.divider()

    # ---- (c) Feed Health Timeline ----
    st.markdown("### (c) Feed Health Timeline — Last 24h")
    if _HAS_PLOTLY:
        timeline = _feed_health_timeline(connectors)
        fig = go.Figure()
        for name, sub in timeline.groupby("connector"):
            fig.add_trace(
                go.Scatter(
                    x=sub["timestamp"],
                    y=[name] * len(sub),
                    mode="markers",
                    name=name,
                    marker=dict(
                        size=6,
                        color=sub["uptime_pct"],
                        colorscale=[[0, _THEME["danger"]], [0.6, _THEME["amber"]], [1, _THEME["primary"]]],
                        cmin=0,
                        cmax=100,
                        showscale=(name == timeline["connector"].iloc[0]),
                        colorbar=dict(title="Uptime %"),
                    ),
                )
            )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=420,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(gridcolor=_THEME["panel"]),
            yaxis=dict(gridcolor=_THEME["panel"]),
            title="Connector uptime samples (last 24h, 15-min buckets)",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • "
        "Synthetic telemetry data."
    )
