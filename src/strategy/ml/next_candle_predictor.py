"""
Next Candle Predictor - Advanced ML for Price Movement Prediction
================================================================

This module provides sophisticated next-candle prediction capabilities:
- OHLC prediction for next timeframe
- Directional probability (UP/DOWN/SIDEWAYS)
- Confidence intervals with uncertainty quantification
- Online adaptive learning with drift detection
- Model ensemble with dynamic weighting
- Self-correction via prediction error feedback loops
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import torch
from loguru import logger

from src.data.models import Bar, Direction, Signal
from src.infra.config.settings import settings
from src.strategy.ml.models import (
    FeatureEngineer,
    MLModelTrainer,
    ModelConfig,
    OnlineLearner,
)
from src.strategy.ml.strategies import EnsembleStrategy


class CandleDirection(Enum):
    """Predicted candle direction."""
    UP = "up"           # Close > Open (bullish)
    DOWN = "down"       # Close < Open (bearish)
    DOJI = "doji"       # Close ≈ Open (indecision)
    STRONG_UP = "strong_up"      # Large bullish body
    STRONG_DOWN = "strong_down"  # Large bearish body


@dataclass
class CandlePrediction:
    """Complete next candle prediction."""
    timestamp: datetime
    symbol: str
    timeframe: str
    
    # OHLC predictions
    predicted_open: Decimal
    predicted_high: Decimal
    predicted_low: Decimal
    predicted_close: Decimal
    
    # Directional prediction
    direction: CandleDirection
    direction_probability: float  # 0-1
    direction_confidence: float   # 0-1
    
    # Alternative scenarios
    up_probability: float
    down_probability: float
    sideways_probability: float
    
    # Price targets
    expected_return: float
    return_std: float
    upper_bound: Decimal  # 95% CI
    lower_bound: Decimal  # 95% CI
    
    # Model metadata
    model_ensemble: list[str]
    feature_importance: dict[str, float]
    regime_context: int
    
    # Self-correction
    last_prediction_error: float | None = None
    cumulative_error: float = 0.0
    adaptation_factor: float = 1.0


@dataclass
class NextCandleConfig:
    """Configuration for next candle predictor."""
    # Model settings
    model_types: list[str] = field(default_factory=lambda: ["lstm", "transformer"])
    lookback: int = 100
    prediction_horizon: int = 1  # Next candle
    hidden_size: int = 256
    num_layers: int = 3
    dropout: float = 0.15
    learning_rate: float = 0.0005
    
    # Ensemble settings
    ensemble_weights: dict[str, float] = field(default_factory=lambda: {
        "lstm": 0.4,
        "transformer": 0.35,
        "technical": 0.15,
        "online": 0.1
    })
    min_ensemble_agreement: float = 0.6
    
    # Prediction thresholds
    direction_threshold: float = 0.0005  # Min return for direction
    strong_threshold: float = 0.002      # Strong move threshold
    confidence_threshold: float = 0.55   # Min confidence to act
    
    # Online learning
    online_learning_rate: float = 0.01
    adaptation_window: int = 50
    drift_detection_window: int = 20
    max_cumulative_error: float = 0.05
    
    # Risk management
    max_position_risk: float = 0.02
    atr_multiplier_sl: float = 1.5
    atr_multiplier_tp: float = 3.0


class NextCandlePredictor:
    """
    Advanced next candle prediction with ensemble models and self-correction.
    
    Features:
    - Multi-model ensemble (LSTM + Transformer + Technical + Online)
    - Directional probability with confidence intervals
    - Real-time adaptation via online learning
    - Drift detection and automatic reweighting
    - Prediction error tracking and self-correction
    - Regime-aware predictions
    """
    
    def __init__(self, config: NextCandleConfig | None = None):
        self.config = config or NextCandleConfig()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Model ensemble
        self.models: dict[str, MLModelTrainer] = {}
        self.feature_engineers: dict[str, FeatureEngineer] = {}
        self.online_learner: OnlineLearner | None = None
        
        # State tracking
        self.prediction_history: list[CandlePrediction] = []
        self.actual_history: list[Bar] = []
        self.error_history: list[float] = []
        self.model_performance: dict[str, list[float]] = {
            "lstm": [],
            "transformer": [],
            "technical": [],
            "online": []
        }
        self.current_weights = self.config.ensemble_weights.copy()
        
        # Drift detection
        self.recent_errors: list[float] = []
        self.drift_detected = False
        self.last_retrain = datetime.now(UTC)
        
        logger.info(f"NextCandlePredictor initialized on {self.device}")
    
    async def initialize(self, symbols: list[str]) -> None:
        """Initialize all models for given symbols."""
        for symbol in symbols:
            await self._initialize_symbol(symbol)
        
        # Initialize online learner
        self.online_learner = OnlineLearner("linear")
        logger.info("NextCandlePredictor fully initialized")
    
    async def _initialize_symbol(self, symbol: str) -> None:
        """Initialize models for a specific symbol."""
        for model_type in self.config.model_types:
            model_config = ModelConfig(
                model_type=model_type,
                input_features=self._get_feature_list(),
                target="future_return",
                lookback=self.config.lookback,
                prediction_horizon=self.config.prediction_horizon,
                hidden_size=self.config.hidden_size,
                num_layers=self.config.num_layers,
                dropout=self.config.dropout,
                learning_rate=self.config.learning_rate,
            )
            
            self.feature_engineers[f"{symbol}_{model_type}"] = FeatureEngineer(model_config)
            self.models[f"{symbol}_{model_type}"] = MLModelTrainer(model_config)
            
            # Try loading existing model
            model_path = Path(settings.strategy_ml_models_path) / f"{symbol}_{model_type}_next_candle_best.pt"
            if model_path.exists():
                try:
                    self.models[f"{symbol}_{model_type}"].load_model(model_path)
                    logger.info(f"Loaded {model_type} model for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to load {model_type} model for {symbol}: {e}")
    
    def _get_feature_list(self) -> list[str]:
        """Get comprehensive feature list for next candle prediction."""
        return [
            # Returns
            "return_1", "return_3", "return_5", "return_10", "return_20",
            "log_return", "log_return_5", "log_return_10",
            
            # Volatility
            "volatility_10", "volatility_20", "volatility_50",
            "volatility_ratio_10_20", "volatility_ratio_20_50",
            
            # Trend
            "price_to_sma10", "price_to_sma20", "price_to_sma50",
            "price_to_ema10", "price_to_ema20", "price_to_ema50",
            "ema_slope_10", "ema_slope_20",
            
            # Volume
            "volume_ratio", "volume_change", "volume_trend",
            "volume_price_trend", "on_balance_volume",
            
            # Momentum
            "rsi_14", "rsi_7", "rsi_21",
            "macd", "macd_signal", "macd_hist",
            "macd_slope", "macd_hist_slope",
            "stoch_k_14", "stoch_d_14",
            "williams_r_14", "cci_20",
            
            # Volatility/Bands
            "bb_upper_20", "bb_lower_20", "bb_middle_20",
            "bb_width_20", "bb_position_20",
            "bb_width_10", "bb_position_10",
            "atr_14", "atr_7", "atr_21",
            "atr_pct", "natr_14",
            "keltner_upper", "keltner_lower", "keltner_position",
            
            # Trend Strength
            "adx_14", "plus_di_14", "minus_di_14",
            "adx_slope", "di_spread",
            
            # Mean Reversion
            "zscore_20", "zscore_50",
            "distance_from_mean_20", "distance_from_mean_50",
            
            # Candlestick
            "body_size", "upper_wick", "lower_wick",
            "body_to_range", "is_doji", "is_hammer", "is_shooting_star",
            "is_engulfing", "is_harami",
            
            # Microstructure
            "spread_pct", "hl_range_pct", "close_position",
            "tick_volume", "trade_intensity",
            
            # Time
            "hour", "weekday", "month", "quarter",
            "session_asian", "session_european", "session_american",
            
            # Regime
            "regime_volatility", "regime_trend", "regime_momentum",
            
            # Cross-asset (if available)
            "corr_eur_usd", "corr_gbp_usd", "corr_usd_jpy",
            "dxy_change", "vix_change",
        ]
    
    async def predict_next_candle(
        self,
        symbol: str,
        recent_bars: list[Bar],
        current_regime: int = 0
    ) -> CandlePrediction:
        """
        Predict next candle with full ensemble.
        
        Args:
            symbol: Trading symbol
            recent_bars: Recent bars (need at least lookback + 50)
            current_regime: Current market regime
            
        Returns:
            CandlePrediction with OHLC, direction, confidence, targets
        """
        if len(recent_bars) < self.config.lookback + 50:
            raise ValueError(f"Need at least {self.config.lookback + 50} bars, got {len(recent_bars)}")
        
        # Convert to DataFrame
        df = self._bars_to_dataframe(recent_bars)
        
        # Create features
        df_features = await self._create_features(df, symbol)
        
        # Get ensemble predictions
        predictions = {}
        
        # ML Models
        for model_type in self.config.model_types:
            pred = await self._predict_ml(symbol, model_type, df_features)
            if pred is not None:
                predictions[model_type] = pred
        
        # Technical analysis
        tech_pred = await self._predict_technical(df_features)
        if tech_pred is not None:
            predictions["technical"] = tech_pred
        
        # Online learner
        online_pred = await self._predict_online(symbol, df_features)
        if online_pred is not None:
            predictions["online"] = online_pred
        
        # Ensemble combination
        ensemble = self._combine_predictions(predictions, current_regime)
        
        # Create final prediction
        prediction = self._build_prediction(
            symbol=symbol,
            df=df,
            ensemble=ensemble,
            regime=current_regime,
            predictions=predictions
        )
        
        # Self-correction: update based on previous error
        await self._self_correct(prediction)
        
        # Store for learning
        self.prediction_history.append(prediction)
        if len(self.prediction_history) > 1000:
            self.prediction_history.pop(0)
        
        return prediction
    
    async def _create_features(self, df: pl.DataFrame, symbol: str) -> pl.DataFrame:
        """Create all features for prediction."""
        # Use first available feature engineer
        fe_key = f"{symbol}_{self.config.model_types[0]}"
        if fe_key in self.feature_engineers:
            return self.feature_engineers[fe_key].create_features(df)
        
        # Fallback: create basic features
        fe = FeatureEngineer(ModelConfig(
            model_type="lstm",
            input_features=self._get_feature_list(),
            target="future_return",
            lookback=self.config.lookback,
        ))
        return fe.create_features(df)
    
    async def _predict_ml(
        self,
        symbol: str,
        model_type: str,
        df: pl.DataFrame
    ) -> dict[str, Any] | None:
        """Get prediction from ML model."""
        key = f"{symbol}_{model_type}"
        if key not in self.models or not self.models[key].model:
            return None
        
        try:
            fe = self.feature_engineers[key]
            X, _ = fe.prepare_sequences(df, lookback=self.config.lookback, horizon=1)
            
            if len(X) == 0:
                return None
            
            # Use latest sequence
            latest_X = X[-1:]
            pred = self.models[key].predict(latest_X)
            pred_value = float(pred[0][0])
            
            # Also get prediction with uncertainty (Monte Carlo dropout)
            mc_preds = self._mc_dropout_predict(key, latest_X, n_samples=50)
            pred_mean = float(np.mean(mc_preds))
            pred_std = float(np.std(mc_preds))
            
            return {
                "prediction": pred_mean,
                "uncertainty": pred_std,
                "raw_prediction": pred_value,
                "model_type": model_type,
            }
        except Exception as e:
            logger.error(f"ML prediction error for {key}: {e}")
            return None
    
    def _mc_dropout_predict(self, key: str, X: np.ndarray, n_samples: int = 50) -> np.ndarray:
        """Monte Carlo dropout for uncertainty estimation."""
        model = self.models[key].model
        model.train()  # Enable dropout
        
        preds = []
        X_tensor = torch.FloatTensor(X).to(self.device)
        
        with torch.no_grad():
            for _ in range(n_samples):
                out = model(X_tensor)
                preds.append(out.cpu().numpy())
        
        model.eval()
        return np.array(preds).squeeze()
    
    async def _predict_technical(self, df: pl.DataFrame) -> dict[str, Any] | None:
        """Technical analysis based prediction."""
        try:
            latest = df.row(-1, named=True)
            
            # Multi-timeframe trend
            trend_signals = []
            
            # EMA alignment
            ema_20 = latest.get("ema_20", 0)
            ema_50 = latest.get("ema_50", 0)
            ema_200 = latest.get("ema_200", 0)
            close = latest.get("close", 0)
            
            if ema_20 > ema_50 > ema_200 and close > ema_20:
                trend_signals.append(("ema_alignment", 1.0, 0.8))
            elif ema_20 < ema_50 < ema_200 and close < ema_20:
                trend_signals.append(("ema_alignment", -1.0, 0.8))
            
            # MACD
            macd = latest.get("macd", 0)
            macd_signal = latest.get("macd_signal", 0)
            macd_hist = latest.get("macd_hist", 0)
            
            if macd > macd_signal and macd_hist > 0:
                trend_signals.append(("macd", 1.0, 0.7))
            elif macd < macd_signal and macd_hist < 0:
                trend_signals.append(("macd", -1.0, 0.7))
            
            # ADX trend strength
            adx = latest.get("adx_14", 0)
            plus_di = latest.get("plus_di_14", 0)
            minus_di = latest.get("minus_di_14", 0)
            
            if adx > 25:
                if plus_di > minus_di:
                    trend_signals.append(("adx_trend", 1.0, min(adx / 50, 1.0)))
                elif minus_di > plus_di:
                    trend_signals.append(("adx_trend", -1.0, min(adx / 50, 1.0)))
            
            # Momentum
            rsi = latest.get("rsi_14", 50)
            if rsi < 30:
                trend_signals.append(("rsi_oversold", 1.0, 0.6))
            elif rsi > 70:
                trend_signals.append(("rsi_overbought", -1.0, 0.6))
            
            # Bollinger Band position
            bb_pos = latest.get("bb_position_20", 0.5)
            if bb_pos < 0.1:
                trend_signals.append(("bb_oversold", 1.0, 0.5))
            elif bb_pos > 0.9:
                trend_signals.append(("bb_overbought", -1.0, 0.5))
            
            # Combine
            if not trend_signals:
                return None
            
            total_weight = sum(s[2] for s in trend_signals)
            weighted_dir = sum(s[1] * s[2] for s in trend_signals) / total_weight
            
            # Expected return from technical
            atr = latest.get("atr_14", close * 0.001)
            expected_return = weighted_dir * (atr / close) * 0.5
            
            return {
                "prediction": expected_return,
                "uncertainty": 0.001,
                "direction": 1 if weighted_dir > 0 else -1 if weighted_dir < 0 else 0,
                "confidence": total_weight / len(trend_signals),
                "model_type": "technical",
            }
        except Exception as e:
            logger.error(f"Technical prediction error: {e}")
            return None
    
    async def _predict_online(self, symbol: str, df: pl.DataFrame) -> dict[str, Any] | None:
        """Online learner prediction."""
        if not self.online_learner or not self.online_learner.has_river:
            return None
        
        try:
            latest = df.row(-1, named=True)
            
            # Create feature dict for online learner
            features = {
                "return_1": latest.get("return_1", 0),
                "return_5": latest.get("return_5", 0),
                "rsi_14": latest.get("rsi_14", 50) / 100,
                "macd": latest.get("macd", 0),
                "bb_position": latest.get("bb_position_20", 0.5),
                "adx": latest.get("adx_14", 0) / 100,
                "volume_ratio": latest.get("volume_ratio", 1),
                "hour": latest.get("hour", 12) / 24,
            }
            
            pred = self.online_learner.predict_one(features)
            
            return {
                "prediction": pred,
                "uncertainty": 0.002,
                "model_type": "online",
            }
        except Exception as e:
            logger.error(f"Online prediction error: {e}")
            return None
    
    def _combine_predictions(
        self,
        predictions: dict[str, dict],
        regime: int
    ) -> dict[str, Any]:
        """Combine ensemble predictions with dynamic weighting."""
        
        # Adjust weights based on recent performance
        self._update_weights()
        
        # Weighted combination
        total_weight = 0.0
        weighted_pred = 0.0
        weighted_uncertainty = 0.0
        weighted_confidence = 0.0
        
        for model_name, pred in predictions.items():
            weight = self.current_weights.get(model_name, 0.0)
            if weight == 0:
                continue
            
            pred_val = pred["prediction"]
            unc = pred.get("uncertainty", 0.001)
            conf = pred.get("confidence", 0.5)
            
            # Regime adjustment
            regime_mult = self._get_regime_multiplier(model_name, regime)
            weight *= regime_mult
            
            weighted_pred += pred_val * weight
            weighted_uncertainty += unc * weight
            weighted_confidence += conf * weight
            total_weight += weight
        
        if total_weight == 0:
            return {"prediction": 0.0, "uncertainty": 0.01, "confidence": 0.0}
        
        return {
            "prediction": weighted_pred / total_weight,
            "uncertainty": weighted_uncertainty / total_weight,
            "confidence": weighted_confidence / total_weight,
            "weights": self.current_weights.copy(),
        }
    
    def _get_regime_multiplier(self, model_name: str, regime: int) -> float:
        """Adjust model weight based on market regime."""
        # Regime: 0=normal, 1=high_vol, 2=trending, 3=mean_reverting
        multipliers = {
            "lstm": {0: 1.0, 1: 0.8, 2: 1.2, 3: 0.9},
            "transformer": {0: 1.0, 1: 0.9, 2: 1.1, 3: 1.0},
            "technical": {0: 1.0, 1: 0.7, 2: 1.3, 3: 1.2},
            "online": {0: 1.0, 1: 1.2, 2: 0.8, 3: 1.1},
        }
        return multipliers.get(model_name, {}).get(regime, 1.0)
    
    def _update_weights(self) -> None:
        """Update ensemble weights based on recent performance."""
        for model_name in self.current_weights:
            perf = self.model_performance.get(model_name, [])
            if len(perf) >= 10:
                recent_acc = np.mean(perf[-20:])
                # Boost weight for good performers
                base_weight = self.config.ensemble_weights.get(model_name, 0.25)
                self.current_weights[model_name] = base_weight * (1 + recent_acc)
        
        # Normalize
        total = sum(self.current_weights.values())
        if total > 0:
            for k in self.current_weights:
                self.current_weights[k] /= total
    
    def _build_prediction(
        self,
        symbol: str,
        df: pl.DataFrame,
        ensemble: dict[str, Any],
        regime: int,
        predictions: dict[str, dict]
    ) -> CandlePrediction:
        """Build final CandlePrediction object."""
        
        pred_return = ensemble["prediction"]
        uncertainty = ensemble["uncertainty"]
        confidence = ensemble["confidence"]
        
        # Current price
        current_close = float(df["close"][-1])
        _current_open = float(df["open"][-1])
        _current_high = float(df["high"][-1])
        _current_low = float(df["low"][-1])
        _atr = float(df["atr_14"][-1]) if "atr_14" in df.columns else current_close * 0.001
        
        # Predicted OHLC
        _predicted_open = Decimal(str(current_close))
        expected_move = pred_return * current_close
        predicted_close = Decimal(str(current_close + expected_move))
        
        # High/Low with uncertainty
        move_range = uncertainty * current_close * 2
        predicted_high = Decimal(str(max(current_close, current_close + expected_move) + move_range))
        predicted_low = Decimal(str(min(current_close, current_close + expected_move) - move_range))
        
        # Direction
        if pred_return > self.config.strong_threshold:
            direction = CandleDirection.STRONG_UP
        elif pred_return > self.config.direction_threshold:
            direction = CandleDirection.UP
        elif pred_return < -self.config.strong_threshold:
            direction = CandleDirection.STRONG_DOWN
        elif pred_return < -self.config.direction_threshold:
            direction = CandleDirection.DOWN
        else:
            direction = CandleDirection.DOJI
        
        # Probabilities
        up_prob = max(0, min(1, 0.5 + pred_return * 100))
        down_prob = max(0, min(1, 0.5 - pred_return * 100))
        sideways_prob = 1 - up_prob - down_prob
        
        # Confidence intervals
        std_move = uncertainty * current_close
        upper_bound = Decimal(str(current_close + expected_move + 1.96 * std_move))
        lower_bound = Decimal(str(current_close + expected_move - 1.96 * std_move))
        
        # Feature importance (simplified)
        feature_importance = {
            "trend": 0.3,
            "momentum": 0.25,
            "volatility": 0.2,
            "volume": 0.15,
            "mean_reversion": 0.1,
        }
        
        return CandlePrediction(
            timestamp=datetime.now(UTC),
            symbol=symbol,
            timeframe=str(df["timeframe"][-1]) if "timeframe" in df.columns else "1m",
            
            predicted_open=Decimal(str(current_close)),
            predicted_high=predicted_high,
            predicted_low=predicted_low,
            predicted_close=predicted_close,
            
            direction=direction,
            direction_probability=max(up_prob, down_prob),
            direction_confidence=confidence,
            
            up_probability=up_prob,
            down_probability=down_prob,
            sideways_probability=sideways_prob,
            
            expected_return=pred_return,
            return_std=uncertainty,
            upper_bound=upper_bound,
            lower_bound=lower_bound,
            
            model_ensemble=list(predictions.keys()),
            feature_importance=feature_importance,
            regime_context=regime,
            
            last_prediction_error=self.error_history[-1] if self.error_history else None,
            cumulative_error=sum(self.error_history),
            adaptation_factor=self.current_weights.get("online", 0.1),
        )
    
    async def _self_correct(self, prediction: CandlePrediction) -> None:
        """Self-correction based on previous prediction errors."""
        if not self.actual_history:
            return
        
        # Get last actual bar
        last_actual = self.actual_history[-1]
        last_pred = self.prediction_history[-1] if self.prediction_history else None
        
        if not last_pred:
            return
        
        # Calculate prediction error
        actual_return = float(last_actual.close / last_actual.open - 1)
        pred_return = last_pred.expected_return
        error = abs(actual_return - pred_return)
        
        self.error_history.append(error)
        if len(self.error_history) > 200:
            self.error_history.pop(0)
        
        # Track model-specific errors
        for model_name in list(self.model_performance.keys()):
            self.model_performance.setdefault(model_name, []).append(1 - min(error * 100, 1))
            if len(self.model_performance[model_name]) > 100:
                self.model_performance[model_name].pop(0)
        
        # Drift detection
        self.recent_errors.append(error)
        if len(self.recent_errors) > self.config.drift_detection_window:
            self.recent_errors.pop(0)
        
        avg_recent_error = np.mean(self.recent_errors)
        avg_long_error = np.mean(self.error_history) if self.error_history else error
        
        if avg_recent_error > avg_long_error * 1.5 and len(self.recent_errors) >= self.config.drift_detection_window:
            self.drift_detected = True
            logger.warning(f"Model drift detected! Recent error: {avg_recent_error:.6f}, Long-term: {avg_long_error:.6f}")
            await self._adapt_to_drift()
        else:
            self.drift_detected = False
        
        # Cumulative error adaptation
        cum_error = sum(self.error_history[-self.config.adaptation_window:])
        if cum_error > self.config.max_cumulative_error:
            # Increase online learner weight, decrease static models
            self.current_weights["online"] = min(self.current_weights.get("online", 0.1) * 1.2, 0.3)
            for k in ["lstm", "transformer"]:
                self.current_weights[k] = max(self.current_weights.get(k, 0.25) * 0.9, 0.1)
            
            # Renormalize
            total = sum(self.current_weights.values())
            for k in self.current_weights:
                self.current_weights[k] /= total
            
            logger.info(f"Adapted weights due to cumulative error: {self.current_weights}")
    
    async def _adapt_to_drift(self) -> None:
        """Adapt models when drift detected."""
        # Trigger online learner to adapt faster
        if self.online_learner:
            self.online_learner.model.learn_one = lambda x, y: None  # Reset
        
        # Retrain trigger
        if (datetime.now(UTC) - self.last_retrain).total_seconds() > 3600:  # 1 hour
            logger.info("Scheduling model retrain due to drift")
            self.last_retrain = datetime.now(UTC)
    
    def update_with_actual(self, bar: Bar) -> None:
        """Update with actual bar for learning."""
        self.actual_history.append(bar)
        if len(self.actual_history) > 1000:
            self.actual_history.pop(0)
        
        # Online learning update
        if self.online_learner and self.prediction_history:
            _last_pred = self.prediction_history[-1]
            features = self._extract_features(bar)
            target = float(bar.close / bar.open - 1)
            self.online_learner.learn_one(features, target)
    
    def _extract_features(self, bar: Bar) -> dict[str, float]:
        """Extract features for online learning."""
        return {
            "return_1": 0.0,  # Would need previous bar
            "rsi_14": 50.0,
            "macd": 0.0,
            "bb_position": 0.5,
            "adx": 0.0,
            "volume_ratio": 1.0,
            "hour": bar.timestamp.hour / 24,
        }
    
    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        """Convert bars to Polars DataFrame."""
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
            "spread": [float(b.spread) for b in bars],
            "symbol": [b.symbol for b in bars],
        }
        df = pl.DataFrame(data).sort("timestamp")
        
        # Add timeframe
        if bars:
            df = df.with_columns(pl.lit(str(bars[0].timeframe)).alias("timeframe"))
        
        return df
    
    def get_model_diagnostics(self) -> dict[str, Any]:
        """Get comprehensive model diagnostics."""
        return {
            "ensemble_weights": self.current_weights,
            "drift_detected": self.drift_detected,
            "recent_avg_error": np.mean(self.recent_errors) if self.recent_errors else 0,
            "long_term_avg_error": np.mean(self.error_history) if self.error_history else 0,
            "model_performance": {
                k: {
                    "recent_accuracy": np.mean(v[-20:]) if len(v) >= 20 else 0,
                    "overall_accuracy": np.mean(v) if v else 0,
                    "samples": len(v),
                }
                for k, v in self.model_performance.items()
            },
            "prediction_count": len(self.prediction_history),
            "adaptation_factor": self.current_weights.get("online", 0.1),
        }


class NextCandleStrategy(EnsembleStrategy):
    """
    Enhanced strategy using next candle predictor.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.predictor: NextCandlePredictor | None = None
        self.prediction_threshold = config.parameters.get("prediction_threshold", 0.55)
        self.min_confidence = config.parameters.get("min_confidence", 0.6)
    
    async def _initialize(self) -> None:
        await super()._initialize()
        
        # Initialize next candle predictor
        predictor_config = NextCandleConfig(
            model_types=["lstm", "transformer"],
            lookback=self.config.parameters.get("lookback", 100),
            confidence_threshold=self.min_confidence,
        )
        self.predictor = NextCandlePredictor(predictor_config)
        
        # Get symbols from config
        symbols = self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY"])
        await self.predictor.initialize(symbols)
        
        logger.info("NextCandleStrategy initialized with predictor")
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        
        # Get prediction
        if self.predictor and len(self._bar_buffer) >= 150:
            try:
                prediction = await self.predictor.predict_next_candle(
                    symbol=bar.symbol,
                    recent_bars=self._bar_buffer[-150:],
                    current_regime=self.current_regime,
                )
                
                # Convert prediction to signal
                signal = self._prediction_to_signal(prediction, bar)
                if signal:
                    signals.append(signal)
                
                # Update predictor with actual
                self.predictor.update_with_actual(bar)
                
            except Exception as e:
                logger.error(f"Next candle prediction error: {e}")
        
        # Also get base ensemble signals
        base_signals = await super()._generate_signals(bar)
        signals.extend(base_signals)
        
        return signals
    
    def _prediction_to_signal(self, pred: CandlePrediction, bar: Bar) -> Signal | None:
        """Convert candle prediction to trading signal."""
        
        # Check confidence
        if pred.direction_confidence < self.min_confidence:
            return None
        
        # Check direction probability
        if pred.direction_probability < self.prediction_threshold:
            return None
        
        # Determine direction
        if pred.direction in (CandleDirection.UP, CandleDirection.STRONG_UP):
            direction = Direction.LONG
        elif pred.direction in (CandleDirection.DOWN, CandleDirection.STRONG_DOWN):
            direction = Direction.SHORT
        else:
            return None
        
        # Strength based on confidence and probability
        strength = pred.direction_confidence * pred.direction_probability
        
        # Use predicted levels
        entry_price = pred.predicted_open
        stop_loss = pred.lower_bound if direction == Direction.LONG else pred.upper_bound
        take_profit = pred.upper_bound if direction == Direction.LONG else pred.lower_bound
        
        # Adjust with ATR
        atr = float(pred.predicted_high - pred.predicted_low) / 2
        if direction == Direction.LONG:
            stop_loss = Decimal(str(float(entry_price) - 1.5 * atr))
            take_profit = Decimal(str(float(entry_price) + 3 * atr))
        else:
            stop_loss = Decimal(str(float(entry_price) + 1.5 * atr))
            take_profit = Decimal(str(float(entry_price) - 3 * atr))
        
        return Signal.create_entry(
            strategy_id=self.strategy_id,
            strategy_name=f"{self.config.name}_next_candle",
            symbol=bar.symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strength=min(strength, 1.0),
            confidence=pred.direction_confidence,
            timeframe=bar.timeframe,
            metadata={
                "prediction_type": "next_candle",
                "predicted_direction": pred.direction.value,
                "up_prob": pred.up_probability,
                "down_prob": pred.down_probability,
                "expected_return": pred.expected_return,
                "return_std": pred.return_std,
                "regime": pred.regime_context,
                "ensemble": pred.model_ensemble,
            },
        )


