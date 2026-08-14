"""Self‑diagnostics health checks.
Provides ``run_checks(bus, market_state)`` which returns a dict mapping
component names to boolean pass/fail values.
"""

def run_checks(bus, market_state):
    """Run a suite of lightweight health checks.
    Returns a dict like ``{"bus": True, "market_state": True}``.
    ``bus`` is expected to be an ``EventBus`` instance; we simply verify it has
    a ``publish`` method. ``market_state`` should be a ``MarketStateEngine``; we
    check that its ``get_state`` returns a dict (even if empty). Additional
    checks can be added later.
    """
    checks = {}
    # EventBus sanity
    checks["bus"] = hasattr(bus, "publish") and callable(bus.publish)
    # MarketStateEngine sanity
    try:
        state = market_state.get_state()
        checks["market_state"] = isinstance(state, dict)
    except Exception:
        checks["market_state"] = False
    return checks
