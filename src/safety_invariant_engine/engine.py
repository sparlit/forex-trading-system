"""Safety Invariant Engine.
Enforces immutable safety rules defined in the design.
"""

from collections.abc import Callable


class SafetyInvariantEngine:
    def __init__(self):
        # List of invariant callables that raise on violation
        self.invariants: list[Callable[[], None]] = []

    def register(self, invariant: Callable[[], None]) -> None:
        """Register a new safety invariant.
        The callable should raise an Exception if the invariant is violated.
        """
        self.invariants.append(invariant)

    def check_all(self) -> None:
        """Execute all registered invariants. Raises at first failure."""
        for inv in self.invariants:
            inv()
