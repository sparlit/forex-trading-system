"""
Agentic AI orchestrator for the Elite Autonomous Quantum Trading System.

The :class:`AgenticAgent` coordinates four responsibilities:

1. **Data analysis** – delegates to ``src.strategy.technical.indicators.TechnicalIndicators``.
2. **Chart pattern analysis** – delegates to
   ``src.strategy.technical.advanced_indicators.AdvancedIndicators`` and a built-in
   pattern detector for head & shoulders, double tops/bottoms, triangles, flags,
   wedges and the main candlestick formations (doji, hammer, engulfing).
3. **Trade decision** – weighs the signals produced by all available strategies
   and emits a Buy / Sell / Hold with a confidence in ``[0.0, 1.0]``.
4. **Self-monitoring and self-healing** – periodically inspects the agent's
   own sub-components, restarts any that have failed and records each
   remediation step in ``self.health_log``.

Heavy work is dispatched through ``multiprocessing.Pool`` and gathered with
``asyncio``. A pure-Python fallback is used when ``concurrent.futures.ProcessPool``
workers cannot be spawned (e.g. on Windows inside a Streamlit re-run where the
``__main__`` guard is missing). The optional Rust acceleration layer
``agentic_core`` (PyO3 + numpy) is loaded opportunistically; when the
compiled extension is missing everything still works via the pure-Python path.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
import time
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------- #
# Optional / soft imports
# ----------------------------------------------------------------------------- #
try:  # pragma: no cover - optional native acceleration
    from src.ai import agentic_core  # type: ignore

    _HAS_RUST_CORE = True
except Exception:  # pragma: no cover
    agentic_core = None  # type: ignore[assignment]
    _HAS_RUST_CORE = False

try:  # TechnicalIndicators (Numba-accelerated)
    from src.strategy.technical.indicators import TechnicalIndicators  # type: ignore

    _HAS_TECH = True
except Exception:  # pragma: no cover
    TechnicalIndicators = None  # type: ignore[assignment,misc]
    _HAS_TECH = False

try:  # AdvancedIndicators (pure numpy / pandas)
    from src.strategy.technical.advanced_indicators import AdvancedIndicators  # type: ignore

    _HAS_ADV = True
except Exception:  # pragma: no cover
    AdvancedIndicators = None  # type: ignore[assignment,misc]
    _HAS_ADV = False

try:  # CandlestickPatterns – ships with TechnicalIndicators
    from src.strategy.technical.indicators import CandlestickPatterns  # type: ignore

    _HAS_CDL = True
except Exception:  # pragma: no cover
    CandlestickPatterns = None  # type: ignore[assignment,misc]
    _HAS_CDL = False

try:  # ProcessPoolExecutor for parallel CPU work
    from concurrent.futures import ProcessPoolExecutor

    _HAS_PPE = True
except Exception:  # pragma: no cover
    _HAS_PPE = False


# ============================================================================ #
# Enums & dataclasses
# ============================================================================ #


class DecisionAction(str, Enum):
    """High-level action emitted by the decision engine."""

    BUY = "Buy"
    SELL = "Sell"
    HOLD = "Hold"


class ComponentState(str, Enum):
    """Lifecycle state of a managed sub-component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class AnalysisResult:
    """Outcome of one analysis module."""

    analysis_type: str
    result: str
    confidence: float
    duration_ms: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartPattern:
    """A detected chart formation."""

    pattern: str
    direction: str  # "bullish" | "bearish" | "neutral"
    confidence: float
    description: str
    indices: list[int] = field(default_factory=list)


@dataclass
class AgentDecision:
    """Final aggregated decision."""

    action: DecisionAction
    confidence: float
    contributing_signals: list[AnalysisResult]
    chart_patterns: list[ChartPattern]
    parallel_metrics: dict[str, float]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": round(self.confidence, 4),
            "contributing_signals": [
                {
                    "analysis_type": s.analysis_type,
                    "result": s.result,
                    "confidence": round(s.confidence, 4),
                    "duration_ms": round(s.duration_ms, 2),
                }
                for s in self.contributing_signals
            ],
            "chart_patterns": [
                {
                    "pattern": p.pattern,
                    "direction": p.direction,
                    "confidence": round(p.confidence, 4),
                    "description": p.description,
                }
                for p in self.chart_patterns
            ],
            "parallel_metrics": {k: round(v, 4) for k, v in self.parallel_metrics.items()},
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================================ #
# Worker functions (must be module-level for pickling under multiprocessing)
# ============================================================================ #


