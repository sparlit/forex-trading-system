"""
Keyboard Shortcuts System for the Elite Autonomous Quantum Trading System.

Maps Bloomberg-style sheet codes (MAIN, GP, WEI, NEWS, etc.) to dashboard
tabs.  Injects a JavaScript keydown listener into the Streamlit page that
intercepts shortcut keys and switches the active tab via session state.

Shortcuts are single or multi-key codes typed in rapid succession. When
the user types a recognized code (e.g. "GP"), the dashboard jumps to the
corresponding tab instantly.

Usage in app.py:
    from src.dashboard.keyboard import (
        SHORTCUT_MAP,
        inject_keyboard_listener,
        get_active_tab_from_shortcut,
    )
    inject_keyboard_listener()
"""
from __future__ import annotations

import streamlit as st

# ── Shortcut → Tab mapping (30 sheet codes) ──────────────────────────────
# Format: "CODE": ("tab_label", "description")

SHORTCUT_MAP: dict[str, tuple[str, str]] = {
    # ── Core terminal tabs ──────────────────────────────────────────────
    "MAIN":      ("📊 OVERVIEW",           "Multi-Asset Scan Matrix & Active trades terminal"),
    "GP":        ("📈 LIVE CHART",         "Graphical Price chart (Supports indicator lines and pivot S/R)"),
    "WEI":       ("🌐 WORLD INDICES",      "World Currency, Crypto and Equity Indices board"),
    "NEWS":      ("📰 NEWS FEED",          "Live macro news headlines feed with dynamic NLP sentiment tags"),
    "ANR":       ("🎯 ANALYST RECS",       "Consensus recommendations matrix, MLP neural model, and Local LLM"),
    "CHART":     ("📈 LIVE CHART",         "TradingView FOSS Candle Chart & Performance trajectory curve"),
    "SESS":      ("🕐 SESSIONS",           "GMT session timelines countdown and overlap directory"),
    "DES":       ("📋 SECURITY SPECS",     "Detailed Security specifications & contract parameters"),
    "YAS":       ("💰 YIELD ANALYTICS",     "Dynamic Yield metrics, Macaulay/Modified duration, and spread index"),
    "ECO":       ("📅 ECON CALENDAR",      "Global Economic Calendar releases tracking actuals/forecasts"),
    "EMSX":      ("🔀 EMSX ROUTING",       "Algorithmic transaction routing configurations (FIT, FXGO venues)"),
    "SET":       ("⚙️ SETTINGS",           "System Settings, risk per trade, and communication configs"),
    "ING":       ("📥 DATA INGESTION",      "Real-time Data Ingestion telemetry (REST / WebSockets feeds)"),
    "FEAT":      ("🔧 FEATURES",           "Quantitative Feature Store input vectors and variances"),
    "STRAT":     ("⚔️ STRATEGY ENGINE",    "Strategy Voting weight matrix and dynamic state transitions"),
    "RISK":      ("⚖️ RISK MANAGER",       "Circuit breakers, VaR boundaries, and stop protection models"),
    "ORD":       ("🗂️ ORDER MANAGER",      "Order Book, Trade Book, Spread multi-leg, and Trigger orders"),
    "LOG":       ("🪵 EXECUTION LOG",      "Direct Execution logs and database transactions logs"),
    "MON":       ("⏱️ MONITORING",         "CPU load, memory leak, and connection pings monitoring"),
    "SEC":       ("🔒 SECURITY",           "User credentials, 2FA dynamic tokens, B-Unit hardware authentication"),
    "SAFE":      ("🌙 OVERNIGHT SAFETY",   "Geopolitical commodity blocker and overnight rollover protectors"),
    "PF":        ("📂 PORTFOLIO",          "Portfolio Position Book, asset holdings, and free ledger funds"),
    "WATCH":     ("👁️ WATCHLIST",         "Interactive visual Symbol Watchlist with Symbols Heatmap"),
    "MKT":       ("📊 MARKET",             "Exchange messages, movers, scanners, and fundamentals"),
    "SYM":       ("🔗 BROKER CONFIG",      "Broker specs, lot sizes, margins, and spreads limits"),
    "AIC":       ("🤖 AI & LLM",           "AI & LLM configurations, learning rates, attention dimensions"),
    "CRAWL":     ("🌐 EXTERNAL DATA",      "Scraper feeds (DeFiLlama, TokenTerminal, dropsTab, ICOdrops)"),
    "TRADEBOOK": ("📚 TRADE BOOK",         "Settled closed trade logs"),
    "HELP":      ("📖 HELP",              "Displays this interactive operational handbook"),
    "SENT":      ("🎭 SENTIMENT ANALYZER", "Deep Market Sentiment Analyzer"),
    "PRED":      ("📊 STOCK PREDICTOR",    "Stock Market Predictor with forecast curves"),
    "AGENT":     ("🤖 AGENTIC AI",        "Agentic AI system manager"),
}


def get_shortcut_table_data() -> list[tuple[str, str, str]]:
    """Return (code, tab, description) tuples for display."""
    return [(code, tab, desc) for code, (tab, desc) in SHORTCUT_MAP.items()]


