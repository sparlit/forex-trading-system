"""market_state.py

Market State Vector engine – a lightweight in‑memory engine that aggregates
incoming market events into a canonical ``MarketStateVector`` for each symbol.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class MarketStateVector:
    """Canonical snapshot of market‑wide descriptors for a single symbol.

    All fields are populated by :class:`MarketStateEngine`.  Fields are typed as
    ``float`` where a numeric value makes sense; ``str`` for categorical data.
    """

    symbol: str
    asset_class: str
    session: str
    regime: str
    trend: str
    momentum: float
    volatility: float
    liquidity: float
    spread: float
    order_flow_state: str
    sentiment: float
    macro_state: str
    correlation: float
    funding: float
    basis: float
    market_depth: float
    news_state: str
    execution_state: str
    updated_time: _dt.datetime = field(default_factory=_dt.datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketStateVector:
        if isinstance(data.get("updated_time"), str):
            data["updated_time"] = _dt.datetime.fromisoformat(data["updated_time"])
        return cls(**data)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class MarketStateEngine:
    """Collect events and keep the latest state for each active symbol.

    The engine is intentionally simple: callers push (symbol, payload) events via
    :meth:`process_event`.  The payload is a mapping that may contain any subset
    of the fields defined in :class:`MarketStateVector`.  Missing fields are left
    unchanged.  After processing, the engine emits a ``MarketStateChanged``
    event via the optional ``on_change`` callback.
    """

    def __init__(self, on_change: Callable[[MarketStateVector], None] | None = None):
        self._states: dict[str, MarketStateVector] = {}
        self.on_change = on_change

    # ---------------------------------------------------------------------
    def _default_state(self, symbol: str) -> MarketStateVector:
        # Provide sensible defaults – most fields zero/empty.
        return MarketStateVector(
            symbol=symbol,
            asset_class="",
            session="",
            regime="",
            trend="",
            momentum=0.0,
            volatility=0.0,
            liquidity=0.0,
            spread=0.0,
            order_flow_state="",
            sentiment=0.0,
            macro_state="",
            correlation=0.0,
            funding=0.0,
            basis=0.0,
            market_depth=0.0,
            news_state="",
            execution_state="",
        )

    # ---------------------------------------------------------------------
    def process_event(self, symbol: str, payload: dict[str, Any]) -> MarketStateVector:
        """Update (or create) the ``MarketStateVector`` for *symbol*.

        ``payload`` may contain any subset of the vector fields.  Numeric values are
        coerced to ``float`` when possible.
        """
        state = self._states.get(symbol) or self._default_state(symbol)
        for key, value in payload.items():
            if not hasattr(state, key):
                continue  # silently ignore unknown keys
            # Basic type coercion for numeric fields.
            if isinstance(getattr(state, key), (int, float)):
                try:
                    value = float(value)
                except Exception:
                    pass
            setattr(state, key, value)
        state.updated_time = _dt.datetime.utcnow()
        self._states[symbol] = state
        if self.on_change:
            self.on_change(state)
        return state

    # ---------------------------------------------------------------------
    def get_state(self, symbol: str) -> MarketStateVector | None:
        """Retrieve the latest state for *symbol* (or ``None`` if unknown)."""
        return self._states.get(symbol)

    def all_symbols(self) -> list[str]:
        return list(self._states.keys())

# End of file
