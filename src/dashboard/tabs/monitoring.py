'''Monitoring tab - system health and service control.

Covers:
  * CPU / Memory / Disk usage gauges
  * Process status (brain, data_feed, execution, api)
  * Prometheus metrics summary
  * Active alerts list with severity
  * Alert rules config (toggle / threshold)
  * Control panel (start / stop / restart services)
  * System uptime
  * Error-rate trend (synthetic time series)
'''

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import psutil
import streamlit as st

# Ensure project root is on sys.path for optional imports
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Optional Prometheus import — fallback to placeholders if unavailable
try:  # pragma: no cover
    from src.infra.monitoring.metrics import (  # type: ignore
        alerts_sent,
        errors_total,
        orders_total,
        signals_total,
        trades_total,
    )
    _PROM = True
except Exception:
    _PROM = False

def _system_metrics() -> dict[str, Any]:
    """Collect basic system metrics using psutil."""
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = (datetime.now(timezone.utc) - boot).total_seconds()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "uptime": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m",
    }

def _process_status() -> pd.DataFrame:
    """Placeholder process table for core services."""
    services = ["brain", "data_feed", "execution", "api"]
    rows = []
    for name in services:
        proc = None
        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
            if name in p.info["name"]:
                proc = p
                break
        if proc:
            status = "running"
            pid = proc.pid
            mem_mb = proc.info["memory_info"].rss / 1e6
            cpu = proc.cpu_percent(interval=0.1)
        else:
            status = "stopped"
            pid = "-"
            mem_mb = "-"
            cpu = "-"
        rows.append({"process": name, "status": status, "pid": pid, "memory_mb": mem_mb, "cpu_pct": cpu})
    return pd.DataFrame(rows)

def _active_alerts() -> pd.DataFrame:
    data = [
        {"id": "ALT-001", "severity": "high",     "message": "CPU > 90%",               "timestamp": datetime.now(timezone.utc), "acknowledged": False},
        {"id": "ALT-002", "severity": "medium",   "message": "Memory > 80%",            "timestamp": datetime.now(timezone.utc), "acknowledged": True},
        {"id": "ALT-003", "severity": "critical", "message": "Margin level below 120%", "timestamp": datetime.now(timezone.utc), "acknowledged": False},
    ]
    return pd.DataFrame(data)


def _prometheus_summary() -> pd.DataFrame:
    """Snapshot of core Prometheus counters (real or placeholder)."""
    if _PROM:
        try:
            return pd.DataFrame([
                {"metric": "orders_total",        "value": int(sum(s.value for s in orders_total.collect()))},
                {"metric": "trades_total",        "value": int(sum(s.value for s in trades_total.collect()))},
                {"metric": "signals_total",       "value": int(sum(s.value for s in signals_total.collect()))},
                {"metric": "errors_total",        "value": int(sum(s.value for s in errors_total.collect()))},
                {"metric": "alerts_sent_total",   "value": int(sum(s.value for s in alerts_sent.collect()))},
            ])
        except Exception:
            logging.getLogger(__name__).exception('Suppressed exception')
    return pd.DataFrame([
        {"metric": "orders_total",      "value": 0},
        {"metric": "trades_total",      "value": 0},
        {"metric": "signals_total",     "value": 0},
        {"metric": "errors_total",      "value": 0},
        {"metric": "alerts_sent_total", "value": 0},
    ])


def _error_rate_trend() -> pd.DataFrame:
    """Synthetic error-per-minute trend for the last hour."""
    import numpy as np
    now = datetime.now(timezone.utc)
    times = [now - pd.Timedelta(minutes=i) for i in range(60, -1, -1)]
    errs = np.clip(np.random.normal(loc=1.5, scale=1.0, size=len(times)), 0, None)
    return pd.DataFrame({"time": times, "errors_per_min": errs})

def _alert_rules() -> pd.DataFrame:
    data = [
        {"rule_name": "CPU High", "metric": "cpu_percent", "condition": ">", "threshold": 90, "enabled": True},
        {"rule_name": "Memory High", "metric": "memory_percent", "condition": ">", "threshold": 80, "enabled": True},
    ]
    return pd.DataFrame(data)

def _control_panel() -> None:
    st.subheader("Service Control Panel")
    services = ["brain", "data_feed", "execution", "api"]
    for svc in services:
        col_name, col_start, col_stop, col_restart = st.columns([2, 1, 1, 1])
        with col_name:
            st.write(f"**{svc}**")
        with col_start:
            if st.button(f"Start {svc}", key=f"start_{svc}"):
                st.success(f"Started {svc} (simulated)")
        with col_stop:
            if st.button(f"Stop {svc}", key=f"stop_{svc}"):
                st.success(f"Stopped {svc} (simulated)")
        with col_restart:
            if st.button(f"Restart {svc}", key=f"restart_{svc}"):
                st.success(f"Restarted {svc} (simulated)")

def render_monitoring_tab() -> None:
    """Render the Monitoring dashboard tab."""
    st.title("🖥️ Monitoring")
    metrics = _system_metrics()
    col_cpu, col_mem, col_disk, col_up = st.columns(4)
    col_cpu.metric("CPU %", f"{metrics['cpu_percent']:.1f}%")
    col_mem.metric("Memory %", f"{metrics['memory_percent']:.1f}%")
    col_disk.metric("Disk %", f"{metrics['disk_percent']:.1f}%")
    col_up.metric("Uptime", metrics["uptime"])

    st.subheader("Process Status")
    st.dataframe(_process_status(), use_container_width=True)

    st.subheader("Active Alerts")
    st.dataframe(_active_alerts(), hide_index=True, use_container_width=True)

    st.subheader("Alert Rules")
    st.dataframe(_alert_rules(), hide_index=True, use_container_width=True)

    st.subheader("Prometheus Metrics")
    st.dataframe(_prometheus_summary(), hide_index=True, use_container_width=True)

    st.subheader("Error Rate Trend (last hour)")
    st.line_chart(_error_rate_trend(), x="time", y="errors_per_min", height=220)

    _control_panel()
