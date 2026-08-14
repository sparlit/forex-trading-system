"""
External Data tab — third-party API providers and website crawler configuration.

Covers:
  (A) API Providers  — AlphaVantage, TwelveData, Finazon, Alpaca, CoinMarketCap,
                       Finnhub, Polygon. Add new providers, test connections,
                       enable/disable.
  (B) Website Crawler — ICO/DeFi/crypto data targets (ICODrops, DeFiLama,
                         TokenTerminal, DropsTab, Farsight, CoinMarketCap,
                         DriveWorth). Schedule, start/stop, scrape previews.

All state is held in `st.session_state`; nothing leaves the browser until the
user explicitly saves or persists (future hook: `src.infra.persistence`).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

# Project-root path bootstrap (so future config integrations resolve)
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Supported API providers with sensible defaults. `name` is the display label,
# `base_url` is the API root, `enabled` is the default on/off state.
_PROVIDER_DEFAULTS: list[dict[str, Any]] = [
    {
        "name": "AlphaVantage",
        "api_key": "",
        "base_url": "https://www.alphavantage.co/query",
        "enabled": True,
    },
    {
        "name": "TwelveData",
        "api_key": "",
        "base_url": "https://api.twelvedata.com/v1",
        "enabled": True,
    },
    {
        "name": "Finazon",
        "api_key": "",
        "base_url": "https://api.finazon.io/v1",
        "enabled": False,
    },
    {
        "name": "Alpaca",
        "api_key": "",
        "base_url": "https://paper-api.alpaca.markets/v2",
        "enabled": False,
    },
    {
        "name": "CoinMarketCap",
        "api_key": "",
        "base_url": "https://pro-api.coinmarketcap.com/v1",
        "enabled": True,
    },
    {
        "name": "Finnhub",
        "api_key": "",
        "base_url": "https://finnhub.io/api/v1",
        "enabled": False,
    },
    {
        "name": "Polygon",
        "api_key": "",
        "base_url": "https://api.polygon.io/v3",
        "enabled": False,
    },
]

# Seed crawler targets. `url` is the homepage (scraper walks from there),
# `crawl_frequency_minutes` is the recurring interval, `robots_txt_compliant`
# must be true to allow the crawl.
_CRAWLER_DEFAULTS: list[dict[str, Any]] = [
    {
        "url": "https://icodrops.com",
        "category": "ICO Calendar",
        "crawl_frequency_minutes": 60,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://defillama.com",
        "category": "DeFi TVL",
        "crawl_frequency_minutes": 30,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://tokenterminal.com",
        "category": "Token Revenue",
        "crawl_frequency_minutes": 120,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://dropstab.com",
        "category": "Airdrops / Drops",
        "crawl_frequency_minutes": 60,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://farsight.ai",
        "category": "On-chain Analytics",
        "crawl_frequency_minutes": 240,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://coinmarketcap.com",
        "category": "Market Listings",
        "crawl_frequency_minutes": 15,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
    {
        "url": "https://driveworth.io",
        "category": "Project Valuation",
        "crawl_frequency_minutes": 360,
        "robots_txt_compliant": True,
        "pages_scraped": 0,
        "status": "Idle",
    },
]

# Cron-like presets used by the schedule config form.
_CRON_PRESETS: list[str] = [
    "Every 5 minutes",
    "Every 15 minutes",
    "Every 30 minutes",
    "Hourly",
    "Every 3 hours",
    "Every 6 hours",
    "Daily",
    "Weekly",
]

_STATUS_EMOJI: dict[str, str] = {
    "Idle": "⚪",
    "Running": "🟢",
    "Stopped": "🔴",
    "Error": "🟠",
    "Unknown": "🟣",
}


# --------------------------------------------------------------------------- #
# Session-state helpers
# --------------------------------------------------------------------------- #

_DEFAULTS: dict[str, Any] = {
    "ext_providers": None,        # populated by _init_state
    "ext_crawler_targets": None,  # populated by _init_state
    "ext_crawl_status": {},       # url -> "Running"/"Stopped"
    "ext_last_test": {},          # provider name -> ISO timestamp
    "ext_test_status": {},        # provider name -> "OK"/"Failed"
    "ext_crawl_log": [],          # recent scraped items (timestamp, url, title)
    "ext_global_schedule": "Every 30 minutes",
    "ext_global_interval_min": 30,
    "ext_persist_path": "",
}


def _init_state() -> None:
    """Populate session_state with default providers + crawler targets."""
    for k, v in _DEFAULTS.items():
        st.session_state.setdefault(k, v)

    if st.session_state.ext_providers is None:
        # Copy defaults so we don't mutate the constant list
        st.session_state.ext_providers = [dict(p) for p in _PROVIDER_DEFAULTS]

    if st.session_state.ext_crawler_targets is None:
        st.session_state.ext_crawler_targets = [dict(t) for t in _CRAWLER_DEFAULTS]


def _now_iso() -> str:
    """ISO-8601 UTC timestamp, second-precision, no microseconds."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _mask_key(key: str) -> str:
    """Return a masked representation of an API key.

    Shows the first 4 + last 4 characters if the key is long enough,
    otherwise returns '***'. Empty keys render as '(not set)'.
    """
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}…{key[-4:]}"