def _worker_technical_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker: compute a bundle of classic technical indicators on ``close``."""

    t0 = time.perf_counter()
    close = np.asarray(payload["close"], dtype=float)
    rsi_period = int(payload.get("rsi_period", 14))
    bb_period = int(payload.get("bb_period", 20))
    macd_fast = int(payload.get("macd_fast", 12))
    macd_slow = int(payload.get("macd_slow", 26))
    macd_signal = int(payload.get("macd_signal", 9))

    out: dict[str, Any] = {}
    if _HAS_TECH and TechnicalIndicators is not None:
        try:
            rsi = TechnicalIndicators.rsi_numba(close, rsi_period)
            mid, upper, lower = TechnicalIndicators.bollinger_bands_numba(close, bb_period)
            macd, signal, hist = TechnicalIndicators.macd_numba(
                close, macd_fast, macd_slow, macd_signal,
            )
            out["rsi"] = _safe_last(rsi)
            out["bb_mid"] = _safe_last(mid)
            out["bb_upper"] = _safe_last(upper)
            out["bb_lower"] = _safe_last(lower)
            out["macd"] = _safe_last(macd)
            out["macd_signal"] = _safe_last(signal)
            out["macd_hist"] = _safe_last(hist)
        except Exception as exc:  # pragma: no cover
            out["error"] = f"{type(exc).__name__}: {exc}"
    else:
        # Pure-Python fallback so workers don't crash when numba isn't available.
        out["rsi"] = _pure_rsi(close, rsi_period)
        sma = _pure_sma(close, bb_period)
        std = _pure_std(close, bb_period)
        out["bb_mid"] = sma
        out["bb_upper"] = sma + 2.0 * std
        out["bb_lower"] = sma - 2.0 * std
        out["macd"] = _pure_ema(close, macd_fast) - _pure_ema(close, macd_slow)

    out["duration_ms"] = (time.perf_counter() - t0) * 1000.0
    out["worker"] = "technical"
    return out


def _worker_advanced_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker: compute advanced indicators (supertrend, adx, ichimoku…)."""

    t0 = time.perf_counter()
    high = np.asarray(payload["high"], dtype=float)
    low = np.asarray(payload["low"], dtype=float)
    close = np.asarray(payload["close"], dtype=float)
    out: dict[str, Any] = {}
    if _HAS_ADV and AdvancedIndicators is not None:
        try:
            out["supertrend"] = _safe_last(AdvancedIndicators.supertrend(high, low, close))
            adx, plus_di, minus_di = AdvancedIndicators.adx(high, low, close)
            out["adx"] = _safe_last(adx)
            out["plus_di"] = _safe_last(plus_di)
            out["minus_di"] = _safe_last(minus_di)
            out["vwap"] = _safe_last(AdvancedIndicators.vwap(high, low, close, np.ones_like(close)))
        except Exception as exc:  # pragma: no cover
            out["error"] = f"{type(exc).__name__}: {exc}"
    else:
        # Cheap fallback signals that still drive a Buy / Sell / Hold.
        rng = float(np.mean(high - low)) if len(high) else 0.0
        out["supertrend"] = float(close[-1]) - rng if len(close) else 0.0
        out["adx"] = 25.0
        out["vwap"] = float(np.mean(close)) if len(close) else 0.0
    out["duration_ms"] = (time.perf_counter() - t0) * 1000.0
    out["worker"] = "advanced"
    return out


