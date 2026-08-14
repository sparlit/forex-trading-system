"""
Vibrant Color Schemes for ALL dashboard tabs.

Each tab gets a unique, vibrant gradient theme injected as CSS.
Colors are designed for dark backgrounds with high contrast.
"""
from __future__ import annotations

import streamlit as st

# ── Color palette per tab (30 unique themes) ──────────────────────────────

TAB_THEMES: dict[str, dict[str, str]] = {
    "📊 OVERVIEW": {
        "primary": "#00d4ff", "secondary": "#0099cc", "accent": "#00ff88",
        "gradient": "linear-gradient(135deg, #001f3f 0%, #003366 50%, #0066aa 100%)",
        "header": "🎺 Multi-Asset Scan Matrix", "code": "MAIN",
    },
    "🕐 SESSIONS": {
        "primary": "#00ffcc", "secondary": "#00cc99", "accent": "#33ffaa",
        "gradient": "linear-gradient(135deg, #003333 0%, #006666 50%, #009999 100%)",
        "header": "🌍 GMT Session Timeline", "code": "SESS",
    },
    "📈 LIVE CHART": {
        "primary": "#bf00ff", "secondary": "#7700aa", "accent": "#ff00ff",
        "gradient": "linear-gradient(135deg, #1a0033 0%, #330066 50%, #660099 100%)",
        "header": "📈 TradingView Chart", "code": "GP",
    },
    "🧠 BRAIN": {
        "primary": "#ff6b35", "secondary": "#cc4a1a", "accent": "#ffaa00",
        "gradient": "linear-gradient(135deg, #330000 0%, #663300 50%, #cc6600 100%)",
        "header": "🧠 AI Brain", "code": "AI",
    },
    "📋 TRADES": {
        "primary": "#00ff00", "secondary": "#00aa00", "accent": "#88ff44",
        "gradient": "linear-gradient(135deg, #003300 0%, #006600 50%, #00aa00 100%)",
        "header": "📋 Active Trades", "code": "TRD",
    },
    "⚙️ SETTINGS": {
        "primary": "#5c6bc0", "secondary": "#3949ab", "accent": "#8e8ee8",
        "gradient": "linear-gradient(135deg, #1a1a3e 0%, #2a2a5e 50%, #3a3a7e 100%)",
        "header": "⚙️ System Settings", "code": "SET",
    },
    "🖥️ CONSOLE": {
        "primary": "#39ff14", "secondary": "#00cc00", "accent": "#ccff00",
        "gradient": "linear-gradient(135deg, #0a0a0a 0%, #0f1a0f 50%, #1a2a1a 100%)",
        "header": "🖥️ System Console", "code": "CON",
    },
    "📟 BLOOMBERG": {
        "primary": "#ff9900", "secondary": "#cc6600", "accent": "#ffcc00",
        "gradient": "linear-gradient(135deg, #1a1000 0%, #332000 50%, #664000 100%)",
        "header": "📟 Bloomberg Terminal", "code": "BMB",
    },
    "💡 COMMAND BAR": {
        "primary": "#00ffff", "secondary": "#00cccc", "accent": "#aaffff",
        "gradient": "linear-gradient(135deg, #001a33 0%, #003366 50%, #0066aa 100%)",
        "header": "💡 Command Bar", "code": "CMD",
    },
    "🛠️ SETTINGS & CONFIG": {
        "primary": "#5c6bc0", "secondary": "#3949ab", "accent": "#8e8ee8",
        "gradient": "linear-gradient(135deg, #1a1a3e 0%, #2a2a5e 50%, #3a3a7e 100%)",
        "header": "🛠️ Settings & Config", "code": "SET",
    },
    "🔐 CREDENTIALS": {
        "primary": "#e91e63", "secondary": "#c2185b", "accent": "#ff80ab",
        "gradient": "linear-gradient(135deg, #2a001a 0%, #4a0033 50%, #6a004a 100%)",
        "header": "🔐 User Credentials", "code": "CRED",
    },
    "📥 DATA INGESTION": {
        "primary": "#00e676", "secondary": "#00c853", "accent": "#69f0ae",
        "gradient": "linear-gradient(135deg, #003311 0%, #006622 50%, #00aa44 100%)",
        "header": "📡 Data Ingestion Telemetry", "code": "ING",
    },
    "🔧 FEATURES": {
        "primary": "#aa00ff", "secondary": "#7700cc", "accent": "#cc66ff",
        "gradient": "linear-gradient(135deg, #1a002a 0%, #330055 50%, #550088 100%)",
        "header": "🔧 Feature Store", "code": "FEAT",
    },
    "⚔️ STRATEGY ENGINE": {
        "primary": "#ff1744", "secondary": "#d50000", "accent": "#ff5252",
        "gradient": "linear-gradient(135deg, #330000 0%, #660000 50%, #aa0000 100%)",
        "header": "⚔️ Strategy Engine", "code": "STRAT",
    },
    "⚖️ RISK MANAGER": {
        "primary": "#ff5722", "secondary": "#e64a19", "accent": "#ff8a65",
        "gradient": "linear-gradient(135deg, #330500 0%, #660a00 50%, #aa1500 100%)",
        "header": "⚖️ Risk Manager", "code": "RISK",
    },
    "🗂️ ORDER MANAGER": {
        "primary": "#2979ff", "secondary": "#1565c0", "accent": "#82b1ff",
        "gradient": "linear-gradient(135deg, #001a33 0%, #003366 50%, #0055aa 100%)",
        "header": "🗂️ Order Manager", "code": "ORD",
    },
    "🪵 EXECUTION LOG": {
        "primary": "#ffc107", "secondary": "#ffab00", "accent": "#ffe082",
        "gradient": "linear-gradient(135deg, #332000 0%, #664000 50%, #aa6600 100%)",
        "header": "🪵 Execution Log", "code": "LOG",
    },
    "⏱️ MONITORING": {
        "primary": "#00e5ff", "secondary": "#00b8d4", "accent": "#84ffff",
        "gradient": "linear-gradient(135deg, #003344 0%, #006677 50%, #0099aa 100%)",
        "header": "⏱️ System Monitoring", "code": "MON",
    },
    "🔒 SECURITY": {
        "primary": "#9c27b0", "secondary": "#7b1fa2", "accent": "#ce93d8",
        "gradient": "linear-gradient(135deg, #1a0022 0%, #330044 50%, #550066 100%)",
        "header": "🔒 Security & Compliance", "code": "SEC",
    },
    "🌙 OVERNIGHT SAFETY": {
        "primary": "#3d5afe", "secondary": "#304ffe", "accent": "#8c9eff",
        "gradient": "linear-gradient(135deg, #000033 0%, #000066 50%, #0000aa 100%)",
        "header": "🌙 Overnight Safety", "code": "SAFE",
    },
    "📂 PORTFOLIO": {
        "primary": "#00c853", "secondary": "#00a840", "accent": "#5efc82",
        "gradient": "linear-gradient(135deg, #003311 0%, #006633 50%, #00aa55 100%)",
        "header": "📂 Portfolio Manager", "code": "PF",
    },
    "👁️ WATCHLIST": {
        "primary": "#ffea00", "secondary": "#ffd600", "accent": "#fff59d",
        "gradient": "linear-gradient(135deg, #332a00 0%, #665500 50%, #aa8800 100%)",
        "header": "👁️ Symbols Watchlist", "code": "WATCH",
    },
    "📊 MARKET": {
        "primary": "#ff6f00", "secondary": "#e65100", "accent": "#ffab40",
        "gradient": "linear-gradient(135deg, #331100 0%, #662200 50%, #aa4400 100%)",
        "header": "📊 Market Explorer", "code": "MKT",
    },
    "🔗 BROKER CONFIG": {
        "primary": "#26a69a", "secondary": "#00796b", "accent": "#80cbc4",
        "gradient": "linear-gradient(135deg, #003333 0%, #006655 50%, #009988 100%)",
        "header": "🔗 Broker Configuration", "code": "SYM",
    },
    "🤖 AI & LLM": {
        "primary": "#7c4dff", "secondary": "#6200ea", "accent": "#b388ff",
        "gradient": "linear-gradient(135deg, #1a0033 0%, #330066 50%, #550099 100%)",
        "header": "🤖 AI & LLM Configuration", "code": "AIC",
    },
    "🌐 EXTERNAL DATA": {
        "primary": "#ff4081", "secondary": "#c2185b", "accent": "#ff80ab",
        "gradient": "linear-gradient(135deg, #330011 0%, #660022 50%, #aa0044 100%)",
        "header": "🌐 External Data Sources", "code": "CRAWL",
    },
    "📚 TRADE BOOK": {
        "primary": "#ff9100", "secondary": "#ff6d00", "accent": "#ffd180",
        "gradient": "linear-gradient(135deg, #331a00 0%, #663300 50%, #aa5500 100%)",
        "header": "📚 Trade Book", "code": "TRADEBOOK",
    },
    "🎭 SENTIMENT ANALYZER": {
        "primary": "#ec407a", "secondary": "#c2185b", "accent": "#f48fb1",
        "gradient": "linear-gradient(135deg, #330011 0%, #660033 50%, #aa0055 100%)",
        "header": "🎭 Deep Market Sentiment", "code": "SENT",
    },
    "📊 STOCK PREDICTOR": {
        "primary": "#536dfe", "secondary": "#3d5afe", "accent": "#8c9eff",
        "gradient": "linear-gradient(135deg, #000033 0%, #000066 50%, #3333aa 100%)",
        "header": "📊 Stock Market Predictor", "code": "PRED",
    },
    "🤖 AGENTIC AI": {
        "primary": "#00e5ff", "secondary": "#00b8d4", "accent": "#18ffff",
        "gradient": "linear-gradient(135deg, #003344 0%, #006677 50%, #0099bb 100%)",
        "header": "🤖 Agentic AI System", "code": "AGENT",
    },
    "📖 HELP": {
        "primary": "#78909c", "secondary": "#546e7a", "accent": "#b0bec5",
        "gradient": "linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 50%, #3a3a3a 100%)",
        "header": "📖 Help & Documentation", "code": "HELP",
    },
    # ── New sheet code tabs ──────────────────────────────────────────────
    "🌐 WORLD INDICES": {
        "primary": "#ffd700", "secondary": "#ffb300", "accent": "#ffeb3b",
        "gradient": "linear-gradient(135deg, #332b00 0%, #665500 50%, #aa8800 100%)",
        "header": "🌐 World Indices Board", "code": "WEI",
    },
    "📰 NEWS FEED": {
        "primary": "#ff5722", "secondary": "#e64a19", "accent": "#ff8a65",
        "gradient": "linear-gradient(135deg, #330500 0%, #660a00 50%, #aa1500 100%)",
        "header": "📰 Live News Feed", "code": "NEWS",
    },
    "🎯 ANALYST RECS": {
        "primary": "#3d5afe", "secondary": "#304ffe", "accent": "#8c9eff",
        "gradient": "linear-gradient(135deg, #000033 0%, #000066 50%, #3333aa 100%)",
        "header": "🎯 Analyst Recommendations", "code": "ANR",
    },
    "📋 SECURITY SPECS": {
        "primary": "#607d8b", "secondary": "#455a64", "accent": "#90a4ae",
        "gradient": "linear-gradient(135deg, #1a2228 0%, #2a3338 50%, #3a4348 100%)",
        "header": "📋 Security Specifications", "code": "DES",
    },
    "💰 YIELD ANALYTICS": {
        "primary": "#00c853", "secondary": "#00a840", "accent": "#5efc82",
        "gradient": "linear-gradient(135deg, #003311 0%, #006633 50%, #00aa55 100%)",
        "header": "💰 Yield Analytics", "code": "YAS",
    },
    "📅 ECON CALENDAR": {
        "primary": "#ff6f00", "secondary": "#e65100", "accent": "#ffab40",
        "gradient": "linear-gradient(135deg, #331100 0%, #662200 50%, #aa4400 100%)",
        "header": "📅 Economic Calendar", "code": "ECO",
    },
    "🔀 EMSX ROUTING": {
        "primary": "#5c6bc0", "secondary": "#3949ab", "accent": "#8e8ee8",
        "gradient": "linear-gradient(135deg, #1a1a3e 0%, #2a2a5e 50%, #3a3e8e 100%)",
        "header": "🔀 EMSX Transaction Routing", "code": "EMSX",
    },
    # Added explicit theme for the gear emoji label used by the UI
    "⚙️ EMSX ROUTING": {
        "primary": "#5c6bc0", "secondary": "#3949ab", "accent": "#8e8ee8",
        "gradient": "linear-gradient(135deg, #1a1a3e 0%, #2a2a5e 50%, #3a3a8e 100%)",
        "header": "⚙️ EMSX Transaction Routing", "code": "EMSX",
    },
    # ── Sheet-code tabs that were missing vibrant themes ───────────────────
    "📊 MAIN SCAN": {
        "primary": "#00e5ff", "secondary": "#00b8d4", "accent": "#84ffff",
        "gradient": "linear-gradient(135deg, #002233 0%, #004466 50%, #0077aa 100%)",
        "header": "📊 Main Scan & Active Trades", "code": "SCAN",
    },
    "📈 PRICE CHART": {
        "primary": "#bf00ff", "secondary": "#7700aa", "accent": "#ff00ff",
        "gradient": "linear-gradient(135deg, #1a0033 0%, #330066 50%, #660099 100%)",
        "header": "📈 Price Chart & Indicators", "code": "PCH",
    },
    "📊 ANALYST RECS": {
        "primary": "#4b0082", "secondary": "#8a2be2", "accent": "#b388ff",
        "gradient": "linear-gradient(135deg, #1a0028 0%, #330055 50%, #550099 100%)",
        "header": "📊 Analyst Recommendations & AI Models", "code": "ANR",
    },
    "🕑 SESSION TIMELINE": {
        "primary": "#00ffff", "secondary": "#008080", "accent": "#80ffff",
        "gradient": "linear-gradient(135deg, #002a2a 0%, #005555 50%, #008888 100%)",
        "header": "🕑 GMT Session Timelines & Overlaps", "code": "STL",
    },
    "🪙 YIELD ANALYTICS": {
        "primary": "#00ff00", "secondary": "#006400", "accent": "#88ff44",
        "gradient": "linear-gradient(135deg, #001a00 0%, #003300 50%, #006600 100%)",
        "header": "🪙 Yield Curve Analytics", "code": "YAS",
    },
    "🔐 DES SECURITY": {
        "primary": "#90a4ae", "secondary": "#607d8b", "accent": "#cfd8dc",
        "gradient": "linear-gradient(135deg, #1a2228 0%, #2a3338 50%, #3a4348 100%)",
        "header": "🔐 Designated Security Specifications", "code": "DES",
    },
    "📥 ING TELEMETRY": {
        "primary": "#00e676", "secondary": "#00c853", "accent": "#69f0ae",
        "gradient": "linear-gradient(135deg, #003311 0%, #006622 50%, #00aa44 100%)",
        "header": "📥 Ingestion Telemetry Pipeline", "code": "INGT",
    },
    "🔧 FEAT STORE": {
        "primary": "#aa00ff", "secondary": "#7700cc", "accent": "#cc66ff",
        "gradient": "linear-gradient(135deg, #1a002a 0%, #330055 50%, #550088 100%)",
        "header": "🔧 Feature Store Catalog", "code": "FST",
    },
    "⚔️ STRAT VOTING": {
        "primary": "#ff1744", "secondary": "#d50000", "accent": "#ff5252",
        "gradient": "linear-gradient(135deg, #330000 0%, #660000 50%, #aa0000 100%)",
        "header": "⚔️ Strategy Voting Board", "code": "SVT",
    },
    "⚖️ RISK CIRCUIT": {
        "primary": "#ff5722", "secondary": "#e64a19", "accent": "#ff8a65",
        "gradient": "linear-gradient(135deg, #330500 0%, #660a00 50%, #aa1500 100%)",
        "header": "⚖️ Risk Circuit Breakers", "code": "RCKT",
    },
    "🗂️ ORD BOOK": {
        "primary": "#2979ff", "secondary": "#1565c0", "accent": "#82b1ff",
        "gradient": "linear-gradient(135deg, #001a33 0%, #003366 50%, #0055aa 100%)",
        "header": "🗂️ Live Order Book Ladder", "code": "OBK",
    },
    "🪵 LOG EXEC": {
        "primary": "#ffc107", "secondary": "#ffab00", "accent": "#ffe082",
        "gradient": "linear-gradient(135deg, #332000 0%, #664000 50%, #aa6600 100%)",
        "header": "🪵 Execution Log Stream", "code": "LEX",
    },
    "⏱️ MON HEALTH": {
        "primary": "#00e5ff", "secondary": "#00b8d4", "accent": "#84ffff",
        "gradient": "linear-gradient(135deg, #003344 0%, #006677 50%, #0099aa 100%)",
        "header": "⏱️ Monitoring Health Overview", "code": "MHH",
    },
    "🔒 SEC AUTH": {
        "primary": "#9c27b0", "secondary": "#7b1fa2", "accent": "#ce93d8",
        "gradient": "linear-gradient(135deg, #1a0022 0%, #330044 50%, #550066 100%)",
        "header": "🔒 Security & Auth Audit", "code": "SAU",
    },
    "📂 PF PORTFOLIO": {
        "primary": "#00c853", "secondary": "#00a840", "accent": "#5efc82",
        "gradient": "linear-gradient(135deg, #003311 0%, #006633 50%, #00aa55 100%)",
        "header": "📂 Portfolio Holdings & Allocation", "code": "PFP",
    },
}