def _status_pill(label: str) -> str:
    """Emoji-prefixed status label suitable for display."""
    return f"{_STATUS_EMOJI.get(label, '⚪')} {label}"


# --------------------------------------------------------------------------- #
# Section A — API Providers
# --------------------------------------------------------------------------- #

def _providers_summary_metrics() -> None:
    """Show quick counts for providers."""
    providers = st.session_state.ext_providers
    total = len(providers)
    enabled = sum(1 for p in providers if p.get("enabled"))
    tested = sum(1 for k in st.session_state.ext_test_status if k in {p["name"] for p in providers})
    ok = sum(1 for k, v in st.session_state.ext_test_status.items() if v == "OK"
             and k in {p["name"] for p in providers})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total providers", total)
    c2.metric("Enabled", enabled, delta=f"{enabled - (total - enabled):+d} vs disabled")
    c3.metric("Tested OK", ok)
    c4.metric("Untested", max(0, total - tested))


def _providers_table() -> None:
    """Render the providers table with per-row controls."""
    st.markdown("#### Configured Providers")

    providers = st.session_state.ext_providers
    if not providers:
        st.info("No providers configured. Add one below.")
        return

    # Header row
    h = st.columns([1.6, 1.6, 2.4, 0.9, 1.6, 1.1, 1.4])
    h[0].markdown("**Provider**")
    h[1].markdown("**API Key**")
    h[2].markdown("**Base URL**")
    h[3].markdown("**Enabled**")
    h[4].markdown("**Last Test**")
    h[5].markdown("**Status**")
    h[6].markdown("**Action**")

    for idx, prov in enumerate(providers):
        name = prov["name"]
        cols = st.columns([1.6, 1.6, 2.4, 0.9, 1.6, 1.1, 1.4])

        cols[0].write(f"**{name}**")
        cols[1].code(_mask_key(prov.get("api_key", "")), language=None)
        cols[2].code(prov.get("base_url", ""), language=None)

        # Enabled toggle — write back immediately
        enabled = cols[3].checkbox(
            "On",
            value=prov.get("enabled", False),
            key=f"_prov_enabled_{idx}",
            label_visibility="collapsed",
        )
        if enabled != prov.get("enabled"):
            st.session_state.ext_providers[idx]["enabled"] = enabled
            prov["enabled"] = enabled

        cols[4].write(st.session_state.ext_last_test.get(name, "—"))

        test_status = st.session_state.ext_test_status.get(name, "Unknown")
        cols[5].write(_status_pill(test_status))

        # Test-connection button — placeholder (real impl would ping the endpoint)
        if cols[6].button("🔌 Test", key=f"_prov_test_{idx}", use_container_width=True):
            with st.spinner(f"Testing {name}…"):
                # Simulated outcome: enabled + key-set -> OK, otherwise Failed.
                has_key = bool(prov.get("api_key"))
                ok = enabled and has_key
                st.session_state.ext_last_test[name] = _now_iso()
                st.session_state.ext_test_status[name] = "OK" if ok else "Failed"
            st.rerun()

    # Bulk actions
    st.markdown("")
    b1, b2, b3, _ = st.columns([1.2, 1.2, 1.2, 4])
    if b1.button("✅ Enable all", key="_prov_enable_all", use_container_width=True):
        for p in st.session_state.ext_providers:
            p["enabled"] = True
        st.rerun()
    if b2.button("⛔ Disable all", key="_prov_disable_all", use_container_width=True):
        for p in st.session_state.ext_providers:
            p["enabled"] = False
        st.rerun()
    if b3.button("🧪 Test all enabled", key="_prov_test_all", use_container_width=True):
        for name, p in [
            (p["name"], p) for p in st.session_state.ext_providers if p.get("enabled")
        ]:
            st.session_state.ext_last_test[name] = _now_iso()
            st.session_state.ext_test_status[name] = "OK" if p.get("api_key") else "Failed"
        st.rerun()


