"""Autonomous evolution engine.
A minimal example that tracks recent performance metrics and decides whether
to trigger a model adaptation. In a real system this would involve
retraining a strategy model, hyper‑parameter search, or policy mutation.
The implementation is deliberately lightweight – it stores a short history
of performance floats and flags when the latest performance drops more than
10% relative to the running average. The `should_adapt` method can be
polled by the main loop to initiate an adaptation step.
"""



class EvolutionEngine:
    """Simple performance‑monitoring engine for autonomous adaptation.
    Usage:
        engine = EvolutionEngine(window=5)
        engine.record(0.12)
        if engine.should_adapt():
            # trigger model update
    """

    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self.history: list[float] = []
        self.adapt_flag = False

    def record(self, performance: float) -> None:
        """Add a new performance measurement.
        ``performance`` should be a normalized metric (e.g., Sharpe ratio,
        profit factor, or win‑rate). The method updates the internal flag
        indicating whether adaptation is recommended.
        """
        self.history.append(performance)
        if len(self.history) > self.window:
            self.history.pop(0)
        self._evaluate()

    def _evaluate(self) -> None:
        """Internal evaluation of recent performance.
        If the latest measurement is more than 10% below the moving average,
        set ``adapt_flag`` to ``True``.
        """
        if not self.history:
            self.adapt_flag = False
            return
        avg = sum(self.history) / len(self.history)
        latest = self.history[-1]
        # Trigger adaptation if latest < 90% of average
        self.adapt_flag = latest < 0.9 * avg

    def should_adapt(self) -> bool:
        """Return ``True`` if recent performance warrants adaptation.
        After returning ``True`` the flag is reset until the next evaluation.
        """
        flag = self.adapt_flag
        self.adapt_flag = False
        return flag

    def get_history(self) -> list[float]:
        """Return a copy of the current performance history."""
        return list(self.history)
