"""Configuration validation using Pydantic.

Loads the YAML file ``config/settings.yaml`` and validates all fields.
Ensures any ``datetime`` values are timezone‑aware (UTC).
Provides a ``settings`` singleton for import throughout the project.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field, ValidationError, validator
from datetime import datetime, timezone

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"

class PrometheusSettings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    # No datetime fields here.

class FeedSettings(BaseModel):
    type: str = Field(..., description="Feed type: 'mt5' or 'ccxt'")
    # Example optional settings per feed
    mt5_endpoint: str | None = None
    ccxt_exchange: str | None = None

class Settings(BaseModel):
    feed: FeedSettings
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    # Example global timeout in seconds (must be positive)
    timeout_seconds: int = Field(default=30, gt=0)

    @validator("*", pre=True)
    def ensure_timezone_aware(cls, v: Any, field):
        # If a datetime is supplied, force UTC timezone.
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

def load_settings() -> Settings:
    """Load and validate ``settings.yaml``.

    Returns a fully validated ``Settings`` instance. Raises ``ValidationError``
    with a clear message if the file is missing or malformed.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in {CONFIG_PATH}: {exc}") from exc

# Create a module‑level singleton for convenient import.
settings = load_settings()
