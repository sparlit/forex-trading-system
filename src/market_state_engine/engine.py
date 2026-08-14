"""Market State Engine skeleton.
Collects data plane feeds, builds a unified market snapshot.
Provides `update_feed(feed_name, data)` and `get_state()`.
"""

from typing import Any


class MarketStateEngine:
    def __init__(self):
        # Holds latest data per feed
        self.feeds: dict[str, Any] = {}
        # Cached unified state
        self._state: dict[str, Any] = {}

    def add_macro_data(self, macro_events: list[dict]) -> None:
        """Add macroeconomic events to the market state.
        Stored under the special feed name "macro".
        """
        self.feeds["macro"] = macro_events
        self._recalculate_state()

    def update_feed(self, feed_name: str, data: Any) -> None:
        """Replace the latest data for a given feed.
        In a real system this would include validation, timestamp checks,
        and alignment with the global clock.
        """
        self.feeds[feed_name] = data
        self._recalculate_state()

    def _recalculate_state(self) -> None:
        """Combine all feed data into a market snapshot.
        Placeholder implementation – simply merges dicts.
        """
        merged: dict[str, Any] = {}
        for feed, payload in self.feeds.items():
            if isinstance(payload, dict):
                merged.update(payload)
        self._state = merged

    def get_state(self) -> dict[str, Any]:
        """Return the current unified market state."""
        return self._state.copy()