def _worker_pattern_detection(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Worker: scan OHLC for chart & candlestick patterns (pure Python)."""

    t0 = time.perf_counter()
    o = np.asarray(payload["open"], dtype=float)
    h = np.asarray(payload["high"], dtype=float)
    l = np.asarray(payload["low"], dtype=float)
    c = np.asarray(payload["close"], dtype=float)
    patterns: list[dict[str, Any]] = []

    # Candlestick patterns
    if _HAS_CDL and CandlestickPatterns is not None:
        try:
            doji = CandlestickPatterns.doji(o, h, l, c)
            hammer = CandlestickPatterns.hammer(o, h, l, c)
            eng = CandlestickPatterns.engulfing(o, c)
            for i in range(len(c)):
                if doji[i] and not math.isnan(doji[i]) and doji[i] != 0:
                    patterns.append({
                        "pattern": "doji",
                        "direction": "neutral",
                        "confidence": 0.55,
                        "index": int(i),
                        "description": "Doji – indecision; watch for reversal confirmation.",
                    })
                if hammer[i] and not math.isnan(hammer[i]) and hammer[i] != 0:
                    patterns.append({
                        "pattern": "hammer",
                        "direction": "bullish",
                        "confidence": 0.7,
                        "index": int(i),
                        "description": "Hammer candle – potential bullish reversal.",
                    })
                if eng[i] and not math.isnan(eng[i]) and eng[i] != 0:
                    direction = "bullish" if eng[i] > 0 else "bearish"
                    patterns.append({
                        "pattern": "engulfing",
                        "direction": direction,
                        "confidence": 0.75,
                        "index": int(i),
                        "description": f"{direction.title()} engulfing – momentum shift.",
                    })
        except Exception as exc:  # pragma: no cover
            logger.warning("CandlestickPatterns failed: %s", exc)

    # Chart patterns (pure-python pivot-based heuristics)
    patterns.extend(_detect_chart_patterns(o, h, l, c))

    # Optional Rust acceleration – delegate pattern detection for speed when
    # the compiled extension is available. Falls back silently otherwise.
    if _HAS_RUST_CORE and agentic_core is not None and hasattr(
        agentic_core, "detect_chart_patterns_fast",
    ):
        try:
            rust_hits = agentic_core.detect_chart_patterns_fast(o, h, l, c)
            patterns.extend(rust_hits)
        except Exception as exc:  # pragma: no cover
            logger.debug("Rust pattern detector failed: %s", exc)

    elapsed = (time.perf_counter() - t0) * 1000.0
    for p in patterns:
        p.setdefault("_duration_ms", round(elapsed, 2))
    return patterns


def _worker_monte_carlo(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker: parallel Monte-Carlo simulation of forward returns."""

    t0 = time.perf_counter()
    close = np.asarray(payload["close"], dtype=float)
    n_sims = int(payload.get("n_sims", 500))
    horizon = int(payload.get("horizon", 50))
    seed = int(payload.get("seed", 42))

    if len(close) < 2:
        return {"mean_return": 0.0, "std_return": 0.0, "duration_ms": 0.0}

    # If Rust is available delegate; otherwise pure numpy.
    if _HAS_RUST_CORE and agentic_core is not None and hasattr(agentic_core, "monte_carlo_parallel"):
        try:
            result = agentic_core.monte_carlo_parallel(
                close, n_sims, horizon, seed,
            )
            result["duration_ms"] = (time.perf_counter() - t0) * 1000.0
            return result
        except Exception as exc:  # pragma: no cover
            logger.debug("Rust monte_carlo failed: %s", exc)

    rng = np.random.default_rng(seed)
    rets = np.diff(np.log(close))
    mu, sigma = float(np.mean(rets)), float(np.std(rets)) + 1e-12
    sims = rng.normal(loc=mu, scale=sigma, size=(n_sims, horizon))
    equity = np.exp(np.cumsum(sims, axis=1)) - 1.0
    final = equity[:, -1]
    return {
        "mean_return": float(np.mean(final)),
        "std_return": float(np.std(final)),
        "p05": float(np.percentile(final, 5)),
        "p95": float(np.percentile(final, 95)),
        "duration_ms": (time.perf_counter() - t0) * 1000.0,
    }


# ----------------------------------------------------------------------------- #
# Pure-Python helpers used both inline and inside worker processes
# ----------------------------------------------------------------------------- #


def _safe_last(arr: Any) -> float:
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return 0.0
    val = a[-1]
    try:
        return float(val) if not (isinstance(val, float) and math.isnan(val)) else 0.0
    except Exception:  # pragma: no cover
        return 0.0


def _pure_sma(x: np.ndarray, period: int) -> float:
    if len(x) < period:
        return float(np.mean(x)) if len(x) else 0.0
    return float(np.mean(x[-period:]))


def _pure_std(x: np.ndarray, period: int) -> float:
    if len(x) < period:
        return float(np.std(x)) if len(x) else 0.0
    return float(np.std(x[-period:]))


def _pure_ema(x: np.ndarray, period: int) -> float:
    if len(x) == 0:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    val = float(x[0])
    for v in x[1:]:
        val = alpha * float(v) + (1.0 - alpha) * val
    return val


def _pure_rsi(x: np.ndarray, period: int = 14) -> float:
    if len(x) < period + 1:
        return 50.0
    diff = np.diff(x)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:])) + 1e-12
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _pivots(arr: np.ndarray, order: int = 3) -> tuple[list[int], list[int]]:
    """Return (high_pivot_indices, low_pivot_indices)."""

    highs: list[int] = []
    lows: list[int] = []
    n = len(arr)
    for i in range(order, n - order):
        window = arr[i - order: i + order + 1]
        if arr[i] == max(window):
            highs.append(i)
        if arr[i] == min(window):
            lows.append(i)
    return highs, lows


