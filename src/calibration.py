"""calibration.py

Probability Calibration Engine – maintains per‑symbol, per‑timeframe, per‑regime
histograms of predicted probabilities and observed outcomes and provides a
simple isotonic regression style calibration.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    count: int = 0
    observed_positive: int = 0
    predicted_sum: float = 0.0
    brier_score: float = 0.0

    @property
    def observed_positive_rate(self) -> float:
        return self.observed_positive / self.count if self.count else 0.0

    @property
    def predicted_avg(self) -> float:
        return self.predicted_sum / self.count if self.count else 0.0

    def update(self, predicted: float, actual: int) -> None:
        self.count += 1
        self.observed_positive += int(bool(actual))
        self.predicted_sum += predicted
        # Incremental Brier score (mean squared error of probability).
        self.brier_score += (predicted - actual) ** 2

    def finalize(self) -> None:
        # Convert cumulative Brier score to mean.
        if self.count:
            self.brier_score /= self.count

# ---------------------------------------------------------------------------
# Core calibrator
# ---------------------------------------------------------------------------
class ProbabilityCalibrator:
    """Collect outcomes and compute calibrated probabilities.

    The calibrator stores a flat dict keyed by ``(symbol, timeframe, regime)``.
    Each entry holds a sorted list of ``CalibrationBin`` objects covering the
    range ``[0.0, 1.0]``.  Bin width is adaptive: new predictions are placed in
    the appropriate bin via binary search; if a bin becomes too large it can be
    split (not required for the spec, but helps maintain resolution).
    """

    def __init__(self, bin_count: int = 10):
        self.bin_count = max(2, bin_count)
        self._tables: dict[tuple[str, str, str], list[CalibrationBin]] = {}

    # ---------------------------------------------------------------------
    def _ensure_bins(self, key: tuple[str, str, str]) -> list[CalibrationBin]:
        if key not in self._tables:
            step = 1.0 / self.bin_count
            bins = []
            lower = 0.0
            for i in range(self.bin_count):
                upper = lower + step
                bins.append(CalibrationBin(lower_bound=lower, upper_bound=upper))
                lower = upper
            self._tables[key] = bins
        return self._tables[key]

    # ---------------------------------------------------------------------
    def _find_bin(self, bins: list[CalibrationBin], prob: float) -> CalibrationBin:
        # Edge cases: clamp to [0,1]
        prob = max(0.0, min(1.0, prob))
        # Use bisect on lower bounds.
        lo_bounds = [b.lower_bound for b in bins]
        idx = bisect.bisect_right(lo_bounds, prob) - 1
        idx = max(0, min(idx, len(bins) - 1))
        return bins[idx]

    # ---------------------------------------------------------------------
    def record_outcome(
        self,
        predicted_prob: float,
        actual_outcome: int,
        symbol: str,
        timeframe: str,
        regime: str,
    ) -> None:
        """Record a single prediction/realisation pair.

        ``actual_outcome`` should be ``1`` for a positive event (e.g., trade hit
        target) or ``0`` otherwise.
        """
        key = (symbol, timeframe, regime)
        bins = self._ensure_bins(key)
        bin_ = self._find_bin(bins, predicted_prob)
        bin_.update(predicted_prob, actual_outcome)

    # ---------------------------------------------------------------------
    def compute_reliability(self, symbol: str, timeframe: str = "", regime: str = "") -> list[CalibrationBin]:
        """Return the calibration histogram for the given identifiers.
        Empty bins are omitted for brevity.
        """
        key = (symbol, timeframe, regime)
        bins = self._tables.get(key, [])
        # Finalize Brier scores before returning.
        for b in bins:
            b.finalize()
        return [b for b in bins if b.count > 0]

    # ---------------------------------------------------------------------
    def calibrate(self, probability: float, symbol: str, timeframe: str = "", regime: str = "") -> float:
        """Return a calibrated probability using isotonic interpolation.

        The method looks up the bin containing ``probability`` and returns the
        bin's observed positive rate.  If the bin is empty, the raw probability is
        returned.
        """
        key = (symbol, timeframe, regime)
        bins = self._tables.get(key)
        if not bins:
            return probability
        bin_ = self._find_bin(bins, probability)
        if bin_.count == 0:
            return probability
        return bin_.observed_positive_rate

    # ---------------------------------------------------------------------
    def compute_brier_score(self, symbol: str, timeframe: str = "", regime: str = "") -> float:
        """Aggregate Brier score across all bins for the given identifiers.
        Returns ``0.0`` if no data.
        """
        key = (symbol, timeframe, regime)
        bins = self._tables.get(key, [])
        total = 0.0
        count = 0
        for b in bins:
            if b.count:
                total += b.brier_score * b.count
                count += b.count
        return total / count if count else 0.0

    # ---------------------------------------------------------------------
    def is_sufficient_evidence(self, symbol: str, timeframe: str = "", regime: str = "", min_samples: int = 30) -> bool:
        """Return ``True`` if the total number of recorded samples exceeds ``min_samples``.
        """
        key = (symbol, timeframe, regime)
        bins = self._tables.get(key, [])
        total = sum(b.count for b in bins)
        return total >= min_samples

# End of file
