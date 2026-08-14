"""
Monitoring Health tab — CPU, memory, process, ping, error trends.

Vibrant neon-green/teal theme. Four sections:
    (a) System health gauges.
    (b) Process status table.
    (c) Connection ping matrix.
    (d) Error rate and memory usage trends (plotly).

Synthetic fallback.
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

try:
    import plotly.graph_objects as go  # type: ignore
    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False

_THEME = {
    "bg": "#0e1117",
    "panel": "#0b1915",
    "panel2": "#081511",
    "text": "#d1fae5",
    "muted": "#86efac",
    "primary": "#00ff7f",        # neon green
    "secondary": "#0dd3ac",
    "accent": "#8ef9de",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "ok": "#34d399",
}


# --------------------------------------------------------------------------- #
# Synthetic data generators
# --------------------------------------------------------------------------- #


def _system_gauges() -> dict[str, float]:
    return {
        "cpu_pct": random.uniform(12, 87),
        "memory_pct": random.uniform(18, 92),
        "disk_pct": random.uniform(30, 95),
        "gpu_pct": random.uniform(0, 70),
    }


def _process_status() -> pd.DataFrame:
    names = ["streamlit", "engine", "data_ingest", "risk_service", "order_manager", "db_proxy"]
    rows = []
    for name in names:
        pid = random.randint(2000, 15000)
        cpu = round(random.uniform(0.5, 35.0), 1)
        mem = round(random.uniform(50, 1024), 1)
        threads = random.randint(2, 30)
        status = random.choice(["RUNNING", "IDLE", "CRASHED"])
        uptime = f"{random.randint(0, 5)}d {random.randint(0,23)}h {random.randint(0,59)}m"
        restart = random.randint(0, 3)
        rows.append({
            "process_name": name,
            "pid": pid,
            "cpu_pct": cpu,
            "memory_mb": mem,
            "threads": threads,
            "status": status,
            "uptime": uptime,
            "restart_count": restart,
        })
    return pd.DataFrame(rows)


def _ping_matrix() -> pd.DataFrame:
    targets = ["broker_api", "data_feed", "db_server", "risk_engine", "exchange_ws", "aws_s3"]
    rows = []
    for t in targets:
        ping = round(random.uniform(10, 350), 1)
        jitter = round(random.uniform(0.5, 30.0), 1)
        loss = round(random.uniform(0, 2.5), 1)
        status = "UP" if loss < 0.5 else "DEGRADED" if loss < 1.5 else "DOWN"
        last = (datetime.now(UTC) - timedelta(seconds=random.randint(0, 600))).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({
            "target": t,
            "ping_ms": ping,
            "jitter_ms": jitter,
            "packet_loss_pct": loss,
            "status": status,
            "last_check": last,
        })
    return pd.DataFrame(rows)


def _error_trend() -> pd.DataFrame:
    now = datetime.now(UTC)
    rows = []
    for i in range(24):
        ts = now - timedelta(hours=23 - i)
        errors = random.randint(0, 15)
        rows.append({"timestamp": ts, "error_count": errors})
    return pd.DataFrame(rows)


def _memory_usage_trend() -> pd.DataFrame:
    now = datetime.now(UTC)
    rows = []
    usage = 5000  # MB start
    for i in range(24):
        ts = now - timedelta(hours=23 - i)
        usage += random.uniform(-200, 350)
        rows.append({"timestamp": ts, "memory_mb": max(usage, 1000)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .mon-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
        }}
        .mon-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .gauge {{ font-size: 22px; font-weight: 600; color: {_THEME['primary']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_mon_health_tab() -> None:
    """Render the Monitoring Health tab."""
    _inject_css()
    st.markdown(
        f"""
        <div class="mon-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">⚙️ System Health Monitoring</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Gauges, process list, connection pings, and error/memory trends.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- (a) Gauges ----
    st.markdown("### (a) System Health Gauges")
    gauges = _system_gauges()
    cols = st.columns(4)
    for label, key in [
        ("CPU %", "cpu_pct"),
        ("Memory %", "memory_pct"),
        ("Disk %", "disk_pct"),
        ("GPU %", "gpu_pct"),
    ]:
        cols[["cpu_pct","memory_pct","disk_pct","gpu_pct"].index(key)].markdown(
            f"<div class='gauge'>{label}<br>{gauges[key]:.1f}%</div>", unsafe_allow_html=True
        )

    st.divider()

    # ---- (b) Process Status ----
    st.markdown("### (b) Process Status")
    proc_df = _process_status()
    st.dataframe(
        proc_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "process_name": st.column_config.TextColumn("Process", width="medium"),
            "pid": st.column_config.NumberColumn("PID", format="%d"),
            "cpu_pct": st.column_config.NumberColumn("CPU %", format="%.1f%%"),
            "memory_mb": st.column_config.NumberColumn("Mem MB", format="%.1f"),
            "threads": st.column_config.NumberColumn("Threads", format="%d"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "uptime": st.column_config.TextColumn("Uptime", width="medium"),
            "restart_count": st.column_config.NumberColumn("Restarts", format="%d"),
        },
    )

    st.divider()

    # ---- (c) Connection Ping Matrix ----
    st.markdown("### (c) Connection Ping Matrix")
    ping_df = _ping_matrix()
    st.dataframe(
        ping_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "target": st.column_config.TextColumn("Target", width="medium"),
            "ping_ms": st.column_config.NumberColumn("Ping ms", format="%.1f"),
            "jitter_ms": st.column_config.NumberColumn("Jitter ms", format="%.1f"),
            "packet_loss_pct": st.column_config.NumberColumn("Loss %", format="%.1f%%"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "last_check": st.column_config.TextColumn("Last Check", width="medium"),
        },
    )

    st.divider()

    # ---- (d) Error Rate Trend ----
    st.markdown("### (d) Error Rate Trend (last 24h)")
    if _HAS_PLOTLY:
        err_df = _error_trend()
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(x=err_df["timestamp"], y=err_df["error_count"], mode="lines+markers", line=dict(color=_THEME["primary"])))
        fig_err.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=340,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(title="Time", gridcolor=_THEME["panel"]),
            yaxis=dict(title="Error Count", gridcolor=_THEME["panel"]),
        )
        st.plotly_chart(fig_err, use_container_width=True)

    # ---- Memory Usage Trend ----
    st.markdown("### Memory Usage Trend (last 24h)")
    if _HAS_PLOTLY:
        mem_df = _memory_usage_trend()
        fig_mem = go.Figure()
        fig_mem.add_trace(go.Scatter(x=mem_df["timestamp"], y=mem_df["memory_mb"], fill="tozeroy", mode="lines", line=dict(color=_THEME["secondary"])) )
        fig_mem.update_layout(
            template="plotly_dark",
            paper_bgcolor=_THEME["bg"],
            plot_bgcolor=_THEME["panel2"],
            font_color=_THEME["text"],
            height=340,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(title="Time", gridcolor=_THEME["panel"]),
            yaxis=dict(title="Memory MB", gridcolor=_THEME["panel"]),
        )
        st.plotly_chart(fig_mem, use_container_width=True)

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} • Synthetic monitoring data."
    )
