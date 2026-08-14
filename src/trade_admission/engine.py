"""Trade Admission component.
Validates a trade request against the authority hierarchy (levels 0‑11).
"""

from typing import Any


class TradeAdmission:
    def __init__(self):
        # In a real system this would load policy/configuration
        self.authority_matrix = {
            "legal": True,
            "safety_invariant": True,
            "safety_kernel": True,
            "capital_governance": True,
            "hard_portfolio_risk": True,
            "independent_risk_verification": True,
            "trade_admission": True,
        }

    def evaluate(self, request: dict[str, Any]) -> bool:
        """Return True if the trade request passes all authority checks.
        Placeholder logic – in practice each check consults the corresponding engine.
        """
        # Simple stub: require that request contains a non‑empty symbol and size
        if not request.get("symbol") or request.get("size", 0) <= 0:
            return False
        # Assume all authority layers approve for the demo
        return all(self.authority_matrix.values())
