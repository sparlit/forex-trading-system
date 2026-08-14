# src/feature_registry.py
"""Feature Registry module (V2.2 Intelligence).

Provides a lightweight registry for feature classes used throughout the
trading system. The registry stores mappings from feature names to callable
objects or classes and offers simple lookup utilities.
"""

from collections.abc import Callable
from typing import Any


class FeatureRegistry:
    """Registry for intelligence features.

    Attributes
    ----------
    _registry: Dict[str, Callable]
        Internal mapping of feature names to constructors or callables.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._registry: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, factory: Callable[..., Any]) -> None:
        """Register a feature.

        Parameters
        ----------
        name: str
            Unique identifier for the feature.
        factory: Callable[..., Any]
            Callable that creates or returns the feature instance.
        """
        if name in self._registry:
            raise KeyError(f"Feature '{name}' is already registered")
        self._registry[name] = factory

    def get(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Retrieve a feature by name, optionally constructing it.

        Parameters
        ----------
        name: str
            Feature identifier.
        *args, **kwargs:
            Arguments passed to the stored factory.
        """
        if name not in self._registry:
            raise KeyError(f"Feature '{name}' not found in registry")
        return self._registry[name](*args, **kwargs)

    def list_features(self) -> list[str]:
        """Return a list of registered feature names."""
        return list(self._registry.keys())

    def clear(self) -> None:
        """Remove all registered features."""
        self._registry.clear()