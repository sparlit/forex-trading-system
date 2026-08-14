
import numpy as np
import pandas as pd
import streamlit as st


def _synthetic_currencies(n=12):
    pairs = [f"{a}/{b}" for a in ['EUR','GBP','USD','AUD','CAD','CHF'] for b in ['USD','JPY','CHF','EUR']]
    chosen = np.random.choice(pairs, n, replace=False)
    data = {
        "currency_pair": chosen,
        "bid": np.round(np.random.uniform(0.8, 1.5, n), 5),
        "ask": np.round(np.random.uniform(0.8, 1.5, n), 5),
        "change_pct": np.round(np.random.uniform(-2, 2, n), 2),
        "52w_high": np.round(np.random.uniform(1.0, 1.8, n), 5),
        "52w_low": np.round(np.random.uniform(0.6, 1.0, n), 5),
        "trend": np.random.choice(['up','down','flat'], n),
    }
    return pd.DataFrame(data)

def _synthetic_crypto(n=8):
    symbols = ['BTC','ETH','ADA','SOL','DOT','LUNA','DOGE','XRP']
    chosen = np.random.choice(symbols, n, replace=False)
    data = {
        "symbol": chosen,
        "price": np.round(np.random.uniform(0.5, 50000, n), 2),
        "24h_change": np.round(np.random.uniform(-10, 10, n), 2),
        "market_cap": np.round(np.random.uniform(1e9, 1e12, n), 0).astype(int),
        "volume": np.round(np.random.uniform(1e7, 1e10, n), 0).astype(int),
        "dominance_pct": np.round(np.random.uniform(0.5, 30, n), 2),
    }
    return pd.DataFrame(data)

def _synthetic_equity_indices(n=6):
    indices = ['S&P 500','NASDAQ','DOW JONES','NIKKEI 225','FTSE 100','DAX']
    chosen = np.random.choice(indices, n, replace=False)
    data = {
        "index_name": chosen,
        "value": np.round(np.random.uniform(2000, 20000, n), 2),
        "change": np.round(np.random.uniform(-200, 200, n), 2),
        "change_pct": np.round(np.random.uniform(-2, 2, n), 2),
        "pe_ratio": np.round(np.random.uniform(10, 30, n), 1),
        "region": np.random.choice(['US','EU','JP','UK'], n),
    }
    return pd.DataFrame(data)

def render_world_indices_tab() -> None:
    """World Currency, Crypto & Equity Indices board – gold / amber theme."""
    st.markdown(f"""{header_template.format(colors='#ffbf00, #ff8000', title='World Indices Dashboard')}""", unsafe_allow_html=True)

    st.subheader('🌍 Currency Pairs')
    df_cur = _synthetic_currencies()
    styled_cur = df_cur.style.applymap(lambda v: 'color: #00ff00;' if v > 0 else 'color: #ff0000;' if isinstance(v,float) and v<0 else '', subset=['change_pct'])
    st.dataframe(styled_cur)

    st.subheader('💎 Crypto Board')
    df_crypto = _synthetic_crypto()
    styled_crypto = df_crypto.style.applymap(lambda v: 'color: #00ff00;' if v > 0 else 'color: #ff0000;' if isinstance(v,float) and v<0 else '', subset=['24h_change'])
    st.dataframe(styled_crypto)

    st.subheader('📈 Equity Indices')
    df_eq = _synthetic_equity_indices()
    styled_eq = df_eq.style.applymap(lambda v: 'color: #00ff00;' if v > 0 else 'color: #ff0000;' if isinstance(v,float) and v<0 else '', subset=['change','change_pct'])
    st.dataframe(styled_eq)
