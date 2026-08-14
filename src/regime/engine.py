# src/regime/engine.py
"""Regime Engine module (V2.2 Intelligence).

Provides a minimal implementation of a regime engine that evaluates market data
and determines the current trading regime (e.g., bullish, bearish, neutral).
The stub implementation uses a simplistic placeholder logic based on the
average of a numeric "signal" field in the provided data.
"""

from typing import Any


class RegimeEngine:
    """Simple regime engine.

    The engine can be extended with sophisticated statistical or ML models.
    For now it implements a deterministic placeholder based on a numeric
    "signal" in market data.
    """

    def __init__(self, threshold: float = 0.0) -> None:
        """Create a RegimeEngine.

        Parameters
        ----------
        threshold: float, optional
            Signal threshold separating bullish from bearish regimes. Default 0.
        """
        self.threshold = threshold

    def evaluate_market(self, market_data: list[dict[str, Any]]) -> str:
        """Evaluate market data and return the current regime.

        Parameters
        ----------
        market_data: List[Dict[str, Any]]
            A list of market data points. Each point should contain a numeric
            ``signal`` key. The stub uses the mean of these signals.

        Returns
        -------
        str
            One of "bullish", "bearish", or "neutral".
        """
        if not market_data:
            return "neutral"
        total = sum(float(item.get("signal", 0)) for item in market_data)
        avg = total / len(market_data)
        if avg > self.threshold:
            return "bullish"
        if avg < -self.threshold:
            return "bearish"
        return "neutral"