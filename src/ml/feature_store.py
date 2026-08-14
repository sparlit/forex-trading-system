"""
Feature Store & Online Learning
================================

A lightweight, in‑memory feature store that can be used by ML models to
persist computed features keyed by ``(symbol, timeframe, timestamp)``.

Also includes a trivial stochastic‑gradient‑descent (SGD) online learner
that updates a linear model's weights after each new example.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger


@dataclass
class FeatureVector:
    """A named feature vector."""

    symbol: str
    timeframe: str
    timestamp: datetime
    values: dict[str, float] = field(default_factory=dict)


class FeatureStore:
    """In‑memory feature store keyed by ``(symbol, timeframe, timestamp)``."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, datetime], FeatureVector] = {}

    def put(self, feature: FeatureVector) -> None:
        key = (feature.symbol, feature.timeframe, feature.timestamp)
        self._store[key] = feature
        logger.debug(
            "Feature stored",
            key=key,
            num_features=len(feature.values),
        )

    def get(self, symbol: str, timeframe: str, timestamp: datetime) -> FeatureVector | None:
        return self._store.get((symbol, timeframe, timestamp))

    def latest(self, symbol: str, timeframe: str) -> FeatureVector | None:
        """Return the most recent feature vector for ``symbol/timeframe``."""
        matching = [k for k in self._store if k[0] == symbol and k[1] == timeframe]
        if not matching:
            return None
        latest_key = max(matching, key=lambda k: k[2])
        return self._store[latest_key]

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Online learner
# ---------------------------------------------------------------------------


class OnlineLinearModel:
    """Simple linear model updated with stochastic gradient descent.

    Useful as a placeholder for more sophisticated online learners such
    as River or sklearn‑SGD.
    """

    def __init__(self, n_features: int, learning_rate: float = 0.01) -> None:
        self.lr = learning_rate
        self.weights: list[float] = [0.0] * n_features
        self.bias: float = 0.0

    def predict(self, x: Iterable[float]) -> float:
        x = list(x)
        if len(x) != len(self.weights):
            raise ValueError("Feature length mismatch")
        return self.bias + sum(w * xi for w, xi in zip(self.weights, x))

    def update(self, x: Iterable[float], y: float) -> None:
        x = list(x)
        y_hat = self.predict(x)
        error = y - y_hat
        # Update weights and bias in place
        for i in range(len(self.weights)):
            self.weights[i] += self.lr * error * x[i]
        self.bias += self.lr * error

    def loss(self, xs: Iterable[Iterable[float]], ys: Iterable[float]) -> float:
        total = 0.0
        n = 0
        for x, y in zip(xs, ys):
            err = y - self.predict(x)
            total += err * err
            n += 1
        return total / n if n else 0.0


# Singleton accessor ---------------------------------------------------------
_default_store: FeatureStore | None = None


def get_feature_store() -> FeatureStore:
    global _default_store
    if _default_store is None:
        _default_store = FeatureStore()
    return _default_store
