"""
Settings tab — user preferences and configuration.

Covers: theme, language, timezone, risk profile, position/leverage limits,
auto-start, notification channels, and a secured API-keys section.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from typing import Any

import streamlit as st

# Project-root path bootstrap (so settings singleton + risk YAML resolve)
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from src.infra.config.settings import settings  # type: ignore
except Exception:  # pragma: no cover - dashboard must still render if config missing
    settings = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Session-state helpers
# --------------------------------------------------------------------------- #

_DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "language": "en",
    "timezone": "UTC",
    "risk_profile": "balanced",
    "max_daily_loss_pct": 5.0,
    "max_open_positions": 10,
    "leverage": 3.0,
    "auto_start_on_launch": True,
    "notif_email": False,
    "notif_telegram": True,
    "notif_discord": False,
    "email_recipient": "",
    "telegram_chat_id": "",
    "discord_webhook_url": "",
    "api_key_unlocked": False,
}


def _init_state() -> None:
    for k, v in _DEFAULTS.items():
        st.session_state.setdefault(k, v)


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #

def _appearance_section() -> None:
    st.markdown("#### 🎨 Appearance & Locale")
    col1, col2, col3 = st.columns(3)

    with col1:
        theme = st.selectbox(
            "Theme",
            options=["dark", "light", "auto"],
            index=["dark", "light", "auto"].index(st.session_state.theme),
            help="Dashboard color theme. 'auto' follows OS preference.",
            key="_theme_box",
        )
        st.session_state.theme = theme

    with col2:
        lang = st.selectbox(
            "Language",
            options=["en", "es", "fr", "de", "ja", "zh"],
            index=["en", "es", "fr", "de", "ja", "zh"].index(st.session_state.language),
            help="UI language for labels and messages.",
            key="_lang_box",
        )
        st.session_state.language = lang

    with col3:
        tz_options = [
            "UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
            "Europe/London", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai",
            "Australia/Sydney",
        ]
        cur_tz = st.session_state.timezone if st.session_state.timezone in tz_options else "UTC"
        tz = st.selectbox(
            "Timezone",
            options=tz_options,
            index=tz_options.index(cur_tz),
            help="Timezone used for all displayed timestamps.",
            key="_tz_box",
        )
        st.session_state.timezone = tz


def _trading_section() -> None:
    st.markdown("#### 💼 Trading Profile")
    profile = st.select_slider(
        "Risk Profile",
        options=["conservative", "balanced", "aggressive"],
        value=st.session_state.risk_profile,
        help=(
            "Conservative: small size, tight stops. "
            "Balanced: medium. "
            "Aggressive: larger size, wider stops."
        ),
        key="_profile_slider",
    )
    st.session_state.risk_profile = profile

    # Profile presets — applied to the three limit fields
    presets = {
        "conservative": (2.0, 5, 1.0),
        "balanced": (5.0, 10, 3.0),
        "aggressive": (10.0, 25, 7.0),
    }
    if st.button(
        "Apply profile preset",
        help="Overwrites the three fields below with recommended values.",
        key="_apply_preset",
    ):
        loss, pos, lev = presets[profile]
        st.session_state.max_daily_loss_pct = loss
        st.session_state.max_open_positions = pos
        st.session_state.leverage = lev
        st.rerun()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input(
            "Max Daily Loss (%)",
            min_value=0.5,
            max_value=50.0,
            value=float(st.session_state.max_daily_loss_pct),
            step=0.5,
            key="_max_daily_loss_pct",
            help="Hard stop on portfolio drawdown per day.",
        )
        st.session_state.max_daily_loss_pct = st.session_state._max_daily_loss_pct

    with col2:
        st.number_input(
            "Max Open Positions",
            min_value=1,
            max_value=100,
            value=int(st.session_state.max_open_positions),
            step=1,
            key="_max_open_positions",
        )
        st.session_state.max_open_positions = st.session_state._max_open_positions

    with col3:
        st.number_input(
            "Leverage (×)",
            min_value=1.0,
            max_value=50.0,
            value=float(st.session_state.leverage),
            step=0.5,
            key="_leverage",
        )
        st.session_state.leverage = st.session_state._leverage

    st.checkbox(
        "Auto-start on launch",
        value=bool(st.session_state.auto_start_on_launch),
        key="_auto_start",
        help="Boot the trading loop automatically when the dashboard opens.",
    )
    st.session_state.auto_start_on_launch = st.session_state._auto_start


def _notifications_section() -> None:
    st.markdown("#### 🔔 Notification Preferences")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.checkbox(
            "📧 Email",
            value=bool(st.session_state.notif_email),
            key="_notif_email",
            help="Send alerts to your email address.",
        )
        st.session_state.notif_email = st.session_state._notif_email
        st.text_input(
            "Email recipient",
            value=str(st.session_state.email_recipient),
            placeholder="trader@example.com",
            key="_email_recipient",
            disabled=not st.session_state.notif_email,
        )
        st.session_state.email_recipient = st.session_state._email_recipient

    with col2:
        st.checkbox(
            "📱 Telegram",
            value=bool(st.session_state.notif_telegram),
            key="_notif_telegram",
        )
        st.session_state.notif_telegram = st.session_state._notif_telegram
        st.text_input(
            "Telegram chat ID",
            value=str(st.session_state.telegram_chat_id),
            placeholder="123456789",
            key="_telegram_chat_id",
            disabled=not st.session_state.notif_telegram,
        )
        st.session_state.telegram_chat_id = st.session_state._telegram_chat_id

    with col3:
        st.checkbox(
            "💬 Discord",
            value=bool(st.session_state.notif_discord),
            key="_notif_discord",
        )
        st.session_state.notif_discord = st.session_state._notif_discord
        st.text_input(
            "Discord webhook URL",
            value=str(st.session_state.discord_webhook_url),
            placeholder="https://discord.com/api/webhooks/…",
            key="_discord_webhook_url",
            disabled=not st.session_state.notif_discord,
            type="password",
        )
        st.session_state.discord_webhook_url = st.session_state._discord_webhook_url


def _api_keys_section() -> None:
    """API-key editor with a simple unlock gate (educational stub).

    Real production deployments must use the secret manager in
    `src/infra/config/secrets.py` (Vault / Azure Key Vault / EnvProvider).
    Keys here are kept in `st.session_state` only and never persisted.
    """
    st.markdown("#### 🔐 API Keys (secured)")
    st.caption(
        "Values are held in session state only. In production, "
        "rotate and store them via Vault / Azure Key Vault — never in plaintext config."
    )

    unlocked = st.session_state.api_key_unlocked
    col1, col2 = st.columns([3, 1])
    with col1:
        if not unlocked:
            pw = st.text_input(
                "Unlock passphrase",
                type="password",
                key="_unlock_pw",
                help="Demo gate. Real systems use SSO / RBAC, not a local password.",
            )
        else:
            pw = ""
    with col2:
        if not unlocked:
            if st.button("🔓 Unlock", use_container_width=True, key="_unlock_btn"):
                if pw:
                    st.session_state.api_key_unlocked = True
                    st.rerun()
                else:
                    st.error("Enter a passphrase to unlock.")
        else:
            if st.button("🔒 Lock", use_container_width=True, key="_lock_btn"):
                st.session_state.api_key_unlocked = False
                st.rerun()

    if unlocked:
        st.markdown("##### MT5")
        c1, c2 = st.columns(2)
        c1.text_input("MT5 login", value="", key="_mt5_login", type="password")
        c2.text_input("MT5 password", value="", key="_mt5_password", type="password")
        st.text_input("MT5 server", value="", key="_mt5_server", type="password")

        st.markdown("##### cTrader")
        c1, c2 = st.columns(2)
        c1.text_input("cTrader client_id", value="", key="_ctrader_client_id", type="password")
        c2.text_input("cTrader client_secret", value="", key="_ctrader_client_secret", type="password")

        st.markdown("##### Data providers")
        st.text_input("Twelve Data API key", value="", key="_twelvedata_key", type="password")
        st.text_input("Alpha Vantage API key", value="", key="_alpha_key", type="password")
        st.text_input("Polygon API key", value="", key="_polygon_key", type="password")
        st.text_input("Finnhub API key", value="", key="_finnhub_key", type="password")

        st.markdown("##### CCXT exchanges")
        st.caption("Format: `exchange:api_key:api_secret` per line")
        st.text_area("CCXT keys", value="", key="_ccxt_keys", height=100)

        st.warning(
            "🔑 These values live in `st.session_state` only. Save them via the "
            "secret-manager CLI (`hermes secrets set …`) or your platform's secret store.",
            icon="⚠️",
        )


def _system_info_section() -> None:
    st.markdown("#### 🧬 System Information")
    cols = st.columns(4)
    cols[0].metric("App name", settings.app_name if settings else "forex-trading-system")
    cols[1].metric(
        "Environment",
        settings.environment.value if settings and hasattr(settings.environment, "value") else "—",
    )
    cols[2].metric(
        "Dashboard port",
        str(settings.dashboard_port) if settings else "8501",
    )
    cols[3].metric(
        "Sim mode",
        "ON" if (settings and settings.simulation_mode) else "OFF",
    )

    with st.expander("Raw settings (read-only)", expanded=False):
        if settings is not None:
            data = settings.model_dump() if hasattr(settings, "model_dump") else settings.dict()
            for masked in (
                "mt5_password", "ctrader_client_secret", "ctrader_access_token",
                "ctrader_refresh_token", "twelve_data_api_key", "alpha_vantage_api_key",
                "polygon_api_key", "finnhub_api_key", "secret_key",
            ):
                if data.get(masked):
                    data[masked] = "***"
            st.json(data)
        else:
            st.info("Settings singleton not importable — environment may be missing.")


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #

def render_settings_tab() -> None:
    """Render the Settings tab inside a Streamlit page."""
    _init_state()
    st.markdown("### ⚙️ Settings")
    st.caption(f"Last opened: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ---- Batch-save form ------------------------------------------------- #
    # Wraps appearance / trading / notifications so all writes commit on
    # a single Save click (avoids per-widget reruns and keeps the page snappy).
    with st.form("settings_form", clear_on_submit=False):
        _appearance_section()
        st.markdown("---")
        _trading_section()
        st.markdown("---")
        _notifications_section()

        st.markdown("---")
        save_col, reset_col, _spacer = st.columns([1, 1, 4])
        with save_col:
            submitted = st.form_submit_button(
                "💾 Save settings", type="primary", use_container_width=True,
            )
        with reset_col:
            reset_clicked = st.form_submit_button(
                "↩️ Reset to defaults", use_container_width=True,
            )
        if submitted:
            st.success(
                "Settings committed to session. Persist with `hermes config set …` "
                "or your platform secret store.",
                icon="✅",
            )
        if reset_clicked:
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()

    st.markdown("---")
    _api_keys_section()
    st.markdown("---")
    _system_info_section()
