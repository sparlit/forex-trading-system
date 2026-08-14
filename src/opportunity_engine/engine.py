"""Opportunity Engine skeleton.
Provides a simple API to evaluate BUY, SELL, or NO_TRADE decisions based on a market state.
"""

from enum import Enum, auto
from typing import Any


class Decision(Enum):
    BUY = auto()
    SELL = auto()
    NO_TRADE = auto()
    DEFER = auto()
    ABSTAIN = auto()

class OpportunityEngine:
    def __init__(self):
        self.last_decision: Decision = Decision.NO_TRADE
        self.context: dict[str, Any] = {}

    def evaluate(self, market_state: dict[str, Any]) -> Decision:
        """Placeholder evaluation logic.
        Real implementation will use strategy models, risk checks, etc.
        """
        # Very naive rule: if price > 1.0 -> BUY, else SELL
        price = market_state.get("price", 0)
        if price > 1.0:
            self.last_decision = Decision.BUY
        else:
            self.last_decision = Decision.SELL
        self.context = market_state
        return self.last_decision

    def get_last_decision(self) -> Decision:
        return self.last_decision

    def get_context(self) -> dict[str, Any]:
        return self.context.copy()
