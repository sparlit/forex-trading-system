from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from loguru import logger

from src.infra.config import settings

# Page configuration
st.set_page_config(
    page_title="Forex Trading System - Autonomous Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #333;
    }
    .positive { color: #00ff00; }
    .negative { color: #ff4444; }
    .neutral { color: #ffff00; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        background-color: #262626;
        border-radius: 4px 4px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e1e1e !important;
    }
    .ea-status-connected { color: #00ff00; font-weight: bold; }
    .ea-status-disconnected { color: #ff4444; font-weight: bold; }
    .regime-trending_up { background-color: #004400; }
    .regime-trending_down { background-color: #440000; }
    .regime-ranging { background-color: #444400; }
    .regime-volatile { background-color: #440044; }
    .regime-unknown { background-color: #333333; }
    .brain-status-active { color: #00ff00; }
    .brain-status-paused { color: #ffff00; }
    .brain-status-error { color: #ff4444; }
    .trade-long { background-color: #003300; border-left: 3px solid #00ff00; }
    .trade-short { background-color: #330000; border-left: 3px solid #ff4444; }
    .session-active { color: #00ff00; }
    .session-inactive { color: #ff4444; }
    .process-running { color: #00ff00; }
    .process-stopped { color: #ff4444; }
    
    /* Mobile-responsive adjustments */
    @media (max-width: 768px) {
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            padding: 0 12px;
            font-size: 0.9rem;
        }
        .metric-card {
            padding: 0.75rem;
        }
        .stMetric {
            font-size: 0.9rem;
        }
    }
    @media (max-width: 480px) {
        .stTabs [data-baseweb="tab"] {
            height: 32px;
            padding: 0 8px;
            font-size: 0.8rem;
        }
        h1 { font-size: 1.4rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.0rem !important; }
    }
</style>
""", unsafe_allow_html=True)


class DashboardApp:
    """Comprehensive Streamlit dashboard for the autonomous trading system."""

    def __init__(self):
        self._initialize_session_state()
        self.api_url = "http://localhost:8000"
        self.ea_bridge_url = "http://localhost:8000"
        import numpy as np
        self.np = np

    def _initialize_session_state(self) -> None:
        """Initialize session state variables."""
        defaults = {
            "last_update": 0,
            "equity_data": [],
            "positions_data": [],
            "signals_data": [],
            "risk_metrics": {},
            "strategies_status": {},
            "mt5_account": {},
            "ea_bridge_status": {},
            "brain_status": {},
            "market_regime": {},
            "active_sessions": {},
            "symbol_indicators": {},
            "background_processes": {},
            "crypto_sessions": {},
        }
        for key, default in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default

    # ---------------------------------------------------------------------
    # Data fetching methods
    # ---------------------------------------------------------------------
    def _fetch_with_timeout(self, url: str, timeout: int = 3) -> Any | None:
        """Fetch data from API with timeout."""
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
        return None

    def _get_equity_data(self) -> pd.DataFrame:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/equity_curve?points=1000")
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame(columns=["timestamp", "equity"])

    def _get_recent_trades(self, limit: int = 100) -> pd.DataFrame:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/trades?limit={limit}")
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "volume", "price", "pnl", "strategy_id", "trade_style", "hold_time"])

    def _get_positions_dataframe(self) -> pd.DataFrame:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/positions")
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame(columns=["symbol", "side", "volume", "entry_price", "current_price", "unrealized_pnl", "strategy_id", "ticket", "trade_style", "entry_time", "hold_time", "stop_loss", "take_profit", "current_rr"])

    def _get_signals_dataframe(self, limit: int = 100) -> pd.DataFrame:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/signals?limit={limit}")
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame(columns=["timestamp", "symbol", "type", "direction", "confidence", "strategy_id", "entry_price", "stop_loss", "take_profit", "trade_style", "risk_reward", "position_size_pct"])

    def _get_risk_metrics(self) -> dict:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/metrics")
        return data or {}

    def _get_strategies_status(self) -> dict:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/strategies/status")
        return data or {}

    def _get_brain_status(self) -> dict:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/brain/status")
        return data or {}

    def _get_mt5_account(self) -> dict:
        data = self._fetch_with_timeout(f"{self.ea_bridge_url}/api/v1/ea/account")
        return data or {}

    def _get_ea_bridge_status(self) -> dict:
        data = self._fetch_with_timeout(f"{self.ea_bridge_url}/health")
        return data or {}

    def _get_market_regime(self) -> dict:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/market/regime")
        return data or {}

    def _get_performance_attribution(self) -> dict:
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/performance/attribution")
        return data or {}

    def _get_active_sessions(self) -> dict:
        """Get active trading sessions for forex and crypto."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/market/sessions")
        return data or {}

    def _get_symbol_indicators(self) -> dict:
        """Get all indicators for all symbols."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/market/indicators")
        return data or {}

    def _get_blind_spot_alerts(self) -> dict:
        """Get blind spot alerts from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/blind-spots/alerts")
        return data or {}

    def _get_blind_spot_summary(self) -> dict:
        """Get blind spot summary from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/blind-spots/summary")
        return data or {}

    def _get_factor_analysis(self) -> dict:
        """Get factor analysis from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/performance/factor-analysis")
        return data or {}

    def _get_correlation_clusters(self) -> dict:
        """Get correlation clusters from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/correlation-clusters")
        return data or {}

    def _get_regime_transitions(self) -> dict:
        """Get regime transition signals from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/market/regime-transitions")
        return data or {}

    def _get_liquidity_metrics(self) -> dict:
        """Get liquidity metrics from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/liquidity")
        return data or {}

    def _get_tail_risk(self) -> dict:
        """Get tail risk metrics from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/tail-risk")
        return data or {}

    def _get_model_health(self) -> dict:
        """Get model health from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/ml/model-health")
        return data or {}

    def _get_behavioral_bias(self) -> dict:
        """Get behavioral bias metrics from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/behavioral-bias")
        return data or {}

    def _get_concentration_risk(self) -> dict:
        """Get concentration risk from API."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/risk/concentration")
        return data or {}

    def _get_background_processes(self) -> dict:
            """Get background processes status."""
            import os

            import psutil
        
            processes = {}
            current_pid = os.getpid()
        
            # Get info for current process and children
            try:
                parent = psutil.Process(current_pid)
                for child in parent.children(recursive=True):
                    try:
                        with child.oneshot():
                            processes[child.name()] = {
                                'running': True,
                                'cpu_percent': child.cpu_percent(),
                                'memory_mb': child.memory_info().rss / 1024 / 1024
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except psutil.NoSuchProcess:
                raise NotImplementedError("Not implemented")
        
            # Also check for common trading system processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if any(keyword in cmdline.lower() for keyword in ['uvicorn', 'streamlit', 'python -m src.data', 'bloomberg']):
                        if proc.info['pid'] != current_pid:
                            with proc.oneshot():
                                processes[proc.info['name']] = {
                                    'running': True,
                                    'cpu_percent': proc.cpu_percent(),
                                    'memory_mb': proc.memory_info().rss / 1024 / 1024
                                }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
            # If no processes found, return basic info from EA Bridge health
            if not processes:
                data = self._fetch_with_timeout(f"{self.ea_bridge_url}/health")
                if data and isinstance(data, dict):
                    processes['ea_bridge'] = {
                        'running': data.get('status') == 'ok',
                        'cpu_percent': 0,
                        'memory_mb': 0
                    }
        
            return processes

    def _get_crypto_sessions(self) -> dict:
        """Get crypto trading sessions."""
        data = self._fetch_with_timeout(f"{self.api_url}/api/v1/market/crypto_sessions")
        return data or {}

    def _check_health_endpoints(self) -> dict[str, bool]:
        """Check API and service health endpoints."""
        health = {}
        
        # Main API
        try:
            resp = requests.get(f"{self.api_url}/health", timeout=2)
            health["api"] = resp.status_code == 200
        except Exception:
            health["api"] = False
        
        # EA Bridge
        try:
            resp = requests.get(f"{self.ea_bridge_url}/health", timeout=2)
            health["ea_bridge"] = resp.status_code == 200
        except Exception:
            health["ea_bridge"] = False
        
        # Database
        health["database"] = health["api"]
        
        return health

    # ---------------------------------------------------------------------
    # Chart creation methods
    # ---------------------------------------------------------------------
    def _create_equity_chart(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            return None
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['equity'], 
            mode='lines', name='Equity',
            line={"color": '#00ff00', "width": 2}
        ))
        fig.update_layout(
            xaxis_title='Time', yaxis_title='Equity ($)', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_drawdown_chart(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            return None
        df = df.copy()
        peak = df['equity'].cummax()
        drawdown = (df['equity'] - peak) / peak * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=drawdown, 
            mode='lines', name='Drawdown',
            fill='tozeroy', fillcolor='rgba(255,68,68,0.3)',
            line={"color": '#ff4444', "width": 1}
        ))
        fig.update_layout(
            xaxis_title='Time', yaxis_title='Drawdown (%)', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_monthly_returns_chart(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            return None
        df = df.copy()
        df['month'] = df['timestamp'].dt.to_period('M')
        df_month = df.groupby('month')['equity'].last().reset_index()
        df_month['timestamp'] = df_month['month'].dt.to_timestamp()
        df_month['return'] = df_month['equity'].pct_change().fillna(0) * 100
        colors = ['#00ff00' if r >= 0 else '#ff4444' for r in df_month['return']]
        fig = go.Figure(data=[go.Bar(
            x=df_month['timestamp'].dt.strftime('%Y-%m'), 
            y=df_month['return'], 
            name='Monthly Return',
            marker_color=colors
        )])
        fig.update_layout(
            xaxis_title='Month', yaxis_title='Return (%)', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_allocation_chart(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            return None
        df = df.copy()
        df['notional'] = df['volume'] * df['current_price']
        fig = go.Figure(data=[go.Pie(
            labels=df['symbol'], values=df['notional'], hole=0.4,
            textinfo='label+percent', textposition='inside'
        )])
        fig.update_layout(
            title='Position Allocation by Notional', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_correlation_heatmap(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "BTCUSD", "ETHUSD"]
            size = len(symbols)
            corr = self.np.eye(size)
        else:
            symbols = df['symbol'].tolist()
            size = len(symbols)
            corr = self.np.eye(size)
        fig = go.Figure(data=go.Heatmap(
            z=corr, x=symbols, y=symbols, 
            colorscale='RdBu', zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr],
            texttemplate="%{text}", textfont={"size": 10}
        ))
        fig.update_layout(
            title='Position Correlation Matrix', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_risk_metrics_table(self, metrics: dict) -> go.Figure | None:
        if not metrics:
            return None
        fig = go.Figure(data=[go.Table(
            header={
                "values": ['Metric', 'Value'], 
                "fill_color": '#262626', "font": {"color": 'white', "size": 12},
                "align": 'left'
            },
            cells={
                "values": [list(metrics.keys()), list(metrics.values())], 
                "fill_color": '#1e1e1e', "font": {"color": 'white', "size": 11},
                "align": 'left'
            }
        )])
        fig.update_layout(
            title='Risk Metrics', template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_signals_table(self, df: pd.DataFrame) -> go.Figure | None:
        if df.empty:
            return None
        display_df = df.copy()
        if 'timestamp' in display_df.columns:
            display_df['timestamp'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        fig = go.Figure(data=[go.Table(
            header={
                "values": list(display_df.columns), 
                "fill_color": '#262626', "font": {"color": 'white', "size": 11},
                "align": 'left'
            },
            cells={
                "values": [display_df[c].tolist() for c in display_df.columns], 
                "fill_color": '#1e1e1e', "font": {"color": 'white', "size": 10},
                "align": 'left'
            }
        )])
        fig.update_layout(
            title='Recent Signals', template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_strategy_performance_chart(self, strategies: dict) -> go.Figure | None:
        if not strategies:
            return None
        
        names, returns, sharpes, win_rates, styles = [], [], [], [], []
        
        for sid, info in strategies.items():
            names.append(info.get('name', sid))
            returns.append(info.get('total_return', 0) * 100)
            sharpes.append(info.get('sharpe_ratio', 0))
            win_rates.append(info.get('win_rate', 0) * 100)
            styles.append(info.get('trade_style', 'Unknown'))
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=names, y=returns, name='Total Return (%)', marker_color='#00ff00'))
        fig.add_trace(go.Bar(x=names, y=sharpes, name='Sharpe Ratio', marker_color='#00ffff', yaxis='y2'))
        fig.add_trace(go.Bar(x=names, y=win_rates, name='Win Rate (%)', marker_color='#ffff00', yaxis='y3'))
        
        fig.update_layout(
            title='Strategy Performance Comparison',
            template='plotly_dark', height=400,
            barmode='group',
            yaxis={"title": 'Return (%)', "side": 'left'},
            yaxis2={"title": 'Sharpe', "overlaying": 'y', "side": 'right', "showgrid": False},
            yaxis3={"title": 'Win Rate (%)', "anchor": 'free', "overlaying": 'y', "side": 'right', "position": 0.95, "showgrid": False},
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_performance_attribution_chart(self, attribution: dict) -> go.Figure | None:
        if not attribution:
            return None
        
        categories, values, colors = [], [], []
        
        for cat, val in attribution.items():
            if isinstance(val, (int, float)):
                categories.append(cat.replace('_', ' ').title())
                values.append(val)
                colors.append('#00ff00' if val >= 0 else '#ff4444')
        
        if not categories:
            return None
        
        fig = go.Figure(data=[go.Bar(
            x=categories, y=values, 
            marker_color=colors,
            text=[f"{v:.2f}%" for v in values],
            textposition='auto'
        )])
        fig.update_layout(
            title='Performance Attribution', 
            template='plotly_dark', height=400,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    def _create_indicator_chart(self, symbol: str, indicators: dict) -> go.Figure | None:
        """Create chart showing all indicators for a symbol."""
        if not indicators or symbol not in indicators:
            return None
        
        ind = indicators[symbol]
        fig = go.Figure()
        
        # Price with moving averages
        if 'close' in ind:
            fig.add_trace(go.Scatter(
                x=list(range(len(ind['close']))), y=ind['close'],
                mode='lines', name='Close', line={"color": 'white', "width": 1}
            ))
        if 'ema_20' in ind:
            fig.add_trace(go.Scatter(
                x=list(range(len(ind['ema_20']))), y=ind['ema_20'],
                mode='lines', name='EMA 20', line={"color": '#00ffff', "width": 1}
            ))
        if 'ema_50' in ind:
            fig.add_trace(go.Scatter(
                x=list(range(len(ind['ema_50']))), y=ind['ema_50'],
                mode='lines', name='EMA 50', line={"color": '#ff8800', "width": 1}
            ))
        
        fig.update_layout(
            title=f'{symbol} - Price & MAs', 
            template='plotly_dark', height=300,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        return fig

    # ---------------------------------------------------------------------
    # Main dashboard render
    # ---------------------------------------------------------------------
    def run(self):
        """Run the Streamlit dashboard."""
        # Auto-refresh every 5 seconds
        st.markdown(
            '<meta http-equiv="refresh" content="5">', 
            unsafe_allow_html=True
        )
        
        st.title("🤖 Forex Trading System - Autonomous Dashboard")
        
        # Fetch all data
        health = self._check_health_endpoints()
        equity_df = self._get_equity_data()
        positions_df = self._get_positions_dataframe()
        signals_df = self._get_signals_dataframe()
        trades_df = self._get_recent_trades()
        risk_metrics = self._get_risk_metrics()
        strategies_status = self._get_strategies_status()
        brain_status = self._get_brain_status()
        mt5_account = self._get_mt5_account()
        ea_bridge_status = self._get_ea_bridge_status()
        market_regime = self._get_market_regime()
        performance_attribution = self._get_performance_attribution()
        active_sessions = self._get_active_sessions()
        symbol_indicators = self._get_symbol_indicators()
        background_processes = self._get_background_processes()
        crypto_sessions = self._get_crypto_sessions()
        
        # New blind spot and factor analysis data
        blind_spot_alerts = self._get_blind_spot_alerts()
        blind_spot_summary = self._get_blind_spot_summary()
        factor_analysis = self._get_factor_analysis()
        correlation_clusters = self._get_correlation_clusters()
        regime_transitions = self._get_regime_transitions()
        liquidity_metrics = self._get_liquidity_metrics()
        tail_risk = self._get_tail_risk()
        model_health = self._get_model_health()
        behavioral_bias = self._get_behavioral_bias()
        concentration_risk = self._get_concentration_risk()
        
        # Update session state
        st.session_state.mt5_account = mt5_account
        st.session_state.ea_bridge_status = ea_bridge_status
        st.session_state.brain_status = brain_status
        st.session_state.market_regime = market_regime
        st.session_state.active_sessions = active_sessions
        st.session_state.symbol_indicators = symbol_indicators
        st.session_state.background_processes = background_processes
        st.session_state.crypto_sessions = crypto_sessions
        st.session_state.risk_metrics = risk_metrics
        st.session_state.strategies_status = strategies_status
        st.session_state.blind_spot_alerts = blind_spot_alerts
        st.session_state.blind_spot_summary = blind_spot_summary
        st.session_state.factor_analysis = factor_analysis
        st.session_state.correlation_clusters = correlation_clusters
        st.session_state.regime_transitions = regime_transitions
        st.session_state.liquidity_metrics = liquidity_metrics
        st.session_state.tail_risk = tail_risk
        st.session_state.model_health = model_health
        st.session_state.behavioral_bias = behavioral_bias
        st.session_state.concentration_risk = concentration_risk
        if not equity_df.empty:
            st.session_state.equity_data = equity_df
        if not positions_df.empty:
            st.session_state.positions_data = positions_df
        if not signals_df.empty:
            st.session_state.signals_data = signals_df
        
        # ============================================================
        # HEADER METRICS ROW
        # ============================================================
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
        
        with col1:
            equity = mt5_account.get('equity', 0)
            balance = mt5_account.get('balance', 0)
            pnl = equity - balance if equity and balance else 0
            st.metric(
                "Account Equity", 
                f"${equity:,.2f}" if equity else "N/A",
                delta=f"${pnl:,.2f}" if pnl else None,
                delta_color="normal" if pnl >= 0 else "inverse"
            )
        
        with col2:
            margin_level = mt5_account.get('margin_level', 0)
            ml_color = "🟢" if margin_level > 500 else "🟡" if margin_level > 200 else "🔴"
            st.metric(
                "Margin Level", 
                f"{margin_level:.1f}%" if margin_level else "N/A",
                delta=f"{ml_color} {'Healthy' if margin_level > 500 else 'Warning' if margin_level > 200 else 'Critical'}"
            )
        
        with col3:
            brain_state = brain_status.get('state', 'UNKNOWN')
            state_emoji = {"ACTIVE": "🟢", "PAUSED": "🟡", "ERROR": "🔴", "STOPPING": "🟠"}.get(brain_state, "⚪")
            st.metric(
                "Brain State", 
                f"{state_emoji} {brain_state}",
                delta=f"Trades: {brain_status.get('trades_executed', 0)}"
            )
        
        with col4:
            regime = market_regime.get('regime', 'UNKNOWN')
            confidence = market_regime.get('confidence', 0)
            regime_emoji = {
                "TRENDING_UP": "📈", "TRENDING_DOWN": "📉", 
                "RANGING": "↔️", "VOLATILE": "⚡",
                "BREAKOUT": "🚀", "MEAN_REVERTING": "🔄"
            }.get(regime, "❓")
            st.metric(
                "Market Regime", 
                f"{regime_emoji} {regime.replace('_', ' ').title()}",
                delta=f"Conf: {confidence:.0%}" if confidence else None
            )
        
        with col5:
            ea_connected = ea_bridge_status.get('connected_eas', 0)
            st.metric(
                "EA Connected", 
                f"{ea_connected} EA(s)",
                delta="🟢 Online" if ea_connected > 0 else "🔴 Offline"
            )
        
        with col6:
            daily_pnl = brain_status.get('daily_pnl', 0)
            st.metric(
                "Daily P&L", 
                f"${daily_pnl:,.2f}",
                delta_color="normal" if daily_pnl >= 0 else "inverse"
            )
        
        with col7:
            total_positions = len(positions_df)
            st.metric(
                "Open Positions", 
                total_positions,
                delta=f"Styles: {positions_df['trade_style'].nunique() if not positions_df.empty and 'trade_style' in positions_df.columns else 0}"
            )
        
        with col8:
            # Active session info
            forex_active = any(s.get('active', False) for s in active_sessions.get('forex', {}).values())
            crypto_active = any(s.get('active', False) for s in crypto_sessions.get('crypto', {}).values())
            session_status = "🟢 Forex" if forex_active else ("🟡 Crypto" if crypto_active else "🔴 None")
            st.metric(
                "Active Session", 
                session_status,
                delta="Auto-switch" if not forex_active and crypto_active else None
            )
        
        # ============================================================
        # SIDEBAR
        # ============================================================
        with st.sidebar:
            st.header("🔧 System Health")
            
            for service, status in health.items():
                color = "🟢" if status else "🔴"
                st.write(f"{color} {service.replace('_', ' ').title()}")
            
            st.divider()
            
            # MT5 Account Details
            if mt5_account:
                st.header("💰 MT5 Account")
                st.write(f"**Login:** {mt5_account.get('login', 'N/A')}")
                st.write(f"**Server:** {mt5_account.get('server', 'N/A')}")
                st.write(f"**Currency:** {mt5_account.get('currency', 'N/A')}")
                st.write(f"**Leverage:** 1:{mt5_account.get('leverage', 'N/A')}")
                st.write(f"**Balance:** ${mt5_account.get('balance', 0):,.2f}")
                st.write(f"**Equity:** ${mt5_account.get('equity', 0):,.2f}")
                st.write(f"**Free Margin:** ${mt5_account.get('free_margin', 0):,.2f}")
                st.write(f"**Margin:** ${mt5_account.get('margin', 0):,.2f}")
                st.write(f"**Profit:** ${mt5_account.get('profit', 0):,.2f}")
            
            st.divider()
            
            # Brain Status
            if brain_status:
                st.header("🧠 Brain Status")
                st.write(f"**State:** {brain_status.get('state', 'UNKNOWN')}")
                st.write(f"**Session:** {brain_status.get('session_duration', 'N/A')}")
                st.write(f"**Decisions:** {brain_status.get('decisions_made', 0)}")
                st.write(f"**Trades:** {brain_status.get('trades_executed', 0)}")
                st.write(f"**Total P&L:** ${brain_status.get('total_pnl', 0):,.2f}")
                st.write(f"**Daily P&L:** ${brain_status.get('daily_pnl', 0):,.2f}")
                st.write(f"**Max DD:** {brain_status.get('max_drawdown', 0):.2%}")
            
            st.divider()
            
            # Active Sessions
            st.header("🌍 Trading Sessions")
            
            # Forex sessions
            if active_sessions.get('forex'):
                st.subheader("Forex")
                for session, info in active_sessions['forex'].items():
                    active = info.get('active', False)
                    status = "🟢" if active else "🔴"
                    st.write(f"{status} {session}: {info.get('time_range', 'N/A')}")
            
            # Crypto sessions
            if crypto_sessions.get('crypto'):
                st.subheader("Crypto (24/7)")
                for session, info in crypto_sessions['crypto'].items():
                    active = info.get('active', False)
                    status = "🟢" if active else "🔴"
                    st.write(f"{status} {session}: {info.get('time_range', '24/7')}")
            
            st.divider()
            
            # Background Processes
            if background_processes:
                st.header("⚙️ Background Processes")
                for proc, info in background_processes.items():
                    running = info.get('running', False)
                    status = "🟢" if running else "🔴"
                    cpu = info.get('cpu_percent', 0)
                    mem = info.get('memory_mb', 0)
                    st.write(f"{status} {proc}: CPU {cpu:.1f}%, Mem {mem:.0f}MB")
            
            st.divider()
            
            # Controls
            st.header("⚙️ Controls")
            if st.button("🔄 Refresh Data", use_container_width=True):
                st.rerun()
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("⏸️ Pause Brain", use_container_width=True):
                    requests.post(f"{self.api_url}/api/v1/brain/pause")
                    st.rerun()
            with col_b:
                if st.button("▶️ Resume Brain", use_container_width=True):
                    requests.post(f"{self.api_url}/api/v1/brain/resume")
                    st.rerun()
            
            if st.button("🛑 Stop Brain", type="secondary", use_container_width=True):
                requests.post(f"{self.api_url}/api/v1/brain/stop")
                st.rerun()
        
        # ============================================================
        # MAIN TABS
        # ============================================================
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
            "📊 Equity & PnL", 
            "📈 Positions", 
            "⚠️ Risk", 
            "🎯 Signals", 
            "📋 Trades", 
            "🧠 Brain & Strategies",
            "📈 Performance",
            "🌍 Sessions & Symbols",
            "⚙️ System & Processes",
            "🛡️ Blind Spots",
            "📊 Factor Analysis",
            "🔬 Model Health"
        ])
        
        with tab1:
            st.subheader("Equity Curve & Drawdown")
            col1, col2 = st.columns(2)
            with col1:
                eq_chart = self._create_equity_chart(equity_df)
                if eq_chart:
                    st.plotly_chart(eq_chart, use_container_width=True)
            with col2:
                dd_chart = self._create_drawdown_chart(equity_df)
                if dd_chart:
                    st.plotly_chart(dd_chart, use_container_width=True)
            
            st.subheader("Monthly Returns & Correlation")
            col3, col4 = st.columns(2)
            with col3:
                monthly_chart = self._create_monthly_returns_chart(equity_df)
                if monthly_chart:
                    st.plotly_chart(monthly_chart, use_container_width=True)
            with col4:
                corr_chart = self._create_correlation_heatmap(positions_df)
                if corr_chart:
                    st.plotly_chart(corr_chart, use_container_width=True)
            
            # Key Statistics
            if not equity_df.empty:
                st.subheader("Key Statistics")
                total_return = (equity_df['equity'].iloc[-1] / equity_df['equity'].iloc[0] - 1) * 100
                max_dd = ((equity_df['equity'].cummax() - equity_df['equity']) / equity_df['equity'].cummax()).max() * 100
                sharpe = equity_df['equity'].pct_change().mean() / equity_df['equity'].pct_change().std() * self.np.sqrt(252) if equity_df['equity'].pct_change().std() > 0 else 0
                
                stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                stat_col1.metric("Total Return", f"{total_return:.2f}%")
                stat_col2.metric("Max Drawdown", f"{max_dd:.2f}%")
                stat_col3.metric("Sharpe Ratio", f"{sharpe:.2f}")
                stat_col4.metric("Current Equity", f"${equity_df['equity'].iloc[-1]:,.2f}")
        
        with tab2:
            st.subheader("Position Allocation")
            pos_chart = self._create_allocation_chart(positions_df)
            if pos_chart:
                st.plotly_chart(pos_chart, use_container_width=True)
            
            st.subheader("Open Positions - Detailed")
            if not positions_df.empty:
                # Add style filter
                if 'trade_style' in positions_df.columns:
                    styles = ['All'] + positions_df['trade_style'].unique().tolist()
                    selected_style = st.selectbox("Filter by Style", styles)
                    if selected_style != 'All':
                        display_df = positions_df[positions_df['trade_style'] == selected_style].copy()
                    else:
                        display_df = positions_df.copy()
                else:
                    display_df = positions_df.copy()
                
                # Format for display
                for col in ['entry_price', 'current_price', 'unrealized_pnl', 'stop_loss', 'take_profit']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else x)
                if 'volume' in display_df.columns:
                    display_df['volume'] = display_df['volume'].apply(lambda x: f"{x:.2f}")
                if 'hold_time' in display_df.columns:
                    display_df['hold_time'] = display_df['hold_time'].apply(lambda x: str(timedelta(seconds=int(x))) if isinstance(x, (int, float)) else x)
                if 'current_rr' in display_df.columns:
                    display_df['current_rr'] = display_df['current_rr'].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
                
                # Color code PnL and RR
                def color_pnl(val):
                    if isinstance(val, str):
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            return ''
                    color = 'green' if val >= 0 else 'red'
                    return f'color: {color}'
                
                def color_rr(val):
                    if isinstance(val, str):
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            return ''
                    color = 'green' if val >= 2 else 'orange' if val >= 1 else 'red'
                    return f'color: {color}'
                
                style_cols = ['unrealized_pnl']
                if 'current_rr' in display_df.columns:
                    style_cols.append('current_rr')
                
                st.dataframe(
                    display_df.style.applymap(color_pnl, subset=['unrealized_pnl']).applymap(
                        color_rr, subset=['current_rr'] if 'current_rr' in display_df.columns else []
                    ),
                    use_container_width=True
                )
                
                # Position summary by style
                if 'trade_style' in positions_df.columns:
                    st.subheader("Positions by Trading Style")
                    style_summary = positions_df.groupby('trade_style').agg(
                        Count=('symbol', 'count'),
                        Total_Volume=('volume', 'sum'),
                        Total_PnL=('unrealized_pnl', 'sum'),
                        Avg_RR=('current_rr', 'mean') if 'current_rr' in positions_df.columns else ('unrealized_pnl', 'mean')
                    ).reset_index()
                    st.dataframe(style_summary, use_container_width=True)
            else:
                st.info("No open positions")
        
        with tab3:
            st.subheader("Risk Metrics")
            risk_table = self._create_risk_metrics_table(risk_metrics)
            if risk_table:
                st.plotly_chart(risk_table, use_container_width=True)
            else:
                st.info("No risk metrics available")
            
            st.subheader("Strategy Performance")
            strat_chart = self._create_strategy_performance_chart(strategies_status)
            if strat_chart:
                st.plotly_chart(strat_chart, use_container_width=True)
            else:
                st.info("No strategy performance data")
            
            # Risk limits status
            st.subheader("Risk Limits Status")
            if risk_metrics:
                limits = {
                    "Daily Loss": (risk_metrics.get('daily_loss_pct', 0), 0.05, "Daily"),
                    "Weekly Loss": (risk_metrics.get('weekly_loss_pct', 0), 0.10, "Weekly"),
                    "Monthly Loss": (risk_metrics.get('monthly_loss_pct', 0), 0.20, "Monthly"),
                    "Max Drawdown": (risk_metrics.get('max_drawdown', 0), 0.10, "Portfolio"),
                    "Portfolio VaR": (risk_metrics.get('var_95', 0), 0.02, "Daily"),
                    "Max Leverage": (risk_metrics.get('leverage', 0), 10.0, "Account"),
                }
                
                limit_data = []
                for name, (current, limit, scope) in limits.items():
                    pct = current / limit if limit > 0 else 0
                    status = "🟢" if pct < 0.7 else "🟡" if pct < 1.0 else "🔴"
                    limit_data.append({
                        "Limit_Name": name,
                        "Current": f"{current:.4f}",
                        "Limit_Value": f"{limit:.4f}",
                        "Usage": f"{pct:.1%}",
                        "Status": status,
                        "Scope": scope
                    })
                
                st.dataframe(pd.DataFrame(limit_data), use_container_width=True)
        
        with tab4:
            st.subheader("Recent Signals")
            signals_table = self._create_signals_table(signals_df)
            if signals_table:
                st.plotly_chart(signals_table, use_container_width=True)
            
            if not signals_df.empty:
                st.subheader("Signal Details")
                display_signals = signals_df.copy()
                if 'timestamp' in display_signals.columns:
                    display_signals['timestamp'] = pd.to_datetime(display_signals['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                for col in ['entry_price', 'stop_loss', 'take_profit', 'confidence', 'risk_reward', 'position_size_pct']:
                    if col in display_signals.columns:
                        display_signals[col] = display_signals[col].apply(lambda x: f"{x:.5f}" if col in ['entry_price', 'stop_loss', 'take_profit'] else f"{x:.2%}" if col in ['confidence', 'position_size_pct'] else f"{x:.2f}" if isinstance(x, (int, float)) else x)
                
                # Color code by direction
                def color_direction(val):
                    if val == 'LONG' or val == 'BUY':
                        return 'background-color: #003300; color: #00ff00'
                    elif val == 'SHORT' or val == 'SELL':
                        return 'background-color: #330000; color: #ff4444'
                    return ''
                
                style_cols = []
                for col in ['direction', 'type']:
                    if col in display_signals.columns:
                        style_cols.append(col)
                
                st.dataframe(
                    display_signals.style.applymap(color_direction, subset=style_cols),
                    use_container_width=True
                )
                
                # Signal summary by style
                if 'trade_style' in signals_df.columns:
                    st.subheader("Signals by Trading Style")
                    style_counts = signals_df['trade_style'].value_counts().reset_index()
                    style_counts.columns = ['Style', 'Count']
                    st.bar_chart(style_counts.set_index('Style'))
            else:
                st.info("No recent signals")
        
        with tab5:
            st.subheader("Recent Trades")
            if not trades_df.empty:
                display_trades = trades_df.copy()
                if 'timestamp' in display_trades.columns:
                    display_trades['timestamp'] = pd.to_datetime(display_trades['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                for col in ['price', 'pnl', 'volume']:
                    if col in display_trades.columns:
                        display_trades[col] = display_trades[col].apply(lambda x: f"{x:.5f}" if col == 'price' else f"{x:.2f}" if isinstance(x, (int, float)) else x)
                if 'hold_time' in display_trades.columns:
                    display_trades['hold_time'] = display_trades['hold_time'].apply(lambda x: str(timedelta(seconds=int(x))) if isinstance(x, (int, float)) else x)
                
                def color_pnl(val):
                    if isinstance(val, str):
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            return ''
                    color = 'green' if val >= 0 else 'red'
                    return f'color: {color}'
                
                def color_side(val):
                    if val == 'BUY' or val == 'LONG':
                        return 'background-color: #003300; color: #00ff00'
                    elif val == 'SELL' or val == 'SHORT':
                        return 'background-color: #330000; color: #ff4444'
                    return ''
                
                st.dataframe(
                    display_trades.style.applymap(color_pnl, subset=['pnl']).applymap(
                        color_side, subset=['side'] if 'side' in display_trades.columns else []
                    ),
                    use_container_width=True
                )
                
                # Trade statistics
                st.subheader("Trade Statistics")
                trade_pnl = pd.to_numeric(trades_df['pnl'], errors='coerce')
                trades_df['side'] if 'side' in trades_df.columns else pd.Series()
                trade_style = trades_df['trade_style'] if 'trade_style' in trades_df.columns else pd.Series()
                
                stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                stat_col1.metric("Total Trades", len(trades_df))
                stat_col2.metric("Win Rate", f"{(trade_pnl > 0).mean():.1%}")
                stat_col3.metric("Avg P&L", f"${trade_pnl.mean():.2f}")
                stat_col4.metric("Profit Factor", f"{trade_pnl[trade_pnl > 0].sum() / abs(trade_pnl[trade_pnl < 0].sum()):.2f}" if (trade_pnl < 0).any() else "∞")
                
                # By style
                if not trade_style.empty:
                    st.subheader("Trades by Style")
                    style_stats = trades_df.groupby('trade_style').agg(
                        Count=('pnl', 'count'),
                        Wins=('pnl', lambda x: (x > 0).sum()),
                        Total_PnL=('pnl', 'sum'),
                        Avg_PnL=('pnl', 'mean'),
                        Avg_Hold=('hold_time', 'mean') if 'hold_time' in trades_df.columns else ('pnl', 'mean')
                    ).reset_index()
                    style_stats['Win_Rate'] = style_stats['Wins'] / style_stats['Count']
                    st.dataframe(style_stats, use_container_width=True)
            else:
                st.info("No recent trades")
        
        with tab6:
            st.subheader("Brain Status")
            if brain_status:
                col1, col2 = st.columns(2)
                with col1:
                    st.json({
                        "state": brain_status.get('state'),
                        "running": brain_status.get('running'),
                        "session_duration": brain_status.get('session_duration'),
                        "strategies_active": brain_status.get('strategies_active'),
                        "decisions_made": brain_status.get('decisions_made'),
                        "trades_executed": brain_status.get('trades_executed'),
                    })
                with col2:
                    st.json({
                        "total_pnl": brain_status.get('total_pnl'),
                        "daily_pnl": brain_status.get('daily_pnl'),
                        "max_drawdown": brain_status.get('max_drawdown'),
                        "current_regime": brain_status.get('current_regime'),
                        "open_positions": brain_status.get('open_positions'),
                    })
            else:
                st.info("Brain status not available")
            
            st.subheader("Active Strategies")
            if strategies_status:
                for sid, info in strategies_status.items():
                    with st.expander(f"{info.get('name', sid)} ({sid}) - {info.get('trade_style', 'Unknown')}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.json({
                                "strategy_id": sid,
                                "name": info.get('name'),
                                "trade_style": info.get('trade_style'),
                                "state": info.get('state'),
                                "symbols": info.get('symbols', []),
                                "timeframes": info.get('timeframes', []),
                            })
                        with col2:
                            st.json({
                                "total_return": info.get('total_return'),
                                "sharpe_ratio": info.get('sharpe_ratio'),
                                "win_rate": info.get('win_rate'),
                                "max_drawdown": info.get('max_drawdown'),
                                "total_trades": info.get('total_trades'),
                                "risk_per_trade": info.get('risk_per_trade'),
                            })
            else:
                st.info("No strategy status available")
            
            st.subheader("Market Regime")
            if market_regime:
                st.json(market_regime)
            else:
                st.info("Market regime not available")
        
        with tab7:
            st.subheader("Performance Attribution")
            attr_chart = self._create_performance_attribution_chart(performance_attribution)
            if attr_chart:
                st.plotly_chart(attr_chart, use_container_width=True)
            else:
                st.info("Performance attribution not available")
            
            st.subheader("Detailed Attribution")
            if performance_attribution:
                st.json(performance_attribution)
            
            # Equity curve with trade markers
            st.subheader("Equity Curve with Trade Markers")
            if not equity_df.empty and not trades_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=equity_df['timestamp'], y=equity_df['equity'],
                    mode='lines', name='Equity', line={"color": '#00ff00', "width": 2}
                ))
                
                # Add trade markers
                trades_df_copy = trades_df.copy()
                if 'timestamp' in trades_df_copy.columns:
                    trades_df_copy['timestamp'] = pd.to_datetime(trades_df_copy['timestamp'])
                    for _, trade in trades_df_copy.iterrows():
                        color = 'green' if trade.get('pnl', 0) > 0 else 'red'
                        symbol = 'triangle-up' if trade.get('side') == 'BUY' else 'triangle-down'
                        fig.add_trace(go.Scatter(
                            x=[trade['timestamp']], y=[trade.get('price', 0)],
                            mode='markers', name=f"Trade {trade.get('side')}",
                            marker={"color": color, "size": 10, "symbol": symbol},
                            showlegend=False
                        ))
                
                fig.update_layout(template='plotly_dark', height=500)
                st.plotly_chart(fig, use_container_width=True)
        
        with tab8:
            st.subheader("🌍 Active Trading Sessions & Timeline")
            
            # Import session manager for timeline
            from src.strategy.session_manager import session_manager
            
            # Session Timeline Visualization
            st.markdown("### 📅 Session Timeline (Next 24 Hours)")
            timeline = session_manager.get_session_timeline(24)
            if timeline:
                timeline_data = []
                for t in timeline:
                    status = "🟢 ACTIVE" if t['is_active'] else "⏳ UPCOMING"
                    countdown = t.get('time_until_start') or t.get('time_until_end') or "N/A"
                    timeline_data.append({
                        "Session": t['name'],
                        "Type": t['type'].upper(),
                        "Status": status,
                        "Start (UTC)": t['start_utc'],
                        "End (UTC)": t['end_utc'],
                        "Countdown": countdown,
                        "Major Pairs": ", ".join(t['major_pairs'][:5]),
                        "Liquidity": t['liquidity_level'],
                        "Volatility": t['volatility_level'],
                    })
                st.dataframe(pd.DataFrame(timeline_data), use_container_width=True)
                
                # Visual timeline chart
                st.markdown("#### Session Timeline Visualization")
                fig = go.Figure()
                current_utc = datetime.now(UTC)
                for t in timeline:
                    start_time = current_utc.replace(hour=int(t['start_utc'].split(':')[0]), minute=int(t['start_utc'].split(':')[1]), second=0, microsecond=0)
                    end_time = current_utc.replace(hour=int(t['end_utc'].split(':')[0]), minute=int(t['end_utc'].split(':')[1]), second=0)
                    if end_time <= start_time:
                        end_time += timedelta(days=1)
                    
                    color = {
                        'forex': '#00ffff',
                        'crypto': '#ff8800', 
                        'overlap': '#00ff00'
                    }.get(t['type'], '#888888')
                    
                    if t['is_active']:
                        # Show active portion
                        fig.add_trace(go.Scatter(
                            x=[start_time, end_time],
                            y=[t['name'], t['name']],
                            mode='lines',
                            line={"color": color, "width": 12},
                            name=t['name'],
                            showlegend=False,
                            hoverinfo='text',
                            hovertext=f"{t['name']} - ACTIVE"
                        ))
                    elif t.get('time_until_start') and isinstance(t.get('time_until_start'), timedelta) and t.get('time_until_start') <= timedelta(hours=24):
                                            fig.add_trace(go.Scatter(
                                                x=[start_time, end_time],
                                                y=[t['name'], t['name']],
                                                mode='lines',
                                                line={"color": color, "width": 8, "dash": 'dash'},
                                                name=t['name'],
                                                showlegend=False,
                                                hoverinfo='text',
                                                hovertext=f"{t['name']} - STARTS IN {t.get('time_until_start')!s}"
                                            ))
                
                fig.update_layout(
                    template='plotly_dark',
                    height=400,
                    xaxis_title="Time (UTC)",
                    yaxis_title="Session",
                    margin={"l": 20, "r": 20, "t": 30, "b": 20},
                    shapes=[
                        {
                            "type": "line",
                            "x0": current_utc, "x1": current_utc,
                            "y0": -0.5, "y1": len(timeline)-0.5,
                            "line": {"color": "red", "width": 2, "dash": "dot"}
                        }
                    ])
                fig.add_annotation(
                    x=current_utc, y=len(timeline)-0.5,
                    text="NOW", showarrow=True, arrowhead=2,
                    arrowcolor="red", font={"color": "red", "size": 12}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Session Countdown
            st.markdown("### ⏱️ Next Session Change")
            session_info = session_manager.update()
            next_change = session_info.get('next_change')
            if next_change:
                tc = next_change['time_until']
                hours, remainder = divmod(tc.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                action = next_change['action']
                session_name = next_change['session'].value
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Next Session", session_name)
                col2.metric("Action", f"{'Starts' if action == 'starts' else 'Ends'}")
                col3.metric("Countdown", f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                col4.metric("Mode", session_info.get('primary_mode', 'unknown').upper())
                
                # Progress bar
                if action == 'starts':
                    total_seconds = 24 * 3600  # approximate
                    progress = 1 - (tc.total_seconds() / total_seconds)
                else:
                    total_seconds = 8 * 3600  # typical session
                    progress = 1 - (tc.total_seconds() / total_seconds)
                st.progress(min(max(progress, 0), 1), text=f"Time until {session_name} {action.lower()}...")
            else:
                st.info("No upcoming session changes in next 24 hours")

            st.divider()

            # Forex Sessions
            st.markdown("### Forex Sessions")
            if active_sessions.get('forex'):
                forex_data = []
                for session, info in active_sessions['forex'].items():
                    forex_data.append({
                        "Session": session,
                        "Active": "🟢 Yes" if info.get('active') else "🔴 No",
                        "Time Range (UTC)": info.get('time_range', 'N/A'),
                        "Major Pairs": ", ".join(info.get('major_pairs', [])),
                        "Volatility": info.get('volatility', 'N/A'),
                        "Liquidity": info.get('liquidity', 'N/A'),
                    })
                st.dataframe(pd.DataFrame(forex_data), use_container_width=True)
            else:
                st.info("No forex session data")

            # Crypto Sessions
            st.markdown("### Crypto Sessions (24/7)")
            if crypto_sessions.get('crypto'):
                crypto_data = []
                for session, info in crypto_sessions['crypto'].items():
                    crypto_data.append({
                        "Session": session,
                        "Active": "🟢 Yes" if info.get('active') else "🔴 No",
                        "Time Range": "24/7",
                        "Major Pairs": ", ".join(info.get('major_pairs', [])),
                        "Volume (24h)": info.get('volume_24h', 'N/A'),
                    })
                st.dataframe(pd.DataFrame(crypto_data), use_container_width=True)
            else:
                st.info("No crypto session data")

            # Session Auto-Switch Logic
            st.markdown("### Auto-Session Switch")
            forex_active = any(s.get('active', False) for s in active_sessions.get('forex', {}).values())
            crypto_active = any(s.get('active', False) for s in crypto_sessions.get('crypto', {}).values())
            
            if forex_active:
                st.success("🟢 Forex session active - Trading forex pairs")
            elif crypto_active:
                st.warning("🟡 No forex session active - Switched to crypto trading")
            else:
                st.error("🔴 No active sessions - System in standby")
        with tab9:
            st.subheader("⚙️ System & Background Processes")
            
            # Background Processes
            if background_processes:
                st.markdown("### Running Processes")
                proc_data = []
                for proc, info in background_processes.items():
                    proc_data.append({
                        "Process": proc,
                        "Status": "🟢 Running" if info.get('running') else "🔴 Stopped",
                        "PID": info.get('pid', 'N/A'),
                        "CPU %": f"{info.get('cpu_percent', 0):.1f}",
                        "Memory (MB)": f"{info.get('memory_mb', 0):.0f}",
                        "Uptime": str(timedelta(seconds=info.get('uptime', 0))) if info.get('uptime') else 'N/A',
                        "Restarts": info.get('restart_count', 0),
                    })
                st.dataframe(pd.DataFrame(proc_data), use_container_width=True)
            else:
                st.info("No process data available")
            
            # System Resources
            st.markdown("### System Resources")
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric("CPU Usage", f"{cpu_percent:.1f}%")
            res_col2.metric("Memory Usage", f"{memory.percent:.1f}%", f"{memory.used / 1e9:.1f}GB / {memory.total / 1e9:.1f}GB")
            res_col3.metric("Disk Usage", f"{disk.percent:.1f}%", f"{disk.used / 1e9:.1f}GB / {disk.total / 1e9:.1f}GB")
            
            # Network Connections
            st.markdown("### Network Connections")
            connections = psutil.net_connections(kind='inet')
            est_connections = [c for c in connections if c.status == 'ESTABLISHED']
            st.write(f"Established connections: {len(est_connections)}")
            
            # Logs
            st.markdown("### Recent Logs")
            log_lines = st.session_state.get('log_lines', [])
            if log_lines:
                for line in log_lines[-50:]:
                    st.text(line)
            else:
                st.info("No log data in session state")
            
            # Configuration
            st.markdown("### Current Configuration")
            st.json({
                "simulation_mode": False,
                "demo_account": True,
                "api_url": self.api_url,
                "ea_bridge_url": self.ea_bridge_url,
                "risk_limits": {
                    "daily_loss": settings.risk_daily_loss_limit,
                    "max_drawdown": settings.risk_max_drawdown,
                    "max_position_size": settings.risk_max_position_size_pct,
                    "max_leverage": settings.risk_max_leverage,
                }
            })




        with tab10:
            st.subheader("🛡️ Blind Spot Monitoring")
            
            # Alert Summary
            if blind_spot_summary:
                st.subheader("Alert Summary")
                alert_col1, alert_col2, alert_col3, alert_col4 = st.columns(4)
                alert_col1.metric("Active Alerts", blind_spot_summary.get('active', 0))
                
                by_severity = blind_spot_summary.get('by_severity', {})
                alert_col2.metric("Critical", by_severity.get('critical', 0))
                alert_col3.metric("Warning", by_severity.get('warning', 0))
                alert_col4.metric("Info", by_severity.get('info', 0))
            
            st.divider()
            
            # Active Alerts
            st.subheader("Active Alerts")
            if blind_spot_alerts:
                for alert_id, alert in blind_spot_alerts.items():
                    severity = alert.get('severity', 'info')
                    severity_color = {
                        'critical': '🔴',
                        'warning': '🟡', 
                        'info': '🔵'
                    }.get(severity, '⚪')
                    
                    with st.expander(f"{severity_color} {alert.get('title', 'Unknown')} [{severity.upper()}]"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Type:** {alert.get('blind_spot_type', 'N/A')}")
                            st.write(f"**Severity:** {severity.upper()}")
                            st.write(f"**Symbols:** {', '.join(alert.get('affected_symbols', [])) or 'N/A'}")
                            st.write(f"**Strategies:** {', '.join(alert.get('affected_strategies', [])) or 'N/A'}")
                        with col2:
                            st.write(f"**Description:** {alert.get('description', 'N/A')}")
                            st.write(f"**Time:** {alert.get('timestamp', 'N/A')}")
                            if alert.get('metrics'):
                                st.json(alert.get('metrics', {}))
                        
                        st.write("**Recommended Actions:**")
                        for action in alert.get('recommended_actions', []):
                            st.write(f"- {action}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("Acknowledge", key=f"ack_{alert_id}"):
                                requests.post(f"{self.api_url}/api/v1/blind-spots/alerts/{alert_id}/acknowledge")
                                st.rerun()
                        with col_b:
                            if st.button("Resolve", key=f"res_{alert_id}"):
                                requests.post(f"{self.api_url}/api/v1/blind-spots/alerts/{alert_id}/resolve")
                                st.rerun()
            else:
                st.success("🟢 No active blind spot alerts")
            
            st.divider()
            
            # Correlation Clusters
            st.subheader("Correlation Clusters")
            if correlation_clusters:
                for cluster in correlation_clusters:
                    with st.expander(f"Cluster {cluster.get('cluster_id', '?')}: {cluster.get('cluster_size', 0)} symbols (avg corr: {cluster.get('avg_correlation', 0):.2f})"):
                        st.write(f"**Symbols:** {', '.join(cluster.get('symbols', []))}")
                        st.write(f"**Avg Correlation:** {cluster.get('avg_correlation', 0):.2f}")
                        st.write(f"**Max Correlation:** {cluster.get('max_correlation', 0):.2f}")
                        st.write(f"**Risk Score:** {cluster.get('risk_score', 0):.2f}")
                        if cluster.get('risk_score', 0) > 0.7:
                            st.warning("⚠️ High correlation concentration risk")
            else:
                st.info("No correlation cluster data")
            
            st.divider()
            
            # Regime Transitions
            st.subheader("Regime Transition Signals")
            if regime_transitions:
                for signal in regime_transitions:
                    st.warning(f"🔄 Regime Transition: {signal.get('from_regime', '?')} -> {signal.get('to_regime', '?')} (confidence: {signal.get('confidence', 0):.1%})")
                    st.write(f"**Time to transition:** ~{signal.get('time_to_transition', '?')} bars")
                    st.write(f"**Affected strategies:** {', '.join(signal.get('affected_strategies', []))}")
                    st.json(signal.get('indicators', {}))
            else:
                st.info("No regime transition signals")
            
            st.divider()
            
            # Liquidity Metrics
            st.subheader("Liquidity Risk")
            if liquidity_metrics:
                liq_data = []
                for symbol, metrics in liquidity_metrics.items():
                    liq_data.append({
                        "Symbol": symbol,
                        "Liquidity Score": f"{metrics.get('liquidity_score', 0):.2f}",
                        "Spread (pips)": metrics.get('bid_ask_spread', 'N/A'),
                        "Spread %ile": f"{metrics.get('spread_percentile', 0):.0f}%",
                        "Volume Ratio": f"{metrics.get('volume_ratio', 0):.2f}",
                        "Slippage Est.": f"{metrics.get('slippage_estimate', 0):.2f} pips",
                    })
                st.dataframe(pd.DataFrame(liq_data), use_container_width=True)
            else:
                st.info("No liquidity data")
            
            st.divider()
            
            # Tail Risk
            st.subheader("Tail Risk (CVaR)")
            if tail_risk:
                col1, col2, col3 = st.columns(3)
                col1.metric("CVaR 95%", f"{tail_risk.get('cvar_95', 0):.2%}")
                col2.metric("CVaR 99%", f"{tail_risk.get('cvar_99', 0):.2%}")
                col3.metric("Threshold", f"{tail_risk.get('threshold', 0):.2%}")
                
                if tail_risk.get('cvar_95', 0) > tail_risk.get('threshold', 0):
                    st.error("🔴 Tail risk exceeds threshold!")
            else:
                st.info("No tail risk data")

        with tab11:
            st.subheader("📊 Factor Analysis")
            
            if factor_analysis:
                # Factor exposures
                st.subheader("Factor Exposures")
                if factor_analysis.get('factor_exposures'):
                    factor_data = []
                    for factor, exposure in factor_analysis['factor_exposures'].items():
                        factor_data.append({
                            "Factor": factor.replace('_', ' ').title(),
                            "Exposure": f"{exposure:.2%}",
                            "Risk Contribution": f"{factor_analysis.get('factor_risk_contrib', {}).get(factor, 0):.2%}"
                        })
                    st.dataframe(pd.DataFrame(factor_data), use_container_width=True)
                
                # Factor returns
                st.subheader("Factor Returns (Annualized)")
                if factor_analysis.get('factor_returns'):
                    returns_data = []
                    for factor, ret in factor_analysis['factor_returns'].items():
                        returns_data.append({
                            "Factor": factor.replace('_', ' ').title(),
                            "Return": f"{ret:.2%}",
                            "Volatility": f"{factor_analysis.get('factor_vol', {}).get(factor, 0):.2%}",
                            "Sharpe": f"{factor_analysis.get('factor_sharpe', {}).get(factor, 0):.2f}"
                        })
                    st.dataframe(pd.DataFrame(returns_data), use_container_width=True)
                
                # Strategy factor loadings
                st.subheader("Strategy Factor Loadings")
                if factor_analysis.get('strategy_loadings'):
                    for strat, loadings in factor_analysis['strategy_loadings'].items():
                        with st.expander(f"{strat} Factor Loadings"):
                            loading_data = []
                            for factor, loading in loadings.items():
                                loading_data.append({
                                    "Factor": factor.replace('_', ' ').title(),
                                    "Loading": f"{loading:.3f}"
                                })
                            st.dataframe(pd.DataFrame(loading_data), use_container_width=True)
                
                # Residual risk
                st.subheader("Residual Risk")
                if factor_analysis.get('residual_risk'):
                    rr = factor_analysis['residual_risk']
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Residual Volatility", f"{rr.get('volatility', 0):.2%}")
                    col2.metric("R-Squared", f"{rr.get('r_squared', 0):.2%}")
                    col3.metric("Alpha", f"{rr.get('alpha', 0):.2%}")
            else:
                st.info("No factor analysis data available")

        with tab12:
            st.subheader("🔬 Model Health & ML Monitoring")
            
            if model_health:
                st.subheader("Registered Models")
                for model_id, health in model_health.items():
                    with st.expander(f"Model: {model_id} (Strategy: {health.get('strategy_id', 'N/A')})"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Status", health.get('status', 'unknown'))
                            st.metric("Baseline Sharpe", f"{health.get('baseline_sharpe', 0):.2f}")
                            st.metric("Current Sharpe", f"{health.get('current_sharpe', 0):.2f}")
                            st.metric("Degradation", f"{health.get('degradation_pct', 0):.1%}")
                        with col2:
                            st.metric("Baseline Accuracy", f"{health.get('baseline_accuracy', 0):.1%}")
                            st.metric("Current Accuracy", f"{health.get('current_accuracy', 0):.1%}")
                            st.metric("Retrain Count", health.get('retrain_count', 0))
                        
                        # Prediction quality
                        if health.get('recent_predictions'):
                            st.subheader("Recent Predictions vs Actuals")
                            pred_data = pd.DataFrame(health['recent_predictions'][-50:])
                            if not pred_data.empty:
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=list(range(len(pred_data))),
                                    y=pred_data['prediction'],
                                    mode='lines', name='Prediction', line={'color': '#00ffff'}
                                ))
                                fig.add_trace(go.Scatter(
                                    x=list(range(len(pred_data))),
                                    y=pred_data['actual'],
                                    mode='lines', name='Actual', line={'color': '#00ff00'}
                                ))
                                fig.update_layout(template='plotly_dark', height=300)
                                st.plotly_chart(fig, use_container_width=True)
                        
                        # Retrain button
                        if st.button(f"Trigger Retrain: {model_id}", key=f"retrain_{model_id}"):
                            requests.post(f"{self.api_url}/api/v1/ml/models/{model_id}/retrain")
                            st.success(f"Retrain triggered for {model_id}")
            else:
                st.info("No model health data available")
            
            st.divider()
            
            # Behavioral Bias
            st.subheader("Behavioral Bias Metrics")
            if behavioral_bias:
                col1, col2, col3 = st.columns(3)
                col1.metric("Disposition Effect Ratio", f"{behavioral_bias.get('disposition_ratio', 0):.2f}")
                col2.metric("Overtrading Score", f"{behavioral_bias.get('overtrading_score', 0):.2f}")
                col3.metric("Revenge Trading Score", f"{behavioral_bias.get('revenge_trading_score', 0):.2f}")
                
                if behavioral_bias.get('disposition_ratio', 1) > 1.5:
                    st.warning("⚠️ Disposition effect detected: holding losers longer than winners")
                if behavioral_bias.get('overtrading_score', 0) > 0.7:
                    st.warning("⚠️ Potential overtrading detected")
            else:
                st.info("No behavioral bias data")
            
            st.divider()
            
            # Concentration Risk
            st.subheader("Concentration Risk")
            if concentration_risk:
                conc_data = []
                for item, metrics in concentration_risk.items():
                    conc_data.append({
                        "Item": item,
                        "Concentration": f"{metrics.get('concentration', 0):.1%}",
                        "Limit": f"{metrics.get('limit', 0):.1%}",
                        "Status": "🔴" if metrics.get('concentration', 0) > metrics.get('limit', 0) else "🟢"
                    })
                st.dataframe(pd.DataFrame(conc_data), use_container_width=True)
            else:
                st.info("No concentration risk data")


def main():
    """Entry point for Streamlit."""
    app = DashboardApp()
    app.run()


if __name__ == "__main__":
    main()
