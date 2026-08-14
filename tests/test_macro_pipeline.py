"""Tests for macro pipeline (economic calendar and news sentiment)."""
import sys
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.macro_pipeline.economic_calendar import fetch_upcoming_events
from src.macro_pipeline.news_sentiment import fetch_sentiment


def test_fetch_upcoming_events_success(monkeypatch):
    # Mock response for requests.get
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "rates": {"USD": 1.0, "EUR": 0.9, "JPY": 110.0}
    }
    monkeypatch.setattr('requests.get', lambda *_, **__: mock_resp)
    events = fetch_upcoming_events(limit=2)
    assert isinstance(events, list)
    assert len(events) == 2
    # Each event should contain the expected keys
    for ev in events:
        assert "time" in ev and "country" in ev and "event" in ev and "impact" in ev


def test_fetch_upcoming_events_fallback(monkeypatch):
    # Simulate requests raising an exception
    monkeypatch.setattr('requests.get', lambda *_, **__: (_ for _ in ()).throw(RuntimeError()))
    events = fetch_upcoming_events(limit=1)
    assert isinstance(events, list)
    assert len(events) == 1
    assert events[0]["event"] == "Non‑Farm Payrolls"


def test_fetch_sentiment_success(monkeypatch):
    # Mock a successful news API response with mixed headlines
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "data": [
            {"title": "Market sees growth amid record gains"},
            {"title": "Negative outlook as stocks fall"},
            {"title": "Neutral report on economic stability"},
        ]
    }
    monkeypatch.setattr('requests.get', lambda *_, **__: mock_resp)
    sentiment = fetch_sentiment(limit=3)
    assert sentiment["positive"] == 1
    assert sentiment["negative"] == 1
    assert sentiment["neutral"] == 1


def test_fetch_sentiment_fallback(monkeypatch):
    # Simulate request failure
    monkeypatch.setattr('requests.get', lambda *_, **__: (_ for _ in ()).throw(RuntimeError()))
    sentiment = fetch_sentiment(limit=5)
    assert sentiment == {"positive": 3, "negative": 1, "neutral": 6}
