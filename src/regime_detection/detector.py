"""Simple regime detection module.
Implements a placeholder regime detector based on moving‑average crossovers.
Given a market state dict (must contain a time‑ordered list of price points),
returns one of: "trending_up", "trending_down", "range_bound".
Real implementations would use statistical tests, volatility measures, etc.
"""


# For this stub we expect `market_state` to contain a key "prices" with a list of recent close prices.

def detect_regime(market_state: dict) -> str:
    prices: list[float] = market_state.get("prices", [])
    if len(prices) < 5:
        return "range_bound"  # insufficient data
    # Simple moving average crossover: short MA (3) vs long MA (5)
    short_ma = sum(prices[-3:]) / 3
    long_ma = sum(prices[-5:]) / 5
    if short_ma > long_ma * 1.01:
        return "trending_up"
    if short_ma < long_ma * 0.99:
        return "trending_down"
    return "range_bound"
