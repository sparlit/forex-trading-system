"""Portfolio Engine skeleton.
Manages allocation of capital across opportunities respecting risk budgets.
"""


class PortfolioEngine:
    def __init__(self):
        self.allocations: dict[str, float] = {}  # symbol -> portion of capital
        self.total_capital: float = 0.0
        self.risk_budget: float = 0.0

    def set_capital(self, amount: float) -> None:
        self.total_capital = amount

    def set_risk_budget(self, risk: float) -> None:
        self.risk_budget = risk

    def allocate(self, symbol: str, weight: float) -> None:
        """Allocate a portion of capital to a symbol.
        Weight should be between 0 and 1 and total allocations must not exceed 1.
        """
        self.allocations[symbol] = weight
        # Simple validation – in production raise if sum>1 or exceeds risk
        if sum(self.allocations.values()) > 1.0:
            raise ValueError("Total allocation exceeds 100% of capital")

    def get_allocations(self) -> dict[str, float]:
        return self.allocations.copy()

    def compute_exposure(self) -> float:
        """Return total exposure as sum(weight * total_capital)."""
        return sum(w * self.total_capital for w in self.allocations.values())