def _add_provider_form() -> None:
    """Form for adding a new API provider."""
    with st.form(key="_add_provider_form", clear_on_submit=True):
        st.markdown("#### ➕ Add a New Provider")
        c1, c2 = st.columns([1, 2])
        with c1:
            name = st.text_input(
                "Provider name",
                placeholder="e.g. IEX Cloud",
                help="Human-readable identifier used in the providers table.",
            )
        with c2:
            api_key = st.text_input(
                "API key",
                type="password",
                placeholder="Paste the secret key here",
                help="Stored only in this session.",
            )
        base_url = st.text_input(
            "Base URL",
            placeholder="https://api.example.com/v1",
            help="Root endpoint the provider exposes.",
        )
        enabled = st.checkbox(
            "Enable immediately",
            value=True,
            help="Off if you just want to register the key for later.",
        )
        submitted = st.form_submit_button("Add provider", use_container_width=True)

    if submitted:
        clean_name = (name or "").strip()
        clean_url = (base_url or "").strip()
        if not clean_name:
            st.error("Provider name is required.")
            return
        if not clean_url:
            st.error("Base URL is required.")
            return
        if any(p["name"].lower() == clean_name.lower()
               for p in st.session_state.ext_providers):
            st.error(f"A provider named '{clean_name}' already exists.")
            return

        st.session_state.ext_providers.append({
            "name": clean_name,
            "api_key": api_key or "",
            "base_url": clean_url,
            "enabled": enabled,
        })
        st.success(f"Added provider '{clean_name}'.")
        st.rerun()


# --------------------------------------------------------------------------- #
# Section B — Website Crawler
# --------------------------------------------------------------------------- #

def _crawler_summary_metrics() -> None:
    """Show quick counts for crawler targets."""
    targets = st.session_state.ext_crawler_targets
    status_map = st.session_state.ext_crawl_status

    total = len(targets)
    running = sum(1 for t in targets if status_map.get(t["url"]) == "Running")
    compliant = sum(1 for t in targets if t.get("robots_txt_compliant"))
    total_pages = sum(int(t.get("pages_scraped", 0)) for t in targets)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Targets", total)
    c2.metric("Running", running)
    c3.metric("Robots-compliant", f"{compliant}/{total}")
    c4.metric("Total pages scraped", total_pages)


def _crawler_table() -> None:
    """Render the crawler-targets table with per-row controls."""
    st.markdown("#### Crawler Targets")

    targets = st.session_state.ext_crawler_targets
    status_map = st.session_state.ext_crawl_status

    if not targets:
        st.info("No crawler targets configured. Add one below.")
        return

    h = st.columns([2.4, 1.0, 1.4, 1.0, 1.0, 1.0, 1.6])
    h[0].markdown("**URL**")
    h[1].markdown("**Frequency**")
    h[2].markdown("**Last Crawl**")
    h[3].markdown("**Pages**")
    h[4].markdown("**Status**")
    h[5].markdown("**Robots.txt**")
    h[6].markdown("**Actions**")

    for idx, t in enumerate(targets):
        url = t["url"]
        cols = st.columns([2.4, 1.0, 1.4, 1.0, 1.0, 1.0, 1.6])

        cols[0].code(url, language=None)
        cols[1].write(f"{int(t.get('crawl_frequency_minutes', 0))} min")
        cols[2].write(t.get("last_crawl", "—"))
        cols[3].write(int(t.get("pages_scraped", 0)))

        cur_status = status_map.get(url, t.get("status", "Idle"))
        cols[4].write(_status_pill(cur_status))

        robots_ok = bool(t.get("robots_txt_compliant"))
        cols[5].write("✅ Yes" if robots_ok else "❌ No")

        # Per-row start/stop
        a, b = cols[6].columns(2)
        is_running = cur_status == "Running"
        if a.button(
            "▶" if not is_running else "•",
            key=f"_crawl_start_{idx}",
            disabled=is_running or not robots_ok,
            help="Start crawl" if not is_running else "Already running",
            use_container_width=True,
        ):
            st.session_state.ext_crawl_status[url] = "Running"
            st.session_state.ext_crawler_targets[idx]["status"] = "Running"
            st.rerun()
        if b.button(
            "■",
            key=f"_crawl_stop_{idx}",
            disabled=not is_running,
            help="Stop crawl",
            use_container_width=True,
        ):
            st.session_state.ext_crawl_status[url] = "Stopped"
            st.session_state.ext_crawler_targets[idx]["status"] = "Stopped"
            st.rerun()

    # Bulk controls
    st.markdown("")
    b1, b2, b3, _ = st.columns([1.2, 1.2, 1.2, 4])
    if b1.button("▶ Start all", key="_crawl_start_all", use_container_width=True):
        for t in st.session_state.ext_crawler_targets:
            if t.get("robots_txt_compliant"):
                st.session_state.ext_crawl_status[t["url"]] = "Running"
                t["status"] = "Running"
        st.rerun()
    if b2.button("■ Stop all", key="_crawl_stop_all", use_container_width=True):
        for t in st.session_state.ext_crawler_targets:
            st.session_state.ext_crawl_status[t["url"]] = "Stopped"
            t["status"] = "Stopped"
        st.rerun()
    if b3.button("🕒 Mark all crawled now", key="_crawl_mark_all", use_container_width=True):
        now = _now_iso()
        for t in st.session_state.ext_crawler_targets:
            t["last_crawl"] = now
        st.rerun()


