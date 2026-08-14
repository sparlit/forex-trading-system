"""Simple Transaction Cost Analysis (TCA) utilities.
Collects executed order data and computes basic metrics:
- **Slippage** – average absolute difference between the executed price and the
  mid‑price at the time of execution (if available).
- **Fill rate** – proportion of orders that were fully filled.
The module stores orders in a module‑level list; in a real system this would be a
persistent store (database, CSV, etc.).
"""


# In‑memory store of executed orders for this session.
_EXECUTED_ORDERS: list[dict] = []


def log_order(order: dict) -> None:
    """Append an executed order to the session store.
    Expected fields (minimal):
        - ``price`` (float): execution price.
        - ``mid_price`` (float, optional): market mid price at execution.
        - ``filled`` (bool): whether the order was fully filled.
    """
    _EXECUTED_ORDERS.append(order)


def compute_metrics() -> tuple[float, float]:
    """Return ``(average_slippage, fill_rate)``.
    If no orders are recorded, both metrics default to ``0.0``.
    """
    if not _EXECUTED_ORDERS:
        return 0.0, 0.0
    slippages: list[float] = []
    filled_count = 0
    for o in _EXECUTED_ORDERS:
        price = float(o.get("price", 0))
        mid = float(o.get("mid_price", price))
        slippages.append(abs(price - mid))
        if o.get("filled", False):
            filled_count += 1
    avg_slippage = sum(slippages) / len(slippages)
    fill_rate = filled_count / len(_EXECUTED_ORDERS)
    return avg_slippage, fill_rate


def reset() -> None:
    """Clear stored orders – useful between test runs."""
    _EXECUTED_ORDERS.clear()

# Convenience wrapper that also pushes metrics to Prometheus.
def record_metrics() -> None:
    """Compute TCA metrics and forward them to Prometheus via the monitoring client."""
    from src.monitoring.prometheus_client import record_tca_metrics
    slippage, fill_rate = compute_metrics()
    record_tca_metrics(slippage, fill_rate)
