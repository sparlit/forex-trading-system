"""Elite Autonomous Quantum Trading System - dashboard tab renderers.

Each module exposes a single ``render_xxx_tab()`` function that draws one
tab of the main Streamlit dashboard. Every tab is self-contained and
gracefully degrades when optional dependencies are unavailable.

Tabs:
    settings         → render_settings_tab()
    credentials      → render_credentials_tab()
    data_ingestion   → render_data_ingestion_tab()
    feature_store    → render_feature_store_tab()
    strategy_engine  → render_strategy_engine_tab()
    risk_manager     → render_risk_manager_tab()
    order_manager    → render_order_manager_tab()
    execution_logger → render_execution_logger_tab()
    monitoring       → render_monitoring_tab()
    security         → render_security_tab()
    overnight        → render_overnight_tab()
    portfolio        → render_portfolio_tab()
    watchlist        → render_watchlist_tab()
    market           → render_market_tab()
    broker_config    → render_broker_config_tab()
    ai_config        → render_ai_config_tab()
    external_data    → render_external_data_tab()
    trade_book       → render_trade_book_tab()
    sentiment        → render_sentiment_tab()
    stock_predictor  → render_stock_predictor_tab()
    agentic_ai       → render_agentic_ai_tab()
    help             → render_help_tab()
"""

from src.dashboard.tabs.agentic_ai import render_agentic_ai_tab
from src.dashboard.tabs.ai_config import render_ai_config_tab
from src.dashboard.tabs.anr_recommend import render_anr_recommend_tab
from src.dashboard.tabs.broker_config import render_broker_config_tab
from src.dashboard.tabs.credentials import render_credentials_tab
from src.dashboard.tabs.data_ingestion import render_data_ingestion_tab
from src.dashboard.tabs.des_security import render_des_security_tab
from src.dashboard.tabs.econ_calendar import render_econ_calendar_tab
from src.dashboard.tabs.emsx_routing import render_emsx_routing_tab
from src.dashboard.tabs.execution_logger import render_execution_logger_tab
from src.dashboard.tabs.external_data import render_external_data_tab
from src.dashboard.tabs.feat_store import render_feat_store_tab
from src.dashboard.tabs.feature_store import render_feature_store_tab
from src.dashboard.tabs.help import render_help_tab
from src.dashboard.tabs.ing_telemetry import render_ing_telemetry_tab
from src.dashboard.tabs.log_exec import render_log_exec_tab

# New tabs
from src.dashboard.tabs.main_scan import render_main_scan_tab
from src.dashboard.tabs.market import render_market_tab
from src.dashboard.tabs.mon_health import render_mon_health_tab
from src.dashboard.tabs.monitoring import render_monitoring_tab
from src.dashboard.tabs.news_feed import render_news_feed_tab
from src.dashboard.tabs.ord_book import render_ord_book_tab
from src.dashboard.tabs.order_manager import render_order_manager_tab
from src.dashboard.tabs.overnight import render_overnight_tab
from src.dashboard.tabs.pf_portfolio import render_pf_portfolio_tab
from src.dashboard.tabs.portfolio import render_portfolio_tab
from src.dashboard.tabs.price_chart import render_price_chart_tab
from src.dashboard.tabs.risk_circuit import render_risk_circuit_tab
from src.dashboard.tabs.risk_manager import render_risk_manager_tab
from src.dashboard.tabs.sec_auth import render_sec_auth_tab
from src.dashboard.tabs.security import render_security_tab
from src.dashboard.tabs.sentiment import render_sentiment_tab
from src.dashboard.tabs.session_timeline import render_session_timeline_tab
from src.dashboard.tabs.settings import render_settings_tab
from src.dashboard.tabs.stock_predictor import render_stock_predictor_tab
from src.dashboard.tabs.strat_voting import render_strat_voting_tab
from src.dashboard.tabs.strategy_engine import render_strategy_engine_tab
from src.dashboard.tabs.trade_book import render_trade_book_tab
from src.dashboard.tabs.watchlist import render_watchlist_tab
from src.dashboard.tabs.world_indices import render_world_indices_tab
from src.dashboard.tabs.yield_analytics import render_yield_analytics_tab

__all__ = [
    "render_agentic_ai_tab",
    "render_ai_config_tab",
    "render_broker_config_tab",
    "render_credentials_tab",
    "render_data_ingestion_tab",
    "render_execution_logger_tab",
    "render_external_data_tab",
    "render_feature_store_tab",
    "render_help_tab",
    "render_market_tab",
    "render_monitoring_tab",
    "render_order_manager_tab",
    "render_overnight_tab",
    "render_portfolio_tab",
    "render_risk_manager_tab",
    "render_security_tab",
    "render_sentiment_tab",
    "render_settings_tab",
    "render_stock_predictor_tab",
    "render_strategy_engine_tab",
    "render_trade_book_tab",
    "render_watchlist_tab",
    # New modules
    "render_main_scan_tab",
    "render_price_chart_tab",
    "render_world_indices_tab",
    "render_news_feed_tab",
    "render_anr_recommend_tab",
    "render_session_timeline_tab",
    "render_yield_analytics_tab",
    "render_econ_calendar_tab",
    "render_emsx_routing_tab",
    "render_des_security_tab",
    "render_ing_telemetry_tab",
    "render_feat_store_tab",
    "render_strat_voting_tab",
    "render_risk_circuit_tab",
    "render_ord_book_tab",
    "render_log_exec_tab",
    "render_mon_health_tab",
    "render_sec_auth_tab",
    "render_pf_portfolio_tab",
]
