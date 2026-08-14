
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _gauge_chart(value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#ff69b4"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    fig.update_layout(template='plotly_dark')
    return fig

def render_sentiment_deep_tab() -> None:
    """Deep Market Sentiment – rose / pink theme with gauges and radar."""
    st.markdown(f"""{header_template.format(colors='#ff1493, #ff69b4', title='Deep Sentiment Dashboard')}""", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader('Overall Sentiment Gauge')
        overall = np.random.uniform(0,100)
        st.plotly_chart(_gauge_chart(overall), use_container_width=True)
    with col2:
        st.subheader('Fear & Greed Index')
        dates = [datetime.now() - timedelta(days=i) for i in range(30)][::-1]
        values = np.clip(np.random.normal(50,15,30),0,100)
        fig = go.Figure(data=go.Scatter(x=dates, y=values, mode='lines+markers'))
        fig.update_layout(template='plotly_dark', height=250)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader('News Sentiment Radar')
    categories = ['Economy','Policy','Geopolitics','Tech','Commodities']
    scores = np.random.uniform(0,100, len(categories))
    radar = go.Figure(data=go.Scatterpolar(r=scores, theta=categories, fill='toself'))
    radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])), template='plotly_dark')
    st.plotly_chart(radar, use_container_width=True)

    st.subheader('Sentiment vs Price Divergence')
    df = pd.DataFrame({
        'symbol': [f"{np.random.choice(['EUR','GBP','USD'])}{np.random.choice(['USD','JPY'])}" for _ in range(8)],
        'sentiment_score': np.round(np.random.uniform(0,100,8),1),
        'price_change_pct': np.round(np.random.uniform(-5,5,8),2),
    })
    st.dataframe(df)

    st.subheader('Central Bank Tracker')
    cb = pd.DataFrame({
        'central_bank': ['Fed','ECB','BOE','BOJ','RBA'],
        'tone': np.random.choice(['Hawkish','Dovish','Neutral'],5),
        'last_statement': [datetime.now() - timedelta(days=np.random.randint(1,10)) for _ in range(5)]
    })
    st.table(cb)
