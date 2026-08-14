"""
Security Authentication tab — User credentials, 2FA tokens, B-Unit hardware auth.

Vibrant dark-purple/silver theme. Four sections:
    (a) User Credentials Management.
    (b) 2FA Dynamic Tokens visualization.
    (c) B-Unit hardware auth status.
    (d) Security Audit Log.

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

_THEME = {
    "bg": "#0e1117",
    "panel": "#1a0a1f",
    "panel2": "#12071a",
    "text": "#f5f3ff",
    "muted": "#c4b5fd",
    "primary": "#7c3aed",        # dark purple
    "secondary": "#a78bfa",
    "accent": "#d8b4fe",
    "warn": "#fbbf24",
    "danger": "#ef4444",
    "ok": "#34d399",
}


def _users() -> pd.DataFrame:
    rows = []
    now = datetime.now(UTC)
    for i in range(8):
        username = f"user{i+1}"
        role = random.choice(["admin", "trader", "analyst", "viewer"])
        status = random.choice(["ACTIVE", "DISABLED", "LOCKED"])
        last_login = (now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M")
        failed = random.randint(0, 5)
        twofa = random.choice([True, False])
        created = (now - timedelta(days=random.randint(90, 365))).strftime("%Y-%m-%d")
        perms = ", ".join(random.sample(["read", "write", "trade", "audit", "config"], k=random.randint(1, 4)))
        rows.append({
            "username": username,
            "role": role,
            "status": status,
            "last_login": last_login,
            "failed_attempts": failed,
            "2fa_enabled": twofa,
            "created_date": created,
            "permissions": perms,
        })
    return pd.DataFrame(rows)


def _totp_tokens() -> pd.DataFrame:
    rows = []
    now = datetime.now(UTC)
    for user in ["user1", "user2", "admin"]:
        # Generate a 6-digit code and a countdown (seconds remaining out of 30)
        code = random.randint(100000, 999999)
        remaining = 30 - (now.second % 30)
        rows.append({"username": user, "totp_code": code, "seconds_remaining": remaining})
    return pd.DataFrame(rows)


def _bunit_status() -> pd.DataFrame:
    rows = []
    now = datetime.now(UTC)
    for dev_id in range(1, 5):
        status = random.choice(["OK", "WARN", "FAIL"])
        last_ch = (now - timedelta(seconds=random.randint(5, 300))).strftime("%Y-%m-%d %H:%M:%S")
        resp = random.randint(50, 250)
        cert_exp = (now + timedelta(days=random.randint(30, 365))).strftime("%Y-%m-%d")
        rows.append({
            "device_id": f"BUNIT-{dev_id}",
            "status": status,
            "last_challenge": last_ch,
            "response_time_ms": resp,
            "cert_expiry": cert_exp,
        })
    return pd.DataFrame(rows)


def _audit_log() -> pd.DataFrame:
    rows = []
    now = datetime.now(UTC)
    actions = ["login", "logout", "password_change", "2fa_setup", "permission_update", "failed_login"]
    resources = ["/admin", "/trade", "/report", "/settings", "/api/v1/orders"]
    for _ in range(30):
        ts = (now - timedelta(minutes=random.randint(0, 1440))).strftime("%Y-%m-%d %H:%M:%S")
        user = f"user{random.randint(1, 8)}"
        act = random.choice(actions)
        ip = f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
        resource = random.choice(resources)
        result = random.choice(["success", "denied"])
        risk = round(random.uniform(0.0, 9.9), 1)
        rows.append({
            "timestamp": ts,
            "user": user,
            "action": act,
            "ip_address": ip,
            "resource": resource,
            "result": result,
            "risk_score": risk,
        })
    return pd.DataFrame(rows)


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .sec-header {{
            background: linear-gradient(90deg, {_THEME['primary']}33, {_THEME['accent']}11);
            border-left: 4px solid {_THEME['primary']};
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
        }}
        .sec-card {{
            background: linear-gradient(135deg, {_THEME['panel']} 0%, {_THEME['panel2']} 100%);
            border: 1px solid {_THEME['primary']}44;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .totp-code {{
            font-family: monospace;
            font-size: 1.4rem;
            letter-spacing: 0.12rem;
            color: {_THEME['secondary']};
        }}
        .status-ok {{ color: {_THEME['ok']}; }}
        .status-warn {{ color: {_THEME['warn']}; }}
        .status-fail {{ color: {_THEME['danger']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sec_auth_tab() -> None:
    """Render the Security Authentication tab."""
    _inject_css()
    st.markdown(
        f"""
        <div class="sec-header">
            <h2 style="color:{_THEME['primary']}; margin:0;">🔒 Security Authentication — Users, 2FA, B-Unit</h2>
            <p style="color:{_THEME['muted']}; margin:4px 0 0 0;">
                Manage user credentials, view live TOTP codes, monitor hardware auth, and audit log.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # (a) User credentials
    st.markdown("### (a) User Credentials Management")
    df_users = _users()
    st.dataframe(
        df_users,
        hide_index=True,
        use_container_width=True,
        column_config={
            "username": st.column_config.TextColumn("Username", width="small"),
            "role": st.column_config.TextColumn("Role", width="small"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "last_login": st.column_config.TextColumn("Last Login", width="medium"),
            "failed_attempts": st.column_config.NumberColumn("Failed", format="%d"),
            "2fa_enabled": st.column_config.CheckboxColumn("2FA"),
            "created_date": st.column_config.TextColumn("Created", width="small"),
            "permissions": st.column_config.TextColumn("Permissions", width="large"),
        },
    )

    st.divider()

    # (b) 2FA TOTP visualization
    st.markdown("### (b) 2FA Dynamic Tokens")
    df_totp = _totp_tokens()
    cols = st.columns(len(df_totp))
    for col, (_, row) in zip(cols, df_totp.iterrows()):
        with col:
            st.markdown(f"**{row['username']}**")
            st.markdown(f"<div class='totp-code'>{row['totp_code']}</div>", unsafe_allow_html=True)
            st.progress(row['seconds_remaining'] / 30)
            st.caption(f"{row['seconds_remaining']}s remaining")

    st.divider()

    # (c) B-Unit hardware auth status
    st.markdown("### (c) B-Unit Hardware Authentication")
    df_bunit = _bunit_status()
    def _status_span(s: str) -> str:
        mapping = {"OK": "status-ok", "WARN": "status-warn", "FAIL": "status-fail"}
        cls = mapping.get(s, "status-warn")
        return f"<span class='{cls}'>{s}</span>"
    df_bunit_display = df_bunit.copy()
    df_bunit_display["status_span"] = df_bunit_display["status"].apply(_status_span)
    st.dataframe(
        df_bunit_display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "device_id": st.column_config.TextColumn("Device", width="medium"),
            "status_span": st.column_config.TextColumn("Status"),
            "status": None,
            "last_challenge": st.column_config.TextColumn("Last Challenge", width="medium"),
            "response_time_ms": st.column_config.NumberColumn("Resp ms", format="%d"),
            "cert_expiry": st.column_config.TextColumn("Cert Expiry", width="small"),
        },
    )

    st.divider()

    # (d) Security Audit Log
    st.markdown("### (d) Security Audit Log")
    df_audit = _audit_log()
    st.dataframe(
        df_audit,
        hide_index=True,
        use_container_width=True,
        column_config={
            "timestamp": st.column_config.TextColumn("Time", width="medium"),
            "user": st.column_config.TextColumn("User", width="small"),
            "action": st.column_config.TextColumn("Action", width="small"),
            "ip_address": st.column_config.TextColumn("IP", width="small"),
            "resource": st.column_config.TextColumn("Resource", width="medium"),
            "result": st.column_config.TextColumn("Result", width="small"),
            "risk_score": st.column_config.NumberColumn("Risk", format="%.1f"),
        },
    )

    st.caption(
        f"Last refreshed: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} \u2022 Synthetic auth data."
    )
