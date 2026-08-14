'''Security tab – vault, API rotation, 2FA, sessions, encryption, compliance.'''

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# Add project root to sys.path for optional imports (e.g., vault client)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

def _vault_status() -> str:
    # Placeholder – would query HashiCorp Vault or similar
    return "unsealed"

def _api_key_rotation() -> pd.DataFrame:
    data = [
        {"service": "MT5", "last_rotated": datetime.now(timezone.utc).strftime('%Y-%m-%d'), "next_rotation_days": 30},
        {"service": "AlphaVantage", "last_rotated": (datetime.now(timezone.utc) - pd.Timedelta(days=15)).strftime('%Y-%m-%d'), "next_rotation_days": 15},
    ]
    return pd.DataFrame(data)

def _session_table() -> pd.DataFrame:
    data = [
        {"session_id": "sess-001", "ip": "192.168.1.10", "user_agent": "Chrome", "created": datetime.now(timezone.utc), "last_active": datetime.now(timezone.utc)},
        {"session_id": "sess-002", "ip": "10.0.0.5", "user_agent": "Firefox", "created": datetime.now(timezone.utc), "last_active": datetime.now(timezone.utc)},
    ]
    return pd.DataFrame(data)

def _encryption_status() -> dict[str, str]:
    return {"at_rest": "enabled", "transit": "enabled"}

def _compliance_checklist() -> pd.DataFrame:
    data = [
        {"item": "KYC", "status": "PASS"},
        {"item": "AML", "status": "PASS"},
        {"item": "audit_trail", "status": "FAIL"},
        {"item": "data_retention", "status": "PASS"},
    ]
    return pd.DataFrame(data)


def _ip_whitelist() -> pd.DataFrame:
    """CIDR ranges currently whitelisted in the API gateway / Vault policy."""
    return pd.DataFrame([
        {"cidr": "127.0.0.1",       "purpose": "loopback"},
        {"cidr": "192.168.1.0/24",  "purpose": "office LAN"},
        {"cidr": "10.0.0.0/8",      "purpose": "VPN"},
    ])


def _data_retention() -> pd.DataFrame:
    """Retention windows per data class (days)."""
    return pd.DataFrame([
        {"data_class": "Tick data",         "retention_days": 365,  "policy": "GDPR-7y"},
        {"data_class": "Orders / fills",    "retention_days": 2555, "policy": "MiFID-7y"},
        {"data_class": "Application logs",  "retention_days": 90,   "policy": "internal"},
        {"data_class": "Audit log",         "retention_days": 2555, "policy": "MiFID-7y"},
        {"data_class": "ML feature store",  "retention_days": 180,  "policy": "internal"},
    ])


def _audit_log() -> pd.DataFrame:
    """Try to load from ``src.security.audit``; fall back to synthetic events."""
    try:  # pragma: no cover
        from src.security.audit import get_audit_logger  # type: ignore
        events = get_audit_logger().events()
        if events:
            return pd.DataFrame([e.to_dict() for e in events]).tail(50)
    except Exception:
        logging.getLogger(__name__).exception('Suppressed exception')
    # Synthetic fallback
    return pd.DataFrame([
        {"event_type": "login",            "actor": "trader", "outcome": "success", "ip": "10.0.0.5"},
        {"event_type": "config_change",    "actor": "admin",  "outcome": "success", "ip": "10.0.0.2"},
        {"event_type": "order_rejected",   "actor": "system", "outcome": "failure", "ip": "-"},
        {"event_type": "secret_access",    "actor": "trader", "outcome": "success", "ip": "10.0.0.5"},
    ])

def render_security_tab() -> None:
    st.title("\U0001F512 Security")
    st.subheader("Vault Status")
    st.metric("Vault", _vault_status().capitalize())

    st.subheader("API Key Rotation")
    st.dataframe(_api_key_rotation(), hide_index=True, use_container_width=True)

    st.subheader("2FA Enrollment")
    enrolled = st.checkbox("2FA Enabled", value=True)
    st.caption("Toggle to simulate enrollment status.")

    st.subheader("Active Sessions")
    st.dataframe(_session_table(), hide_index=True, use_container_width=True)

    st.subheader("Encryption Status")
    enc = _encryption_status()
    cols = st.columns(2)
    cols[0].metric("At Rest", enc["at_rest"].upper())
    cols[1].metric("Transit", enc["transit"].upper())

    st.subheader("Compliance Checklist")
    df = _compliance_checklist()
    # add badge styling via markdown
    def badge(row):
        color = "green" if row["status"] == "PASS" else "red"
        return f"<span style='color:{color};font-weight:bold'>{row['status']}</span>"
    df["status_badge"] = df.apply(badge, axis=1)
    st.write(df[['item','status_badge']].to_html(escape=False, index=False), unsafe_allow_html=True)

    st.subheader("IP Whitelist")
    st.dataframe(_ip_whitelist(), hide_index=True, use_container_width=True)

    st.subheader("Data Retention Policy")
    st.dataframe(_data_retention(), hide_index=True, use_container_width=True)

    st.subheader("Security Audit Log")
    st.dataframe(_audit_log(), hide_index=True, use_container_width=True)

    st.caption("Compliance items should be reviewed regularly.")
