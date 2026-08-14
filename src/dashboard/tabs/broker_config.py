'''Broker Config tab – connections, symbols, mapping and control panels.'''

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

def _brokers_table() -> pd.DataFrame:
    data = [
        {"broker": "MT5", "status": "connected", "account_id": "123456", "balance": 20000.0, "equity": 21000.0, "leverage": 100},
        {"broker": "IBKR", "status": "disconnected", "account_id": "IB-7890", "balance": 5000.0, "equity": 5000.0, "leverage": 30},
        {"broker": "Binance", "status": "connected", "account_id": "BN-001", "balance": 15000.0, "equity": 15500.0, "leverage": 1},
        {"broker": "Bybit", "status": "connected", "account_id": "BY-002", "balance": 12000.0, "equity": 12500.0, "leverage": 1},
        {"broker": "Kraken", "status": "disconnected", "account_id": "KR-003", "balance": 8000.0, "equity": 8000.0, "leverage": 1},
    ]
    return pd.DataFrame(data)

def _symbols_config() -> pd.DataFrame:
    data = [
        {"broker": "MT5", "symbol": "EURUSD",   "min_lot": 0.01,  "max_lot": 100,   "contract_size": 100000, "margin_requirement": 0.02, "enabled": True},
        {"broker": "MT5", "symbol": "GBPJPY",   "min_lot": 0.01,  "max_lot": 100,   "contract_size": 100000, "margin_requirement": 0.02, "enabled": True},
        {"broker": "IBKR", "symbol": "AAPL",    "min_lot": 1,     "max_lot": 1000,  "contract_size": 1,      "margin_requirement": 0.5,  "enabled": True},
        {"broker": "IBKR", "symbol": "MSFT",    "min_lot": 1,     "max_lot": 1000,  "contract_size": 1,      "margin_requirement": 0.5,  "enabled": True},
        {"broker": "Binance", "symbol": "BTCUSDT", "min_lot": 0.0001, "max_lot": 10, "contract_size": 1, "margin_requirement": 0.0, "enabled": True},
        {"broker": "Binance", "symbol": "ETHUSDT", "min_lot": 0.001,  "max_lot": 100, "contract_size": 1, "margin_requirement": 0.0, "enabled": True},
        {"broker": "Bybit", "symbol": "BTCUSDT",   "min_lot": 0.001,  "max_lot": 5,   "contract_size": 1, "margin_requirement": 0.0, "enabled": True},
        {"broker": "Kraken", "symbol": "XBTUSD",    "min_lot": 0.0001, "max_lot": 5,   "contract_size": 1, "margin_requirement": 0.0, "enabled": False},
    ]
    return pd.DataFrame(data)

def _symbol_mapping() -> pd.DataFrame:
    data = [
        {"mt5_symbol": "EURUSD", "ibkr_symbol": "EUR.USD"},
        {"mt5_symbol": "GBPJPY", "ibkr_symbol": "GBP.JPY"},
    ]
    return pd.DataFrame(data)

def render_broker_config_tab() -> None:
    st.title("\U0001F4E6 Broker Config")
    st.subheader("Broker Connections")
    df = _brokers_table()
    st.dataframe(df, hide_index=True, use_container_width=True)
    for idx, row in df.iterrows():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.write(f"**{row['broker']}** (Account {row['account_id']})")
        with col2:
            if st.button("Connect", key=f"connect_{row['broker']}"):
                st.success(f"{row['broker']} connected (simulated)")
        with col3:
            if st.button("Disconnect", key=f"disconnect_{row['broker']}"):
                st.info(f"{row['broker']} disconnected (simulated)")

    st.subheader("Tradable Symbols Config")
    st.dataframe(_symbols_config(), hide_index=True, use_container_width=True)

    st.subheader("Symbol Mapping Table")
    st.dataframe(_symbol_mapping(), hide_index=True, use_container_width=True)
