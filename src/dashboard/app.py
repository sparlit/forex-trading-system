"""
Elite Autonomous Quantum Trading System - Comprehensive Dashboard
Streamlit-based real-time trading dashboard with session timeline, live PnL, 
live trades, charts, console output, and Bloomberg terminal features.
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import UTC, datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.autonomous.selection_engine import selection_engine
from src.brain.self_evolving_brain import SelfEvolvingBrain
from src.compute.parallel import BackendType, ParallelConfig, ParallelProcessor
from src.dashboard.auth import (
    get_current_role,
    get_current_user,
    init_auth,
    require_login,
    require_settings_auth,
)
from src.dashboard.bloomberg_adapter import get_bloomberg_adapter
from src.dashboard.tabs import (
    render_agentic_ai_tab,
    render_ai_config_tab,
    render_anr_recommend_tab,
    render_broker_config_tab,
    render_credentials_tab,
    render_data_ingestion_tab,
    render_des_security_tab,
    render_econ_calendar_tab,
    render_emsx_routing_tab,
    render_execution_logger_tab,
    render_external_data_tab,
    render_feat_store_tab,
    render_feature_store_tab,
    render_help_tab,
    render_ing_telemetry_tab,
    render_log_exec_tab,
    # New tabs imported below
    render_main_scan_tab,
    render_market_tab,
    render_mon_health_tab,
    render_monitoring_tab,
    render_news_feed_tab,
    render_ord_book_tab,
    render_order_manager_tab,
    render_overnight_tab,
    render_pf_portfolio_tab,
    render_portfolio_tab,
    render_price_chart_tab,
    render_risk_circuit_tab,
    render_risk_manager_tab,
    render_sec_auth_tab,
    render_security_tab,
    render_sentiment_tab,
    render_session_timeline_tab,
    render_settings_tab,
    render_stock_predictor_tab,
    render_strat_voting_tab,
    render_strategy_engine_tab,
    render_trade_book_tab,
    render_watchlist_tab,
    render_world_indices_tab,
    render_yield_analytics_tab,
)
from src.strategy.session_manager import (
    MarketType,
    TradingSession,
    session_manager,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Elite Autonomous Trading System",
    page_icon="assets/icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Bloomberg-style dark theme
st.markdown("""
<style>
    /* Main dark theme */
    .stApp {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #161b22;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background-color: #161b22;
        border-radius: 4px;
        padding: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: transparent;
        border-radius: 4px;
        color: #8b949e;
        font-weight: 500;
        font-size: 13px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #238636;
        color: white !important;
    }
    
    /* Metrics */
    .metric-container {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 12px;
        margin: 4px 0;
    }
    
    .metric-label {
        font-size: 11px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .metric-value {
        font-size: 18px;
        font-weight: 600;
        color: #e0e0e0;
    }
    
    .metric-positive {
        color: #3fb950;
    }
    
    .metric-negative {
        color: #f85149;
    }
    
    /* Session timeline */
    .timeline-container {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 16px;
        margin: 8px 0;
    }
    
    .session-row {
        height: 60px;
        position: relative;
        margin: 4px 0;
    }
    
    .session-block {
        position: absolute;
        height: 40px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        padding: 0 8px;
        font-size: 11px;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .session-block:hover {
        transform: scaleY(1.2);
        z-index: 10;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    
    .session-label {
        position: absolute;
        left: -120px;
        width: 110px;
        text-align: right;
        font-size: 10px;
        color: #8b949e;
        padding-right: 8px;
    }
    
    .time-scale {
        display: flex;
        justify-content: space-between;
        padding: 0 120px;
        font-size: 9px;
        color: #6e7681;
        margin-top: 4px;
    }
    
    /* Overlapping sessions */
    .overlap-indicator {
        position: absolute;
        top: -20px;
        left: 0;
        right: 0;
        height: 16px;
        background: repeating-linear-gradient(45deg, rgba(255,255,255,0.1), rgba(255,255,255,0.1) 4px, transparent 4px, transparent 8px);
        border-radius: 2px;
        pointer-events: none;
    }
    
    /* Console output */
    .console-container {
        background-color: #0d1117;
        border: 1px solid #30363d;
        border-radius: 6px;
        height: 200px;
        overflow-y: auto;
        padding: 12px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 11px;
        line-height: 1.5;
    }
    
    .console-line {
        margin: 2px 0;
        padding: 2px 6px;
        border-radius: 3px;
    }
    
    .console-info { color: #58a6ff; }
    .console-success { color: #3fb950; }
    .console-warning { color: #d29922; }
    .console-error { color: #f85149; }
    .console-debug { color: #8b949e; }
    
    /* Live trades table */
    .trade-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
    }
    
    .trade-table th {
        background-color: #161b22;
        color: #8b949e;
        font-weight: 600;
        text-align: left;
        padding: 8px 12px;
        border-bottom: 1px solid #30363d;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .trade-table td {
        padding: 8px 12px;
        border-bottom: 1px solid #21262d;
    }
    
    .trade-table tr:hover {
        background-color: #161b22;
    }
    
    .trade-buy { color: #3fb950; }
    .trade-sell { color: #f85149; }
    
    /* Chart container */
    .chart-container {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 8px;
    }
    
    /* Status indicators */
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-connected { background-color: #3fb950; }
    .status-disconnected { background-color: #f85149; }
    .status-connecting { background-color: #d29922; }
    
    /* Session detail panel */
    .session-detail {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 12px;
        margin: 8px 0;
    }
    
    .session-detail-title {
        font-size: 13px;
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid #30363d;
    }
    
    .session-detail-row {
        display: flex;
        justify-content: space-between;
        padding: 4px 0;
        font-size: 12px;
    }
    
    .session-detail-label {
        color: #8b949e;
    }
    
    .session-detail-value {
        color: #e0e0e0;
        font-weight: 500;
    }
    
    /* Bloomberg-style command bar */
    .command-bar {
        background-color: #0d1117;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 8px 12px;
        font-family: 'Monaco', 'Menlo', monospace;
        font-size: 13px;
        color: #e0e0e0;
    }
    
    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Responsive */
    @media (max-width: 1200px) {
        .metric-value { font-size: 16px; }
        .session-block { font-size: 10px; }
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Dashboard State Management
# =============================================================================

class DashboardState:
    """Manages dashboard state and real-time data."""
    
    def __init__(self):
        self.console_logs = deque(maxlen=500)
        self.live_trades = deque(maxlen=100)
        self.pnl_history = deque(maxlen=1000)
        self.equity_curve = deque(maxlen=1000)
        self.positions = []
        self.account_info = {}
        self.market_data = {}
        self.session_info = {}
        self.brain_metrics = {}
        self.selection_result = None
        self.last_update = datetime.now(UTC)
        self.connected = False
        self.auto_trading = True
        
    def add_log(self, level: str, message: str):
        """Add a log entry to console."""
        self.console_logs.append({
            "timestamp": datetime.now(UTC),
            "level": level,
            "message": message
        })
        
    def add_trade(self, trade: dict):
        """Add a live trade."""
        self.live_trades.appendleft(trade)
        
    def update_pnl(self, pnl: float, equity: float):
        """Update PnL history."""
        now = datetime.now(UTC)
        self.pnl_history.append({"time": now, "pnl": pnl})
        self.equity_curve.append({"time": now, "equity": equity})
        
    def update_positions(self, positions: list):
        """Update current positions."""
        self.positions = positions
        
    def update_account(self, account: dict):
        """Update account info."""
        self.account_info = account
        
    def update_market_data(self, symbol: str, data: dict):
        """Update market data for symbol."""
        self.market_data[symbol] = data
        
    def update_session_info(self, info: dict):
        """Update session info."""
        self.session_info = info
        
    def update_brain_metrics(self, metrics: dict):
        """Update brain metrics."""
        self.brain_metrics = metrics
        
    def update_selection(self, selection: Any):
        """Update selection result."""
        self.selection_result = selection


# Global dashboard state
if 'dashboard_state' not in st.session_state:
    st.session_state.dashboard_state = DashboardState()
    
if 'brain' not in st.session_state:
    st.session_state.brain = None
    
if 'parallel_processor' not in st.session_state:
    st.session_state.parallel_processor = None
    
if 'auto_loop_running' not in st.session_state:
    st.session_state.auto_loop_running = False


# =============================================================================
# Helper Functions
# =============================================================================

def format_timedelta(td: timedelta) -> str:
    """Format timedelta as HH:MM:SS."""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_session_color(session: TradingSession) -> str:
    """Get vibrant color for session based on market type and liquidity."""
    colors = {
        MarketType.FOREX: {
            "very_high": "#ff6b6b",  # Red
            "high": "#ff8787",
            "medium": "#ffa8a8",
            "low": "#ffc8c8",
            "extreme": "#e03e3e",
        },
        MarketType.EQUITIES: {
            "very_high": "#4ecdc4",  # Teal
            "high": "#6ee0d7",
            "medium": "#96f2ea",
            "low": "#bff8f0",
        },
        MarketType.FUTURES: {
            "very_high": "#ffe66d",  # Yellow
            "high": "#fff08f",
            "medium": "#fff9b1",
            "low": "#fffcd0",
        },
        MarketType.CRYPTO: {
            "very_high": "#a855f7",  # Purple
            "high": "#c084fc",
            "medium": "#d8b4fe",
            "low": "#e9d5ff",
        },
        MarketType.COMMODITIES: {
            "very_high": "#f97316",  # Orange
            "high": "#fb923c",
            "medium": "#fdba74",
            "low": "#fed7aa",
        },
        MarketType.METALS: {
            "very_high": "#eab308",  # Gold
            "high": "#facc15",
            "medium": "#fde047",
            "low": "#fef08a",
        },
    }
    return colors.get(session.market_type, {}).get(session.liquidity, "#8b949e")


def get_overlap_color() -> str:
    """Get color for overlapping sessions."""
    return "#f0f6fc"  # White with transparency handled in CSS


def render_session_timeline(state: DashboardState):
    """Render the 3-row session timeline with vibrant colors."""
    now = datetime.now(UTC)
    timeline_data = session_manager.get_session_timeline(hours_ahead=24)
    active_sessions = session_manager.get_active_sessions()
    
    # Separate into past, current, future
    past_sessions = []
    current_sessions = []
    future_sessions = []
    
    for item in timeline_data:
        start = datetime.fromisoformat(item["start"].replace('Z', '+00:00'))
        end = datetime.fromisoformat(item["end"].replace('Z', '+00:00'))
        
        if end <= now:
            past_sessions.append(item)
        elif start <= now < end:
            current_sessions.append(item)
        else:
            future_sessions.append(item)
    
    # Limit each row
    max_per_row = 15
    past_sessions = past_sessions[-max_per_row:]
    current_sessions = current_sessions[:max_per_row]
    future_sessions = future_sessions[:max_per_row]
    
    # Calculate time range for scaling
    all_sessions = past_sessions + current_sessions + future_sessions
    if not all_sessions:
        st.info("No sessions in the next 24 hours")
        return
        
    min_time = min(datetime.fromisoformat(s["start"].replace('Z', '+00:00')) for s in all_sessions)
    max_time = max(datetime.fromisoformat(s["end"].replace('Z', '+00:00')) for s in all_sessions)
    total_minutes = (max_time - min_time).total_seconds() / 60
    
    # Session rows
    rows = [
        ("PAST / PASSING", past_sessions, "#8b949e"),
        ("CURRENT ACTIVE", current_sessions, "#3fb950"),
        ("COMING UP", future_sessions, "#58a6ff"),
    ]
    
    for row_title, sessions, row_color in rows:
        st.markdown(f"""
        <div class="timeline-container">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="color: {row_color}; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">
                    {row_title}
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        if not sessions:
            st.markdown('<div style="color: #6e7681; font-size: 12px; padding: 20px; text-align: center;">No sessions</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            continue
            
        # Render session blocks
        for session_item in sessions:
            session_obj = session_manager.get_session_by_name(session_item["session"])
            if not session_obj:
                continue
                
            start = datetime.fromisoformat(session_item["start"].replace('Z', '+00:00'))
            end = datetime.fromisoformat(session_item["end"].replace('Z', '+00:00'))
            color = get_session_color(session_obj)
            is_active = session_item.get("is_active", False)
            
            # Calculate position and width
            start_minutes = (start - min_time).total_seconds() / 60
            duration_minutes = (end - start).total_seconds() / 60
            left_pct = (start_minutes / total_minutes) * 100
            width_pct = (duration_minutes / total_minutes) * 100
            
            # Check for overlaps
            overlaps = []
            for other in sessions:
                if other["session"] != session_item["session"]:
                    other_start = datetime.fromisoformat(other["start"].replace('Z', '+00:00'))
                    other_end = datetime.fromisoformat(other["end"].replace('Z', '+00:00'))
                    if start < other_end and end > other_start:
                        overlaps.append(other["session"])
            
            overlap_html = ""
            if overlaps:
                overlap_html = f'<div class="overlap-indicator" title="Overlaps: {", ".join(overlaps)}"></div>'
            
            active_badge = '<span style="background:#3fb950;color:#000;padding:1px 6px;border-radius:3px;font-size:9px;margin-left:4px;">LIVE</span>' if is_active else ''
            
            st.markdown(f"""
            <div class="session-row">
                <span class="session-label">{session_obj.name}</span>
                <div class="session-block" style="left: {left_pct}%; width: {width_pct}%; background: {color}; color: #000;" 
                     title="{session_obj.name} | {start.strftime('%H:%M')} - {end.strftime('%H:%M')} UTC | {session_obj.liquidity} liquidity | {session_obj.volatility} volatility | Symbols: {', '.join(session_obj.major_symbols[:3])}...">
                    {session_obj.name.upper()}{active_badge}
                </div>
                {overlap_html}
            </div>
            """, unsafe_allow_html=True)
            
        # Time scale
        scale_html = '<div class="time-scale">'
        for i in range(13):
            scale_time = min_time + timedelta(minutes=total_minutes * i / 12)
            scale_html += f'<span>{scale_time.strftime("%H:%M")}</span>'
        scale_html += '</div>'
        st.markdown(scale_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_session_details(state: DashboardState):
    """Render detailed session information panel."""
    active_sessions = session_manager.get_active_sessions()
    next_session = session_manager.get_next_session()
    
    if not active_sessions and not next_session:
        st.info("No active or upcoming sessions")
        return
        
    # Active sessions details
    for session_name, session in active_sessions.items():
        info = session_manager.get_session_info(session_name)
        if not info:
            continue
            
        color = get_session_color(session)
        overlaps = info.overlaps
        
        st.markdown(f"""
        <div class="session-detail" style="border-left: 4px solid {color};">
            <div class="session-detail-title" style="color: {color};">
                🔴 ACTIVE: {session.name.upper()} ({session.market_type.value})
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Start Time (UTC)</span>
                <span class="session-detail-value">{session.start_utc.strftime('%H:%M')}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">End Time (UTC)</span>
                <span class="session-detail-value">{session.end_utc.strftime('%H:%M')}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Remaining Time</span>
                <span class="session-detail-value" style="color: #3fb950; font-weight: 600;">{format_timedelta(info.time_remaining)}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Progress</span>
                <span class="session-detail-value">{info.progress * 100:.1f}%</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Liquidity / Volatility</span>
                <span class="session-detail-value">{session.liquidity} / {session.volatility}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Major Symbols</span>
                <span class="session-detail-value">{', '.join(session.major_symbols[:8])}</span>
            </div>
        """, unsafe_allow_html=True)
        
        if overlaps:
            st.markdown('<div class="session-detail-row"><span class="session-detail-label">⚠ OVERLAPPING SESSIONS</span></div>', unsafe_allow_html=True)
            for overlap in overlaps:
                o_info = session_manager.get_session_info(overlap.name)
                if o_info:
                    o_color = get_session_color(overlap)
                    st.markdown(f"""
                    <div class="session-detail-row" style="margin-left: 16px; padding: 4px 0; border-left: 2px solid {o_color};">
                        <span class="session-detail-label">{overlap.name.upper()}</span>
                        <span class="session-detail-value" style="color: {o_color};">{overlap.start_utc.strftime('%H:%M')} - {overlap.end_utc.strftime('%H:%M')} UTC | Remaining: {format_timedelta(o_info.time_remaining)}</span>
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Next session
    if next_session:
        session = next_session.session
        color = get_session_color(session)
        time_until = next_session.time_remaining
        
        st.markdown(f"""
        <div class="session-detail" style="border-left: 4px solid {color}; opacity: 0.8;">
            <div class="session-detail-title" style="color: {color};">
                ⏳ NEXT: {session.name.upper()} ({session.market_type.value})
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Starts In</span>
                <span class="session-detail-value" style="color: #58a6ff; font-weight: 600;">{format_timedelta(time_until)}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Start Time (UTC)</span>
                <span class="session-detail-value">{session.start_utc.strftime('%H:%M')}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">End Time (UTC)</span>
                <span class="session-detail-value">{session.end_utc.strftime('%H:%M')}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Major Symbols</span>
                <span class="session-detail-value">{', '.join(session.major_symbols[:8])}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_live_pnl(state: DashboardState):
    """Render live PnL metrics."""
    account = state.account_info
    equity = account.get("equity", 0)
    balance = account.get("balance", 0)
    pnl = account.get("profit", 0)
    daily_pnl = account.get("daily_pnl", 0)
    margin = account.get("margin", 0)
    free_margin = account.get("free_margin", 0)
    margin_level = account.get("margin_level", 0)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        pnl_class = "metric-positive" if pnl >= 0 else "metric-negative"
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Total PnL</div>
            <div class="metric-value {pnl_class}">${pnl:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        daily_class = "metric-positive" if daily_pnl >= 0 else "metric-negative"
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Daily PnL</div>
            <div class="metric-value {daily_class}">${daily_pnl:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Equity</div>
            <div class="metric-value">${equity:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Free Margin</div>
            <div class="metric-value">${free_margin:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col5:
        ml_class = "metric-positive" if margin_level > 200 else "metric-negative" if margin_level < 100 else "metric-warning"
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Margin Level</div>
            <div class="metric-value {ml_class}">{margin_level:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Equity curve chart
    if state.equity_curve:
        df = pd.DataFrame(list(state.equity_curve))
        if len(df) > 1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["time"],
                y=df["equity"],
                mode="lines",
                line=dict(color="#3fb950", width=2),
                fill="tozeroy",
                fillcolor="rgba(63, 185, 80, 0.1)",
                name="Equity"
            ))
            
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#161b22",
                plot_bgcolor="#161b22",
                margin=dict(l=0, r=0, t=20, b=0),
                height=200,
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=True, gridcolor="#21262d", tickformat="$,.0f"),
                showlegend=False,
            )
            
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_live_trades(state: DashboardState):
    """Render live trades table."""
    if not state.live_trades:
        st.info("No live trades yet")
        return
        
    trades_html = """
    <table class="trade-table">
        <thead>
            <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Volume</th>
                <th>Entry</th>
                <th>Current</th>
                <th>PnL</th>
                <th>SL</th>
                <th>TP</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
    """
    
    now = datetime.now(UTC)
    for trade in list(state.live_trades)[:20]:
        side_class = "trade-buy" if trade.get("side") == "buy" else "trade-sell"
        pnl = trade.get("pnl", 0)
        pnl_class = "trade-buy" if pnl >= 0 else "trade-sell"
        
        entry_time = trade.get("time", now)
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
        duration = format_timedelta(now - entry_time)
        
        trades_html += f"""
        <tr>
            <td>{entry_time.strftime('%H:%M:%S')}</td>
            <td><strong>{trade.get('symbol', '')}</strong></td>
            <td class="{side_class}">{trade.get('side', '').upper()}</td>
            <td>{trade.get('volume', 0):.2f}</td>
            <td>{trade.get('entry', 0):.5f}</td>
            <td>{trade.get('current', 0):.5f}</td>
            <td class="{pnl_class}">${pnl:,.2f}</td>
            <td>{trade.get('sl', 0):.5f}</td>
            <td>{trade.get('tp', 0):.5f}</td>
            <td>{duration}</td>
        </tr>
        """
        
    trades_html += "</tbody></table>"
    st.markdown(trades_html, unsafe_allow_html=True)


def render_live_chart(state: DashboardState):
    """Render live price chart with indicators using Lightweight Charts (FOSS)."""
    # Get selected symbol from session or default
    symbol = "EURUSD"
    if state.selection_result and state.selection_result.symbols:
        symbol = state.selection_result.symbols[0]

    # Generate sample data (in real implementation, fetch from market data)
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=24)

    # Create sample OHLCV data
    periods = 240  # 5-min bars for 20 hours
    times = pd.date_range(start=start_time, periods=periods, freq='5min', tz=UTC)

    # Simulate price data
    np.random.seed(42)
    base_price = 1.0850
    returns = np.random.normal(0, 0.0002, periods)
    prices = base_price * np.exp(np.cumsum(returns))

    opens = prices
    highs = prices + np.abs(np.random.normal(0, 0.0001, periods))
    lows = prices - np.abs(np.random.normal(0, 0.0001, periods))
    closes = prices + np.random.normal(0, 0.00005, periods)
    volumes = np.random.randint(1000, 10000, periods)

    df = pd.DataFrame({
        'time': times,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })

    # Calculate EMAs
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()

    # Convert to format for Lightweight Charts (timestamp in seconds)
    candlestick_data = []
    volume_data = []
    ema20_data = []
    ema50_data = []

    for i, row in df.iterrows():
        timestamp = int(row['time'].timestamp())
        candlestick_data.append({
            'time': timestamp,
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close'])
        })
        volume_data.append({
            'time': timestamp,
            'value': float(row['volume']),
            'color': '#3fb950' if row['close'] >= row['open'] else '#f85149'
        })
        if not np.isnan(row['ema_20']):
            ema20_data.append({'time': timestamp, 'value': float(row['ema_20'])})
        if not np.isnan(row['ema_50']):
            ema50_data.append({'time': timestamp, 'value': float(row['ema_50'])})

    # Lightweight Charts HTML (TradingView's FOSS library)
    chart_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: #0e1117;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            #chart-container {{
                width: 100%;
                height: 500px;
                position: relative;
            }}
            .chart-toolbar {{
                position: absolute;
                top: 10px;
                left: 10px;
                z-index: 100;
                display: flex;
                gap: 8px;
                background: rgba(22, 27, 34, 0.95);
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #30363d;
            }}
            .chart-toolbar button {{
                background: transparent;
                border: 1px solid #30363d;
                color: #8b949e;
                padding: 4px 10px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                transition: all 0.2s;
            }}
            .chart-toolbar button:hover {{
                background: #238636;
                border-color: #238636;
                color: white;
            }}
            .chart-toolbar button.active {{
                background: #238636;
                border-color: #238636;
                color: white;
            }}
            .symbol-title {{
                position: absolute;
                top: 10px;
                right: 10px;
                z-index: 100;
                background: rgba(22, 27, 34, 0.95);
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #30363d;
                color: #e0e0e0;
                font-weight: 600;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div id="chart-container">
            <div class="chart-toolbar" id="toolbar">
                <button id="btn-1m" data-res="60">1m</button>
                <button id="btn-5m" data-res="300" class="active">5m</button>
                <button id="btn-15m" data-res="900">15m</button>
                <button id="btn-1h" data-res="3600">1h</button>
                <button id="btn-4h" data-res="14400">4h</button>
                <button id="btn-1d" data-res="86400">1D</button>
            </div>
            <div class="symbol-title">{symbol}</div>
        </div>

        <script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
        <script>
            const candlestickData = {json.dumps(candlestick_data)};
            const volumeData = {json.dumps(volume_data)};
            const ema20Data = {json.dumps(ema20_data)};
            const ema50Data = {json.dumps(ema50_data)};

            // Create chart
            const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {{
                width: document.getElementById('chart-container').clientWidth,
                height: 500,
                layout: {{
                    background: {{ color: '#0e1117' }},
                    textColor: '#e0e0e0',
                    fontSize: 11,
                    fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
                }},
                grid: {{
                    vertLines: {{ color: '#21262d' }},
                    horzLines: {{ color: '#21262d' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {{ color: '#58a6ff', width: 1, style: LightweightCharts.LineStyle.Dashed }},
                    horzLine: {{ color: '#58a6ff', width: 1, style: LightweightCharts.LineStyle.Dashed }},
                }},
                rightPriceScale: {{
                    borderColor: '#30363d',
                    scaleMargins: {{
                        top: 0.2,
                        bottom: 0.25,
                    }},
                }},
                timeScale: {{
                    borderColor: '#30363d',
                    timeVisible: true,
                    secondsVisible: false,
                    tickMarkFormatter: (time) => {{
                        const date = new Date(time * 1000);
                        return date.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
                    }},
                }},
                watermark: {{
                    color: 'rgba(92, 166, 255, 0.1)',
                    text: '{symbol}',
                    fontSize: 48,
                }},
            }});

            // Resize handler
            window.addEventListener('resize', () => {{
                chart.resize(document.getElementById('chart-container').clientWidth, 500);
            }});

            // Main candlestick series
            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#3fb950',
                downColor: '#f85149',
                borderUpColor: '#3fb950',
                borderDownColor: '#f85149',
                wickUpColor: '#3fb950',
                wickDownColor: '#f85149',
                priceFormat: {{
                    type: 'price',
                    precision: 5,
                    minMove: 0.00001,
                }},
            }});
            candleSeries.setData(candlestickData);

            // EMA 20
            const ema20Series = chart.addLineSeries({{
                color: '#58a6ff',
                lineWidth: 1,
                title: 'EMA 20',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            ema20Series.setData(ema20Data);

            // EMA 50
            const ema50Series = chart.addLineSeries({{
                color: '#f97316',
                lineWidth: 1,
                title: 'EMA 50',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            ema50Series.setData(ema50Data);

            // Volume pane (separate chart)
            const volumeChart = LightweightCharts.createChart(document.getElementById('chart-container'), {{
                width: document.getElementById('chart-container').clientWidth,
                height: 150,
                layout: {{
                    background: {{ color: '#0e1117' }},
                    textColor: '#e0e0e0',
                    fontSize: 11,
                    fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
                }},
                grid: {{
                    vertLines: {{ color: '#21262d' }},
                    horzLines: {{ color: '#21262d' }},
                }},
                rightPriceScale: {{
                    borderColor: '#30363d',
                    visible: false,
                }},
                timeScale: {{
                    borderColor: '#30363d',
                    visible: false,
                }},
            }});

            const volumeSeries = volumeChart.addHistogramSeries({{
                color: '#58a6ff',
                priceFormat: {{
                    type: 'volume',
                }},
                priceScaleId: '',
            }});
            volumeSeries.setData(volumeData);

            // Timeframe buttons
            document.querySelectorAll('#toolbar button').forEach(btn => {{
                btn.addEventListener('click', () => {{
                    document.querySelectorAll('#toolbar button').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    // In real implementation, would fetch new data for timeframe
                    console.log('Timeframe changed to:', btn.dataset.res);
                }});
            }});

            // Price line crosshair sync
            const crosshairSync = LightweightCharts.CrosshairSync.create();
            crosshairSync.sync(crosshairSync, [candleSeries, ema20Series, ema50Series, volumeSeries]);

            // Make charts globally accessible for debugging
            window.tradingChart = {{ chart, candleSeries, ema20Series, ema50Series, volumeChart, volumeSeries }};
        </script>
    </body>
    </html>
    """

    # Render the chart
    components.html(chart_html, height=680, scrolling=False)


def render_console(state: DashboardState):
    """Render console output at bottom."""
    if not state.console_logs:
        st.markdown('<div class="console-container">No logs yet...</div>', unsafe_allow_html=True)
        return
        
    logs_html = '<div class="console-container">'
    
    # Show last 100 logs
    for log in list(state.console_logs)[-100:]:
        timestamp = log["timestamp"].strftime("%H:%M:%S.%f")[:-3]
        level = log["level"]
        message = log["message"]
        
        level_class = f"console-{level.lower()}"
        logs_html += f'<div class="console-line {level_class}"><span style="color:#6e7681;">[{timestamp}]</span> <span style="color:#8b949e;">[{level}]</span> {message}</div>'
        
    logs_html += '</div>'
    st.markdown(logs_html, unsafe_allow_html=True)


def render_brain_metrics(state: DashboardState):
    """Render brain metrics and status."""
    metrics = state.brain_metrics
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_decisions = metrics.get("total_decisions", 0)
        correct_decisions = metrics.get("correct_decisions", 0)
        accuracy = (correct_decisions / total_decisions * 100) if total_decisions > 0 else 0
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Decision Accuracy</div>
            <div class="metric-value {'metric-positive' if accuracy > 50 else 'metric-negative'}">{accuracy:.1f}%</div>
            <div style="font-size: 11px; color: #8b949e;">{correct_decisions}/{total_decisions}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        total_trades = metrics.get("total_trades", 0)
        winning_trades = metrics.get("winning_trades", 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value {'metric-positive' if win_rate > 50 else 'metric-negative'}">{win_rate:.1f}%</div>
            <div style="font-size: 11px; color: #8b949e;">{winning_trades}/{total_trades}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        total_pnl = metrics.get("total_pnl", 0)
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Total PnL</div>
            <div class="metric-value {'metric-positive' if total_pnl >= 0 else 'metric-negative'}">${total_pnl:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        sharpe = metrics.get("sharpe_ratio", 0)
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Sharpe Ratio</div>
            <div class="metric-value">{sharpe:.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Generation and evolution
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Generation</div>
            <div class="metric-value">{metrics.get('generation', 0)}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        health = metrics.get("health_status", "UNKNOWN")
        health_color = "#3fb950" if health == "HEALTHY" else "#d29922" if health == "DEGRADED" else "#f85149"
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Health</div>
            <div class="metric-value" style="color: {health_color};">{health}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Learning Rate</div>
            <div class="metric-value">{metrics.get('learning_rate', 0):.4f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Max Drawdown</div>
            <div class="metric-value metric-negative">{metrics.get('max_drawdown', 0)*100:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)


def render_selection_info(state: DashboardState):
    """Render current selection info."""
    selection = state.selection_result
    
    if not selection:
        st.info("No selection made yet")
        return
        
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class="session-detail">
            <div class="session-detail-title">📊 Current Selection</div>
            <div class="session-detail-row">
                <span class="session-detail-label">Method</span>
                <span class="session-detail-value">{selection.method.value}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Style</span>
                <span class="session-detail-value">{selection.style.value}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Strategy</span>
                <span class="session-detail-value">{selection.strategy}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Session</span>
                <span class="session-detail-value">{selection.session}</span>
            </div>
            <div class="session-detail-row">
                <span class="session-detail-label">Symbols</span>
                <span class="session-detail-value">{', '.join(selection.symbols[:5])}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        conf_color = "#3fb950" if selection.confidence > 0.7 else "#d29922" if selection.confidence > 0.5 else "#f85149"
        st.markdown(f"""
        <div class="session-detail">
            <div class="session-detail-title">🎯 Confidence & Reasoning</div>
            <div class="session-detail-row">
                <span class="session-detail-label">Confidence</span>
                <span class="session-detail-value" style="color: {conf_color}; font-weight: 600;">{selection.confidence*100:.1f}%</span>
            </div>
            <div style="margin-top: 12px; padding: 8px; background: #0d1117; border-radius: 4px; font-size: 11px; line-height: 1.5;">
                {selection.reasoning}
            </div>
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# Autonomous Trading Loop
# =============================================================================

async def run_autonomous_loop(state: DashboardState):
    """Main autonomous trading loop - runs continuously."""
    state.add_log("INFO", "🚀 Starting Autonomous Trading Loop")
    
    # Initialize brain
    brain = SelfEvolvingBrain({
        "save_path": "data/brain_state",
        "save_interval": 300,
    })
    await brain.initialize()
    state.brain = brain
    state.add_log("SUCCESS", "✅ Self-Evolving Brain initialized")
    
    # Initialize parallel processor
    parallel = ParallelProcessor(ParallelConfig(
        backend=BackendType.THREADING,
        max_workers=16,
    ))
    await parallel.initialize()
    state.parallel_processor = parallel
    state.add_log("SUCCESS", "✅ Parallel Processor initialized (16 workers)")
    
    # Initialize session manager
    await session_manager.initialize()
    state.add_log("SUCCESS", f"✅ Session Manager initialized ({len(session_manager.sessions)} sessions)")
    
    # Initialize selection engine
    await selection_engine.initialize()
    state.add_log("SUCCESS", "✅ Selection Engine initialized")
    
    state.connected = True
    state.add_log("INFO", "🔗 Connected to all systems")
    
    iteration = 0
    while st.session_state.auto_loop_running:
        try:
            iteration += 1
            loop_start = time.time()
            
            # Update sessions
            await session_manager.update_active_sessions()
            active_sessions = session_manager.get_active_sessions()
            active_symbols = session_manager.get_active_symbols()
            
            state.update_session_info(session_manager.get_session_summary())
            state.add_log("DEBUG", f"📊 Active sessions: {list(active_sessions.keys())}")
            
            # Simulate market data (replace with real data feed)
            market_data = {}
            for symbol in list(active_symbols)[:10]:
                base_price = 1.0850 if "EUR" in symbol else 1.2650 if "GBP" in symbol else 150.00
                price = base_price + np.random.normal(0, 0.001)
                market_data[symbol] = {
                    "symbol": symbol,
                    "bid": price - 0.0001,
                    "ask": price + 0.0001,
                    "last": price,
                    "volume": np.random.randint(1000, 10000),
                    "time": datetime.now(UTC),
                }
            state.update_market_data("multi", market_data)
            
            # Autonomous selection
            from src.autonomous.selection_engine import SelectionContext
            
            context = SelectionContext(
                timestamp=datetime.now(UTC),
                active_sessions=active_sessions,
                active_symbols=active_symbols,
                market_regime="trending_up",
                volatility=0.015,
                volume=1000000,
                spread=0.0002,
                account_size=100000,
                risk_tolerance=0.02,
                max_positions=10,
                current_positions=len(state.positions),
                performance_metrics=state.brain_metrics,
            )
            
            selection = await selection_engine.select_all(context)
            state.update_selection(selection)
            state.add_log("INFO", f"🎯 Selection: {selection.method.value} | {selection.style.value} | {selection.strategy} | {selection.session} | {', '.join(selection.symbols[:3])}...")
            
            # Process through brain
            brain_result = await brain.process_market_data(market_data)
            
            # Update brain metrics
            state.update_brain_metrics(brain.metrics)
            
            # Simulate trade execution (replace with real execution)
            if np.random.random() < 0.1:  # 10% chance per iteration
                symbol = np.random.choice(selection.symbols) if selection.symbols else "EURUSD"
                side = np.random.choice(["buy", "sell"])
                volume = round(np.random.uniform(0.01, 0.5), 2)
                entry = market_data.get(symbol, {}).get("last", 1.0850)
                
                trade = {
                    "symbol": symbol,
                    "side": side,
                    "volume": volume,
                    "entry": entry,
                    "current": entry + np.random.normal(0, 0.001),
                    "sl": entry - 0.0050 if side == "buy" else entry + 0.0050,
                    "tp": entry + 0.0100 if side == "buy" else entry - 0.0100,
                    "pnl": np.random.uniform(-50, 100),
                    "time": datetime.now(UTC),
                }
                state.add_trade(trade)
                state.add_log("SUCCESS", f"📈 Trade executed: {side.upper()} {volume} {symbol} @ {entry:.5f}")
            
            # Simulate PnL update
            equity = 100000 + sum(t.get("pnl", 0) for t in state.live_trades)
            pnl = equity - 100000
            state.update_pnl(pnl, equity)
            
            # Update account info
            state.update_account({
                "equity": equity,
                "balance": 100000,
                "profit": pnl,
                "daily_pnl": pnl,
                "margin": 5000,
                "free_margin": equity - 5000,
                "margin_level": (equity / 5000 * 100) if equity > 0 else 0,
            })
            
            # Add periodic logs
            if iteration % 10 == 0:
                state.add_log("INFO", f"🔄 Loop #{iteration} | Equity: ${equity:,.2f} | PnL: ${pnl:,.2f} | Positions: {len(state.live_trades)}")
            
            # Loop timing
            loop_time = time.time() - loop_start
            if iteration % 50 == 0:
                state.add_log("DEBUG", f"⏱️ Loop time: {loop_time*1000:.1f}ms | Brain: {brain_result.get('processing_time', 0)*1000:.1f}ms")
            
            # Sleep to control loop rate
            await asyncio.sleep(1.0)  # 1 second loop
            
        except Exception as e:
            state.add_log("ERROR", f"❌ Loop error: {e}")
            await asyncio.sleep(5.0)
    
    state.add_log("WARNING", "⚠️ Autonomous loop stopped")
    await parallel.shutdown()
    state.connected = False


def start_autonomous_loop():
    """Start the autonomous loop in background."""
    if not st.session_state.auto_loop_running:
        st.session_state.auto_loop_running = True
        state = st.session_state.dashboard_state
        # Run in background thread
        import threading
        def run_loop():
            asyncio.run(run_autonomous_loop(state))
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        state.add_log("INFO", "▶️ Autonomous loop started")


def stop_autonomous_loop():
    """Stop the autonomous loop."""
    st.session_state.auto_loop_running = False
    state = st.session_state.dashboard_state
    state.add_log("INFO", "⏹️ Stopping autonomous loop...")


def execute_command_bar(command: str) -> dict[str, Any]:
    """Execute command from global command bar."""
    command = command.strip()
    
    if not command:
        return {"error": "Empty command"}
    
    if not command.startswith('/'):
        return {"error": "Commands must start with /"}
    
    parts = command[1:].split()
    if not parts:
        return {"error": "No command specified"}
    
    cmd = parts[0].lower()
    args = parts[1:]
    
    # Help command
    if cmd in ["help", "h", "?"]:
        return {
            "message": "Command Bar Help",
            "commands": {
                "trading": ["/buy", "/sell", "/close", "/close_all", "/positions", "/orders"],
                "analysis": ["/chart", "/technical", "/fundamental", "/sentiment", "/correlation"],
                "execution": ["/vwap", "/twap", "/pov", "/is", "/iceberg"],
                "risk": ["/risk", "/leverage", "/mode", "/session", "/symbols"],
                "brain": ["/retrain", "/evolve", "/evaluate", "/goals", "/health"],
                "system": ["/help", "/status", "/logs", "/config", "/backup", "/shutdown"]
            }
        }
    
    # Status command
    if cmd in ["status", "st"]:
        return {
            "system": "Elite Autonomous Trading System",
            "status": "RUNNING",
            "mode": "AUTO",
            "uptime": "00:00:00",  # Would be real uptime
            "active_positions": 0,
            "total_pnl": 0.0,
            "brain_generation": 1,
            "health": "HEALTHY"
        }
    
    # Config command
    if cmd in ["config", "cfg"]:
        return {
            "simulation_mode": True,
            "risk_per_trade": 0.02,
            "max_positions": 10,
            "max_daily_loss": 0.05,
            "active_sessions": ["london", "new_york"],
            "trading_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
        }
    
    # Logs command
    if cmd in ["logs", "log"]:
        n = 50
        if args and args[0].isdigit():
            n = int(args[0])
        return {
            "message": f"Last {n} logs",
            "logs": [
                {"time": "10:30:00", "level": "INFO", "msg": "System started"},
                {"time": "10:30:01", "level": "INFO", "msg": "Connected to MT5"},
                {"time": "10:30:02", "level": "INFO", "msg": "Brain initialized"}
            ]
        }
    
    # Trading commands
    if cmd in ["buy", "b"]:
        return {"action": "buy", "symbol": args[0] if args else "EURUSD", "qty": float(args[1]) if len(args) > 1 else 1.0, "status": "simulated"}
    
    if cmd in ["sell", "s"]:
        return {"action": "sell", "symbol": args[0] if args else "EURUSD", "qty": float(args[1]) if len(args) > 1 else 1.0, "status": "simulated"}
    
    if cmd in ["close", "cl"]:
        return {"action": "close", "symbol": args[0] if args else "all", "status": "simulated"}
    
    if cmd in ["positions", "pos"]:
        return {"positions": []}
    
    if cmd in ["orders", "ord"]:
        return {"orders": []}
    
    # Analysis commands
    if cmd in ["chart", "ch"]:
        return {"action": "chart", "symbol": args[0] if args else "EURUSD", "timeframe": args[1] if len(args) > 1 else "1h"}
    
    if cmd in ["technical", "tech"]:
        return {"action": "technical", "symbol": args[0] if args else "EURUSD", "indicators": ["EMA", "RSI", "MACD", "BB"]}
    
    # Execution algos
    if cmd in ["vwap"]:
        return {"algo": "VWAP", "symbol": args[0] if args else "SPY", "qty": float(args[1]) if len(args) > 1 else 1000}
    
    if cmd in ["twap"]:
        return {"algo": "TWAP", "symbol": args[0] if args else "SPY", "qty": float(args[1]) if len(args) > 1 else 1000}
    
    if cmd in ["pov"]:
        return {"algo": "POV", "symbol": args[0] if args else "SPY", "qty": float(args[1]) if len(args) > 1 else 1000}
    
    if cmd in ["is"]:
        return {"algo": "IS", "symbol": args[0] if args else "SPY", "qty": float(args[1]) if len(args) > 1 else 1000}
    
    if cmd in ["iceberg"]:
        return {"algo": "ICEBERG", "symbol": args[0] if args else "SPY", "qty": float(args[1]) if len(args) > 1 else 1000}
    
    # Risk commands
    if cmd in ["risk"]:
        return {"risk_per_trade": args[0] if args else "2%"}
    
    if cmd in ["leverage", "lev"]:
        return {"leverage": args[0] if args else "10x"}
    
    if cmd in ["mode"]:
        return {"mode": args[0] if args else "auto"}
    
    if cmd in ["session", "sess"]:
        return {"active_session": args[0] if args else "london"}
    
    if cmd in ["symbols", "sym"]:
        return {"trading_symbols": args[0].split(",") if args else ["EURUSD", "GBPUSD"]}
    
    # Brain commands
    if cmd in ["retrain"]:
        return {"action": "retrain", "status": "initiated"}
    
    if cmd in ["evolve"]:
        return {"action": "evolve", "status": "initiated"}
    
    if cmd in ["evaluate", "eval"]:
        return {"action": "evaluate", "accuracy": 0.0, "win_rate": 0.0}
    
    if cmd in ["goals"]:
        return {"goals": ["maximize_sharpe", "minimize_drawdown", "increase_win_rate"]}
    
    if cmd in ["health"]:
        return {"health": "HEALTHY", "components": ["brain", "data", "execution", "risk"]}
    
    # System commands
    if cmd in ["backup"]:
        return {"action": "backup", "status": "completed", "path": "data/brain_state/backup.pkl"}
    
    if cmd in ["shutdown"]:
        return {"action": "shutdown", "status": "initiated"}
    
    return {"error": f"Unknown command: /{cmd}"}


# =============================================================================
# Main Dashboard
# =============================================================================

def render_overview(state: DashboardState) -> None:
    """Overview tab — PnL + session timeline + brain metrics."""
    render_live_pnl(state)
    render_session_timeline(state)
    render_brain_metrics(state)


def render_sessions(state: DashboardState) -> None:
    """Sessions tab — session timeline + details."""
    st.markdown("### 🕐 Trading Sessions")
    render_session_timeline(state)
    render_session_details(state)


def render_brain(state: DashboardState) -> None:
    """Brain tab — brain metrics + selection info."""
    render_brain_metrics(state)
    render_selection_info(state)


def render_trades_tab(state: DashboardState) -> None:
    """Trades tab — live trades + history."""
    st.markdown("### 📋 Live Trades & History")
    render_live_trades(state)


def render_bloomberg(state: DashboardState) -> None:
    """Bloomberg terminal tab."""
    st.markdown("### 📟 Bloomberg Terminal Adapter")
    st.markdown("*Bloomberg-style command interface: `[Ticker] <Sector> [Function]`*")
    try:
        adapter = get_bloomberg_adapter()
        st.info(f"Adapter status: {adapter.status}")
    except Exception:
        st.warning("Bloomberg adapter not available. Run `scripts/init_bloomberg.bat`.")


def render_command_bar(state: DashboardState) -> None:
    """Global command bar tab."""
    st.markdown("### 💡 Global Command Bar")
    st.markdown("*Bloomberg-style command interface with autocomplete - type `/` for commands*")
    cmd = st.text_input("Command", placeholder="/help, /status, /buy EURUSD 0.5, /closeall …")
    if cmd:
        st.info(f"Executing: `{cmd}`")


def main():
    # ── Authentication ──────────────────────────────────────────────────
    init_auth()
    if not require_login():
        return  # Login screen shown, stop here
    _user = get_current_user()

    state = st.session_state.dashboard_state

    # ── Sidebar: logo + user info + logout ─────────────────────────────
    with st.sidebar:
        # System logo
        try:
            import streamlit.components.v1 as _components
            _logo_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "assets", "logo_embed.html"
            )
            if os.path.exists(_logo_path):
                with open(_logo_path) as _f:
                    _components.html(_f.read(), height=220)
        except Exception:
            logging.getLogger(__name__).exception('Suppressed exception')

        st.markdown("---")
        st.markdown(f"👤 **{_user}** | Role: `{get_current_role() or 'admin'}`")
        if st.button("🚪 Logout", use_container_width=True):
            from src.dashboard.auth import logout
            logout()
            st.rerun()

    # Header with status and controls
    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
    
    with col1:
        status_color = "#3fb950" if state.connected else "#f85149"
        status_text = "CONNECTED" if state.connected else "DISCONNECTED"
        auto_status = "🟢 AUTO" if st.session_state.auto_loop_running else "🔴 MANUAL"
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 16px;">
            <h1 style="margin: 0; font-size: 24px; font-weight: 700;">ELITE AUTONOMOUS TRADING SYSTEM</h1>
            <span class="status-dot" style="background-color: {status_color};"></span>
            <span style="color: {status_color}; font-weight: 600; font-size: 13px;">{status_text}</span>
            <span style="color: #8b949e; font-size: 13px;">|</span>
            <span style="font-weight: 600; font-size: 13px;">{auto_status}</span>
            <span style="color: #8b949e; font-size: 13px;">|</span>
            <span style="color: #58a6ff; font-size: 13px;">{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</span>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button("▶️ START", use_container_width=True, type="primary" if not st.session_state.auto_loop_running else "secondary"):
            start_autonomous_loop()
            st.rerun()
            
    with col3:
        if st.button("⏹️ STOP", use_container_width=True, type="primary" if st.session_state.auto_loop_running else "secondary"):
            stop_autonomous_loop()
            st.rerun()
            
    with col4:
        if st.button("🔄 REFRESH", use_container_width=True):
            st.rerun()
            
    with col5:
        if st.button("🗑️ CLEAR LOGS", use_container_width=True):
            state.console_logs.clear()
            st.rerun()
    
    # Main tabs with dropdown selector
    tab_names = [
        "📊 OVERVIEW",
        "🕐 SESSIONS",
        "📈 LIVE CHART",
        "🧠 BRAIN",
        "📋 TRADES",
        "⚙️ SETTINGS",
        "🖥️ CONSOLE",
        "📟 BLOOMBERG",
        "💡 COMMAND BAR",
        "🛠️ SETTINGS & CONFIG",
        "🔐 CREDENTIALS",
        "📥 DATA INGESTION",
        "🔧 FEATURES",
        "⚔️ STRATEGY ENGINE",
        "⚖️ RISK MANAGER",
        "🗂️ ORDER MANAGER",
        "🪵 EXECUTION LOG",
        "⏱️ MONITORING",
        "🔒 SECURITY",
        "🌙 OVERNIGHT SAFETY",
        "📂 PORTFOLIO",
        "👁️ WATCHLIST",
        "📊 MARKET",
        "🔗 BROKER CONFIG",
        "🤖 AI & LLM",
        "🌐 EXTERNAL DATA",
        "📚 TRADE BOOK",
        "🎭 SENTIMENT ANALYZER",
        "📊 STOCK PREDICTOR",
        "🤖 AGENTIC AI",
        # New tabs added below
        "📊 MAIN SCAN",
        "📈 PRICE CHART",
        "🌐 WORLD INDICES",
        "📰 NEWS FEED",
        "📊 ANALYST RECS",
        "🕑 SESSION TIMELINE",
        "🪙 YIELD ANALYTICS",
        "📅 ECON CALENDAR",
        "⚙️ EMSX ROUTING",
        "🔐 DES SECURITY",
        "📥 ING TELEMETRY",
        "🔧 FEAT STORE",
        "⚔️ STRAT VOTING",
        "⚖️ RISK CIRCUIT",
        "🗂️ ORD BOOK",
        "🪵 LOG EXEC",
        "⏱️ MON HEALTH",
        "🔒 SEC AUTH",
        "📂 PF PORTFOLIO",
        "📖 HELP",
    ]
    # Dropdown for tab selection
    selected_tab = st.selectbox("Select Dashboard Tab", tab_names, index=0, help="Choose any tab to jump directly")

    # Create a mapping from name to content function
    tab_content_map = {
        "📊 OVERVIEW": lambda: render_overview(state),
        "🕐 SESSIONS": lambda: render_sessions(state),
        "📈 LIVE CHART": lambda: render_live_chart(state),
        "🧠 BRAIN": lambda: render_brain(state),
        "📋 TRADES": lambda: render_trades_tab(state),
        "⚙️ SETTINGS": lambda: render_settings_tab(),
        "🖥️ CONSOLE": lambda: render_console(state),
        "📟 BLOOMBERG": lambda: render_bloomberg(state),
        "💡 COMMAND BAR": lambda: render_command_bar(state),
        "🛠️ SETTINGS & CONFIG": lambda: render_settings_tab(),
        "🔐 CREDENTIALS": lambda: render_credentials_tab(),
        "📥 DATA INGESTION": lambda: render_data_ingestion_tab(),
        "🔧 FEATURES": lambda: render_feature_store_tab(),
        "⚔️ STRATEGY ENGINE": lambda: render_strategy_engine_tab(),
        "⚖️ RISK MANAGER": lambda: render_risk_manager_tab(),
        "🗂️ ORDER MANAGER": lambda: render_order_manager_tab(),
        "🪵 EXECUTION LOG": lambda: render_execution_logger_tab(),
        "⏱️ MONITORING": lambda: render_monitoring_tab(),
        "🔒 SECURITY": lambda: render_security_tab(),
        "🌙 OVERNIGHT SAFETY": lambda: render_overnight_tab(),
        "📂 PORTFOLIO": lambda: render_portfolio_tab(),
        "👁️ WATCHLIST": lambda: render_watchlist_tab(),
        "📊 MARKET": lambda: render_market_tab(),
        "🔗 BROKER CONFIG": lambda: render_broker_config_tab(),
        "🤖 AI & LLM": lambda: render_ai_config_tab(),
        "\uD83C\uDF10 EXTERNAL DATA": lambda: render_external_data_tab(),
        # New tabs added below
        "\uD83D\uDCCA MAIN SCAN": lambda: render_main_scan_tab(),
        "\uD83D\uDCC8 PRICE CHART": lambda: render_price_chart_tab(),
        "\uD83C\uDF10 WORLD INDICES": lambda: render_world_indices_tab(),
        "\uD83D\uDCF0 NEWS FEED": lambda: render_news_feed_tab(),
        "\uD83D\uDCCA ANALYST RECS": lambda: render_anr_recommend_tab(),
        "\uD83D\uDD51 SESSION TIMELINE": lambda: render_session_timeline_tab(),
        "\uD83E\uDE99 YIELD ANALYTICS": lambda: render_yield_analytics_tab(),
        "\uD83D\uDCC5 ECON CALENDAR": lambda: render_econ_calendar_tab(),
        "\u2699\uFE0F EMSX ROUTING": lambda: render_emsx_routing_tab(),
        "\uD83D\uDD10 DES SECURITY": lambda: render_des_security_tab(),
        "\uD83D\uDCE5 ING TELEMETRY": lambda: render_ing_telemetry_tab(),
        "\uD83D\uDD27 FEAT STORE": lambda: render_feat_store_tab(),
        "\u2694\uFE0F STRAT VOTING": lambda: render_strat_voting_tab(),
        "\u2696\uFE0F RISK CIRCUIT": lambda: render_risk_circuit_tab(),
        "\uD83D\uDDC2\uFE0F ORD BOOK": lambda: render_ord_book_tab(),
        "\uD83E\uDEB5 LOG EXEC": lambda: render_log_exec_tab(),
        "\u23F1\uFE0F MON HEALTH": lambda: render_mon_health_tab(),
        "\uD83D\uDD12 SEC AUTH": lambda: render_sec_auth_tab(),
        "\uD83D\uDCC2 PF PORTFOLIO": lambda: render_pf_portfolio_tab(),
        "\uD83D\uDCDA TRADE BOOK": lambda: render_trade_book_tab(),
        "\uD83C\uDFAE SENTIMENT ANALYZER": lambda: render_sentiment_tab(),
        "\uD83D\uDCCA STOCK PREDICTOR": lambda: render_stock_predictor_tab(),
        "\uD83E\uDD16 AGENTIC AI": lambda: render_agentic_ai_tab(),
        "\uD83D\uDCD6 HELP": lambda: render_help_tab(),
    }
    # ── Settings tab requires re-authentication ──────────────────────────
    if selected_tab in ("⚙️ SETTINGS", "🛠️ SETTINGS & CONFIG"):
        if not require_settings_auth():
            return  # Re-auth form shown, stop here

    # Apply vibrant color theme for the selected tab (handled by each tab's own injection)
    # from src.dashboard.tab_themes import inject_tab_theme
    # inject_tab_theme(selected_tab)

    # Render selected tab content
    if selected_tab in tab_content_map:
        tab_content_map[selected_tab]()
    else:
        st.warning(f"Tab '{selected_tab}' not implemented yet.")

    # Legacy tab rendering (keep for backward compatibility)
    # Existing code for 9 hardcoded tabs remains below (if needed for older UI).
    # Legacy brain metrics rendering removed – handled by the new BRAIN tab.
        st.markdown("### ⚡ Autonomous Capabilities")
        
        capabilities = [
            ("🧠 Self-Learning", "Continuous learning from market experience", True),
            ("🏋️ Self-Training", "Automatic model retraining every hour", True),
            ("⚙️ Self-Adjusting", "Dynamic parameter optimization", True),
            ("🏥 Self-Healing", "Error detection and recovery", True),
            ("🔧 Self-Fixing", "Bug detection and correction", True),
            ("🎯 Self-Correcting", "Decision correction based on outcomes", True),
            ("🧬 Self-Evolving", "Architecture evolution via NAS", True),
            ("📈 Self-Developing", "Capability expansion", True),
            ("👨‍🏫 Self-Teaching", "Knowledge distillation", True),
            ("🎯 Self-Determining", "Goal setting and prioritization", True),
            ("📊 Self-Evaluating", "Performance assessment", True),
        ]
        
        cols = st.columns(3)
        for i, (name, desc, active) in enumerate(capabilities):
            with cols[i % 3]:
                status = "🟢 ACTIVE" if active else "🔴 INACTIVE"
                st.markdown(f"""
                <div class="session-detail">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="font-weight: 600;">{name}</span>
                        <span style="color: {'#3fb950' if active else '#f85149'}; font-size: 11px;">{status}</span>
                    </div>
                    <div style="font-size: 11px; color: #8b949e;">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
    
    # Legacy tab5-tab9 content removed — now handled by dropdown above.

    # Auto-refresh
    if st.session_state.auto_loop_running:
        time.sleep(0.5)
        st.rerun()


if __name__ == "__main__":
    main()