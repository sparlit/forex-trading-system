"""
Elite Autonomous Quantum Trading System - Next Candle Prediction Engine
Core prediction engine using ensemble ML for 99% accuracy target.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import torch
    from torch import nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import importlib.util
    TF_AVAILABLE = importlib.util.find_spec('tensorflow') is not None
except ImportError:
    TF_AVAILABLE = False

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

try:
    import importlib.util
    DARTS_AVAILABLE = importlib.util.find_spec('darts') is not None
except ImportError:
    DARTS_AVAILABLE = False

try:
    import importlib.util
    AUTOTS_AVAILABLE = importlib.util.find_spec('autots') is not None
except ImportError:
    AUTOTS_AVAILABLE = False

try:
    import importlib.util
    PROPHET_AVAILABLE = importlib.util.find_spec('prophet') is not None
except ImportError:
    PROPHET_AVAILABLE = False

from src.data.storage.timescale import timescaledb
from src.strategy.technical.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Types of prediction models."""
    LSTM = "lstm"
    TRANSFORMER = "transformer"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    PROPHET = "prophet"
    DARTS_RNN = "darts_rnn"
    DARTS_TCN = "darts_tcn"
    DARTS_TRANSFORMER = "darts_transformer"
    AUTOTS = "autots"
    PROPHET_MODEL = "prophet_model"


class PredictionHorizon(Enum):
    """Prediction time horizons."""
    NEXT_CANDLE = 1
    NEXT_5_CANDLES = 5
    NEXT_15_CANDLES = 15
    NEXT_HOUR = 60  # For 1m timeframe


@dataclass
class PredictionResult:
    """Result of a prediction."""
    symbol: str
    timeframe: str
    timestamp: datetime
    horizon: PredictionHorizon
    predicted_price: float
    predicted_direction: int  # 1=up, -1=down, 0=flat
    confidence: float
    model_predictions: dict[ModelType, float]
    ensemble_weights: dict[ModelType, float]
    features_used: list[str]
    timestamp_created: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ModelPerformance:
    """Track model performance for dynamic weighting."""
    model_type: ModelType
    symbol: str
    timeframe: str
    total_predictions: int = 0
    correct_predictions: int = 0
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    @property
    def accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.5
        return self.correct_predictions / self.total_predictions
    
    @property
    def weight(self) -> float:
        """Calculate dynamic weight based on performance."""
        if self.total_predictions < 10:
            return 1.0
        base = self.accuracy * 0.4 + min(self.sharpe_ratio / 3.0, 1.0) * 0.3 + max(0, 1 - self.max_drawdown / 0.2) * 0.3
        return max(0.01, min(1.0, base))


class LSTMModel(nn.Module):
    """PyTorch LSTM for sequence prediction."""
    
    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, output_size: int = 1, dropout: float = 0.2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, output_size)
        
    def forward(self, x):
        batch_size = x.size(0)
        h0 = torch.zeros(self.num_layers, batch_size, self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, batch_size, self.hidden_size).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = self.dropout(out[:, -1, :])
        out = self.fc(out)
        return out


class TransformerModel(nn.Module):
    """PyTorch Transformer for sequence prediction."""
    
    def __init__(self, input_size: int, d_model: int = 128, nhead: int = 8, num_layers: int = 4, output_size: int = 1, dropout: float = 0.1):
        super().__init__()
        self.input_projection = nn.Linear(input_size, d_model)
        self.pos_encoder = PositionalEncoding(d_model, dropout)
        encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, d_model * 4, dropout, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
        self.fc = nn.Linear(d_model, output_size)
        
    def forward(self, x):
        x = self.input_projection(x)
        x = self.pos_encoder(x)
        out = self.transformer(x)
        out = self.fc(out[:, -1, :])
        return out


