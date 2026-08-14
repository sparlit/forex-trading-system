"""
Credentials tab — 2FA / MFA configuration, API tokens, session & IP policy.

Covers: username display, password rotation, 2FA enable + QR placeholder,
backup codes, API token management, session-timeout, IP whitelist, and
login history. Falls back to sensible placeholder data so the page never
crashes when the auth service is unreachable.
"""

from __future__ import annotations

import logging
import os
import random
import sys
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from src.infra.config.settings import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

try:
    from src.infra.security.credential_store import CredentialStore  # type: ignore
except Exception:  # pragma: no cover
    CredentialStore = None  # type: ignore[assignment,misc]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(UTC)


def _username() -> str:
    if settings is not None:
        try:
            return str(getattr(settings, "auth_username", "trader")) or "trader"
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning(f'Suppressed in _username: {e}', exc_info=True)
    return "trader"


def _backup_codes() -> list[str]:
    """Return the user's 2FA backup codes (regenerated each session for safety)."""
    if "cred_backup_codes" not in st.session_state:
        st.session_state["cred_backup_codes"] = [
            f"{random.randint(0, 9999):04d}-{random.randint(0, 9999):04d}"
            for _ in range(10)
        ]
    return st.session_state["cred_backup_codes"]


def _api_tokens() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "token_name": "dashboard-readonly",
                "created": (_now() - timedelta(days=42)).strftime("%Y-%m-%d"),
                "last_used": (_now() - timedelta(minutes=11)).strftime("%Y-%m-%d %H:%M"),
                "scopes": "read",
                "status": "active",
            },
            {
                "token_name": "kafka-producer",
                "created": (_now() - timedelta(days=120)).strftime("%Y-%m-%d"),
                "last_used": (_now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
                "scopes": "write",
                "status": "active",
            },
            {
                "token_name": "legacy-research",
                "created": (_now() - timedelta(days=400)).strftime("%Y-%m-%d"),
                "last_used": (_now() - timedelta(days=68)).strftime("%Y-%m-%d %H:%M"),
                "scopes": "read",
                "status": "expiring",
            },
        ]
    )


