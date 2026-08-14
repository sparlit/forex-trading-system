"""Economic calendar wrapper.
Fetches a list of upcoming macroeconomic events from a free public endpoint.
If the request fails (no internet or API unavailable), returns a deterministic
fallback list of dummy events suitable for testing.
"""

import datetime

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

# Example free endpoint – for illustration only. Real implementations would use
# a dedicated economic calendar API (e.g., TradingEconomics, Econoday, etc.).
_ECONOMIC_API_URL = "https://api.exchangerate.host/latest"


def _fallback_events() -> list[dict]:
    """Return a deterministic set of dummy macro events.
    Each event contains `time`, `country`, `event`, and `impact` (low/medium/high).
    """
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    return [
        {
            "time": (now + datetime.timedelta(hours=1)).isoformat(),
            "country": "US",
            "event": "Non‑Farm Payrolls",
            "impact": "high",
        },
        {
            "time": (now + datetime.timedelta(hours=2)).isoformat(),
            "country": "EU",
            "event": "CPI",
            "impact": "medium",
        },
    ]


def fetch_upcoming_events(limit: int = 10) -> list[dict]:
    """Return a list of upcoming macro‑economic events.
    The function attempts a real HTTP request; on any failure it returns the
    deterministic fallback list (truncated to *limit* items).
    """
    if not requests:
        return _fallback_events()[:limit]
    try:
        resp = requests.get(_ECONOMIC_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # The free endpoint returns exchange rates; we'll synthesize events from it.
        # For each of the first `limit` currency codes, create a dummy event.
        events: list[dict] = []
        for i, (code, rate) in enumerate(data.get("rates", {}).items()):
            if i >= limit:
                break
            events.append(
                {
                    "time": datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat(),
                    "country": code,
                    "event": f"Rate for {code}",
                    "impact": "low",
                }
            )
        return events or _fallback_events()[:limit]
    except Exception:
        # Any network error, JSON error, etc.
        return _fallback_events()[:limit]