def inject_keyboard_listener() -> None:
    """
    Inject a JavaScript keydown listener into the Streamlit page.

    Captures typed key sequences and stores them in a hidden input field.
    When a recognized shortcut code is typed, it sets the target tab in
    a visible Streamlit widget via DOM manipulation and triggers a rerun.

    The listener:
    1. Listens for alphanumeric key presses (case-insensitive)
    2. Accumulates characters in a buffer (resets after 2s of no typing)
    3. When the buffer matches a shortcut code, switches the tab
    4. Shows a brief toast/notification with the matched shortcut
    """
    # Build the shortcut→tab index map for JavaScript
    import json

    # Map shortcut codes to their index in the tab dropdown
    # We need the tab_names list to find the index
    js_shortcuts = json.dumps({code: tab for code, (tab, _) in SHORTCUT_MAP.items()})

    html = f"""
    <div id="kbd-shortcut-bar" style="
        position: fixed; bottom: 12px; right: 12px; z-index: 99999;
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border: 1px solid #0f3460; border-radius: 8px; padding: 6px 12px;
        font-family: 'Courier New', monospace; font-size: 11px; color: #a0a0a0;
        max-width: 280px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        transition: opacity 0.3s; opacity: 0.5;
    " onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">
        <span style="color: #00ff88;">⌨�</span> Type a sheet code:
        <input id="kbd-buffer" type="text" style="
            background: transparent; border: none; color: #00ff88;
            font-family: 'Courier New', monospace; font-size: 11px;
            width: 120px; outline: none; text-transform: uppercase;
        " placeholder="e.g. GP, RISK..." readonly />
        <span id="kbd-toast" style="color: #ffcc00; margin-left: 6px;"></span>
    </div>

    <script>
    (function() {{
        const SHORTCUTS = {js_shortcuts};
        let buffer = "";
        let lastKeyTime = 0;
        const RESET_MS = 2000;

        // Tab labels are in the Streamlit selectbox options
        function findSelectboxOptions() {{
            // Streamlit renders selectbox as a div with role="listbox"
            const options = document.querySelectorAll('[data-baseweb="select"] [role="option"]');
            if (options.length) return Array.from(options).map(o => o.textContent.trim());
            // Fallback: look for the selectbox container
            const sb = document.querySelector('[data-baseweb="select"]');
            if (sb) {{
                // Try to get all option text from the menu
                return null;
            }}
            return null;
        }}

        function switchTab(tabLabel) {{
            // Streamlit selectbox: find the select overlay and click the matching option
            // Strategy: click on the selectbox to open it, then click the matching option
            const selectbox = document.querySelector('[data-baseweb="select"]');
            if (!selectbox) {{
                showToast("⌨ No selectbox found");
                return;
            }}

            // Try using Streamlit's internal state manipulation
            // Approach: find the selectbox, open it, find the option, click it
            selectbox.click();

            setTimeout(() => {{
                const options = document.querySelectorAll('[role="option"]');
                for (const opt of options) {{
                    if (opt.textContent.trim() === tabLabel) {{
                        opt.click();
                        showToast("✓ " + tabLabel);
                        return;
                    }}
                }}
                showToast("✗ Tab not found: " + tabLabel);
            }}, 100);
        }}

        function showToast(msg) {{
            const toast = document.getElementById("kbd-toast");
            if (toast) {{
                toast.textContent = msg;
                setTimeout(() => {{ if (toast) toast.textContent = ""; }}, 2000);
            }}
        }}

        function updateBuffer() {{
            const el = document.getElementById("kbd-buffer");
            if (el) el.value = buffer;
        }}

        function handleKey(e) {{
            // Skip if user is typing in an input/textarea
            const tag = e.target.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
            if (e.target.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;

            const key = e.key.toUpperCase();
            if (!/^[A-Z]$/.test(key)) return;

            // Reset buffer if too much time passed
            const now = Date.now();
            if (now - lastKeyTime > RESET_MS) buffer = "";
            lastKeyTime = now;

            buffer += key;
            updateBuffer();

            // Check for exact match
            if (SHORTCUTS[buffer]) {{
                const tabLabel = SHORTCUTS[buffer];
                switchTab(tabLabel);
                buffer = "";
                updateBuffer();
                return;
            }}

            // Check if any shortcut starts with current buffer (prefix match)
            const hasPrefix = Object.keys(SHORTCUTS).some(code => code.startsWith(buffer));
            if (!hasPrefix) {{
                // No shortcut starts with this → reset
                buffer = "";
                updateBuffer();
            }}
        }}

        // Add listener on keydown
        window.addEventListener("keydown", handleKey);
    }})();
    </script>
    """
    st.components.v1.html(html, height=0)


def get_active_tab_from_shortcut() -> str | None:
    """
    Check if a keyboard shortcut was typed and return the corresponding tab name.
    Returns None if no shortcut was activated.
    """
    # The JavaScript listener manipulates the Streamlit selectbox directly,
    # so Streamlit's own state will update and trigger a rerun naturally.
    # This function is for programmatic access if needed.
    return None


__all__ = [
    "SHORTCUT_MAP",
    "get_active_tab_from_shortcut",
    "get_shortcut_table_data",
    "inject_keyboard_listener",
]
