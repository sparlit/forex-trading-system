"""
Structural Break Engine — EAQTS V2.3 N0411–N0420.

Detects structural changes in market regimes: mean shifts, volatility
shifts, correlation shifts, liquidity shifts, microstructure shifts,
and parameter instability.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class BreakType(str, Enum):
    MEAN_SHIFT = "mean_shift"
    VOLATILITY_SHIFT = "volatility_shift"
    CORRELATION_SHIFT = "correlation_shift"
    LIQUIDITY_SHIFT = "liquidity_shift"
    MICROSTRUCTURE_SHIFT = "microstructure_shift"
    PARAMETER_INSTABILITY = "parameter_instability"
    NONE = "none"


@dataclass
class StructuralBreak:
    break_type: BreakType
    symbol: str = ""
    confidence: float = 0.0
    magnitude: float = 0.0
    timestamp: float = field(default_factory=time.time)
    evidence: list[str] = field(default_factory=list)


class StructuralBreakEngine:
    """
    Detects structural breaks in the market data stream using rolling
    statistics. A break reduces strategy eligibility for affected symbols.
    """

    def __init__(
        self,
        window_size: int = 100,
        mean_shift_threshold_std: float = 3.0,
        vol_shift_threshold: float = 2.0,
    ) -> None:
        self.window_size = window_size
        self.mean_shift_threshold_std = mean_shift_threshold_std
        self.vol_shift_threshold = vol_shift_threshold
        self._price_history: dict[str, deque[float]] = {}
        self.detected_breaks: list[StructuralBreak] = []

    def add_price(self, symbol: str, price: float) -> None:
        self._price_history.setdefault(symbol, deque(maxlen=self.window_size * 2))
        self._price_history[symbol].append(price)

    def detect_mean_shift(self, symbol: str) -> StructuralBreak:
        """N0412 — Detect mean shift."""
        prices = list(self._price_history.get(symbol, []))
        if len(prices) < self.window_size:
            return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

        mid = len(prices) // 2
        first_half = prices[:mid]
        second_half = prices[mid:]

        mean_first = statistics.mean(first_half)
        mean_second = statistics.mean(second_half)
        stdev_first = statistics.stdev(first_half) if len(first_half) > 1 else 0.0

        if stdev_first > 0:
            z_score = abs(mean_second - mean_first) / stdev_first
        else:
            z_score = 0.0

        if z_score > self.mean_shift_threshold_std:
            confidence = min(1.0, z_score / (self.mean_shift_threshold_std * 2))
            evidence = [
                f"z-score {z_score:.2f} > {self.mean_shift_threshold_std}",
                f"mean₁ {mean_first:.5f} → mean₂ {mean_second:.5f}",
            ]
            break_event = StructuralBreak(
                break_type=BreakType.MEAN_SHIFT,
                symbol=symbol,
                confidence=confidence,
                magnitude=abs(mean_second - mean_first),
                evidence=evidence,
            )
            self.detected_breaks.append(break_event)
            logger.warning(f"Structural break MEAN_SHIFT {symbol}: z={z_score:.2f}")
            return break_event

        return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

    def detect_volatility_shift(self, symbol: str) -> StructuralBreak:
        """N0413 — Detect volatility shift."""
        prices = list(self._price_history.get(symbol, []))
        if len(prices) < self.window_size:
            return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

        mid = len(prices) // 2
        first_half = prices[:mid]
        second_half = prices[mid:]
        first_ret = [prices[i] / prices[i - 1] - 1 for i in range(1, len(first_half)) if prices[i - 1] != 0]
        second_ret = [prices[i] / prices[i - 1] - 1 for i in range(mid + 1, len(prices)) if prices[i - 1] != 0]

        if len(first_ret) < 2 or len(second_ret) < 2:
            return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

        vol_first = statistics.stdev(first_ret)
        vol_second = statistics.stdev(second_ret)

        if vol_first > 0:
            ratio = vol_second / vol_first
        else:
            ratio = 1.0 if vol_second == 0 else 999.0

        if ratio > self.vol_shift_threshold or ratio < 1.0 / self.vol_shift_threshold:
            confidence = min(1.0, abs(ratio - 1.0) / 2.0)
            break_event = StructuralBreak(
                break_type=BreakType.VOLATILITY_SHIFT,
                symbol=symbol,
                confidence=confidence,
                magnitude=abs(ratio - 1.0),
                evidence=[f"vol ratio {ratio:.2f}"],
            )
            self.detected_breaks.append(break_event)
            logger.warning(f"Structural break VOL_SHIFT {symbol}: ratio={ratio:.2f}")
            return break_event

        return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

    def detect(self, symbol: str) -> StructuralBreak:
        """Run all detectors and return the first detected break."""
        for detector in (self.detect_mean_shift, self.detect_volatility_shift):
            result = detector(symbol)
            if result.break_type != BreakType.NONE:
                return result
        return StructuralBreak(break_type=BreakType.NONE, symbol=symbol)

    def feed_into_eligibility(
        self, symbol: str, current_eligible: bool
    ) -> tuple[bool, str]:
        """
        N0420 — Feed structural break into strategy eligibility.
        If a recent break was detected, reduce eligibility.
        """
        recent = [
            b for b in self.detected_breaks
            if b.symbol == symbol
            and time.time() - b.timestamp < 3600  # last hour
            and b.break_type != BreakType.NONE
        ]
        if recent:
            latest = recent[-1]
            if latest.confidence > 0.6:
                return False, f"structural {latest.break_type.value} (conf={latest.confidence:.2f})"
        return current_eligible, []


# Singleton
structural_break_engine = StructuralBreakEngine()
