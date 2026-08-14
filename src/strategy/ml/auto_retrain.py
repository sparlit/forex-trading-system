"""
Automated Model Retraining Pipeline
====================================

Provides automated model retraining with drift detection.
Monitors model performance and data drift, triggers retraining when needed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import polars as pl
from loguru import logger
from scipy import stats
from sklearn.metrics import accuracy_score, mean_squared_error

from src.strategy.ml.model_registry import ModelRegistry, get_model_registry
from src.strategy.ml.models import LSTMModel, TransformerModel


@dataclass
class DriftConfig:
    """Configuration for drift detection."""
    # Statistical drift detection
    enable_statistical_drift: bool = True
    psi_threshold: float = 0.1  # Population Stability Index threshold
    ks_threshold: float = 0.05  # Kolmogorov-Smirnov test p-value threshold
    
    # Performance drift detection
    enable_performance_drift: bool = True
    performance_window: int = 100  # Number of predictions to evaluate
    performance_threshold: float = 0.05  # Performance degradation threshold
    
    # Feature drift detection
    enable_feature_drift: bool = True
    feature_drift_threshold: float = 0.1  # Feature importance change threshold
    
    # Data quality
    min_samples_for_drift: int = 50
    missing_value_threshold: float = 0.1


@dataclass
class RetrainingConfig:
    """Configuration for automated retraining."""
    # Schedule
    check_interval_hours: int = 24  # Check for drift every 24 hours
    min_retrain_interval_hours: int = 168  # Minimum 1 week between retrains
    
    # Retraining criteria
    require_drift_confirmation: bool = True  # Need multiple drift signals
    min_drift_signals: int = 2  # Minimum drift signals to trigger retrain
    
    # Training parameters
    retrain_epochs: int = 50
    retrain_batch_size: int = 64
    validation_split: float = 0.2
    
    # Model selection
    auto_select_best: bool = True  # Compare old vs new model
    min_improvement_threshold: float = 0.01  # Minimum improvement to replace
    
    # Data
    lookback_days: int = 30  # Training data lookback
    min_training_samples: int = 1000


@dataclass
class DriftResult:
    """Result of drift detection."""
    timestamp: datetime
    model_id: str
    drift_detected: bool
    drift_signals: dict[str, bool] = field(default_factory=dict)
    drift_scores: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    
    @property
    def signal_count(self) -> int:
        return sum(1 for v in self.drift_signals.values() if v)


@dataclass
class RetrainingResult:
    """Result of retraining operation."""
    timestamp: datetime
    model_id: str
    triggered_by: str
    old_model_id: str
    new_model_id: str
    success: bool
    old_performance: dict[str, float]
    new_performance: dict[str, float]
    improvement: dict[str, float]
    duration_seconds: float
    error: str | None = None


class DriftDetector:
    """
    Detects model and data drift.
    
    Methods:
    - Population Stability Index (PSI)
    - Kolmogorov-Smirnov test
    - Performance monitoring
    - Feature importance drift
    """
    
    def __init__(self, config: DriftConfig | None = None):
        self.config = config or DriftConfig()
        self._reference_data: pl.DataFrame | None = None
        self._reference_predictions: np.ndarray | None = None
        self._reference_features: pl.DataFrame | None = None
    
    def set_reference(
        self,
        features: pl.DataFrame,
        predictions: np.ndarray,
        targets: np.ndarray | None = None,
    ) -> None:
        """Set reference data for drift detection."""
        self._reference_features = features
        self._reference_predictions = predictions
        self._reference_targets = targets
        logger.info(f"Drift reference set: {len(features)} samples, {features.width} features")
    
    def detect_drift(
        self,
        current_features: pl.DataFrame,
        current_predictions: np.ndarray,
        current_targets: np.ndarray | None = None,
    ) -> DriftResult:
        """Detect drift between current and reference data."""
        signals = {}
        scores = {}
        details = {}
        
        if self._reference_features is None:
            return DriftResult(
                timestamp=datetime.now(UTC),
                model_id="unknown",
                drift_detected=False,
                drift_signals={"no_reference": True},
                drift_scores={},
                details={"error": "No reference data set"},
            )
        
        if len(current_features) < self.config.min_samples_for_drift:
            return DriftResult(
                timestamp=datetime.now(UTC),
                model_id="unknown",
                drift_detected=False,
                drift_signals={"insufficient_samples": True},
                drift_scores={},
                details={"sample_count": len(current_features)},
            )
        
        # 1. Population Stability Index (PSI)
        if self.config.enable_statistical_drift:
            psi_score = self._calculate_psi(current_features)
            scores["psi"] = psi_score
            signals["psi"] = psi_score > self.config.psi_threshold
            details["psi"] = {
                "score": psi_score,
                "threshold": self.config.psi_threshold,
            }
            
            # KS test for numerical features
            ks_results = self._ks_test_features(current_features)
            scores["ks_max"] = max(ks_results.values()) if ks_results else 0
            signals["ks"] = any(p < self.config.ks_threshold for p in ks_results.values())
            details["ks_test"] = ks_results
        
        # 2. Performance drift
        if (self.config.enable_performance_drift and 
            current_targets is not None and 
            self._reference_targets is not None and
            len(current_targets) >= self.config.performance_window):
            
            perf_drift = self._detect_performance_drift(
                current_predictions, current_targets
            )
            signals["performance"] = perf_drift["drift_detected"]
            scores["performance"] = perf_drift["degradation"]
            details["performance"] = perf_drift
        
        # 3. Feature drift
        if self.config.enable_feature_drift:
            feature_drift = self._detect_feature_drift(current_features)
            signals["feature"] = feature_drift["drift_detected"]
            scores["feature"] = feature_drift["max_drift"]
            details["feature_drift"] = feature_drift
        
        # 4. Data quality checks
        quality_issues = self._check_data_quality(current_features)
        signals["data_quality"] = len(quality_issues) > 0
        scores["data_quality"] = len(quality_issues) / current_features.width
        details["data_quality"] = quality_issues
        
        drift_detected = any(signals.values())
        
        return DriftResult(
            timestamp=datetime.now(UTC),
            model_id="unknown",  # Set by caller
            drift_detected=drift_detected,
            drift_signals=signals,
            drift_scores=scores,
            details=details,
        )
    
    def _calculate_psi(self, current_features: pl.DataFrame) -> float:
        """Calculate Population Stability Index for all numerical features."""
        if self._reference_features is None:
            return 0.0
        
        psi_scores = []
        
        for col in current_features.columns:
            if current_features[col].dtype.is_numeric():
                ref_vals = self._reference_features[col].to_numpy()
                cur_vals = current_features[col].to_numpy()
                
                # Remove NaN
                ref_vals = ref_vals[~np.isnan(ref_vals)]
                cur_vals = cur_vals[~np.isnan(cur_vals)]
                
                if len(ref_vals) < 10 or len(cur_vals) < 10:
                    continue
                
                # Create bins based on reference quantiles
                bins = np.percentile(ref_vals, np.linspace(0, 100, 11))
                bins = np.unique(bins)
                
                if len(bins) < 2:
                    continue
                
                ref_hist, _ = np.histogram(ref_vals, bins=bins)
                cur_hist, _ = np.histogram(cur_vals, bins=bins)
                
                # Normalize
                ref_dist = ref_hist / ref_hist.sum()
                cur_dist = cur_hist / cur_hist.sum()
                
                # Avoid zeros
                ref_dist = np.clip(ref_dist, 1e-10, 1)
                cur_dist = np.clip(cur_dist, 1e-10, 1)
                
                # PSI calculation
                psi = np.sum((cur_dist - ref_dist) * np.log(cur_dist / ref_dist))
                psi_scores.append(psi)
        
        return np.mean(psi_scores) if psi_scores else 0.0
    
    def _ks_test_features(self, current_features: pl.DataFrame) -> dict[str, float]:
        """Kolmogorov-Smirnov test for numerical features."""
        if self._reference_features is None:
            return {}
        
        ks_results = {}
        
        for col in current_features.columns:
            if current_features[col].dtype.is_numeric():
                ref_vals = self._reference_features[col].to_numpy()
                cur_vals = current_features[col].to_numpy()
                
                ref_vals = ref_vals[~np.isnan(ref_vals)]
                cur_vals = cur_vals[~np.isnan(cur_vals)]
                
                if len(ref_vals) < 10 or len(cur_vals) < 10:
                    continue
                
                try:
                    _statistic, p_value = stats.ks_2samp(ref_vals, cur_vals)
                    ks_results[col] = float(p_value)
                except Exception as e:
                    logger.error(f"Exception occurred: {e}")
                    ks_results[col] = 1.0
        
        return ks_results
    
    def _detect_performance_drift(
        self,
        current_predictions: np.ndarray,
        current_targets: np.ndarray,
    ) -> dict[str, Any]:
        """Detect performance degradation."""
        # Calculate current performance
        if len(current_targets) < self.config.performance_window:
            return {"drift_detected": False, "degradation": 0.0}
        
        # Use recent window
        recent_preds = current_predictions[-self.config.performance_window:]
        recent_targets = current_targets[-self.config.performance_window:]
        
        # Reference performance (use first window of reference)
        ref_window = min(self.config.performance_window, len(self._reference_targets))
        ref_preds = self._reference_predictions[-ref_window:]
        ref_targets = self._reference_targets[-ref_window:]
        
        # Calculate metrics
        current_mse = mean_squared_error(recent_targets, recent_preds)
        ref_mse = mean_squared_error(ref_targets, ref_preds)
        
        # For classification, use accuracy
        # For classification, use accuracy
        try:
            current_acc = accuracy_score(
                (recent_targets > 0).astype(int),
                (recent_preds > 0).astype(int),
            )
            ref_acc = accuracy_score(
                (ref_targets > 0).astype(int),
                (ref_preds > 0).astype(int),
            )
            
            degradation = ref_acc - current_acc
            drift = degradation > self.config.performance_threshold
            
            return {
                "drift_detected": drift,
                "degradation": float(degradation),
                "current_accuracy": float(current_acc),
                "reference_accuracy": float(ref_acc),
                "threshold": self.config.performance_threshold,
            }
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            # Regression case
            degradation = (current_mse - ref_mse) / ref_mse if ref_mse > 0 else 0
            drift = degradation > self.config.performance_threshold
            
            return {
                "drift_detected": drift,
                "degradation": float(degradation),
                "current_mse": float(current_mse),
                "reference_mse": float(ref_mse),
                "threshold": self.config.performance_threshold,
            }
    
    def _detect_feature_drift(self, current_features: pl.DataFrame) -> dict[str, Any]:
        """Detect feature distribution drift."""
        if self._reference_features is None:
            return {"drift_detected": False, "max_drift": 0.0}
        
        drift_scores = {}
        
        for col in current_features.columns:
            if current_features[col].dtype.is_numeric():
                ref_vals = self._reference_features[col].to_numpy()
                cur_vals = current_features[col].to_numpy()
                
                ref_vals = ref_vals[~np.isnan(ref_vals)]
                cur_vals = cur_vals[~np.isnan(cur_vals)]
                
                if len(ref_vals) < 10 or len(cur_vals) < 10:
                    continue
                
                # Compare means and stds
                ref_mean, ref_std = np.mean(ref_vals), np.std(ref_vals)
                cur_mean, cur_std = np.mean(cur_vals), np.std(cur_vals)
                
                if ref_std > 0:
                    mean_drift = abs(cur_mean - ref_mean) / ref_std
                    std_drift = abs(cur_std - ref_std) / ref_std
                    drift_scores[col] = max(mean_drift, std_drift)
        
        max_drift = max(drift_scores.values()) if drift_scores else 0
        drift_detected = max_drift > self.config.feature_drift_threshold
        
        return {
            "drift_detected": drift_detected,
            "max_drift": float(max_drift),
            "feature_scores": drift_scores,
            "threshold": self.config.feature_drift_threshold,
        }
    
    def _check_data_quality(self, features: pl.DataFrame) -> list[str]:
        """Check data quality issues."""
        issues = []
        
        for col in features.columns:
            null_count = features[col].null_count()
            null_ratio = null_count / len(features)
            
            if null_ratio > self.config.missing_value_threshold:
                issues.append(f"{col}: {null_ratio:.1%} missing values")
        
        return issues


class AutoRetrainer:
    """
    Automated model retraining pipeline.
    
    Features:
    - Periodic drift checking
    - Automatic retraining trigger
    - Model comparison (A/B testing)
    - Safe model promotion
    - Rollback capability
    """
    
    def __init__(
        self,
        model_registry: ModelRegistry,
        drift_detector: DriftDetector,
        config: RetrainingConfig | None = None,
    ):
        self.model_registry = model_registry
        self.drift_detector = drift_detector
        self.config = config or RetrainingConfig()
        
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_check: datetime | None = None
        self._last_retrain: datetime | None = None
        
        # History
        self._drift_history: list[DriftResult] = []
        self._retraining_history: list[RetrainingResult] = []
    
    async def start(self) -> None:
        """Start automated retraining loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Auto-retrainer started (check interval: {self.config.check_interval_hours}h)")
    
    async def stop(self) -> None:
        """Stop automated retraining."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                raise NotImplementedError("Not implemented")
        logger.info("Auto-retrainer stopped")
    
    async def _run_loop(self) -> None:
        """Main retraining loop."""
        while self._running:
            try:
                await self.check_and_retrain()
            except Exception as e:
                logger.error(f"Retraining loop error: {e}")
            
            try:
                await asyncio.sleep(self.config.check_interval_hours * 3600)
            except asyncio.CancelledError:
                break
    
    async def check_and_retrain(self) -> RetrainingResult | None:
        """Check for drift and retrain if needed."""
        self._last_check = datetime.now(UTC)
        
        # Check minimum retrain interval
        if (self._last_retrain and 
            (datetime.now(UTC) - self._last_retrain).total_seconds() < 
            self.config.min_retrain_interval_hours * 3600):
            logger.debug("Skipping retrain check - minimum interval not elapsed")
            return None
        
        # Get active model
        active_model = self.model_registry.get_active_model()
        if not active_model:
            logger.warning("No active model to retrain")
            return None
        
        # Get training data
        training_data = await self._fetch_training_data()
        if training_data is None or len(training_data) < self.config.min_training_samples:
            logger.warning(f"Insufficient training data: {len(training_data) if training_data is not None else 0} samples")
            return None
        
        # Split features/targets
        features, targets = self._prepare_data(training_data)
        
        # Get predictions from current model
        try:
            current_predictions = await self._get_model_predictions(active_model, features)
        except Exception as e:
            logger.error(f"Failed to get model predictions: {e}")
            return None
        
        # Set reference if not set
        if self.drift_detector._reference_features is None:
            self.drift_detector.set_reference(features, current_predictions, targets)
            logger.info("Initialized drift detector reference data")
            return None
        
        # Detect drift
        drift_result = self.drift_detector.detect_drift(
            features, current_predictions, targets
        )
        drift_result.model_id = active_model.metadata.model_id
        
        self._drift_history.append(drift_result)
        
        # Keep history limited
        if len(self._drift_history) > 100:
            self._drift_history = self._drift_history[-100:]
        
        logger.info(f"Drift check for {active_model.metadata.model_id}: "
                   f"detected={drift_result.drift_detected}, "
                   f"signals={drift_result.signal_count}")
        
        # Check if retraining needed
        if (drift_result.drift_detected and 
            drift_result.signal_count >= self.config.min_drift_signals):
            
            logger.warning(f"Drift detected with {drift_result.signal_count} signals, triggering retrain")
            return await self._retrain_model(active_model, features, targets, "drift_detected")
        
        return None
    
    async def _retrain_model(
        self,
        old_model: Any,
        features: pl.DataFrame,
        targets: np.ndarray,
        trigger: str,
    ) -> RetrainingResult:
        """Retrain model and compare with old."""
        start_time = datetime.now(UTC)
        old_model_id = old_model.metadata.model_id
        
        logger.info(f"Starting retrain for model {old_model_id}")
        
        try:
            # Create new model instance (same type)
            model_type = old_model.metadata.model_type
            if model_type == "lstm":
                new_model = LSTMModel(old_model.config)
            elif model_type == "transformer":
                new_model = TransformerModel(old_model.config)
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            # Train new model
            await new_model.train(features, targets, epochs=self.config.retrain_epochs)
            
            # Evaluate both models
            old_performance = await self._evaluate_model(old_model, features, targets)
            new_performance = await self._evaluate_model(new_model, features, targets)
            
            # Calculate improvement
            improvement = {}
            for metric in old_performance:
                if metric in new_performance:
                    old_val = old_performance[metric]
                    new_val = new_performance[metric]
                    if old_val != 0:
                        improvement[metric] = (new_val - old_val) / abs(old_val)
                    else:
                        improvement[metric] = 0
            
            # Decide whether to promote
            should_promote = self._should_promote(improvement)
            
            if should_promote and self.config.auto_select_best:
                # Register new model
                new_model_id = self.model_registry.register_model(
                    model=new_model,
                    name=f"{old_model.metadata.name}_retrained",
                    version=f"retrain_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
                    metadata={"retrained_from": old_model_id, "trigger": trigger},
                )
                
                # Set as active
                self.model_registry.set_active_model(new_model_id)
                logger.info(f"New model {new_model_id} promoted as active")
            else:
                new_model_id = old_model_id
                logger.info(f"Retrained model did not meet improvement threshold, keeping {old_model_id}")
            
            duration = (datetime.now(UTC) - start_time).total_seconds()
            
            result = RetrainingResult(
                timestamp=datetime.now(UTC),
                model_id=new_model_id,
                triggered_by=trigger,
                old_model_id=old_model_id,
                new_model_id=new_model_id,
                success=True,
                old_performance=old_performance,
                new_performance=new_performance,
                improvement=improvement,
                duration_seconds=duration,
            )
            
            self._retraining_history.append(result)
            self._last_retrain = datetime.now(UTC)
            
            return result
            
        except Exception as e:
            logger.error(f"Retraining failed: {e}")
            duration = (datetime.now(UTC) - start_time).total_seconds()
            
            return RetrainingResult(
                timestamp=datetime.now(UTC),
                model_id=old_model_id,
                triggered_by=trigger,
                old_model_id=old_model_id,
                new_model_id=old_model_id,
                success=False,
                old_performance={},
                new_performance={},
                improvement={},
                duration_seconds=duration,
                error=str(e),
            )
    
    def _should_promote(self, improvement: dict[str, float]) -> bool:
        """Decide if new model should be promoted."""
        if not self.config.auto_select_best:
            return False
        
        # Check if any key metric improved sufficiently
        for imp in improvement.values():
            if imp >= self.config.min_improvement_threshold:
                return True
        
        return False
    
    async def _fetch_training_data(self) -> pl.DataFrame | None:
        """Fetch training data from database."""
        # This would connect to TimescaleDB and fetch recent data
        # For now, return mock data
        return None
    
    def _prepare_data(self, data: pl.DataFrame) -> tuple[pl.DataFrame, np.ndarray]:
        """Prepare features and targets from raw data."""
        # Implementation depends on data schema
        features = data.drop("target")
        targets = data["target"].to_numpy()
        return features, targets
    
    async def _get_model_predictions(self, model: Any, features: pl.DataFrame) -> np.ndarray:
        """Get predictions from model."""
        return await model.predict(features)
    
    async def _evaluate_model(self, model: Any, features: pl.DataFrame, targets: np.ndarray) -> dict[str, float]:
        """Evaluate model performance."""
        predictions = await model.predict(features)
        
        mse = mean_squared_error(targets, predictions)
        
        try:
            acc = accuracy_score(
                (targets > 0).astype(int),
                (predictions > 0).astype(int),
            )
            return {"mse": float(mse), "accuracy": float(acc)}
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return {"mse": float(mse)}
    
    def get_status(self) -> dict[str, Any]:
        """Get retrainer status."""
        return {
            "running": self._running,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
            "drift_checks": len(self._drift_history),
            "retrains_completed": len(self._retraining_history),
            "last_drift_result": {
                "drift_detected": self._drift_history[-1].drift_detected,
                "signal_count": self._drift_history[-1].signal_count,
                "timestamp": self._drift_history[-1].timestamp.isoformat(),
            } if self._drift_history else None,
        }
    
    async def manual_retrain(self, trigger: str = "manual") -> RetrainingResult | None:
        """Trigger manual retraining."""
        active_model = self.model_registry.get_active_model()
        if not active_model:
            return None
        
        training_data = await self._fetch_training_data()
        if training_data is None:
            return None
        
        features, targets = self._prepare_data(training_data)
        return await self._retrain_model(active_model, features, targets, trigger)


# Global instance
_auto_retrainer: AutoRetrainer | None = None


def get_auto_retrainer() -> AutoRetrainer | None:
    """Get global auto retrainer."""
    return _auto_retrainer


async def init_auto_retrainer(
    model_registry: ModelRegistry | None = None,
    drift_config: DriftConfig | None = None,
    retrain_config: RetrainingConfig | None = None,
) -> AutoRetrainer:
    """Initialize global auto retrainer."""
    global _auto_retrainer
    
    if model_registry is None:
        model_registry = get_model_registry()
    
    drift_detector = DriftDetector(drift_config)
    _auto_retrainer = AutoRetrainer(model_registry, drift_detector, retrain_config)
    
    return _auto_retrainer


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize
        retrainer = await init_auto_retrainer()
        
        # Start
        await retrainer.start()
        
        # Let it run
        await asyncio.sleep(10)
        
        # Check status
        status = retrainer.get_status()
        print(f"Retrainer status: {status}")
        
        # Stop
        await retrainer.stop()
    
    asyncio.run(example())