def _detect_chart_patterns(
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
) -> list[dict[str, Any]]:
    """Pivot-based heuristics for head&shoulders, double tops/bottoms, etc."""

    out: list[dict[str, Any]] = []
    if len(c) < 20:
        return out
    highs, lows = _pivots(h, order=3)
    lows_c, _ = _pivots(c, order=3)  # used for divergence

    # --- Double top / bottom on closing-price pivots ------------------------- #
    if len(lows_c) >= 2:
        a, b = lows_c[-2], lows_c[-1]
        if abs(c[a] - c[b]) / max(abs(c[a]), 1e-12) < 0.01:
            out.append({
                "pattern": "double_top",
                "direction": "bearish",
                "confidence": 0.6,
                "index": b,
                "description": "Double top – two similar highs suggest resistance.",
            })
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if abs(h[a] - h[b]) / max(abs(h[a]), 1e-12) < 0.01:
            out.append({
                "pattern": "double_bottom",
                "direction": "bullish",
                "confidence": 0.6,
                "index": b,
                "description": "Double bottom – two similar lows suggest support.",
            })

    # --- Head & shoulders ----------------------------------------------------- #
    if len(highs) >= 3:
        a, b, d = highs[-3], highs[-2], highs[-1]
        if h[b] > h[a] and h[b] > h[d] and abs(h[a] - h[d]) / max(abs(h[a]), 1e-12) < 0.03:
            out.append({
                "pattern": "head_and_shoulders",
                "direction": "bearish",
                "confidence": 0.7,
                "index": d,
                "description": "Head & shoulders – bearish reversal pattern.",
            })
    if len(lows) >= 3:
        a, b, d = lows[-3], lows[-2], lows[-1]
        if l[b] < l[a] and l[b] < l[d] and abs(l[a] - l[d]) / max(abs(l[a]), 1e-12) < 0.03:
            out.append({
                "pattern": "inverse_head_and_shoulders",
                "direction": "bullish",
                "confidence": 0.7,
                "index": d,
                "description": "Inverse H&S – bullish reversal pattern.",
            })

    # --- Triangles (symmetrical / ascending / descending) --------------------- #
    if len(highs) >= 3 and len(lows) >= 3:
        upper = [h[i] for i in highs[-3:]]
        lower = [l[i] for i in lows[-3:]]
        if upper[0] > upper[1] > upper[2] and lower[0] < lower[1] < lower[2]:
            out.append({
                "pattern": "symmetrical_triangle",
                "direction": "neutral",
                "confidence": 0.55,
                "index": highs[-1],
                "description": "Symmetrical triangle – breakout imminent.",
            })
        elif upper[0] < upper[1] < upper[2] and lower[0] < lower[1] < lower[2]:
            out.append({
                "pattern": "ascending_triangle",
                "direction": "bullish",
                "confidence": 0.6,
                "index": highs[-1],
                "description": "Ascending triangle – bullish continuation.",
            })
        elif upper[0] > upper[1] > upper[2] and lower[0] > lower[1] > lower[2]:
            out.append({
                "pattern": "descending_triangle",
                "direction": "bearish",
                "confidence": 0.6,
                "index": highs[-1],
                "description": "Descending triangle – bearish continuation.",
            })

    # --- Flags / wedges (slope of last 10 highs) ------------------------------ #
    if len(highs) >= 5:
        recent_h = [h[i] for i in highs[-5:]]
        recent_l = [l[i] for i in lows[-5:]] if len(lows) >= 5 else recent_h
        slope_h = recent_h[-1] - recent_h[0]
        slope_l = recent_l[-1] - recent_l[0]
        if abs(slope_h) < 0.001 * max(abs(recent_h[-1]), 1e-12):
            out.append({
                "pattern": "flag",
                "direction": "bullish" if c[-1] > c[-len(c) // 2] else "bearish",
                "confidence": 0.5,
                "index": highs[-1],
                "description": "Flag consolidation against prevailing trend.",
            })
        if slope_h < 0 < slope_l:
            out.append({
                "pattern": "falling_wedge",
                "direction": "bullish",
                "confidence": 0.55,
                "index": highs[-1],
                "description": "Falling wedge – typically bullish reversal.",
            })
        elif slope_h > 0 > slope_l:
            out.append({
                "pattern": "rising_wedge",
                "direction": "bearish",
                "confidence": 0.55,
                "index": highs[-1],
                "description": "Rising wedge – typically bearish reversal.",
            })

    return out


# ============================================================================ #
# Decision engine
# ============================================================================ #


class DecisionEngine:
    """
    Combines numeric indicator scores and chart-pattern votes into a single
    Buy / Sell / Hold decision.

    Each contribution is mapped to a polarity in ``{-1, 0, +1}`` and weighted
    by its confidence. The aggregate score is clipped to ``[-1, +1]`` and then
    compared against ``buy_threshold`` / ``sell_threshold`` to choose the
    action; the resulting confidence is the absolute aggregate mapped back to
    ``[0.0, 1.0]``.
    """

    def __init__(
        self,
        buy_threshold: float = 0.25,
        sell_threshold: float = -0.25,
        min_confidence: float = 0.15,
    ) -> None:
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)
        self.min_confidence = float(min_confidence)

    # ------------------------------------------------------------------ public

    def decide(
        self,
        tech: dict[str, Any],
        adv: dict[str, Any],
        patterns: list[dict[str, Any]],
        mc: dict[str, Any],
    ) -> tuple[DecisionAction, float, list[AnalysisResult]]:
        signals: list[AnalysisResult] = []

        polarity, confidence = self._score_technical(tech)
        signals.append(AnalysisResult(
            "technical", self._label(polarity), confidence, tech.get("duration_ms", 0.0),
        ))

        polarity_a, confidence_a = self._score_advanced(adv)
        signals.append(AnalysisResult(
            "advanced", self._label(polarity_a), confidence_a, adv.get("duration_ms", 0.0),
        ))

        polarity_p, confidence_p = self._score_patterns(patterns)
        signals.append(AnalysisResult(
            "patterns", self._label(polarity_p), confidence_p, 0.0,
            detail={"count": len(patterns)},
        ))

        polarity_m, confidence_m = self._score_montecarlo(mc)
        signals.append(AnalysisResult(
            "monte_carlo", self._label(polarity_m), confidence_m, mc.get("duration_ms", 0.0),
        ))

        weights = [0.30, 0.25, 0.25, 0.20]
        score = (
            polarity * confidence * weights[0]
            + polarity_a * confidence_a * weights[1]
            + polarity_p * confidence_p * weights[2]
            + polarity_m * confidence_m * weights[3]
        )
        score = max(-1.0, min(1.0, score))

        if score >= self.buy_threshold:
            action = DecisionAction.BUY
        elif score <= self.sell_threshold:
            action = DecisionAction.SELL
        else:
            action = DecisionAction.HOLD

        confidence_out = abs(score)
        if confidence_out < self.min_confidence:
            action = DecisionAction.HOLD
            confidence_out = max(confidence_out, 0.05)
        return action, confidence_out, signals

    # --------------------------------------------------------------- scoring

    @staticmethod
    def _score_technical(tech: dict[str, Any]) -> tuple[int, float]:
        if "error" in tech:
            return 0, 0.1
        rsi = float(tech.get("rsi", 50.0))
        macd_hist = float(tech.get("macd_hist", 0.0))
        price = float(tech.get("bb_mid", 0.0))
        upper = float(tech.get("bb_upper", 0.0))
        lower = float(tech.get("bb_lower", 0.0))

        polarity = 0
        if rsi < 30:
            polarity += 1
        elif rsi > 70:
            polarity -= 1
        if macd_hist > 0:
            polarity += 1
        elif macd_hist < 0:
            polarity -= 1
        if price and upper and price >= upper * 0.999:
            polarity -= 1
        if price and lower and price <= lower * 1.001:
            polarity += 1
        polarity = max(-1, min(1, polarity))
        confidence = min(1.0, abs(rsi - 50.0) / 50.0 + min(1.0, abs(macd_hist) * 100.0))
        return polarity, max(0.1, confidence)

    @staticmethod
    def _score_advanced(adv: dict[str, Any]) -> tuple[int, float]:
        if "error" in adv:
            return 0, 0.1
        adx = float(adv.get("adx", 25.0))
        plus_di = float(adv.get("plus_di", 25.0))
        minus_di = float(adv.get("minus_di", 25.0))
        polarity = 0
        if plus_di > minus_di and adx > 20:
            polarity = 1
        elif minus_di > plus_di and adx > 20:
            polarity = -1
        confidence = max(0.1, min(1.0, adx / 50.0))
        return polarity, confidence

    @staticmethod
    def _score_patterns(patterns: Iterable[dict[str, Any]]) -> tuple[int, float]:
        votes = {"bullish": 0, "bearish": 0, "neutral": 0}
        for p in patterns:
            d = p.get("direction", "neutral")
            if d in votes:
                votes[d] += float(p.get("confidence", 0.5))
        net = votes["bullish"] - votes["bearish"]
        polarity = 0
        if net > 0.2:
            polarity = 1
        elif net < -0.2:
            polarity = -1
        confidence = min(1.0, abs(net))
        return polarity, max(0.1, confidence)

    @staticmethod
    def _score_montecarlo(mc: dict[str, Any]) -> tuple[int, float]:
        mean = float(mc.get("mean_return", 0.0))
        std = float(mc.get("std_return", 0.0)) + 1e-9
        polarity = 0
        if mean > 0.005:
            polarity = 1
        elif mean < -0.005:
            polarity = -1
        confidence = min(1.0, abs(mean) / max(std, 0.01))
        return polarity, max(0.1, confidence)

    @staticmethod
    def _label(polarity: int) -> str:
        return {1: "bullish", -1: "bearish", 0: "neutral"}[polarity]


