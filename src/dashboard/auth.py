"""
User authentication for the Elite Autonomous Quantum Trading System.

Provides:
  - Startup login screen (username + password + optional 2FA/TOTP)
  - Session management with configurable timeout
  - Settings tab access gate (requires re-auth for sensitive config)
  - Role-based access (admin / trader / viewer)
  - Password hashing with PBKDF2 + salt
  - TOTP 2FA via pyotp (RFC 6238)
  - Failed-attempt lockout
  - Session persistence via st.session_state

Usage in app.py:
    from src.dashboard.auth import init_auth, require_login, require_settings_auth
import logging
    init_auth()               # call once at startup
    require_login()           # blocks all tabs until logged in
    require_settings_auth()   # blocks settings tab until re-authed
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any

import streamlit as st

# ── Optional TOTP ────────────────────────────────────────────────────────────
try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:
    _HAS_PYOTP = False

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_USERS_DB = os.path.join(
    os.path.expanduser("~"), ".forex_trading_system", "users.json"
)
SESSION_TIMEOUT_SEC = 1800  # 30 minutes
SETTINGS_REAUTH_SEC = 300    # 5 minutes — re-auth for settings after this
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SEC = 300  # 5 min lockout after too many failures


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class User:
    username: str
    password_hash: str
    salt: str
    role: str  # "admin" | "trader" | "viewer"
    totp_secret: str | None = None  # 2FA secret (base32), None = no 2FA
    enabled: bool = True


@dataclass
class AuthState:
    logged_in: bool = False
    username: str = ""
    role: str = ""
    login_time: float = 0.0
    last_activity: float = 0.0
    settings_auth_time: float = 0.0
    failed_attempts: int = 0
    locked_until: float = 0.0
    message: str = ""
    message_type: str = ""  # "success" | "error" | "warning" | "info"


# ── Password hashing (PBKDF2) ──────────────────────────────────────────────

def _hash_password(password: str, salt: str, iterations: int = 200_000) -> str:
    """Hash a password with PBKDF2 + salt."""
    pw_bytes = password.encode("utf-8")
    salt_bytes = bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac("sha256", pw_bytes, salt_bytes, iterations)
    return dk.hex()


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify password with constant-time comparison."""
    actual = _hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


def _gen_salt() -> str:
    """Generate a random 32-byte salt as hex string."""
    return os.urandom(32).hex()


# ── User database (JSON file, simplified) ────────────────────────────────────

def _ensure_users_db() -> dict[str, dict[str, Any]]:
    """Load/create the users database JSON file."""
    db_path = DEFAULT_USERS_DB
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if not os.path.exists(db_path):
        # Create default admin user
        salt = _gen_salt()
        default_pw = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
        default_users = {
            "admin": {
                "password_hash": _hash_password(default_pw, salt),
                "salt": salt,
                "role": "admin",
                "totp_secret": None,
                "enabled": True,
            }
        }
        import json
        with open(db_path, "w") as f:
            json.dump(default_users, f, indent=2)
        return default_users

    import json
    with open(db_path) as f:
        return json.load(f)


def _save_users_db(users: dict[str, dict[str, Any]]) -> None:
    """Save the users database."""
    db_path = DEFAULT_USERS_DB
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    import json
    with open(db_path, "w") as f:
        json.dump(users, f, indent=2)


# ── TOTP / 2FA ──────────────────────────────────────────────────────────────

def _verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against the secret."""
    if not _HAS_PYOTP:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)  # 1 step (30s) leeway
    except Exception:
        return False


def setup_totp(user: str) -> str | None:
    """Generate a new TOTP secret for a user. Returns the base32secret."""
    if not _HAS_PYOTP:
        return None
    secret = pyotp.random_base32()
    users = _ensure_users_db()
    if user in users:
        users[user]["totp_secret"] = secret
        _save_users_db(users)
    return secret


def get_totp_uri(secret: str, account: str, issuer: str = "ForexTradingSystem") -> str:
    """Get an otpauth:// URI for QR code generation."""
    if _HAS_PYOTP:
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=account, issuer_name=issuer)
    return ""


