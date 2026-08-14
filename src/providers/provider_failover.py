"""
Provider Failover module.
Implements a thin abstraction over primary and secondary data providers
(e.g., CCXT exchange APIs, custom REST endpoints). If the primary provider
fails (connection error, timeout, or explicit error response), the call
automatically falls back to the secondary provider.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

@runtime_checkable
class ProviderProtocol(Protocol):
    """Minimal interface required for a data provider.

    Implementations must provide a ``get_market_data`` method that returns a
    mapping with at least ``symbol`` and ``timestamp`` keys (additional fields
    such as ``bid``, ``ask``, ``volume`` are optional but recommended).
    """

    def get_market_data(self, symbol: str) -> dict[str, Any]:
        ...

class ProviderFailover:
    """Wrap two providers – primary and secondary – and attempt primary first.

    Parameters
    ----------
    primary: ProviderProtocol
        The preferred provider (e.g., live CCXT exchange).
    secondary: ProviderProtocol
        Backup provider used when the primary raises an exception or returns a
        falsy payload.
    max_retries: int, optional
        Number of attempts against the primary before falling back. Defaults
        to 2.
    """

    def __init__(self, primary: ProviderProtocol, secondary: ProviderProtocol, max_retries: int = 2):
        self.primary = primary
        self.secondary = secondary
        self.max_retries = max_retries
        logger.info(
            "ProviderFailover configured – primary=%s, secondary=%s, max_retries=%d",
            primary.__class__.__name__, secondary.__class__.__name__, max_retries
        )

    def _call_provider(self, provider: ProviderProtocol, symbol: str) -> dict[str, Any] | None:
        try:
            data = provider.get_market_data(symbol)
            if not data:
                logger.debug("Provider %s returned empty payload for %s", provider.__class__.__name__, symbol)
                return None
            return data
        except Exception as exc:
            logger.warning("Provider %s failed for %s: %s", provider.__class__.__name__, symbol, exc)
            return None

    def get_market_data(self, symbol: str) -> dict[str, Any]:
        """Retrieve market data using primary, falling back to secondary as needed.

        Returns the first successful payload. Raises ``RuntimeError`` if both
        providers fail.
        """
        # Try primary up to max_retries
        for attempt in range(1, self.max_retries + 1):
            result = self._call_provider(self.primary, symbol)
            if result:
                if attempt > 1:
                    logger.info("Primary provider succeeded on retry %d for %s", attempt, symbol)
                return result
            logger.debug("Retry %d/%d for primary provider %s", attempt, self.max_retries, symbol)

        # Primary exhausted – try secondary once
        logger.info("Primary provider exhausted for %s – attempting secondary %s", symbol, self.secondary.__class__.__name__)
        secondary_result = self._call_provider(self.secondary, symbol)
        if secondary_result:
            return secondary_result

        raise RuntimeError(f"Both primary and secondary providers failed for symbol {symbol}")
