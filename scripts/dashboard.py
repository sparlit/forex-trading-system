"""Interactive Streamlit dashboard for EAQTS.

The dashboard shows a few key performance indicators exposed by the
Prometheus client running inside the trading loop:

* ``eaqts_live_positions`` – current number of open positions
* ``eaqts_total_pnl`` – cumulative profit & loss
* ``eaqts_trade_count_total`` – total number of trades executed

It also provides ``Start`` and ``Stop`` buttons that invoke the ``eaqts.cmd``
wrapper via ``subprocess``. The UI refreshes every 5 seconds to keep the
metrics up‑to‑date.
"""

import subprocess
import time
from pathlib import Path

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]

METRICS_URL = "http://localhost:8000/metrics"

def _fetch_metrics() -> dict:
    """Pull Prometheus metrics and return a dict of the three KPIs.

    If the metrics endpoint is unavailable, the values are set to ``None``.
    """
    try:
        resp = requests.get(METRICS_URL, timeout=2)
        resp.raise_for_status()
    except Exception:
        return {"positions": None, "pnl": None, "trades": None}

    # Parse the plain‑text exposition format – each metric appears as
    # ``metric_name value`` on its own line.
    result = {"positions": None, "pnl": None, "trades": None}
    for line in resp.text.splitlines():
        if line.startswith("eaqts_live_positions"):
            try:
                result["positions"] = int(float(line.split()[-1]))
            except Exception:
                result["positions"] = None
        elif line.startswith("eaqts_total_pnl"):
            try:
                result["pnl"] = float(line.split()[-1])
            except Exception:
                result["pnl"] = None
        elif line.startswith("eaqts_trade_count_total"):
            try:
                result["trades"] = int(float(line.split()[-1]))
            except Exception:
                result["trades"] = None
    return result

def _run_cmd(args: list[str]):
    """Execute ``eaqts.cmd`` with the given arguments.

    The wrapper lives in the project root, so we invoke it via ``cmd.exe`` on
    Windows. Errors are displayed in the UI.
    """
    cmd_path = PROJECT_ROOT / "eaqts.cmd"
    try:
        subprocess.run(["cmd.exe", "/c", str(cmd_path), *args], check=True)
    except subprocess.CalledProcessError as exc:
        st.error(f"Command failed: {exc}")

st.set_page_config(page_title="EAQTS Dashboard", layout="centered")
st.title("EAQTS – Live Trading Dashboard")

# Control buttons – they trigger commands when clicked.
col1, col2 = st.columns(2)
with col1:
    if st.button("Start Trading Loop"):
        _run_cmd(["start"])
with col2:
    if st.button("Stop Trading Loop"):
        _run_cmd(["stop"])

# Auto‑refresh block – Streamlit reruns the script on each interval.
st_autorefresh = st.experimental_rerun
# Fetch and display metrics.
metrics = _fetch_metrics()
st.subheader("Key Performance Indicators")
st.metric("Live Positions", metrics["positions"] if metrics["positions"] is not None else "—")
st.metric("Total PnL", f"{metrics['pnl']:.2f}" if metrics["pnl"] is not None else "—")
st.metric("Trades Executed", metrics["trades"] if metrics["trades"] is not None else "—")

# Refresh every 5 seconds.
st.experimental_set_query_params(refresh=str(time.time()))
st.experimental_rerun()
