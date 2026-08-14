
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _synthetic_consensus(n=15):
    symbols = [f"{np.random.choice(['EUR','GBP','USD','JPY'])}{np.random.choice(['USD','JPY'])}" for _ in range(n)]
    data = {
        'symbol': symbols,
        'strong_buy': np.random.randint(0,5,n),
        'buy': np.random.randint(5,15,n),
        'hold': np.random.randint(5,15,n),
        'sell': np.random.randint(0,5,n),
        'strong_sell': np.random.randint(0,2,n),
        'consensus': np.random.choice(['Buy','Hold','Sell'], n),
        'target_price': np.round(np.random.uniform(0.8,1.6,n),5),
        'upside_pct': np.round(np.random.uniform(-5,15,n),2),
    }
    return pd.DataFrame(data)

def _mlp_info():
    # placeholders for model info
    info = {
        'accuracy': f"{np.random.uniform(0.80,0.95):.2%}",
        'last_training': (datetime.now() - timedelta(days=np.random.randint(1,30))).strftime('%Y-%m-%d'),
    }
    # synthetic prediction for a random symbol
    pred = {
        'symbol': 'EURUSD',
        'predicted_direction': np.random.choice(['Up','Down','Sideways']),
        'confidence': f"{np.random.uniform(0.6,0.95):.2%}",
        'inputs_summary': 'ATR, RSI, MACD, Volume',
    }
    return info, pred

def render_anr_recommend_tab() -> None:
    """Consensus Recommendations + MLP Model + Local LLM – indigo / violet theme."""
    st.markdown(f"""{header_template.format(colors='#4b0082, #8a2be2', title='Analyst Recommendations & AI Models')}""", unsafe_allow_html=True)

    # Section A – Consensus Matrix
    st.subheader('📊 Consensus Recommendations Matrix')
    df_cons = _synthetic_consensus()
    st.dataframe(df_cons)

    # Section B – MLP Neural Model panel
    st.subheader('🤖 MLP Neural Model')
    model_info, prediction = _mlp_info()
    col1, col2 = st.columns(2)
    with col1:
        st.metric('Model Accuracy', model_info['accuracy'])
        st.metric('Last Training', model_info['last_training'])
    with col2:
        st.metric('Predicted Direction', prediction['predicted_direction'])
        st.metric('Confidence', prediction['confidence'])
        st.write('Inputs:', prediction['inputs_summary'])
    # Architecture diagram – simple text box
    st.text('MLP Architecture: Input(20) → Dense(64) → ReLU → Dense(32) → ReLU → Output(3)')
    # Training loss curve placeholder
    epochs = list(range(1,51))
    loss = np.exp(-np.array(epochs)/10) + np.random.normal(0,0.02,len(epochs))
    fig_loss = go.Figure()
    fig_loss.add_trace(go.Scatter(x=epochs, y=loss, mode='lines', name='Loss'))
    fig_loss.update_layout(title='Training Loss Over Epochs', template='plotly_dark')
    st.plotly_chart(fig_loss, use_container_width=True)

    # Section C – Local LLM panel
    st.subheader('🧠 Local LLM Demo')
    prompt = st.text_area('Prompt to LLM', value='Explain the impact of a rising US Dollar on emerging markets.')
    if st.button('Run LLM'):
        # Simulated response
        response = "A stronger USD typically puts pressure on emerging market currencies, leading to capital outflows and lower commodity prices."
        st.success('LLM generated response:')
        st.write(response)
        st.metric('Context Window Usage', f"{np.random.randint(500,3500)} / 4096 tokens")
