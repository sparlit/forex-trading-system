"""
Config Package
==============

Configuration management with hot-reload support.

This module exposes a single ``AppConfig`` instance (``app_config``) that
wraps the global :class:`settings` object and provides helpers for
validation, secret retrieval and environment summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.infra.config.hot_reload import (
    ConfigReloader,
    get_config_reloader,
    init_config_reloader,
    on_config_reload,
    setup_settings_reload,
)
from src.infra.config.secrets import get_secret
from src.infra.config.settings import settings

__all__ = [
    "AppConfig",
    "ConfigReloader",
    "app_config",
    "get_config_reloader",
    "init_config_reloader",
    "on_config_reload",
    "settings",
    "setup_settings_reload",
]


@dataclass
class AppConfig:
    """Aggregated application configuration.

    Provides convenience access to the underlying ``settings`` singleton
    plus a lightweight ``validate`` method and a helper for secret
    retrieval.
    """

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - delegation
        # Delegate any unknown attribute to the global ``settings`` object
        return getattr(settings, item)

    @property
    def environment(self) -> str:
        """Return ``"production"`` if ``settings.environment`` is missing."""
        try:
            return str(settings.environment)
        except Exception:  # pragma: no cover - defensive
            return "unknown"

    def validate(self) -> list[str]:
        """Validate the configuration and return a list of warnings.

        The function never raises – callers can decide what to do with the
        warnings.  The goal is to surface mis‑configuration early.
        """
        warnings: list[str] = []

        # Database
        if not getattr(settings, "timescale_host", None):
            warnings.append("timescale_host is not configured")

        # Messaging
        if not getattr(settings, "nats_url", None):
            warnings.append("nats_url is not configured")

        # Cache
        if not getattr(settings, "redis_host", None):
            warnings.append("redis_host is not configured")

        # Secrets – warn if vault is configured but unreachable
        vault_url = getattr(settings, "vault_url", None)
        if vault_url and not vault_url.startswith("http"):
            warnings.append("vault_url is not a valid URL")

        return warnings

    def get_secret(self, key: str, default: Any | None = None) -> Any:
        """Retrieve a secret via :func:`get_secret`."""
        return get_secret(key, default)


# Singleton accessor – use this everywhere: ``from src.infra.config import app_config``
app_config = AppConfig()