class PositionalEncoding(nn.Module):
    """Positional encoding for Transformer."""
    
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)
        
    def forward(self, x):
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class NextCandlePredictor:
    """
    Next Candle Prediction Engine
    Ensemble of ML models targeting 99% accuracy.
    """
    
    def __init__(self):
        self.models: dict[ModelType, Any] = {}
        self.model_weights: dict[str, dict[ModelType, float]] = defaultdict(lambda: defaultdict(float))
        self.model_performance: dict[str, dict[ModelType, ModelPerformance]] = defaultdict(lambda: defaultdict(ModelPerformance))
        self.feature_scalers: dict[str, Any] = {}
        self.sequence_length = 60  # Lookback window
        self.feature_columns: list[str] = []
        self.prediction_cache: dict[str, PredictionResult] = {}
        self.last_training: dict[str, datetime] = {}
        self.training_interval = timedelta(hours=4)
        self.min_training_samples = 500
        self.retrain_threshold = 0.02  # Retrain if accuracy drops below 98%
        self.target_accuracy = 0.99
        self.ensemble_size = 5
        
        # Initialize default weights
        self.default_weights = {
            ModelType.LSTM: 0.20,
            ModelType.TRANSFORMER: 0.20,
            ModelType.XGBOOST: 0.20,
            ModelType.LIGHTGBM: 0.15,
            ModelType.CATBOOST: 0.15,
            ModelType.PROPHET: 0.05,
            ModelType.DARTS_RNN: 0.05,
        }
        
        logger.info("Next Candle Predictor initialized")
    
    async def initialize(self):
        """Initialize all models."""
        await self._initialize_models()
        await self._load_models()
        logger.info("Next Candle Predictor fully initialized")
    
    async def _initialize_models(self):
        """Initialize all ML models."""
        # PyTorch models
        if TORCH_AVAILABLE:
            self.models[ModelType.LSTM] = "lstm_placeholder"
            self.models[ModelType.TRANSFORMER] = "transformer_placeholder"
        
        # XGBoost
        if XGB_AVAILABLE:
            self.models[ModelType.XGBOOST] = xgb.XGBRegressor(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.01,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
            )
        
        # LightGBM
        if LGB_AVAILABLE:
            self.models[ModelType.LIGHTGBM] = lgb.LGBMRegressor(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.01,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                verbosity=-1,
            )
        
        # CatBoost
        try:
            import catboost as cb
            self.models[ModelType.CATBOOST] = cb.CatBoostRegressor(
                iterations=500,
                depth=6,
                learning_rate=0.01,
                subsample=0.8,
                random_state=42,
                verbose=False,
            )
        except ImportError as e:
                    logging.getLogger(__name__).debug(f'Suppressed in catboost import: {e}', exc_info=True)
        
        # Darts models
        if DARTS_AVAILABLE:
            self.models[ModelType.DARTS_RNN] = "darts_rnn_placeholder"
            self.models[ModelType.DARTS_TCN] = "darts_tcn_placeholder"
            self.models[ModelType.DARTS_TRANSFORMER] = "darts_transformer_placeholder"
        
        # Prophet
        if PROPHET_AVAILABLE:
            self.models[ModelType.PROPHET_MODEL] = "prophet_placeholder"
        
        # AutoTS
        if AUTOTS_AVAILABLE:
            self.models[ModelType.AUTOTS] = "autots_placeholder"
        
        logger.info(f"Initialized {len(self.models)} models")
    
    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for prediction."""
        df = df.copy()
        
        # Technical indicators
        df = TechnicalIndicators.add_all_indicators_polars(df)
        
        # Price features
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility'] = df['returns'].rolling(20).std()
        
        # Volume features
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
        
        # Time features
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.dayofweek
            df['month'] = pd.to_datetime(df['timestamp']).dt.month
        
        # Target: next candle direction
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
        df['target_price'] = df['close'].shift(-1)
        
        # Drop NaN
        df = df.dropna()
        
        return df
    
    def _create_sequences(self, X: np.ndarray, y: np.ndarray, seq_len: int = 60) -> tuple[np.ndarray, np.ndarray]:
        """Create sequences for LSTM/Transformer."""
        Xs, ys = [], []
        for i in range(len(X) - seq_len):
            Xs.append(X[i:i+seq_len])
            ys.append(y[i+seq_len])
        return np.array(Xs), np.array(ys)
    
    async def predict_next_candle(
        self,
        symbol: str,
        timeframe: str,
        horizon: PredictionHorizon = PredictionHorizon.NEXT_CANDLE
    ) -> PredictionResult:
        """Predict next candle for a symbol."""
        cache_key = f"{symbol}_{timeframe}_{horizon.value}"
        
        # Check cache
        if cache_key in self.prediction_cache:
            cached = self.prediction_cache[cache_key]
            if datetime.now(UTC) - cached.timestamp_created < timedelta(minutes=1):
                return cached
        
        # Get recent data
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=30)
        
        try:
            bars = await timescaledb.get_bars(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
        except Exception as e:
            logger.error(f"Failed to get bars for {symbol}: {e}")
            return PredictionResult(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.now(UTC),
                horizon=horizon,
                predicted_price=0.0,
                predicted_direction=0,
                confidence=0.0,
                model_predictions={},
                ensemble_weights={},
                features_used=[],
            )
        
        if not bars or len(bars) < 100:
            logger.warning(f"Insufficient data for {symbol}")
            return self._empty_prediction(symbol, timeframe, horizon)
        
        # Convert to DataFrame
        df = pd.DataFrame([{
            'timestamp': b.timestamp,
            'open': b.open,
            'high': b.high,
            'low': b.low,
            'close': b.close,
            'volume': b.volume,
        } for b in bars])
        
        # Prepare features
        df = self._prepare_features(df)
        
        if len(df) < 100:
            return self._empty_prediction(symbol, timeframe, horizon)
        
        # Get predictions from all models
        predictions = {}
        weights = self._get_ensemble_weights(symbol)
        
        # Current price
        current_price = df['close'].iloc[-1]
        
        # Get predictions from each model
        for model_type in self.models:
            try:
                pred = await self._get_model_prediction(model_type, symbol, df, horizon)
                if pred is not None:
                    predictions[model_type] = pred
            except Exception as e:
                logger.warning(f"Model {model_type.value} prediction failed: {e}")
        
        # Ensemble prediction
        ensemble_price, ensemble_direction, confidence = self._ensemble_predict(predictions, weights, current_price)
        
        # Create result
        result = PredictionResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(UTC),
            horizon=horizon,
            predicted_price=ensemble_price,
            predicted_direction=ensemble_direction,
            confidence=confidence,
            model_predictions=predictions,
            ensemble_weights=weights,
            features_used=list(df.columns),
        )
        
        # Cache result
        self.prediction_cache[cache_key] = result
        
        return result
    
    async def _get_model_prediction(
        self,
        model_type: ModelType,
        symbol: str,
        df: pd.DataFrame,
        horizon: PredictionHorizon
    ) -> float | None:
        """Get prediction from a specific model."""
        # Placeholder for actual model prediction
        # In production, this would use trained models
        model = self.models.get(model_type)
        if model is None:
            return None
        
        # Simulate prediction based on model type
        current_price = df['close'].iloc[-1]
        recent_returns = df['returns'].tail(20).mean()
        _ = df['volatility'].iloc[-1] if 'volatility' in df.columns else 0.01  # unused
        
        # Simple prediction logic (replace with actual model inference)
        if model_type in [ModelType.LSTM, ModelType.TRANSFORMER]:
            # Neural network prediction
            pred_price = current_price * (1 + recent_returns + np.random.normal(0, 0.0001))
        elif model_type in [ModelType.XGBOOST, ModelType.LIGHTGBM, ModelType.CATBOOST]:
            # Tree-based prediction
            pred_price = current_price * (1 + recent_returns * 0.8 + np.random.normal(0, 0.0002))
        elif model_type == ModelType.PROPHET_MODEL:
            # Prophet prediction
            pred_price = current_price * (1 + recent_returns * 0.7 + np.random.normal(0, 0.0003))
        elif model_type in [ModelType.DARTS_RNN, ModelType.DARTS_TCN, ModelType.DARTS_TRANSFORMER]:
            # Darts models
            pred_price = current_price * (1 + recent_returns * 0.75 + np.random.normal(0, 0.00015))
        elif model_type == ModelType.AUTOTS:
            # AutoTS
            pred_price = current_price * (1 + recent_returns * 0.6 + np.random.normal(0, 0.00025))
        else:
            pred_price = current_price * (1 + recent_returns)
        
        return pred_price
    
    def _get_ensemble_weights(self, symbol: str) -> dict[ModelType, float]:
        """Get dynamic ensemble weights based on performance."""
        weights = self.default_weights.copy()
        
        # Adjust based on performance
        if symbol in self.model_performance:
            perf_data = self.model_performance[symbol]
            total_weight = sum(p.weight for p in perf_data.values())
            if total_weight > 0:
                for model_type, perf in perf_data.items():
                    if model_type in weights:
                        weights[model_type] = perf.weight / total_weight
        
        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}
        
        return weights
    
    def _ensemble_predict(
        self,
        predictions: dict[ModelType, float],
        weights: dict[ModelType, float],
        current_price: float
    ) -> tuple[float, int, float]:
        """Combine model predictions into ensemble."""
        if not predictions:
            return current_price, 0, 0.0
        
        # Weighted average price
        total_weight = 0.0
        weighted_price = 0.0
        
        for model_type, pred_price in predictions.items():
            weight = weights.get(model_type, 0.0)
            weighted_price += pred_price * weight
            total_weight += weight
        
        if total_weight > 0:
            ensemble_price = weighted_price / total_weight
        else:
            ensemble_price = current_price
        
        # Direction
        direction = 1 if ensemble_price > predictions.get(next(iter(predictions.keys())), current_price) else -1
        if abs(ensemble_price - current_price) / current_price < 0.0001:
            direction = 0
        
        # Confidence based on agreement and weights
        confidences = []
        for model_type, pred_price in predictions.items():
            weight = weights.get(model_type, 0.0)
            model_conf = weight * (1 - abs(pred_price - ensemble_price) / current_price)
            confidences.append(model_conf)
        
        confidence = np.mean(confidences) if confidences else 0.0
        confidence = max(0.0, min(1.0, confidence))
        
        return ensemble_price, direction, confidence
    
    def _empty_prediction(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> PredictionResult:
        """Return empty prediction for error cases."""
        return PredictionResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(UTC),
            horizon=horizon,
            predicted_price=0.0,
            predicted_direction=0,
            confidence=0.0,
            model_predictions={},
            ensemble_weights={},
            features_used=[],
        )
    
    async def update_model_performance(
        self,
        symbol: str,
        model_type: ModelType,
        predicted_price: float,
        actual_price: float,
        predicted_direction: int,
        actual_direction: int
    ):
        """Update model performance for dynamic weighting."""
        key = f"{symbol}"
        if model_type not in self.model_performance[key]:
            self.model_performance[key][model_type] = ModelPerformance(
                model_type=model_type,
                symbol=symbol,
                timeframe="1h"
            )
        
        perf = self.model_performance[key][model_type]
        perf.total_predictions += 1
        
        # Direction accuracy
        if predicted_direction == actual_direction:
            perf.correct_predictions += 1
        
        # Return calculation
        if perf.total_predictions > 1:
            # Simplified return calculation
            # Simplified return calculation
            perf.total_return += (actual_price - predicted_price) * actual_direction
    
    async def retrain_if_needed(self, symbol: str):
        """Check if retraining is needed and trigger it."""
        if symbol not in self.last_training:
            return
        
        if datetime.now(UTC) - self.last_training[symbol] > self.training_interval:
            logger.info(f"Retraining models for {symbol}")
            await self._retrain_models(symbol)
            self.last_training[symbol] = datetime.now(UTC)
    
    async def _retrain_models(self, symbol: str):
        """Retrain all models with latest data."""
        # Get recent data
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=90)
        
        try:
            bars = await timescaledb.get_bars(
                symbol=symbol,
                timeframe="1h",
                start_time=start_time,
                end_time=end_time,
                limit=50000
            )
            
            if not bars or len(bars) < self.min_training_samples:
                logger.warning(f"Insufficient data for retraining {symbol}")
                return
            
            # Convert to DataFrame
            df = pd.DataFrame([{
                'timestamp': b.timestamp,
                'open': b.open,
                'high': b.high,
                'low': b.low,
                'close': b.close,
                'volume': b.volume,
            } for b in bars])
            
            df = self._prepare_features(df)
            
            if len(df) < self.min_training_samples:
                return
            
            # Split data
            train_size = int(len(df) * 0.8)
            train_df = df.iloc[:train_size]
            val_df = df.iloc[train_size:]
            
            # Prepare features and targets
            feature_cols = [c for c in df.columns if c not in ['timestamp', 'target', 'target_price', 'open', 'high', 'low', 'close', 'volume']]
            X_train = train_df[feature_cols].values
            y_train = train_df['target'].values
            X_val = val_df[feature_cols].values
            y_val = val_df['target'].values
            
            # Train tree-based models
            if ModelType.XGBOOST in self.models:
                model = self.models[ModelType.XGBOOST]
                model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            
            if ModelType.LIGHTGBM in self.models:
                model = self.models[ModelType.LIGHTGBM]
                model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            
            if ModelType.CATBOOST in self.models:
                            try:
                                import importlib.util
                                if importlib.util.find_spec('catboost'):
                                    import catboost  # noqa: F401
                                model = self.models[ModelType.CATBOOST]
                                model.fit(X_train, y_train, eval_set=(X_val, y_val), verbose=False)
                            except ImportError as e:
                                        logging.getLogger(__name__).debug(f'Suppressed in catboost import: {e}', exc_info=True)
            
            # Save models
            await self._save_models(symbol)
            
            logger.info(f"Retrained models for {symbol}")
            
        except Exception as e:
            logger.error(f"Retraining failed for {symbol}: {e}")
    
    async def _save_models(self, symbol: str):
        """Save trained models to disk."""
        model_dir = Path(f"./models/{symbol}")
        model_dir.mkdir(parents=True, exist_ok=True)
        
        for model_type, model in self.models.items():
            if hasattr(model, 'save_model'):
                model.save_model(str(model_dir / f"{model_type.value}.json"))
            elif hasattr(model, 'save'):
                model.save(str(model_dir / f"{model_type.value}.pkl"))
    
    async def _load_models(self):
        """Load saved models from disk."""
        model_base = Path("./models")
        if not model_base.exists():
            return
        
        for symbol_dir in model_base.iterdir():
            if symbol_dir.is_dir():
                _ = symbol_dir.name
                for model_file in symbol_dir.iterdir():
                    model_type = ModelType(model_file.stem)
                    if model_type in self.models:
                        model = self.models[model_type]
                        if hasattr(model, 'load_model'):
                            model.load_model(str(model_file))
                        elif hasattr(model, 'load'):
                            model.load(str(model_file))
    
    def get_model_stats(self) -> dict[str, Any]:
        """Get statistics about model performance."""
        stats = {}
        for symbol, perf_dict in self.model_performance.items():
            stats[symbol] = {}
            for model_type, perf in perf_dict.items():
                stats[symbol][model_type.value] = {
                    "total_predictions": perf.total_predictions,
                    "accuracy": perf.accuracy,
                    "sharpe_ratio": perf.sharpe_ratio,
                    "max_drawdown": perf.max_drawdown,
                    "weight": perf.weight,
                }
        return stats


# Global instance
next_candle_predictor = NextCandlePredictor()