'''AI Config tab – model selection, parameters, training status, module toggles, data sources, schedule, resources.'''

from __future__ import annotations

import os
import sys

import streamlit as st

# Ensure repo root for LLM imports
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Optional import of custom LLM – gracefully degrade if unavailable
try:
    from src.ai.custom_llm import get_custom_llm
except Exception:  # pragma: no cover
    get_custom_llm = None

def _model_selection() -> None:
    options = ["Custom LLM", "FinGPT", "Ollama"]
    choice = st.radio("Model selection", options, index=0)
    st.session_state.model_choice = choice

def _model_parameters() -> None:
    st.subheader("Model Parameters")
    col_d, col_n = st.columns(2)
    with col_d:
        st.slider("d_model", min_value=64, max_value=1024, value=256, step=32, key="d_model")
    with col_n:
        st.slider("n_layers", min_value=1, max_value=24, value=6, step=1, key="n_layers")
    st.slider("learning_rate", min_value=1e-5, max_value=1e-2, value=3e-4, step=1e-5, format="%e", key="learning_rate")
    st.slider("batch_size", min_value=8, max_value=256, value=32, step=8, key="batch_size")

def _training_status() -> None:
    st.subheader("Training Status")
    if get_custom_llm:
        llm = get_custom_llm()
        metrics = llm.get_metrics()
        col1, col2 = st.columns(2)
        col1.metric("Trained", str(metrics.get("trained")))
        col2.metric("Accuracy", f"{metrics.get('best_val_accuracy',0):.2%}")
        st.metric("Target Accuracy", f"{metrics.get('target_accuracy',0):.2%}")
        st.metric("Device", metrics.get("device", "cpu"))
        st.caption(f"Samples: {metrics.get('total_candle_samples',0)} candles, {metrics.get('total_text_samples',0)} texts")
    else:
        st.info("Custom LLM not available – static placeholder metrics.")
        st.metric("Training", "N/A")
        st.metric("Accuracy", "N/A")

def _module_toggles() -> None:
    st.subheader("Brain Module Toggles")
    modules = ["analysis", "prediction", "self_evolving"]
    for m in modules:
        st.checkbox(f"Enable {m}", key=f"mod_{m}")

def _data_sources() -> None:
    st.subheader("Training Data Sources")
    sources = ["MT5 ticks", "Web news", "Filings"]
    for src in sources:
        st.checkbox(src, key=f"src_{src.replace(' ', '_').lower()}")

def _retrain_schedule() -> None:
    st.subheader("Retrain Schedule")
    interval = st.number_input("Retrain interval (hours)", min_value=1, max_value=168, value=24, step=1, key="retrain_interval")
    target = st.slider("Target accuracy", 0.80, 0.99, 0.95, 0.01, key="target_accuracy")
    st.write(f"Will retrain every {interval}h aiming for {target:.0%} accuracy.")

def _resource_limits() -> None:
    st.subheader("Resource Limits")
    st.slider("GPU memory (GB)", 0, 32, 8, 1, key="gpu_mem")
    st.slider("CPU cores", 1, 16, 4, 1, key="cpu_cores")

def render_ai_config_tab() -> None:
    st.title("\U0001F527 AI Config")
    _model_selection()
    st.markdown("---")
    _model_parameters()
    st.markdown("---")
    _training_status()
    st.markdown("---")
    _module_toggles()
    st.markdown("---")
    _data_sources()
    st.markdown("---")
    _retrain_schedule()
    st.markdown("---")
    _resource_limits()

    if st.button("Apply Settings"):
        st.success("AI configuration applied (simulated).")
