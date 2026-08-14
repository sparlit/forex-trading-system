"""Tests for simple regime detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.regime_detection.detector import detect_regime

def test_regime_trending_up():
    market_state = {"prices": [1.0, 1.1, 1.2, 1.3, 1.4]}
    assert detect_regime(market_state) == "trending_up"

def test_regime_trending_down():
    market_state = {"prices": [1.4, 1.3, 1.2, 1.1, 1.0]}
    assert detect_regime(market_state) == "trending_down"

def test_regime_range_bound():
    market_state = {"prices": [1.0, 1.01, 1.02, 1.01, 1.0]}
    assert detect_regime(market_state) == "range_bound"

def test_regime_insufficient_data():
    market_state = {"prices": [1.0, 1.1]}
    assert detect_regime(market_state) == "range_bound"
