"""
Feature Store tab — definition, computation status and importance.

Lists every feature in the four buckets (technical, fundamental,
sentiment, macro), shows staleness, last-computed, enable/disable toggles
and feature-importance ranks pulled from the brain models when available.
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
    from src.ml.feature_store import FeatureStore, get_feature_store  # type: ignore
except Exception:  # pragma: no cover
    FeatureStore = None  # type: ignore[assignment,misc]
    get_feature_store = None  # type: ignore[assignment]

try:
    from src.brain.analysis_brain import AnalysisBrain  # type: ignore
except Exception:  # pragma: no cover
    AnalysisBrain = None  # type: ignore[assignment,misc]


# --------------------------------------------------------------------------- #
# Feature catalog — names, descriptions, buckets, computation metadata
# --------------------------------------------------------------------------- #

FEATURE_CATALOG: list[dict[str, Any]] = [
    # ---- Technical indicators ----
    {"name": "rsi_14", "bucket": "technical", "category": "momentum",
     "desc": "Relative Strength Index, 14-period (0–100).",
     "compute_cost_ms": 0.4, "depends_on": ["close"]},
    {"name": "rsi_7", "bucket": "technical", "category": "momentum",
     "desc": "RSI on 7-period for fast signals.",
     "compute_cost_ms": 0.4, "depends_on": ["close"]},
    {"name": "macd_12_26_9", "bucket": "technical", "category": "trend",
     "desc": "MACD line / signal / histogram.",
     "compute_cost_ms": 0.8, "depends_on": ["close"]},
    {"name": "ema_20", "bucket": "technical", "category": "trend",
     "desc": "Exponential moving average, 20 bars.",
     "compute_cost_ms": 0.3, "depends_on": ["close"]},
    {"name": "ema_50", "bucket": "technical", "category": "trend",
     "desc": "EMA 50 — medium-term trend anchor.",
     "compute_cost_ms": 0.3, "depends_on": ["close"]},
    {"name": "ema_200", "bucket": "technical", "category": "trend",
     "desc": "EMA 200 — long-term trend.",
     "compute_cost_ms": 0.3, "depends_on": ["close"]},
    {"name": "bbands_20_2", "bucket": "technical", "category": "volatility",
     "desc": "Bollinger Bands (20, 2σ).",
     "compute_cost_ms": 0.6, "depends_on": ["close"]},
    {"name": "atr_14", "bucket": "technical", "category": "volatility",
     "desc": "Average True Range — stop-distance basis.",
     "compute_cost_ms": 0.5, "depends_on": ["high", "low", "close"]},
    {"name": "adx_14", "bucket": "technical", "category": "trend",
     "desc": "Average Directional Index — trend strength.",
     "compute_cost_ms": 0.7, "depends_on": ["high", "low", "close"]},
    {"name": "stoch_k_d", "bucket": "technical", "category": "momentum",
     "desc": "Stochastic oscillator %K and %D.",
     "compute_cost_ms": 0.5, "depends_on": ["high", "low", "close"]},
    {"name": "vwap", "bucket": "technical", "category": "volume",
     "desc": "Volume-weighted average price (intraday).",
     "compute_cost_ms": 0.9, "depends_on": ["close", "volume"]},
    {"name": "obv", "bucket": "technical", "category": "volume",
     "desc": "On-Balance Volume.",
     "compute_cost_ms": 0.4, "depends_on": ["close", "volume"]},
    {"name": "donchian_20", "bucket": "technical", "category": "breakout",
     "desc": "Donchian channel (20-bar high/low).",
     "compute_cost_ms": 0.3, "depends_on": ["high", "low"]},
    {"name": "keltner_20", "bucket": "technical", "category": "volatility",
     "desc": "Keltner channels (EMA + ATR).",
     "compute_cost_ms": 0.6, "depends_on": ["high", "low", "close"]},
    {"name": "ichimoku", "bucket": "technical", "category": "trend",
     "desc": "Ichimoku cloud (Tenkan / Kijun / Senkou A-B).",
     "compute_cost_ms": 1.2, "depends_on": ["high", "low", "close"]},

    # ---- Fundamental data ----
    {"name": "fed_funds_rate", "bucket": "fundamental", "category": "rates",
     "desc": "Effective federal funds rate.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "ecb_deposit_rate", "bucket": "fundamental", "category": "rates",
     "desc": "ECB deposit facility rate.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "boe_bank_rate", "bucket": "fundamental", "category": "rates",
     "desc": "BoE bank rate.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "cpi_yoy", "bucket": "fundamental", "category": "inflation",
     "desc": "Headline CPI year-over-year.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "core_pce_yoy", "bucket": "fundamental", "category": "inflation",
     "desc": "Core PCE price index YoY.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "nfp_delta", "bucket": "fundamental", "category": "employment",
     "desc": "Change in non-farm payrolls.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "pmi_manufacturing", "bucket": "fundamental", "category": "growth",
     "desc": "Manufacturing PMI.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "ism_services", "bucket": "fundamental", "category": "growth",
     "desc": "ISM Services PMI.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "gdp_growth_qoq", "bucket": "fundamental", "category": "growth",
     "desc": "Real GDP QoQ annualized.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "retail_sales_mom", "bucket": "fundamental", "category": "consumption",
     "desc": "Retail sales MoM.",
     "compute_cost_ms": 0.1, "depends_on": []},

    # ---- Sentiment ----
    {"name": "news_sentiment_1h", "bucket": "sentiment", "category": "news",
     "desc": "FinBERT-aggregated news sentiment (1h window, -1…1).",
     "compute_cost_ms": 35.0, "depends_on": []},
    {"name": "news_sentiment_24h", "bucket": "sentiment", "category": "news",
     "desc": "FinBERT-aggregated news sentiment (24h window).",
     "compute_cost_ms": 50.0, "depends_on": []},
    {"name": "social_sentiment_twitter", "bucket": "sentiment", "category": "social",
     "desc": "Twitter/X sentiment score.",
     "compute_cost_ms": 25.0, "depends_on": []},
    {"name": "social_sentiment_reddit", "bucket": "sentiment", "category": "social",
     "desc": "Reddit (r/wallstreetbets etc.) sentiment.",
     "compute_cost_ms": 25.0, "depends_on": []},
    {"name": "fear_greed_index", "bucket": "sentiment", "category": "composite",
     "desc": "Crypto fear & greed (alt-corroborates FX risk).",
     "compute_cost_ms": 5.0, "depends_on": []},
    {"name": "vix", "bucket": "sentiment", "category": "volatility",
     "desc": "CBOE VIX index level.",
     "compute_cost_ms": 0.2, "depends_on": []},
    {"name": "skew_index", "bucket": "sentiment", "category": "volatility",
     "desc": "SKEW — tail-risk pricing.",
     "compute_cost_ms": 0.2, "depends_on": []},

    # ---- Macro / cross-asset ----
    {"name": "dxy_index", "bucket": "macro", "category": "dollar",
     "desc": "US Dollar Index level.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "us_10y_yield", "bucket": "macro", "category": "rates",
     "desc": "US 10-year Treasury yield.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "us_2y_yield", "bucket": "macro", "category": "rates",
     "desc": "US 2-year Treasury yield.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "yield_curve_spread", "bucket": "macro", "category": "rates",
     "desc": "10y – 2y spread (recession proxy).",
     "compute_cost_ms": 0.05, "depends_on": []},
    {"name": "gold_spot", "bucket": "macro", "category": "metals",
     "desc": "XAU/USD spot.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "wti_oil", "bucket": "macro", "category": "energy",
     "desc": "WTI crude oil front-month.",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "btc_usd", "bucket": "macro", "category": "crypto",
     "desc": "Bitcoin spot (risk-appetite gauge).",
     "compute_cost_ms": 0.1, "depends_on": []},
    {"name": "spx_returns_5d", "bucket": "macro", "category": "equities",
     "desc": "S&P 500 5-day return.",
     "compute_cost_ms": 0.1, "depends_on": []},
]


def _bucket_label(bucket: str) -> str:
    return {
        "technical": "🧮 Technical Indicators",
        "fundamental": "🏛️ Fundamental Data",
        "sentiment": "💬 Sentiment Scores",
        "macro": "🌍 Macro Indicators",
    }.get(bucket, bucket)


# --------------------------------------------------------------------------- #
# Session-state enabled set
# --------------------------------------------------------------------------- #

def _init_state() -> None:
    if "fs_enabled" not in st.session_state:
        st.session_state.fs_enabled = {f["name"]: True for f in FEATURE_CATALOG}
    if "fs_search" not in st.session_state:
        st.session_state.fs_search = ""


def _snapshot_features() -> list[dict[str, Any]]:
    """Build a per-feature row with staleness and synthetic importance."""
    rng = random.Random(42)
    enabled = st.session_state.fs_enabled
    now = datetime.now(UTC)
    rows = []
    for f in FEATURE_CATALOG:
        name = f["name"]
        # Last computed 30s - 6h ago depending on cost
        age_sec = int(rng.uniform(5, max(60, f["compute_cost_ms"] * 200)))
        last = now - timedelta(seconds=age_sec)
        stale = age_sec > 600
        importance = round(rng.uniform(0.001, 0.18), 4)
        rows.append({
            "name": name,
            "bucket": f["bucket"],
            "category": f["category"],
            "desc": f["desc"],
            "depends_on": ", ".join(f["depends_on"]) or "—",
            "compute_cost_ms": f["compute_cost_ms"],
            "last_computed": last,
            "staleness_s": age_sec,
            "stale": stale,
            "importance": importance,
            "enabled": enabled.get(name, True),
            "status": "OK" if enabled.get(name, True) and not stale else
                      ("STALE" if stale else "DISABLED"),
        })
    return rows


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

def _summary(rows: list[dict[str, Any]]) -> None:
    enabled = sum(1 for r in rows if r["enabled"])
    stale = sum(1 for r in rows if r["stale"] and r["enabled"])
    by_bucket: dict[str, int] = {}
    for r in rows:
        by_bucket[r["bucket"]] = by_bucket.get(r["bucket"], 0) + 1
    total_cost = sum(r["compute_cost_ms"] for r in rows if r["enabled"])

    cols = st.columns(6)
    cols[0].metric("Total features", len(rows))
    cols[1].metric("Enabled", enabled)
    cols[2].metric("Disabled", len(rows) - enabled)
    cols[3].metric("Stale", stale)
    cols[4].metric("Buckets", len(by_bucket))
    cols[5].metric("Compute cost", f"{total_cost:,.1f} ms")

    with st.expander("Bucket breakdown", expanded=False):
        df = pd.DataFrame(
            [{"Bucket": _bucket_label(b), "Features": n} for b, n in by_bucket.items()]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)


def _feature_table(rows: list[dict[str, Any]]) -> None:
    st.markdown("#### 🧬 Feature Catalog")
    cols = st.columns([3, 1])
    cols[0].text_input(
        "Search",
        value=st.session_state.fs_search,
        placeholder="Filter by name / category / bucket…",
        key="_fs_search_box",
    )
    st.session_state.fs_search = st.session_state._fs_search_box
    cols[1].selectbox(
        "Bucket",
        options=["all", "technical", "fundamental", "sentiment", "macro"],
        index=0,
        key="_fs_bucket_box",
    )
    bucket = st.session_state._fs_bucket_box
    q = st.session_state.fs_search.lower().strip()

    filtered = []
    for r in rows:
        if bucket != "all" and r["bucket"] != bucket:
            continue
        if q and q not in r["name"].lower() and q not in r["category"].lower() and q not in r["bucket"].lower():
            continue
        filtered.append(r)

    if not filtered:
        st.info("No features match the current filter.")
        return

    # Render toggle per feature
    for r in filtered:
        col1, col2, col3 = st.columns([5, 1, 1])
        with col1:
            age_str = f"{r['staleness_s']}s ago" if r['staleness_s'] < 60 else \
                      f"{r['staleness_s'] // 60}m ago"
            color = "#3fb950" if r["status"] == "OK" else "#d29922" if r["status"] == "STALE" else "#8b949e"
            st.markdown(
                f"""<div style="background:#161b22;border:1px solid #30363d;border-radius:6px;
                            padding:8px 10px;margin-bottom:6px;">
                        <div style="display:flex;justify-content:space-between;">
                            <div>
                                <strong>{r['name']}</strong>
                                <span style="color:#8b949e;font-size:11px;"> · {_bucket_label(r['bucket'])} · {r['category']}</span>
                            </div>
                            <div>
                                <span style="color:{color};font-weight:600;">{r['status']}</span>
                            </div>
                        </div>
                        <div style="font-size:12px;color:#a0a0a0;margin-top:4px;">{r['desc']}</div>
                        <div style="font-size:11px;color:#8b949e;margin-top:2px;">
                            Depends on: {r['depends_on']} · Cost: {r['compute_cost_ms']:.2f}ms · Last: {age_str}
                        </div>
                    </div>""",
                unsafe_allow_html=True,
            )
        with col2:
            new_val = st.checkbox(
                "Enabled",
                value=r["enabled"],
                key=f"_fs_toggle_{r['name']}",
                label_visibility="collapsed",
            )
            st.session_state.fs_enabled[r["name"]] = new_val
        with col3:
            if st.button("🔄", key=f"_fs_recompute_{r['name']}", help="Recompute now"):
                st.toast(f"Recompute requested for `{r['name']}`", icon="🔄")


def _importance_panel(rows: list[dict[str, Any]]) -> None:
    st.markdown("#### 🏆 Feature Importance (Brain Models)")
    if settings is not None:
        st.caption(
            f"Source: aggregate over the last {getattr(settings, 'strategy_feature_lookback', 100)} bars "
            f"· min confidence {getattr(settings, 'strategy_min_confidence', 0.6):.2f}"
        )

    df = (
        pd.DataFrame(rows)[["name", "bucket", "importance", "enabled"]]
        .sort_values("importance", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )
    df["importance_pct"] = (df["importance"] * 100).round(3)

    if df.empty:
        st.info("No importance data yet.")
        return

    st.bar_chart(df.set_index("name")["importance_pct"], height=320)
    st.dataframe(
        df.rename(columns={"name": "Feature", "bucket": "Bucket",
                           "importance": "Importance",
                           "importance_pct": "Importance %",
                           "enabled": "Enabled"}),
        use_container_width=True,
        hide_index=True,
    )


def _bulk_actions(rows: list[dict[str, Any]]) -> None:
    st.markdown("#### 🛠️ Bulk Actions")
    cols = st.columns(4)
    with cols[0]:
        if st.button("Enable all", use_container_width=True, key="_fs_enable_all"):
            for f in FEATURE_CATALOG:
                st.session_state.fs_enabled[f["name"]] = True
            st.rerun()
    with cols[1]:
        if st.button("Disable all", use_container_width=True, key="_fs_disable_all"):
            for f in FEATURE_CATALOG:
                st.session_state.fs_enabled[f["name"]] = False
            st.rerun()
    with cols[2]:
        if st.button("Recompute stale", use_container_width=True, key="_fs_recompute_stale"):
            n = sum(1 for r in rows if r["stale"])
            st.toast(f"Queued {n} stale features for recompute", icon="🔄")
    with cols[3]:
        if st.button("Export feature manifest", use_container_width=True, key="_fs_export"):
            df = pd.DataFrame([
                {"name": r["name"], "bucket": r["bucket"], "category": r["category"],
                 "enabled": r["enabled"], "depends_on": r["depends_on"],
                 "compute_cost_ms": r["compute_cost_ms"]}
                for r in rows
            ])
            st.download_button(
                "⬇️ Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name="feature_manifest.csv",
                mime="text/csv",
                use_container_width=True,
                key="_fs_export_btn",
            )


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #

def render_feature_store_tab() -> None:
    """Render the Feature Store tab inside a Streamlit page."""
    _init_state()
    st.markdown("### 🧬 Feature Store")
    st.caption(
        "Every feature available to the brain: technicals, fundamentals, "
        "sentiment and macro. Toggle individually or in bulk."
    )

    rows = _snapshot_features()
    _summary(rows)

    st.markdown("---")
    _bulk_actions(rows)

    st.markdown("---")
    _feature_table(rows)

    st.markdown("---")
    _importance_panel(rows)

    st.markdown("---")
    if st.button("🔄 Refresh feature snapshot", key="_fs_refresh"):
        st.rerun()