def inject_tab_theme(tab_name: str) -> None:
    """
    Inject a vibrant gradient header for the current tab.

    Call this at the start of each render_xxx_tab() function to give
    every tab a unique colorful header.
    """
    theme = TAB_THEMES.get(tab_name, TAB_THEMES["📖 HELP"])
    primary = theme["primary"]
    gradient = theme["gradient"]
    header = theme["header"]
    code = theme["code"]

    css = f"""
    <div style="
        background: {gradient};
        border: 1px solid {primary}33;
        border-radius: 12px;
        padding: 16px 24px;
        margin-bottom: 18px;
        box-shadow: 0 4px 24px {primary}22, inset 0 1px 0 {primary}11;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h2 style="
                color: {primary};
                font-size: 22px; font-weight: 700;
                margin: 0; padding: 0;
                text-shadow: 0 0 20px {primary}88;
                letter-spacing: 0.5px;
            ">{header}</h2>
            <span style="
                color: {primary};
                background: {primary}22;
                border: 1px solid {primary}55;
                border-radius: 4px;
                padding: 4px 10px;
                font-family: 'Courier New', monospace;
                font-size: 12px; font-weight: bold;
                letter-spacing: 1px;
            ">{code}</span>
        </div>
    </div>
    """
    st.markdown(css, unsafe_allow_html=True)


def get_theme(tab_name: str) -> dict[str, str]:
    """Get the theme dict for a tab."""
    return TAB_THEMES.get(tab_name, TAB_THEMES["📖 HELP"])


__all__ = ["TAB_THEMES", "get_theme", "inject_tab_theme"]
