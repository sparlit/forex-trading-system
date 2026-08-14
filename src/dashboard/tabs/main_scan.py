
from datetime import timedelta

import numpy as np
import pandas as pd
import streamlit as st


def _synthetic_account_stats():
    return {
        "Equity": round(np.random.uniform(100000, 200000), 2),
        "Balance": round(np.random.uniform(90000, 190000), 2),
        "Free Margin": round(np.random.uniform(5000, 50000), 2),
        "Margin Level": f"{np.random.uniform(100, 300):.2f}%",
        "Open Positions": np.random.randint(0, 20),
        "Total P/L": round(np.random.uniform(-5000, 5000), 2),
    }

def _synthetic_scan_matrix(n=20):
    symbols = [f"{np.random.choice(['EUR','GBP','USD','JPY','AUD','CAD','CHF'])}{np.random.choice(['USD','JPY','CHF','EUR'])}" for _ in range(n)]
    data = {
        "symbol": symbols,
        "bid": np.round(np.random.uniform(0.8, 1.5, n), 5),
        "ask": np.round(np.random.uniform(0.8, 1.5, n), 5),
        "spread_pips": np.round(np.random.uniform(0.1, 3.0, n), 2),
        "ATR(14)": np.round(np.random.uniform(0.5, 2.0, n), 4),
        "RSI(14)": np.round(np.random.uniform(10, 90, n), 1),
        "signal": np.random.choice(["Buy", "Sell", "Hold"], n),
        "trend_strength": np.round(np.random.uniform(0, 100, n), 1),
        "score_0_100": np.round(np.random.uniform(0, 100, n), 1),
    }
    return pd.DataFrame(data)

def _synthetic_active_trades(m=8):
    data = {
        "ticket": [np.random.randint(10000, 99999) for _ in range(m)],
        "symbol": [f"{np.random.choice(['EUR','GBP','USD','JPY'])}{np.random.choice(['USD','JPY'])}" for _ in range(m)],
        "side": np.random.choice(["Buy", "Sell"], m),
        "volume": np.round(np.random.uniform(0.01, 1.0, m), 2),
        "entry": np.round(np.random.uniform(0.8, 1.5, m), 5),
        "current": np.round(np.random.uniform(0.8, 1.5, m), 5),
        "SL": np.round(np.random.uniform(0.7, 1.4, m), 5),
        "TP": np.round(np.random.uniform(0.9, 1.6, m), 5),
        "floating_pnl": np.round(np.random.uniform(-200, 200, m), 2),
        "duration": [str(timedelta(minutes=np.random.randint(1, 720))) for _ in range(m)],
        "swap": np.round(np.random.uniform(-5, 5, m), 2),
    }
    return pd.DataFrame(data)

def render_main_scan_tab() -> None:
    """Main Scan Dashboard Tab – electric‑blue / cyan theme."""
    st.markdown(f"""{header_template.format(colors='#00bfff, #00e5ff', title='Main Scan & Active Trades')}""", unsafe_allow_html=True)

    # Top metric cards – 2 rows x 5 columns (10 metrics, we’ll show 5 for brevity)
    stats = _synthetic_account_stats()
    cols = st.columns(5)
    for i, (k, v) in enumerate(list(stats.items())[:5]):
        with cols[i]:
            st.metric(label=k, value=v)

    left, right = st.columns([2, 1])
    with left:
        st.subheader('🗂 Multi‑Asset Scan Matrix')
        df = _synthetic_scan_matrix()
        # Apply simple heatmap styling via pandas Styler – blue gradient
        styled = df.style.background_gradient(cmap='Blues')
        st.dataframe(styled)
    with right:
        st.subheader('📈 Active Trades Terminal')
        trades = _synthetic_active_trades()
        def color_pnl(val):
            color = "#00ff00" if val > 0 else "#ff0000"
            return f"color: {color}; font-weight: bold;"
        styled_trades = trades.style.applymap(lambda v: color_pnl(v) if isinstance(v, (int,float)) else "", subset=['floating_pnl'])
        st.dataframe(styled_trades)

    # Bottom action bar
    st.markdown('---')
    col_buy, col_sell, col_close, col_refresh = st.columns(4)
    with col_buy:
        if st.button('🟢 BUY'):
            st.toast('Buy order sent (simulated)')
    with col_sell:
        if st.button('🔴 SELL'):
            st.toast('Sell order sent (simulated)')
    with col_close:
        if st.button('⚪ CLOSE ALL'):
            st.toast('All positions closed (simulated)')
    with col_refresh:
        if st.button('🔄 REFRESH'):
            st.experimental_rerun()