# ── Session state helpers ───────────────────────────────────────────────────

def _get_auth_state() -> AuthState:
    """Get or initialize auth state in streamlit session_state."""
    if "_auth_state" not in st.session_state:
        st.session_state._auth_state = AuthState()
    return st.session_state._auth_state


def _update_activity() -> None:
    """Update last activity timestamp."""
    auth = _get_auth_state()
    auth.last_activity = time.time()


# ── Public API ──────────────────────────────────────────────────────────────

def init_auth() -> None:
    """Initialize the authentication system. Call once at app startup."""
    _ensure_users_db()
    _get_auth_state()


def is_logged_in() -> bool:
    """Check if user is logged in with an active session."""
    auth = _get_auth_state()
    if not auth.logged_in:
        return False
    # Check session timeout
    if time.time() - auth.last_activity > SESSION_TIMEOUT_SEC:
        auth.logged_in = False
        auth.username = ""
        auth.role = ""
        auth.message = "Session expired. Please log in again."
        auth.message_type = "warning"
        return False
    _update_activity()
    return True


def has_settings_access() -> bool:
    """Check if user has recently re-authenticated for settings access."""
    auth = _get_auth_state()
    if not auth.logged_in:
        return False
    return (time.time() - auth.settings_auth_time) < SETTINGS_REAUTH_SEC


def require_login() -> bool:
    """Render login screen if not logged in. Returns True if logged in."""
    auth = _get_auth_state()

    # Check lockout
    if auth.locked_until > time.time():
        remaining = int(auth.locked_until - time.time())
        st.error(f"🔒 Account locked. Try again in {remaining} seconds.")
        st.stop()
        return False

    if is_logged_in():
        return True

    # ── Login UI ──────────────────────────────────────────────────────────
    _render_login_screen(auth)
    return False


def require_settings_auth() -> bool:
    """Gate for settings tab — requires recent re-authentication."""
    auth = _get_auth_state()

    if has_settings_access():
        return True

    # Show re-auth form
    st.warning("⚠️ Settings access requires re-authentication.")
    with st.form("settings_reauth"):
        col1, col2 = st.columns(2)
        with col1:
            reauth_pw = st.text_input("Confirm Password", type="password", key="settings_reauth_pw")
        with col2:
            reauth_2fa = st.text_input("2FA Code (if enabled)", key="settings_reauth_2fa")

        if st.form_submit_button("🔓 Unlock Settings", use_container_width=True):
            if _authenticate(auth.username, reauth_pw, reauth_2fa):
                auth.settings_auth_time = time.time()
                st.success("✅ Settings access granted.")
                st.rerun()
            else:
                st.error("❌ Re-authentication failed.")

    st.stop()
    return False


def logout() -> None:
    """Log out the current user."""
    auth = _get_auth_state()
    auth.logged_in = False
    auth.username = ""
    auth.role = ""
    auth.settings_auth_time = 0.0
    auth.message = "Logged out successfully."
    auth.message_type = "info"


