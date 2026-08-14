
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _synthetic_yields():
    countries = ['US','Germany','Japan','UK','Australia','Canada']
    data = {
        'country': countries,
        '2y': np.round(np.random.uniform(0.5, 3.5, len(countries)), 2),
        '5y': np.round(np.random.uniform(1.0, 4.0, len(countries)), 2),
        '10y': np.round(np.random.uniform(1.5, 5.0, len(countries)), 2),
        '30y': np.round(np.random.uniform(2.0, 6.0, len(countries)), 2),
        'yield_curve_shape': np.random.choice(['normal','steep','inverted'], len(countries)),
    }
    return pd.DataFrame(data)

def _synthetic_duration():
    bonds = ['US Treasury 10Y','German Bund 10Y','Japanese Gov 10Y']
    data = {
        'bond_name': bonds,
        'macaulay_duration': np.round(np.random.uniform(5,12, len(bonds)),2),
        'modified_duration': np.round(np.random.uniform(4,11, len(bonds)),2),
        'dv01': np.round(np.random.uniform(0.01,0.10, len(bonds)),4),
        'convexity': np.round(np.random.uniform(50,200, len(bonds)),1),
    }
    return pd.DataFrame(data)

def _synthetic_spread_index():
    ratings = ['AAA','AA','A','BBB','BB','B']
    data = {
        'rating': ratings,
        'spread_bps': np.round(np.random.uniform(20,200, len(ratings)),1),
        '1d_change': np.round(np.random.uniform(-5,5, len(ratings)),1),
        '30d_trend': np.round(np.random.uniform(-20,20, len(ratings)),1),
    }
    return pd.DataFrame(data)

def render_yield_analytics_tab() -> None:
    """Yield curve analytics – emerald / green theme."""
    st.markdown(f"""{header_template.format(colors='#006400, #00ff00', title='Yield Analytics Dashboard')}""", unsafe_allow_html=True)

    st.subheader('📊 Government Yields')
    df_yld = _synthetic_yields()
    # color heatmap: lower yields green, higher red – use background_gradient with custom cmap
    styled = df_yld.style.background_gradient(subset=['2y','5y','10y','30y'], cmap='RdYlGn_r')
    st.dataframe(styled)

    st.subheader('⏳ Duration Analysis')
    df_dur = _synthetic_duration()
    st.table(df_dur)

    st.subheader('📈 Credit Spread Index')
    df_spread = _synthetic_spread_index()
    fig = go.Figure(data=[go.Bar(x=df_spread['rating'], y=df_spread['spread_bps'], text=df_spread['spread_bps'], textposition='auto')])
    fig.update_layout(template='plotly_dark', title='Spread (bps) by Rating')
    st.plotly_chart(fig, use_container_width=True)
