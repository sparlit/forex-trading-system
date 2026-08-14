
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

CATEGORIES = ['econ','political','central_bank','geopolitical']
IMPACTS = ['LOW','MEDIUM','HIGH']

def _synthetic_news(num=30):
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(num):
        ts = now - timedelta(minutes=random.randint(0, 720))
        rows.append({
            'timestamp_utc': ts.strftime('%Y-%m-%d %H:%M'),
            'source': random.choice(['Reuters','Bloomberg','FT','WSJ','CNBC']),
            'headline': f"{random.choice(['Fed','ECB','BOE','PBOC'])} policy update {i}",
            'category': random.choice(CATEGORIES),
            'sentiment_tag': random.choice(['Bullish','Neutral','Bearish']),
            'impact': random.choice(IMPACTS),
            'related_symbols': random.choice(['EURUSD','USDJPY','GBPUSD','XAUUSD','BTCUSD']),
        })
    return pd.DataFrame(rows)

def render_news_feed_tab() -> None:
    """Live macro news feed – orange / red theme with sentiment charts."""
    st.markdown(f"""{header_template.format(colors='#ff6600, #ff0000', title='Macro News & Sentiment')}""", unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        st.subheader('📰 News Feed')
        df = _synthetic_news()
        st.dataframe(df)
    with right:
        st.subheader('📊 Sentiment Overview')
        # Pie chart of sentiment tags
        sentiment_counts = df['sentiment_tag'].value_counts().reset_index()
        sentiment_counts.columns = ['sentiment','count']
        fig_pie = px.pie(sentiment_counts, names='sentiment', values='count', title='Sentiment Distribution')
        st.plotly_chart(fig_pie, use_container_width=True)
        # Keyword frequency mock – using headlines words
        words = ' '.join(df['headline']).split()
        freq = pd.Series(words).value_counts().nlargest(10).reset_index()
        freq.columns = ['word','count']
        fig_bar = px.bar(freq, x='word', y='count', title='Top Keywords')
        st.plotly_chart(fig_bar, use_container_width=True)
        # Breaking news alert box
        high_impact = df[df['impact']=='HIGH'].head(1)
        if not high_impact.empty:
            st.warning(f"🚨 BREAKING: {high_impact.iloc[0]['headline']} ({high_impact.iloc[0]['source']})")