def _render_login_screen(auth: AuthState) -> None:
    """Render the login screen."""
    # ── Logo ─────────────────────────────────────────────────────────────
    try:
        import streamlit.components.v1 as components
        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "assets", "logo_embed.html"
        )
        if os.path.exists(logo_path):
            with open(logo_path) as f:
                components.html(f.read(), height=220)
    except Exception:
        logging.getLogger(__name__).exception('Suppressed exception')

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='text-align: center; padding: 40px 0 20px;'>
            <h1 style='color: #58a6ff; font-size: 32px; margin: 0;'>
                🚀 Elite Autonomous Quantum Trading System
            </h1>
            <p style='color: #8b949e; font-size: 14px; margin-top: 8px;'>
                Please authenticate to access the dashboard
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Message ──────────────────────────────────────────────────────────
    if auth.message:
        if auth.message_type == "error":
            st.error(auth.message)
        elif auth.message_type == "warning":
            st.warning(auth.message)
        elif auth.message_type == "success":
            st.success(auth.message)
        else:
            st.info(auth.message)

    # ── Login Form ────────────────────────────────────────────────────────
    col_login, col_spacer = st.columns([2, 1])
    with col_login:
        with st.form("login_form"):
            username = st.text_input("👤 Username", value="", key="login_username")
            password = st.text_input("🔑 Password", value="", type="password", key="login_password")
            totp_code = st.text_input(
                "🔐 2FA Code (if enabled)",
                value="",
                key="login_totp",
                help="Enter your 6-digit authenticator code if you have 2FA enabled.",
            )
            col_btn, col_info = st.columns([1, 1])
            with col_btn:
                submitted = st.form_submit_button("🔓 Login", use_container_width=True, type="primary")
            with col_info:
                st.markdown(
                    "<div style='font-size: 11px; color: #8b949e; padding-top: 8px;'>"
                    "Default: admin / admin123<br>Change after first login.</div>",
                    unsafe_allow_html=True,
                )

            if submitted:
                if _authenticate(username, password, totp_code):
                    auth.logged_in = True
                    auth.username = username
                    auth.login_time = time.time()
                    auth.last_activity = time.time()
                    auth.settings_auth_time = time.time()  # fresh login grants settings access
                    auth.failed_attempts = 0
                    auth.message = f"Welcome, {username}!"
                    auth.message_type = "success"
                    st.rerun()
                else:
                    auth.failed_attempts += 1
                    if auth.failed_attempts >= MAX_FAILED_ATTEMPTS:
                        auth.locked_until = time.time() + LOCKOUT_SEC
                        auth.failed_attempts = 0
                        st.error(f"🔒 Too many failed attempts. Locked for {LOCKOUT_SEC // 60} minutes.")
                    else:
                        remaining = MAX_FAILED_ATTEMPTS - auth.failed_attempts
                        st.error(f"❌ Invalid credentials. {remaining} attempts remaining.")
                    st.stop()

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style='text-align: center; padding: 20px; color: #6e7681; font-size: 11px;'>
            🔒 PBKDF2-SHA256 · Sessions expire after {SESSION_TIMEOUT_SEC // 60} min ·
            Settings re-auth every {SETTINGS_REAUTH_SEC // 60} min ·
            Lockout after {MAX_FAILED_ATTEMPTS} failures
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.stop()


def _authenticate(username: str, password: str, totp_code: str = "") -> bool:
    """Authenticate a user with password + optional TOTP."""
    if not username or not password:
        return False

    users = _ensure_users_db()
    user = users.get(username)

    if not user or not user.get("enabled", True):
        return False

    salt = user.get("salt", "")
    expected = user.get("password_hash", "")

    if not _verify_password(password, salt, expected):
        return False

    # Check TOTP if user has 2FA configured
    totp_secret = user.get("totp_secret")
    if totp_secret:
        if not totp_code:
            return False
        if not _verify_totp(totp_secret, totp_code):
            return False

    return True


def get_current_user() -> str:
    """Return current logged-in username."""
    auth = _get_auth_state()
    return auth.username if auth.logged_in else ""


def get_current_role() -> str:
    """Return current user's role."""
    auth = _get_auth_state()
    return auth.role if auth.logged_in else ""


def change_password(old_pw: str, new_pw: str) -> bool:
    """Change current user's password."""
    auth = _get_auth_state()
    if not auth.logged_in:
        return False
    users = _ensure_users_db()
    user = users.get(auth.username)
    if not user:
        return False
    if not _verify_password(old_pw, user["salt"], user["password_hash"]):
        return False
    new_salt = _gen_salt()
    users[auth.username]["password_hash"] = _hash_password(new_pw, new_salt)
    users[auth.username]["salt"] = new_salt
    _save_users_db(users)
    return True


__all__ = [
    "AuthState",
    "change_password",
    "get_current_role",
    "get_current_user",
    "get_totp_uri",
    "has_settings_access",
    "init_auth",
    "is_logged_in",
    "logout",
    "require_login",
    "require_settings_auth",
    "setup_totp",
]