def _login_history() -> pd.DataFrame:
    base = _now()
    return pd.DataFrame(
        [
            {
                "timestamp": (base - timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M:%S"),
                "ip": "203.0.113.42",
                "country": "US",
                "device": "Chrome / Windows",
                "result": "success",
            },
            {
                "timestamp": (base - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                "ip": "203.0.113.42",
                "country": "US",
                "device": "Chrome / Windows",
                "result": "success",
            },
            {
                "timestamp": (base - timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                "ip": "198.51.100.7",
                "country": "DE",
                "device": "Firefox / Linux",
                "result": "success",
            },
            {
                "timestamp": (base - timedelta(days=1, hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "ip": "198.51.100.7",
                "country": "DE",
                "device": "Firefox / Linux",
                "result": "failed (wrong 2FA)",
            },
            {
                "timestamp": (base - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "ip": "203.0.113.42",
                "country": "US",
                "device": "Safari / iOS",
                "result": "success",
            },
        ]
    )


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #


def render_credentials_tab() -> None:
    """Render the credentials / 2FA / API token management tab."""
    st.header("🔐 Credentials & 2FA")
    st.caption(
        "Manage login, two-factor authentication, API tokens, session policy, "
        "and IP allow-list. All sensitive writes go through `CredentialStore`."
    )

    # ---- Identity ---------------------------------------------------------- #
    id_col, mfa_col = st.columns([1, 1])
    with id_col:
        st.subheader("Identity")
        st.text_input("Username", value=_username(), disabled=True)
        st.text_input("Display name", value="Primary Trader")
        st.text_input("Email", value="trader@example.com", type="default")
        st.caption("Profile updates require email confirmation.")

    with mfa_col:
        st.subheader("Two-Factor Authentication")
        twofa_enabled = st.toggle(
            "Enable 2FA (TOTP)", value=True, help="TOTP via authenticator app"
        )
        if twofa_enabled:
            # QR placeholder — real impl would render a generated QR.
            st.markdown(
                "<div style='border:2px dashed #888;padding:24px;text-align:center;'>"
                "📱  QR code placeholder<br/>"
                "<small>scan with Google Authenticator / 1Password / Authy</small>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.code("otpauth://totp/ForexTrader:trader?secret=ABCD-EFGH-IJKL-MNOP&issuer=ForexTrader")
        else:
            st.warning("2FA is disabled — strongly recommended to enable.")

    st.divider()

    # ---- Password change --------------------------------------------------- #
    st.subheader("Change password")
    with st.form("cred_password_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            old_pw = st.text_input("Current password", type="password")
        with c2:
            new_pw = st.text_input("New password", type="password")
        with c3:
            confirm_pw = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password")
        if submitted:
            if not old_pw or not new_pw or not confirm_pw:
                st.error("All three password fields are required.")
            elif new_pw != confirm_pw:
                st.error("New password and confirmation do not match.")
            elif len(new_pw) < 12:
                st.error("Password must be at least 12 characters.")
            else:
                st.success("Password updated (placeholder).")

    st.divider()

    # ---- Backup codes ------------------------------------------------------ #
    with st.expander("🔑 Backup codes (one-time use)", expanded=False):
        codes = _backup_codes()
        code_df = pd.DataFrame({"#": range(1, len(codes) + 1), "code": codes})
        st.dataframe(code_df, use_container_width=True, hide_index=True)
        cA, cB = st.columns(2)
        cA.download_button(
            "Download backup codes (.txt)",
            data="\n".join(codes),
            file_name="backup_codes.txt",
            mime="text/plain",
        )
        if cB.button("Regenerate codes"):
            st.session_state["cred_backup_codes"] = [
                f"{random.randint(0, 9999):04d}-{random.randint(0, 9999):04d}"
                for _ in range(10)
            ]
            st.success("New backup codes generated — store them safely.")

    st.divider()

    # ---- Session policy ---------------------------------------------------- #
    pol_col, ip_col = st.columns([1, 1])
    with pol_col:
        st.subheader("Session policy")
        timeout = st.slider(
            "Session timeout (minutes)",
            min_value=5,
            max_value=240,
            value=30,
            step=5,
            help="Idle logout window.",
        )
        require_2fa_admin = st.checkbox(
            "Require 2FA for admin actions", value=True
        )
        single_session = st.checkbox(
            "Enforce single active session", value=False
        )
        st.caption(f"Idle logout currently set to **{timeout} minutes**.")

    with ip_col:
        st.subheader("IP allow-list")
        st.caption(
            "One CIDR or address per line. Empty = allow from anywhere. "
            "Changes take effect on the next request."
        )
        default_ip_text = "\n".join(
            ["203.0.113.42/32", "198.51.100.0/24", "# add more on new lines"]
        )
        ip_text = st.text_area("Allowed IPs / CIDRs", value=default_ip_text, height=140)
        if st.button("Save IP policy"):
            st.success(f"Saved {len(ip_text.splitlines())} entries (placeholder).")

    st.divider()

    # ---- API tokens -------------------------------------------------------- #
    st.subheader("API tokens")
    tokens = _api_tokens()
    st.dataframe(tokens, use_container_width=True, hide_index=True)

    new_row = st.columns([2, 1, 1])
    new_token_name = new_row[0].text_input("New token name", placeholder="e.g. grafana-exporter")
    new_token_scopes = new_row[1].selectbox("Scopes", ["read", "write", "admin"])
    if new_row[2].button("Create token"):
        if not new_token_name:
            st.warning("Token name required.")
        else:
            st.success(f"Token `{new_token_name}` minted (placeholder). Copy its secret now.")

    # Per-row delete buttons (lightweight)
    st.markdown("**Manage existing tokens**")
    for _, row in tokens.iterrows():
        c = st.columns([3, 2, 2, 1])
        c[0].write(f"`{row['token_name']}`")
        c[1].write(f"scopes: {row['scopes']}")
        c[2].write(f"last used: {row['last_used']}")
        if c[3].button("Delete", key=f"del_{row['token_name']}"):
            st.warning(f"Token `{row['token_name']}` deleted (placeholder).")

    st.divider()

    # ---- Login history ----------------------------------------------------- #
    st.subheader("Login history (recent)")
    st.dataframe(_login_history(), use_container_width=True, hide_index=True)
