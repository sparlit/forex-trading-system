
import numpy as np
import pandas as pd
import streamlit as st

from src.dashboard.tab_themes import inject_tab_theme


def _synthetic_venues(n=8):
    venues = [f"Venue{idx}" for idx in range(1,n+1)]
    df = pd.DataFrame({
        'venue_name': venues,
        'venue_type': np.random.choice(['ECN','BANK','DARK','EXCHANGE'], n),
        'enabled': np.random.choice([True, False], n),
        'avg_latency_ms': np.round(np.random.uniform(0.5,5.0, n),2),
        'fill_rate': np.round(np.random.uniform(80,100, n),1),
        'rejections': np.random.randint(0,10, n),
        'min_order_size': np.round(np.random.uniform(0.01,0.1, n),4),
        'max_order_size': np.round(np.random.uniform(1,10, n),2),
        'fee_bps': np.round(np.random.uniform(0,2, n),3),
    })
    return df

def render_emsx_routing_tab() -> None:
    """Algorithmic transaction routing configurations – steel-\u200bblue theme."""
    inject_tab_theme("⚙️ EMSX ROUTING")


    st.subheader('🏦 Venue Routing Table')
    df = _synthetic_venues()
    # Enable/disable toggles per row – Streamlit does not support per-row widgets directly, so we show checkboxes above the table for demo.
    enabled_all = st.checkbox('Enable all venues', value=False)
    if enabled_all:
        df['enabled'] = True
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader('🧭 Smart Order Router Config')
    algorithm = st.selectbox('Routing Algorithm', options=['TWAP','VWAP','IS','POV','Adaptive'], index=0)
    slicing_period = st.slider('Slicing Period (seconds)', 1, 60, 10)
    max_child_pct = st.slider('Max Child % of Order', 1, 100, 20)
    randomize = st.checkbox('Randomize routes', value=True)
    min_fill = st.number_input('Min Fill %', min_value=0.0, max_value=100.0, value=50.0)
    if st.button('Run Backtest (simulated)'):
        st.info(f'Backtest complete – profit: {np.random.uniform(-2,5):.2f}%')