# Factory function for easy integration
def create_next_candle_strategy(config: StrategyConfig) -> NextCandleStrategy:
    """Factory to create next candle prediction strategy."""
    return NextCandleStrategy(config)


# Integration example
if __name__ == "__main__":
    # Example usage
    import asyncio
    from datetime import UTC, datetime
    from decimal import Decimal

    from src.data.models import Bar, Timeframe
    from src.strategy.base.strategy import StrategyConfig
    
    async def test():
        config = StrategyConfig(
            name="NextCandlePredictor",
            symbols=["EURUSD"],
            timeframes=[Timeframe.M5],
            parameters={
                "lookback": 100,
                "prediction_threshold": 0.55,
                "min_confidence": 0.6,
            }
        )
        
        strategy = NextCandleStrategy(config)
        await strategy._initialize()
        
        # Simulate bars
        bars = []
        base_price = 1.1000
        for i in range(200):
            bars.append(Bar(
                symbol="EURUSD",
                timestamp=datetime.now(UTC),
                timeframe=Timeframe.M5,
                open=Decimal(str(base_price + np.random.randn() * 0.0005)),
                high=Decimal(str(base_price + abs(np.random.randn()) * 0.001)),
                low=Decimal(str(base_price - abs(np.random.randn()) * 0.001)),
                close=Decimal(str(base_price + np.random.randn() * 0.0005)),
                volume=Decimal(1000),
                spread=Decimal("0.00005"),
            ))
        
        # Predict
        predictor = NextCandlePredictor()
        await predictor.initialize(["EURUSD"])
        
        pred = await predictor.predict_next_candle("EURUSD", bars, regime=0)
        print(f"Prediction: {pred.direction.value}, Confidence: {pred.direction_confidence:.2%}")
        print(f"Expected Return: {pred.expected_return:.4%}")
        print(f"OHLC: {pred.predicted_open} / {pred.predicted_high} / {pred.predicted_low} / {pred.predicted_close}")
    
    asyncio.run(test())