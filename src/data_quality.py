"""
Data Quality Engine
Implements freshness, completeness, and consistency checks for incoming market data.
Provides a QualityReport dataclass and a DataQualityEngine for per‑symbol evaluation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """Aggregated quality metrics for a symbol's data stream."""

    symbol: str
    freshness_seconds: float
    completeness_ratio: float
    consistency_score: float
    missing_fields: list[str] = field(default_factory=list)
    out_of_range_fields: list[tuple[str, Any, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "freshness_seconds": self.freshness_seconds,
            "completeness_ratio": self.completeness_ratio,
            "consistency_score": self.consistency_score,
            "missing_fields": self.missing_fields,
            "out_of_range_fields": self.out_of_range_fields,
            "generated_at": self.generated_at.isoformat(),
        }


class DataQualityEngine:
    """Evaluates data quality for market‑data payloads.

    Expected payload format (example)::

        {
            "symbol": "EURUSD",
            "timestamp": "2026-08-12T14:30:00Z",
            "bid": 1.12345,
            "ask": 1.12355,
            "volume": 0.01,
            "extra": {...}
        }

    The engine checks:
    * **Freshness** – time delta between now and payload timestamp.
    * **Completeness** – required fields are present.
    * **Consistency** – simple sanity checks (bid < ask, non‑negative volume, reasonable ranges).
    """

    REQUIRED_FIELDS = {"symbol", "timestamp", "bid", "ask", "volume"}
    # Expected numeric ranges per field (min, max). Adjust as needed.
    FIELD_RANGES: dict[str, tuple[float, float]] = {
        "bid": (0.0, 1_000_000.0),
        "ask": (0.0, 1_000_000.0),
        "volume": (0.0, 1_000_000.0),
    }
    STALE_THRESHOLD = timedelta(seconds=5)  # data older than 5 s considered stale

    def __init__(self) -> None:
        self._last_timestamp: dict[str, datetime] = {}
        logger.info("DataQualityEngine initialized")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def evaluate(self, payload: dict[str, Any]) -> QualityReport:
        """Run all quality checks and return a :class:`QualityReport`.

        Parameters
        ----------
        payload:
            Raw market‑data dictionary. Keys must be JSON‑serialisable.
        """
        symbol = payload.get("symbol", "UNKNOWN")
        ts_str = payload.get("timestamp")
        now = datetime.now(timezone.utc)

        # ----- Freshness ---------------------------------------------------
        try:
            ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        except Exception as exc:
            logger.warning("Invalid timestamp in payload for %s: %s", symbol, exc)
            ts = now
        freshness = (now - ts).total_seconds()
        self._last_timestamp[symbol] = ts

        # ----- Completeness ------------------------------------------------
        present = set(payload.keys())
        missing = list(self.REQUIRED_FIELDS - present)
        completeness = 1.0 - len(missing) / len(self.REQUIRED_FIELDS)

        # ----- Consistency -------------------------------------------------
        consistency_score = 1.0
        out_of_range: list[tuple[str, Any, Any]] = []
        # Basic numeric sanity
        for field, (low, high) in self.FIELD_RANGES.items():
            val = payload.get(field)
            if val is None:
                continue
            if not (low <= float(val) <= high):
                out_of_range.append((field, low, high))
                consistency_score -= 0.2
        # Bid/Ask relationship
        bid = payload.get("bid")
        ask = payload.get("ask")
        if bid is not None and ask is not None and float(bid) >= float(ask):
            logger.debug("Bid >= Ask for %s (bid=%s ask=%s)", symbol, bid, ask)
            consistency_score -= 0.3
        # Volume non‑negative
        vol = payload.get("volume")
        if vol is not None and float(vol) < 0:
            consistency_score -= 0.2

        consistency_score = max(0.0, consistency_score)

        report = QualityReport(
            symbol=symbol,
            freshness_seconds=freshness,
            completeness_ratio=round(completeness, 3),
            consistency_score=round(consistency_score, 3),
            missing_fields=missing,
            out_of_range_fields=out_of_range,
        )
        logger.debug("QualityReport for %s: %s", symbol, report.as_dict())
        return report

    # ---------------------------------------------------------------------
    # Helper utilities – can be used by downstream components
    # ---------------------------------------------------------------------
    def is_fresh(self, payload: dict[str, Any]) -> bool:
        """Return ``True`` if payload timestamp is within ``STALE_THRESHOLD``.
        """
        ts_str = payload.get("timestamp")
        if not ts_str:
            return False
        try:
            ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return (datetime.now(timezone.utc) - ts) <= self.STALE_THRESHOLD

    def is_complete(self, payload: dict[str, Any]) -> bool:
        """Check that all ``REQUIRED_FIELDS`` are present.
        """
        return self.REQUIRED_FIELDS.issubset(set(payload.keys()))

    def is_consistent(self, payload: dict[str, Any]) -> bool:
        """Run lightweight consistency checks – returns ``True`` if no violations.
        """
        # Numeric range checks
        for field, (low, high) in self.FIELD_RANGES.items():
            val = payload.get(field)
            if val is None:
                continue
            try:
                if not (low <= float(val) <= high):
                    return False
            except Exception:
                return False
        # Bid/Ask
        bid = payload.get("bid")
        ask = payload.get("ask")
        if bid is not None and ask is not None:
            try:
                if float(bid) >= float(ask):
                    return False
            except Exception:
                return False
        # Volume non‑negative
        vol = payload.get("volume")
        if vol is not None:
            try:
                if float(vol) < 0:
                    return False
            except Exception:
                return False
        return True
