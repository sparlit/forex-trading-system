
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _generate_candles(symbol: str, periods: int = 200):
    np.random.seed(abs(hash(symbol)) % 2**32)
    base = np.random.uniform(0.8, 1.5)
    dates = pd.date_range(end=datetime.now(tz=timezone.utc), periods=periods, freq='15T')
    price = base + np.cumsum(np.random.normal(0, 0.001, periods))
    df = pd.DataFrame({
        'date': dates,
        'open': price + np.random.normal(0, 0.0005, periods),
        'high': price + np.random.normal(0.001, 0.0005, periods),
        'low': price - np.random.normal(0.001, 0.0005, periods),
        'close': price,
    })
    df['high'] = df[['open','close','high']].max(axis=1)
    df['low'] = df[['open','close','low']].min(axis=1)
    return df

def render_price_chart_tab() -> None:
    """Price chart with overlays – purple / magenta theme."""
    st.markdown(f"""{header_template.format(colors='#800080, #ff00ff', title='Price Chart & Indicators')}""", unsafe_allow_html=True)

    symbol = st.text_input('Symbol', value='EURUSD')
    df = _generate_candles(symbol)

    show_ema20 = st.checkbox('EMA 20', value=True)
    show_ema50 = st.checkbox('EMA 50')
    show_ema200 = st.checkbox('EMA 200')
    show_bb = st.checkbox('Bollinger Bands')
    show_rsi = st.checkbox('RSI')
    show_macd = st.checkbox('MACD')
    show_fibo = st.checkbox('Fibonacci Levels')

    fig = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                                     name='Price')])
    # EMA calculations
    if show_ema20:
        ema20 = df['close'].ewm(span=20, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df['date'], y=ema20, mode='lines', name='EMA 20'))
    if show_ema50:
        ema50 = df['close'].ewm(span=50, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df['date'], y=ema50, mode='lines', name='EMA 50'))
    if show_ema200:
        ema200 = df['close'].ewm(span=200, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df['date'], y=ema200, mode='lines', name='EMA 200'))
    if show_bb:
        std = df['close'].rolling(20).std()
        upper = df['close'].rolling(20).mean() + 2 * std
        lower = df['close'].rolling(20).mean() - 2 * std
        fig.add_trace(go.Scatter(x=df['date'], y=upper, line=dict(color='rgba(255,0,255,0.5)'), name='BB Upper'))
        fig.add_trace(go.Scatter(x=df['date'], y=lower, line=dict(color='rgba(255,0,255,0.5)'), name='BB Lower'))

    fig.update_layout(height=600, template='plotly_dark', margin=dict(l=20,r=20,t=30,b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Subplots for RSI/MACD if selected
    if show_rsi:
        rsi = 100 - (100 / (1 + df['close'].pct_change().apply(lambda x: np.exp(x)).rolling(14).mean()))
        fig_rsi = go.Figure()
        fig_rsi.add_trace(go.Scatter(x=df['date'], y=rsi, name='RSI'))
        fig_rsi.update_layout(height=200, template='plotly_dark', title='RSI (14)')
        st.plotly_chart(fig_rsi, use_container_width=True)
    if show_macd:
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        fig_macd = go.Figure()
        fig_macd.add_trace(go.Scatter(x=df['date'], y=macd, name='MACD'))
        fig_macd.add_trace(go.Scatter(x=df['date'], y=signal, name='Signal'))
        fig_macd.update_layout(height=200, template='plotly_dark', title='MACD')
        st.plotly_chart(fig_macd, use_container_width=True)

    if show_fibo:
        high = df['high'].max()
        low = df['low'].min()
        diff = high - low
        levels = [low + diff * r for r in [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]]
        fibo_df = pd.DataFrame({'Level': ['0%', '23.6%', '38.2%', '50%', '61.8%', '78.6%', '100%'],
                                'Price': levels})
        st.table(fibo_df)