def _add_url_form() -> None:
    """Form for adding a new crawler target."""
    with st.form(key="_add_url_form", clear_on_submit=True):
        st.markdown("#### ➕ Add a Crawler Target")
        c1, c2 = st.columns([2.4, 1.4])
        with c1:
            url = st.text_input(
                "URL",
                placeholder="https://example.com",
                help="Starting page for the scraper.",
            )
        with c2:
            category = st.text_input(
                "Category (optional)",
                placeholder="e.g. NFT Drops",
            )
        c3, c4 = st.columns([1.4, 1.6])
        with c3:
            freq = st.number_input(
                "Crawl frequency (minutes)",
                min_value=1,
                max_value=10080,  # 1 week
                value=60,
                step=1,
            )
        with c4:
            robots_ok = st.checkbox(
                "Robots.txt compliant",
                value=True,
                help="Uncheck to register a target you will manually gate.",
            )
        submitted = st.form_submit_button("Add target", use_container_width=True)

    if submitted:
        clean_url = (url or "").strip()
        if not clean_url:
            st.error("URL is required.")
            return
        if not clean_url.startswith(("http://", "https://")):
            st.error("URL must start with http:// or https://.")
            return
        if any(t["url"].lower() == clean_url.lower()
               for t in st.session_state.ext_crawler_targets):
            st.error(f"Target '{clean_url}' already exists.")
            return

        new_target = {
            "url": clean_url,
            "category": (category or "").strip(),
            "crawl_frequency_minutes": int(freq),
            "robots_txt_compliant": bool(robots_ok),
            "pages_scraped": 0,
            "status": "Idle",
            "last_crawl": "—",
        }
        st.session_state.ext_crawler_targets.append(new_target)
        st.success(f"Added crawler target '{clean_url}'.")
        st.rerun()


def _schedule_form() -> None:
    """Cron-like schedule config (global default for new targets)."""
    with st.form(key="_schedule_form"):
        st.markdown("#### ⏰ Crawl Schedule")
        st.caption(
            "Default interval applied to newly added targets. "
            "Existing targets keep their per-row frequency unless edited."
        )
        c1, c2 = st.columns([1.6, 1.4])
        with c1:
            preset = st.selectbox(
                "Preset",
                options=_CRON_PRESETS,
                index=_CRON_PRESETS.index(
                    st.session_state.ext_global_schedule
                )
                if st.session_state.ext_global_schedule in _CRON_PRESETS
                else 2,
                help="Quick presets; switch to 'Custom' to set arbitrary minutes.",
            )
            st.session_state.ext_global_schedule = preset

        with c2:
            custom_min = st.number_input(
                "Interval (minutes)",
                min_value=1,
                max_value=10080,
                value=int(st.session_state.ext_global_interval_min),
                step=1,
                help="Used when 'Custom' is selected below.",
            )

        c3, c4 = st.columns([1, 1])
        apply_preset = c3.form_submit_button(
            "Apply preset to all targets",
            use_container_width=True,
        )
        apply_custom = c4.form_submit_button(
            "Apply custom minutes to all targets",
            use_container_width=True,
        )

    # Map presets to minutes
    preset_to_minutes: dict[str, int] = {
        "Every 5 minutes": 5,
        "Every 15 minutes": 15,
        "Every 30 minutes": 30,
        "Hourly": 60,
        "Every 3 hours": 180,
        "Every 6 hours": 360,
        "Daily": 1440,
        "Weekly": 10080,
    }

    if apply_preset:
        minutes = preset_to_minutes.get(preset, int(custom_min))
        for t in st.session_state.ext_crawler_targets:
            t["crawl_frequency_minutes"] = minutes
        st.session_state.ext_global_interval_min = minutes
        st.success(f"Applied '{preset}' ({minutes} min) to {len(st.session_state.ext_crawler_targets)} target(s).")

    if apply_custom:
        for t in st.session_state.ext_crawler_targets:
            t["crawl_frequency_minutes"] = int(custom_min)
        st.session_state.ext_global_interval_min = int(custom_min)
        st.success(f"Applied custom interval ({int(custom_min)} min) to {len(st.session_state.ext_crawler_targets)} target(s).")


