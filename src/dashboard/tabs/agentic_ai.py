"""
Agentic AI dashboard tab.

Renders the live status, current decision, analysis breakdown, detected
chart patterns, self-healing log and parallel-execution metrics for the
:class:`src.ai.agentic_ai.AgenticAgent`. Uses a dark theme via inline CSS,
falls back to graceful placeholders when optional dependencies or the
underlying ``AgenticAgent`` import is unavailable.
import logging

Designed to mirror the look-and-feel of the existing tabs in this package
(see ``strategy_engine.py``, ``monitoring.py``).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import plotly.express as px  # type: ignore
    import plotly.graph_objects as go  # type: ignore

    _HAS_PLOTLY = True
except Exception:  # pragma: no cover
    _HAS_PLOTLY = False

try:  # The orchestrator itself – always lazy-loaded.
    from src.ai.agentic_ai import (  # type: ignore
        AgenticAgent,
        ComponentState,
        DecisionAction,
    )

    _HAS_AGENT = True
except Exception as exc:  # pragma: no cover
    AgenticAgent = None  # type: ignore[assignment,misc]
    DecisionAction = None  # type: ignore[assignment,misc]
    ComponentState = None  # type: ignore[assignment,misc]
    _HAS_AGENT = False
    _IMPORT_ERROR = str(exc)
else:
    _IMPORT_ERROR = ""


# --------------------------------------------------------------------------- #
# Dark-theme CSS – injected once per Streamlit session
# --------------------------------------------------------------------------- #


_DARK_CSS = """
<style>
    .stApp header {background-color: #0e1117;}
    section.main > div.block-container {background-color: #0e1117; color: #e6e6e6;}
    .agentic-card {
        background-color: #1a1f2b;
        border: 1px solid #2a3142;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
        color: #e6e6e6;
    }
    .agentic-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .pill-online  {background: #154d2c; color: #6ff09a;}
    .pill-offline {background: #4a1c1c; color: #ff8585;}
    .pill-buy     {background: #154d2c; color: #6ff09a;}
    .pill-sell    {background: #4a1c1c; color: #ff8585;}
    .pill-hold    {background: #3a3f4b; color: #d0d4dc;}
    .pill-healthy {background: #154d2c; color: #6ff09a;}
    .pill-degraded{background: #4a3814; color: #f0c46f;}
    .pill-failed  {background: #4a1c1c; color: #ff8585;}
</style>
"""


def _inject_css() -> None:
    """Inject dark-theme CSS once per Streamlit run."""

    if not st.session_state.get("_agentic_css_loaded"):
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
        st.session_state["_agentic_css_loaded"] = True


def _pill(label: str, kind: str) -> str:
    """Tiny HTML helper for status / action pills."""

    return f'<span class="agentic-pill pill-{kind}">{label}</span>'


# --------------------------------------------------------------------------- #
# Synthetic data – kept here so the tab is import-safe without the agent.
# --------------------------------------------------------------------------- #


def _synthetic_decision() -> dict[str, Any]:
    """Return a plausible decision dict so the tab is meaningful even without
    the agent. The numbers change a little each call so the UI feels alive.
    """

    rng = random.Random(42)
    actions = ["Buy", "Sell", "Hold"]
    weights = [0.45, 0.30, 0.25]
    action = rng.choices(actions, weights=weights, k=1)[0]
    confidence = round(rng.uniform(0.45, 0.92), 3)
    return {
        "action": action,
        "confidence": confidence,
        "timestamp": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
        "contributing_signals": [
            {
                "analysis_type": "technical",
                "result": "bullish" if action == "Buy" else "bearish" if action == "Sell" else "neutral",
                "confidence": round(rng.uniform(0.55, 0.9), 3),
                "duration_ms": round(rng.uniform(2, 8), 2),
            },
            {
                "analysis_type": "advanced",
                "result": "bullish" if action == "Buy" else "bearish" if action == "Sell" else "neutral",
                "confidence": round(rng.uniform(0.5, 0.85), 3),
                "duration_ms": round(rng.uniform(2, 8), 2),
            },
            {
                "analysis_type": "patterns",
                "result": rng.choice(["bullish", "bearish", "neutral"]),
                "confidence": round(rng.uniform(0.4, 0.8), 3),
                "duration_ms": round(rng.uniform(5, 15), 2),
            },
            {
                "analysis_type": "monte_carlo",
                "result": rng.choice(["bullish", "bearish", "neutral"]),
                "confidence": round(rng.uniform(0.4, 0.75), 3),
                "duration_ms": round(rng.uniform(10, 30), 2),
            },
        ],
        "chart_patterns": [
            {
                "pattern": "ascending_triangle",
                "direction": "bullish",
                "confidence": 0.62,
                "description": "Ascending triangle – bullish continuation.",
            },
            {
                "pattern": "hammer",
                "direction": "bullish",
                "confidence": 0.71,
                "description": "Hammer candle – potential bullish reversal.",
            },
        ]
        if action != "Sell"
        else [
            {
                "pattern": "head_and_shoulders",
                "direction": "bearish",
                "confidence": 0.69,
                "description": "Head & shoulders – bearish reversal pattern.",
            },
            {
                "pattern": "engulfing",
                "direction": "bearish",
                "confidence": 0.74,
                "description": "Bearish engulfing – momentum shift.",
            },
        ],
        "parallel_metrics": {
            "workers": 4,
            "total_ms": round(rng.uniform(18, 35), 2),
            "serial_ms": round(rng.uniform(40, 70), 2),
            "speedup": round(rng.uniform(1.6, 2.4), 2),
            "backend": "process",
        },
    }


def _synthetic_health_log() -> pd.DataFrame:
    """A small history of self-heal events – shown even when the agent
    isn't connected so operators can preview the layout."""

    now = datetime.now(UTC)
    rows = [
        {
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
            "component": "pattern_detector",
            "state": "healthy",
            "note": "Restarted after timeout in worker process.",
        },
        {
            "timestamp": (now - timedelta(minutes=10)).isoformat(),
            "component": "decision_engine",
            "state": "healthy",
            "note": "Recalibrated weights after regime shift to trending.",
        },
        {
            "timestamp": (now - timedelta(minutes=27)).isoformat(),
            "component": "monte_carlo",
            "state": "degraded",
            "note": "Slow simulation (28 ms) – switched to Rust backend.",
        },
    ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Cached agent accessor (one per Streamlit session)
# --------------------------------------------------------------------------- #


@st.cache_resource(show_spinner=False)
def _get_agent() -> AgenticAgent | None:  # type: ignore[valid-type]
    """Lazy-build a single ``AgenticAgent`` per browser session.

    Returns ``None`` when the orchestrator cannot be imported so the tab can
    still render with placeholder data instead of throwing.
    """

    if not _HAS_AGENT or AgenticAgent is None:
        return None
    try:
        return AgenticAgent(name="dashboard-agentic", workers=4)
    except Exception as exc:  # pragma: no cover
        st.session_state["_agentic_init_error"] = str(exc)
        return None


# --------------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------------- #


def _render_status(decision: dict[str, Any], online: bool, last_cycle: datetime | None) -> None:
    """Top row: online/offline pill + current decision + confidence."""

    cols = st.columns([1, 1, 1, 1])
    if online:
        cols[0].markdown(
            f'<div class="agentic-card">Agent<br/>{_pill("● online", "online")}</div>',
            unsafe_allow_html=True,
        )
    else:
        cols[0].markdown(
            f'<div class="agentic-card">Agent<br/>{_pill("○ offline (synthetic data)", "offline")}</div>',
            unsafe_allow_html=True,
        )

    action = decision["action"]
    pill_kind = {"Buy": "buy", "Sell": "sell", "Hold": "hold"}.get(action, "hold")
    cols[1].markdown(
        f'<div class="agentic-card">Decision<br/>{_pill(action, pill_kind)}</div>',
        unsafe_allow_html=True,
    )

    cols[2].metric(
        label="Confidence",
        value=f"{decision['confidence'] * 100:.1f} %",
    )

    if last_cycle is None:
        last_str = "—"
    else:
        delta = datetime.now(UTC) - last_cycle
        last_str = last_cycle.strftime("%H:%M:%S") + f"  ({int(delta.total_seconds())}s ago)"
    cols[3].markdown(
        f'<div class="agentic-card">Last cycle<br/>{last_str}</div>',
        unsafe_allow_html=True,
    )


def _render_analysis_breakdown(decision: dict[str, Any]) -> None:
    """Table: analysis_type | result | confidence | duration_ms."""

    st.subheader("Analysis Breakdown")
    signals = decision.get("contributing_signals", [])
    if not signals:
        st.info("No analysis signals yet – run a cycle to populate.")
        return

    df = pd.DataFrame(
        [
            {
                "analysis_type": s["analysis_type"],
                "result": s["result"],
                "confidence": round(float(s["confidence"]) * 100, 1),
                "duration_ms": float(s["duration_ms"]),
            }
            for s in signals
        ],
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    if _HAS_PLOTLY:
        try:
            fig = px.bar(
                df,
                x="analysis_type",
                y="confidence",
                color="result",
                color_discrete_map={
                    "bullish": "#6ff09a",
                    "bearish": "#ff8585",
                    "neutral": "#7d8597",
                },
                title="Confidence by module",
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#1a1f2b",
                height=320,
                margin={"l":10, "r":10, "t":40, "b":10},
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning('Suppressed error in _render_chart_confidence module', exc_info=True)


def _render_chart_patterns(decision: dict[str, Any]) -> None:
    """Visual list of detected chart patterns with emoji indicators."""

    st.subheader("Detected Chart Patterns")
    patterns = decision.get("chart_patterns", [])
    if not patterns:
        st.info("No chart patterns detected this cycle.")
        return

    icons = {
        "head_and_shoulders": "🗻 H&S",
        "inverse_head_and_shoulders": "🗻 Inverse H&S",
        "double_top": "⛰ Double top",
        "double_bottom": "🏞 Double bottom",
        "symmetrical_triangle": "△ Sym. triangle",
        "ascending_triangle": "▲ Asc. triangle",
        "descending_triangle": "▽ Desc. triangle",
        "flag": "🚩 Flag",
        "falling_wedge": "🔻 Falling wedge",
        "rising_wedge": "🔺 Rising wedge",
        "doji": "✚ Doji",
        "hammer": "🔨 Hammer",
        "engulfing": "≋ Engulfing",
    }
    rows = []
    for p in patterns:
        rows.append(
            {
                "pattern": icons.get(p["pattern"], p["pattern"]),
                "direction": p["direction"],
                "confidence": round(float(p["confidence"]) * 100, 1),
                "description": p["description"],
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if _HAS_PLOTLY:
        try:
            fig = go.Figure(
                go.Bar(
                    x=[r["pattern"] for r in rows],
                    y=[r["confidence"] for r in rows],
                    marker_color=[
                        "#6ff09a" if r["direction"] == "bullish"
                        else "#ff8585" if r["direction"] == "bearish"
                        else "#7d8597"
                        for r in rows
                    ],
                )
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#1a1f2b",
                title="Pattern confidence",
                height=280,
                margin={"l":10, "r":10, "t":40, "b":10},
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning('Suppressed error in _render_chart_confidence module', exc_info=True)


def _render_self_healing_log(health_log: pd.DataFrame) -> None:
    """Recent self-heal events."""

    st.subheader("Self-Healing Log")
    if health_log.empty:
        st.info("No self-heal events recorded.")
        return
    st.dataframe(health_log, use_container_width=True, hide_index=True)

    if _HAS_PLOTLY and "state" in health_log.columns:
        try:
            counts = (
                health_log["state"]
                .value_counts()
                .rename_axis("state")
                .reset_index(name="count")
            )
            fig = px.pie(
                counts,
                names="state",
                values="count",
                color="state",
                color_discrete_map={
                    "healthy": "#6ff09a",
                    "degraded": "#f0c46f",
                    "failed": "#ff8585",
                    "restarting": "#7d8597",
                },
                title="Component health distribution",
                hole=0.45,
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#1a1f2b",
                height=280,
                margin={"l":10, "r":10, "t":40, "b":10},
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning('Suppressed error in _render_chart_confidence module', exc_info=True)


def _render_parallel_metrics(metrics: dict[str, Any]) -> None:
    """Workers, total time, speedup vs serial."""

    st.subheader("Parallel Execution Metrics")
    if not metrics:
        st.info("No parallel metrics available yet.")
        return

    cols = st.columns(4)
    cols[0].metric("Workers", int(metrics.get("workers", 0)))
    cols[1].metric("Total time", f"{float(metrics.get('total_ms', 0.0)):.1f} ms")
    cols[2].metric(
        "Serial baseline",
        f"{float(metrics.get('serial_ms', 0.0)):.1f} ms",
    )
    cols[3].metric("Speedup", f"{float(metrics.get('speedup', 1.0)):.2f}×")

    if _HAS_PLOTLY:
        try:
            fig = go.Figure(
                data=[
                    go.Bar(
                        name="Parallel",
                        x=["Total time (ms)"],
                        y=[float(metrics.get("total_ms", 0.0))],
                        marker_color="#6ff09a",
                    ),
                    go.Bar(
                        name="Serial baseline",
                        x=["Total time (ms)"],
                        y=[float(metrics.get("serial_ms", 0.0))],
                        marker_color="#7d8597",
                    ),
                ],
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#1a1f2b",
                barmode="group",
                title="Parallel vs serial execution",
                height=260,
                margin={"l":10, "r":10, "t":40, "b":10},
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning('Suppressed error in _render_chart_confidence module', exc_info=True)


# --------------------------------------------------------------------------- #
# Main tab entry point
# --------------------------------------------------------------------------- #


def render_agentic_ai_tab() -> None:
    """Render the Agentic AI dashboard tab."""

    _inject_css()
    st.header("🤖 Agentic AI")
    st.caption(
        "Live status, current decision, analysis breakdown, chart patterns, "
        "self-healing log and parallel-execution metrics for the autonomous agent.",
    )

    if not _HAS_AGENT:
        st.warning(
            "AgenticAgent could not be imported "
            f"({_IMPORT_ERROR or 'unknown error'}). Showing synthetic data.",
        )

    # Sidebar-style controls inside an expander so the tab stays compact.
    with st.expander("Controls", expanded=False):
        cols = st.columns([1, 1, 1])
        run_clicked = cols[0].button("▶ Run analysis cycle", use_container_width=True)
        heal_clicked = cols[1].button("🩹 Self-heal", use_container_width=True)
        auto_refresh = cols[2].checkbox("Auto-refresh every 5 s", value=False)

    agent = _get_agent()
    decision: dict[str, Any]
    health_log: pd.DataFrame

    # ----------------------------------------------------------------- action
    if heal_clicked and agent is not None:
        try:
            report = asyncio.run(agent.self_heal())
            healed = report.get("healed", [])
            failing = report.get("still_failing", [])
            if healed and not failing:
                st.success(f"Self-heal complete: restarted {', '.join(healed)}.")
            elif failing:
                st.error(
                    f"Self-heal partial. Healed: {healed or '∅'}. "
                    f"Still failing: {failing}."
                )
            else:
                st.info("All components healthy – nothing to restart.")
        except Exception as exc:  # pragma: no cover
            st.error(f"Self-heal failed: {exc}")

    # ----------------------------------------------------------- decision data
    decision = _synthetic_decision()
    health_log = _synthetic_health_log()
    online = False
    last_cycle: datetime | None = None

    if agent is not None:
        try:
            if run_clicked or "agentic_last_decision" not in st.session_state:
                decision = asyncio.run(agent.run_analysis_cycle())
                st.session_state["agentic_last_decision"] = decision
                st.session_state["agentic_last_cycle_at"] = datetime.now(UTC)
            else:
                decision = st.session_state["agentic_last_decision"]
            online = True
            last_cycle = st.session_state.get("agentic_last_cycle_at")
            health_df = pd.DataFrame(list(agent.health_log))
            if not health_df.empty:
                health_log = health_df
        except Exception as exc:  # pragma: no cover
            st.warning(f"Agent cycle failed ({exc}); showing last cached or synthetic data.")

    # ----------------------------------------------------------- render blocks
    _render_status(decision, online=online, last_cycle=last_cycle)

    st.divider()
    _render_analysis_breakdown(decision)

    st.divider()
    cols = st.columns(2)
    with cols[0]:
        _render_chart_patterns(decision)
    with cols[1]:
        _render_self_healing_log(health_log)

    st.divider()
    _render_parallel_metrics(decision.get("parallel_metrics", {}))

    if auto_refresh:
        import time as _t

        _t.sleep(5)
        st.rerun()


# --------------------------------------------------------------------------- #
# Stand-alone smoke-test: ``streamlit run src/dashboard/tabs/agentic_ai.py``
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    st.set_page_config(page_title="Agentic AI", layout="wide")
    render_agentic_ai_tab()
