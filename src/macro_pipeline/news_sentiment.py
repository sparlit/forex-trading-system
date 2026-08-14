"""News sentiment wrapper.
Fetches recent news headlines and returns a simple sentiment score.
If the external request fails, returns a deterministic synthetic sentiment.
"""

import re

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

_NEWS_API_URL = "https://api.first.org/data/v1/news?limit=10"
_POSITIVE_WORDS = {"growth", "gain", "up", "positive", "record", "surge"}
_NEGATIVE_WORDS = {"loss", "down", "negative", "drop", "record", "fall"}


def _fallback_sentiment() -> dict:
    """Deterministic synthetic sentiment when any request fails.
    Returns a dict with `positive`, `negative`, and `neutral` counts.
    """
    return {"positive": 3, "negative": 1, "neutral": 6}


def _score_headline(text: str) -> str:
    """Very naive sentiment classifier for a headline.
    Returns "positive", "negative", or "neutral" based on keyword presence.
    """
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if words & _POSITIVE_WORDS:
        return "positive"
    if words & _NEGATIVE_WORDS:
        return "negative"
    return "neutral"


def fetch_sentiment(limit: int = 10) -> dict:
    """Fetch recent news headlines and return aggregate sentiment counts.
    On any failure, returns deterministic fallback data.
    """
    if not requests:
        return _fallback_sentiment()
    try:
        resp = requests.get(_NEWS_API_URL, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        headlines: list[str] = [item.get("title", "") for item in payload.get("data", [])][:limit]
        counts = {"positive": 0, "negative": 0, "neutral": 0}
        for h in headlines:
            sentiment = _score_headline(h)
            counts[sentiment] += 1
        # If API returned no headlines, fallback.
        if sum(counts.values()) == 0:
            return _fallback_sentiment()
        return counts
    except Exception:
        return _fallback_sentiment()