def _scraped_preview() -> None:
    """Recent scraped items preview."""
    st.markdown("#### 📦 Recent Scraped Items")
    log = st.session_state.ext_crawl_log or []

    if not log:
        st.caption(
            "_No scraped items yet. In production this table is fed by the "
            "crawler worker; for now it shows the items recorded in this session._"
        )
        # Seed a couple of demo rows so the table is not empty on first load
        seed = [
            {
                "id": str(uuid.uuid4())[:8],
                "timestamp": (datetime.now(UTC) - timedelta(minutes=7)).replace(microsecond=0).isoformat(),
                "url": "https://defillama.com",
                "title": "New protocol listed: ExampleDEX — TVL $12.4M",
                "snippet": "Chain: Ethereum • Category: DEX • Change 24h: +3.2%",
            },
            {
                "id": str(uuid.uuid4())[:8],
                "timestamp": (datetime.now(UTC) - timedelta(minutes=22)).replace(microsecond=0).isoformat(),
                "url": "https://icodrops.com",
                "title": "ICO upcoming: SampleToken — Round: Seed",
                "snippet": "Raise: $2.5M • Vesting: 12m cliff, 36m linear",
            },
        ]
        st.session_state.ext_crawl_log = seed
        log = seed

    df = pd.DataFrame(log)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.TextColumn("ID", width="small"),
            "timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
            "url": st.column_config.LinkColumn("Source", width="medium"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "snippet": st.column_config.TextColumn("Snippet", width="large"),
        },
    )

    c1, c2, _ = st.columns([1.2, 1.2, 4])
    if c1.button("🧹 Clear log", key="_log_clear", use_container_width=True):
        st.session_state.ext_crawl_log = []
        st.rerun()
    if c2.button("➕ Add demo entry", key="_log_demo", use_container_width=True):
        demo = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": _now_iso(),
            "url": "https://coinmarketcap.com",
            "title": "Demo scrape — top gainer XYZ +18.4%",
            "snippet": "Volume 24h: $412M • Market cap: $2.1B",
        }
        st.session_state.ext_crawl_log.insert(0, demo)
        # Keep only the most recent 50 entries
        st.session_state.ext_crawl_log = st.session_state.ext_crawl_log[:50]
        st.rerun()


# --------------------------------------------------------------------------- #
# Top-level renderer
# --------------------------------------------------------------------------- #

def render_external_data_tab() -> None:
    """Render the External Data tab inside a Streamlit page."""
    st.markdown("### 🌐 External Data")
    st.caption(
        "Manage third-party API providers and configure the website crawler "
        "for ICO/DeFi/crypto research feeds."
    )

    _init_state()

    api_tab, crawler_tab = st.tabs(["🔌 API Providers", "🕷️ Website Crawler"])

    with api_tab:
        st.markdown("---")
        _providers_summary_metrics()
        st.markdown("---")
        _providers_table()
        st.markdown("---")
        _add_provider_form()

    with crawler_tab:
        st.markdown("---")
        _crawler_summary_metrics()
        st.markdown("---")
        _crawler_table()
        st.markdown("---")
        _add_url_form()
        st.markdown("---")
        _schedule_form()
        st.markdown("---")
        _scraped_preview()

    st.markdown("---")
    if st.button("🔄 Refresh external data", key="_refresh_external_data"):
        st.cache_data.clear()
        st.rerun()
