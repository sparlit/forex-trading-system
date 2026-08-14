"""Adversarial testing fuzzer.
Applies simple random perturbations (Gaussian noise) to numeric values in the
market state to simulate noisy or malicious data streams. This is useful for
robustness testing of the regime detector and downstream components.
"""

import copy
import random
from typing import Any


def _add_noise(value: Any, magnitude: float) -> Any:
    if isinstance(value, (int, float)):
        # Apply Gaussian noise scaled by magnitude of the value (or 1 if zero)
        scale = magnitude * (abs(value) if value != 0 else 1)
        return value + random.gauss(0, scale)
    if isinstance(value, dict):
        return {k: _add_noise(v, magnitude) for k, v in value.items()}
    if isinstance(value, list):
        return [_add_noise(v, magnitude) for v in value]
    return value


def apply_noise(state: dict[str, Any], magnitude: float = 0.01) -> dict[str, Any]:
    """Return a new market‑state dict where numeric entries are perturbed.
    ``magnitude`` controls the relative noise level (e.g., ``0.01`` ≈ 1 % noise).
    The original ``state`` dict is not mutated.
    """
    noisy_state = copy.deepcopy(state)
    return _add_noise(noisy_state, magnitude)