# ============================================================================ #
# AgenticAgent
# ============================================================================ #


class AgenticAgent:
    """
    High-level orchestrator that runs a parallel analysis cycle and emits a
    Buy / Sell / Hold decision. Self-heals by tracking component health and
    re-creating anything that has raised an exception.
    """

    DEFAULT_COMPONENTS: tuple[str, ...] = (
        "technical_analyzer",
        "advanced_analyzer",
        "pattern_detector",
        "monte_carlo",
        "decision_engine",
    )

    def __init__(
        self,
        name: str = "agentic-ai",
        workers: int | None = None,
        max_workers: int = 4,
        decision_engine: DecisionEngine | None = None,
    ) -> None:
        self.name = name
        self.workers = workers or max(1, min(max_workers, (os.cpu_count() or 2)))
        self.decision_engine = decision_engine or DecisionEngine()

        self.status: ComponentState = ComponentState.HEALTHY
        self.last_cycle_at: datetime | None = None
        self.last_decision: AgentDecision | None = None
        self.health_log: deque[dict[str, Any]] = deque(maxlen=200)

        self._component_state: dict[str, ComponentState] = {
            c: ComponentState.HEALTHY for c in self.DEFAULT_COMPONENTS
        }
        self._cycle_count = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ public

    async def run_analysis_cycle(
        self,
        market_data: pd.DataFrame | dict[str, Sequence[float]] | None = None,
    ) -> dict[str, Any]:
        """
        Run every analysis module in parallel and return the resulting decision.

        The returned dict always contains ``action``, ``confidence``,
        ``analysis_breakdown``, ``chart_patterns``, ``parallel_metrics`` and
        ``timestamp``; it can be fed directly into a Streamlit dashboard.
        """

        async with self._lock:
            self._cycle_count += 1
            cycle_id = self._cycle_count
            self.status = ComponentState.RUNNING if hasattr(
                ComponentState, "RUNNING",
            ) else ComponentState.HEALTHY

            payload = self._normalise_payload(market_data)
            if payload is None:
                msg = "No market data supplied and default sample unavailable."
                logger.warning(msg)
                self.status = ComponentState.DEGRADED
                return {
                    "action": DecisionAction.HOLD.value,
                    "confidence": 0.0,
                    "analysis_breakdown": [],
                    "chart_patterns": [],
                    "parallel_metrics": {"workers": 0, "total_ms": 0.0, "speedup": 1.0},
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": msg,
                }

            try:
                tech, adv, patterns, mc, parallel_metrics = await self._run_parallel(payload)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Parallel analysis failed")
                self._record_health("orchestrator", ComponentState.FAILED, str(exc))
                self.status = ComponentState.DEGRADED
                tech, adv, patterns, mc = {}, {}, [], {}
                parallel_metrics = {
                    "workers": 0, "total_ms": 0.0, "serial_ms": 0.0, "speedup": 1.0,
                }

            action, confidence, breakdown = self.decision_engine.decide(
                tech, adv, patterns, mc,
            )

            chart_patterns = [ChartPattern(**self._pattern_kwargs(p)) for p in patterns]
            decision = AgentDecision(
                action=action,
                confidence=float(confidence),
                contributing_signals=breakdown,
                chart_patterns=chart_patterns,
                parallel_metrics=parallel_metrics,
            )
            self.last_decision = decision
            self.last_cycle_at = datetime.now(UTC)
            self.status = ComponentState.HEALTHY
            self._record_health(
                "cycle", ComponentState.HEALTHY,
                f"Cycle {cycle_id} finished in {parallel_metrics['total_ms']:.1f} ms",
            )
            return decision.to_dict()

    async def analyze_chart_patterns(
        self, market_data: pd.DataFrame | dict[str, Sequence[float]],
    ) -> list[dict[str, Any]]:
        """Detect chart and candlestick patterns. Pure-python, safe fallback."""

        payload = self._normalise_payload(market_data)
        if payload is None:
            return []
        try:
            if self._can_use_processes():
                loop = asyncio.get_running_loop()
                with ProcessPoolExecutor(max_workers=1) as ex:
                    patterns = await loop.run_in_executor(
                        ex, _worker_pattern_detection, payload,
                    )
            else:
                patterns = await asyncio.to_thread(_worker_pattern_detection, payload)
            return [self._pattern_kwargs(p) for p in patterns]
        except Exception as exc:  # pragma: no cover
            logger.exception("Pattern analysis failed")
            self._record_health("pattern_detector", ComponentState.FAILED, str(exc))
            return []

    async def self_heal(self) -> dict[str, Any]:
        """
        Inspect every component, restart failed ones, and return a summary.

        A "restart" here means resetting the in-process state – the lightweight
        subprocess pool is rebuilt lazily on the next ``run_analysis_cycle``.
        """

        healed: list[str] = []
        still_failing: list[str] = []
        for component, state in list(self._component_state.items()):
            if state in (ComponentState.FAILED, ComponentState.DEGRADED):
                try:
                    self._component_state[component] = ComponentState.RESTARTING
                    self._restart_component(component)
                    self._component_state[component] = ComponentState.HEALTHY
                    healed.append(component)
                    self._record_health(
                        component, ComponentState.HEALTHY, "restarted by self_heal()",
                    )
                except Exception as exc:  # pragma: no cover
                    self._component_state[component] = ComponentState.FAILED
                    still_failing.append(component)
                    self._record_health(
                        component, ComponentState.FAILED,
                        f"restart failed: {exc}",
                    )

        if still_failing:
            self.status = ComponentState.DEGRADED
        elif healed:
            self.status = ComponentState.HEALTHY

        return {
            "healed": healed,
            "still_failing": still_failing,
            "component_states": {
                k: v.value for k, v in self._component_state.items()
            },
            "agent_status": self.status.value,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # --------------------------------------------------------------- internal

    def _restart_component(self, component: str) -> None:
        """Lightweight restart hook – override in subclasses for real restart."""

        if component == "decision_engine":
            self.decision_engine = DecisionEngine()
        # Other components are stateless functions, so resetting their flag
        # is enough to mark them healthy.

    async def _run_parallel(
        self, payload: dict[str, np.ndarray],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, float]]:
        """Run all four worker analyses concurrently."""

        serial_estimate = sum(_serial_cost(p) for p in (
            payload["close"], payload["high"], payload["low"],
            payload["close"],  # monte-carlo again
        ))

        if self._can_use_processes():
            tech, adv, patterns, mc, metrics = await self._run_via_processpool(payload)
        else:
            tech, adv, patterns, mc, metrics = await self._run_via_threads(payload)

        metrics["serial_ms"] = float(serial_estimate)
        if metrics["total_ms"] > 0:
            metrics["speedup"] = float(metrics["serial_ms"]) / max(metrics["total_ms"], 1e-6)
        else:
            metrics["speedup"] = 1.0
        metrics["workers"] = float(self.workers)
        metrics["backend"] = "process" if self._can_use_processes() else "thread"
        return tech, adv, patterns, mc, metrics

    async def _run_via_threads(
        self, payload: dict[str, np.ndarray],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, float]]:
        t0 = time.perf_counter()
        tech, adv, patterns, mc = await asyncio.gather(
            asyncio.to_thread(_worker_technical_analysis, payload),
            asyncio.to_thread(_worker_advanced_analysis, payload),
            asyncio.to_thread(_worker_pattern_detection, payload),
            asyncio.to_thread(_worker_monte_carlo, payload),
        )
        total_ms = (time.perf_counter() - t0) * 1000.0
        return tech, adv, patterns, mc, {"total_ms": total_ms}

    async def _run_via_processpool(
        self, payload: dict[str, np.ndarray],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, float]]:
        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:
            with ProcessPoolExecutor(max_workers=self.workers) as ex:
                tech, adv, patterns, mc = await asyncio.gather(
                    loop.run_in_executor(ex, _worker_technical_analysis, payload),
                    loop.run_in_executor(ex, _worker_advanced_analysis, payload),
                    loop.run_in_executor(ex, _worker_pattern_detection, payload),
                    loop.run_in_executor(ex, _worker_monte_carlo, payload),
                )
        except (RuntimeError, OSError) as exc:
            # Pickling can fail on Windows when running inside Streamlit.
            logger.warning("ProcessPool unavailable (%s); falling back to threads.", exc)
            self._component_state["process_pool"] = ComponentState.DEGRADED
            return await self._run_via_threads(payload)
        total_ms = (time.perf_counter() - t0) * 1000.0
        return tech, adv, patterns, mc, {"total_ms": total_ms}

    # -------------------------------------------------------------- utilities

    @staticmethod
    def _can_use_processes() -> bool:
        return bool(_HAS_PPE) and sys.platform != "win32" or __name__ == "__main__"

    def _normalise_payload(
        self, market_data: pd.DataFrame | dict[str, Sequence[float]] | None,
    ) -> dict[str, np.ndarray] | None:
        if market_data is None:
            return _synthetic_payload()
        if isinstance(market_data, pd.DataFrame):
            try:
                return {
                    "open": np.asarray(market_data["open"], dtype=float),
                    "high": np.asarray(market_data["high"], dtype=float),
                    "low": np.asarray(market_data["low"], dtype=float),
                    "close": np.asarray(market_data["close"], dtype=float),
                }
            except KeyError as exc:
                logger.warning("Market DataFrame missing required column: %s", exc)
                return None
        if isinstance(market_data, dict):
            try:
                return {
                    "open": np.asarray(market_data["open"], dtype=float),
                    "high": np.asarray(market_data["high"], dtype=float),
                    "low": np.asarray(market_data["low"], dtype=float),
                    "close": np.asarray(market_data["close"], dtype=float),
                }
            except KeyError as exc:
                logger.warning("Market dict missing key: %s", exc)
                return None
        return None

    @staticmethod
    def _pattern_kwargs(p: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": str(p.get("pattern", "unknown")),
            "direction": str(p.get("direction", "neutral")),
            "confidence": float(p.get("confidence", 0.5)),
            "description": str(p.get("description", "")),
            "indices": [int(p["index"])] if "index" in p else [],
        }

    def _record_health(self, component: str, state: ComponentState, note: str) -> None:
        self._component_state[component] = state
        self.health_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "component": component,
            "state": state.value,
            "note": note[:240],
        })


# ----------------------------------------------------------------------------- #
# Helpers shared between this module and the dashboard tab
# ----------------------------------------------------------------------------- #


def _synthetic_payload(n: int = 240, seed: int = 7) -> dict[str, np.ndarray]:
    """Generate a deterministic OHLC sample – never raises."""

    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, 0.001, size=n)
    close = 1.1000 * np.exp(np.cumsum(rets))
    spread = np.abs(rng.normal(0.0008, 0.0002, size=n))
    open_ = np.concatenate([[close[0]], close[:-1] + rng.normal(0, 0.0003, n - 1)])
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def _serial_cost(arr: np.ndarray) -> float:
    """Rough serial-equivalent cost in ms – 1 µs per element, capped."""

    return float(min(50.0, max(1.0, len(arr) * 1e-3)))


# ----------------------------------------------------------------------------- #
# Demo / smoke-test entry-point
# ----------------------------------------------------------------------------- #


async def _demo() -> dict[str, Any]:  # pragma: no cover
    agent = AgenticAgent(name="demo")
    decision = await agent.run_analysis_cycle()
    print(json.dumps(decision, indent=2))
    return decision


if __name__ == "__main__":  # pragma: no cover
    import json
    asyncio.run(_demo())
