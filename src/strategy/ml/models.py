from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import torch
from loguru import logger
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from torch import nn, optim

from src.infra.config.settings import settings

if TYPE_CHECKING:
    from src.strategy.ml.model_registry import ModelMetadata


@dataclass
class ModelConfig:
    """Configuration for ML models."""
    model_type: str  # "lstm", "transformer", "lightgbm", "xgboost"
    input_features: list[str]
    target: str
    lookback: int = 100
    prediction_horizon: int = 10
    hidden_size: int = 128
    num_layers: int = 2
    dropout: float = 0.2
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 100
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


class FeatureEngineer:
    """Feature engineering for ML models."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.scaler: StandardScaler | None = None
        self.target_scaler: MinMaxScaler | None = None
        self._fitted = False

    def create_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Create all features for ML models."""
        # Price-based features
        df = df.with_columns([
            # Returns
            pl.col("close").pct_change().alias("return_1"),
            pl.col("close").pct_change(5).alias("return_5"),
            pl.col("close").pct_change(20).alias("return_20"),

            # Log returns
            (pl.col("close").log() - pl.col("close").shift(1).log()).alias("log_return"),

            # Volatility
            pl.col("close").pct_change().rolling_std(window_size=20).alias("volatility_20"),
            pl.col("close").pct_change().rolling_std(window_size=50).alias("volatility_50"),

            # Price relative to MAs
            (pl.col("close") / pl.col("close").rolling_mean(window_size=20) - 1).alias("price_to_sma20"),
            (pl.col("close") / pl.col("close").rolling_mean(window_size=50) - 1).alias("price_to_sma50"),

            # Volume features
            (pl.col("volume") / pl.col("volume").rolling_mean(window_size=20)).alias("volume_ratio"),
            pl.col("volume").pct_change().alias("volume_change"),

            # Spread features
            (pl.col("spread") / pl.col("close")).alias("spread_pct"),

            # High-Low range
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("hl_range_pct"),

            # Time features
            pl.col("timestamp").dt.hour().alias("hour"),
            pl.col("timestamp").dt.weekday().alias("weekday"),
            pl.col("timestamp").dt.month().alias("month"),
        ])

        # Technical indicators (using existing indicator functions)
        from src.strategy.technical.indicators import TechnicalIndicators
        df = TechnicalIndicators.add_all_indicators_polars(df)

        # Candlestick patterns
        from src.strategy.technical.indicators import CandlestickPatterns
        df = CandlestickPatterns.detect_all_patterns(df)

        return df

    def prepare_sequences(
        self,
        df: pl.DataFrame,
        lookback: int | None = None,
        horizon: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for training."""
        lookback = lookback or self.config.lookback
        horizon = horizon or self.config.prediction_horizon

        # Select feature columns (exclude non-numeric)
        feature_cols = [c for c in df.columns if c not in [
            "timestamp", "symbol", "timeframe", "source", "is_complete"
        ]]

        # Drop rows with NaN
        df_clean = df.select(feature_cols).drop_nulls()

        if len(df_clean) < lookback + horizon:
            return np.array([]), np.array([])

        # Scale features
        if not self._fitted:
            self.scaler = StandardScaler()
            self.target_scaler = MinMaxScaler()
            self.scaler.fit(df_clean.to_numpy())
            self.target_scaler.fit(df_clean["close"].to_numpy().reshape(-1, 1))
            self._fitted = True

        data_scaled = self.scaler.transform(df_clean.to_numpy())

        # Create sequences
        X, y = [], []
        for i in range(lookback, len(data_scaled) - horizon):
            X.append(data_scaled[i - lookback:i])
            # Target: future return
            future_return = (df_clean["close"][i + horizon] - df_clean["close"][i]) / df_clean["close"][i]
            y.append(future_return)

        return np.array(X), np.array(y)

    def save_scalers(self, path: Path) -> None:
        """Save fitted scalers."""
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "feature_scaler.pkl", "wb") as f:
            pickle.dump(self.scaler, f)
        with open(path / "target_scaler.pkl", "wb") as f:
            pickle.dump(self.target_scaler, f)

    def load_scalers(self, path: Path) -> None:
        """Load fitted scalers."""
        with open(path / "feature_scaler.pkl", "rb") as f:
            self.scaler = pickle.load(f)
        with open(path / "target_scaler.pkl", "rb") as f:
            self.target_scaler = pickle.load(f)
        self._fitted = True


class LSTMModel(nn.Module):
    """LSTM model for time series prediction."""

    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.2, output_size: int = 1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
        )

        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, input_size)
        lstm_out, (_h_n, _c_n) = self.lstm(x)
        # Use last hidden state
        out = self.dropout(lstm_out[:, -1, :])
        out = self.fc(out)
        return out


class TransformerModel(nn.Module):
    """Transformer model for time series prediction."""

    def __init__(
        self,
        input_size: int,
        d_model: int = 128,
        nhead: int = 8,
        num_layers: int = 4,
        dropout: float = 0.2,
        output_size: int = 1,
        max_seq_len: int = 500,
    ):
        super().__init__()
        self.d_model = d_model
        self.input_projection = nn.Linear(input_size, d_model)

        # Positional encoding
        self.pos_encoding = nn.Parameter(torch.zeros(1, max_seq_len, d_model))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(d_model, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, input_size)
        seq_len = x.size(1)

        # Project input
        x = self.input_projection(x)

        # Add positional encoding
        x = x + self.pos_encoding[:, :seq_len, :]

        # Transformer
        x = self.transformer(x)

        # Use last token
        x = self.dropout(x[:, -1, :])
        x = self.fc(x)
        return x


class MLModelTrainer:
    """Trainer for ML models."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.device = torch.device(config.device)
        self.model: nn.Module | None = None
        self.optimizer: optim.Optimizer | None = None
        self.criterion = nn.MSELoss()
        self.scheduler: optim.lr_scheduler._LRScheduler | None = None
        self.feature_engineer = FeatureEngineer(config)

    def build_model(self, input_size: int) -> nn.Module:
        """Build model based on config."""
        if self.config.model_type == "lstm":
            self.model = LSTMModel(
                input_size=input_size,
                hidden_size=self.config.hidden_size,
                num_layers=self.config.num_layers,
                dropout=self.config.dropout,
            )
        elif self.config.model_type == "transformer":
            self.model = TransformerModel(
                input_size=input_size,
                d_model=self.config.hidden_size,
                num_layers=self.config.num_layers,
                dropout=self.config.dropout,
            )
        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")

        self.model.to(self.device)

        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=1e-5,
        )

        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode="min", patience=10, factor=0.5
        )

        return self.model

    def train_epoch(self, dataloader) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0

        for batch_x, batch_y in dataloader:
            batch_x = batch_x.to(self.device)
            batch_y = batch_y.to(self.device)

            self.optimizer.zero_grad()
            outputs = self.model(batch_x)
            loss = self.criterion(outputs.squeeze(), batch_y)
            loss.backward()

            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

            self.optimizer.step()
            total_loss += loss.item()

        return total_loss / len(dataloader)

    def validate(self, dataloader) -> float:
        """Validate model."""
        self.model.eval()
        total_loss = 0.0

        with torch.no_grad():
            for batch_x, batch_y in dataloader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                outputs = self.model(batch_x)
                loss = self.criterion(outputs.squeeze(), batch_y)
                total_loss += loss.item()

        return total_loss / len(dataloader)

    def train(
        self,
        train_dataloader,
        val_dataloader,
        epochs: int | None = None,
    ) -> dict[str, list[float]]:
        """Full training loop."""
        epochs = epochs or self.config.epochs
        history = {"train_loss": [], "val_loss": []}

        best_val_loss = float("inf")
        patience_counter = 0
        max_patience = 20

        for epoch in range(epochs):
            train_loss = self.train_epoch(train_dataloader)
            val_loss = self.validate(val_dataloader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            self.scheduler.step(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save best model
                self.save_model(Path(settings.strategy_ml_models_path) / f"{self.config.model_type}_best.pt")
            else:
                patience_counter += 1

            if epoch % 10 == 0:
                logger.info(f"Epoch {epoch}: train_loss={train_loss:.6f}, val_loss={val_loss:.6f}")

            if patience_counter >= max_patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions."""
        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X).to(self.device)
            outputs = self.model(X_tensor)
            return outputs.cpu().numpy()

    def save_model(self, path: Path) -> None:
        """Save model and config."""
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "config": self.config,
            "feature_engineer": self.feature_engineer,
        }, path)

    def save_model_with_registry(
        self,
        symbol: str,
        timeframe: str,
        version: str,
        training_samples: int,
        metrics: dict[str, float],
        tags: list[str] | None = None,
    ) -> ModelMetadata:
        """Save model using the model registry."""
        from src.strategy.ml.model_registry import get_model_registry
        registry = get_model_registry()
        return registry.register_model(
            trainer=self,
            symbol=symbol,
            timeframe=timeframe,
            version=version,
            training_samples=training_samples,
            metrics=metrics,
            tags=tags,
        )

    def load_model(self, path: Path) -> None:
        """Load model and config."""
        checkpoint = torch.load(path, map_location=self.device)
        self.config = checkpoint["config"]
        self.feature_engineer = checkpoint["feature_engineer"]

        # Rebuild model
        input_size = len(self.config.input_features)
        self.build_model(input_size)

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.model.to(self.device)

    @classmethod
    def load_from_registry(
        cls,
        model_type: str,
        symbol: str,
        timeframe: str,
        version: str = "latest",
    ) -> MLModelTrainer | None:
        """Load model from registry."""
        from src.strategy.ml.model_registry import get_model_registry
        registry = get_model_registry()
        return registry.load_model(model_type, symbol, timeframe, version)


class OnlineLearner:
    """Online/incremental learning using River."""

    def __init__(self, model_type: str = "linear"):
        try:
            from river import compose, linear_model, metrics, preprocessing
            self.has_river = True

            if model_type == "linear":
                self.model = compose.Pipeline(
                    preprocessing.StandardScaler(),
                    linear_model.LinearRegression(intercept_lr=0.01),
                )
            elif model_type == "sgd":
                self.model = compose.Pipeline(
                    preprocessing.StandardScaler(),
                    linear_model.LinearRegression(intercept_lr=0.01, optimizer=optim.SGD(lr=0.01)),
                )
            else:
                self.model = compose.Pipeline(
                    preprocessing.StandardScaler(),
                    linear_model.LinearRegression(),
                )

            self.metric = metrics.MAE()
        except ImportError:
            self.has_river = False
            logger.warning("River not installed, online learning disabled")

    def learn_one(self, features: dict[str, float], target: float) -> float:
        """Update model with one sample."""
        if not self.has_river:
            return 0.0

        pred = self.model.predict_one(features)
        self.model.learn_one(features, target)
        self.metric.update(target, pred)
        return pred

    def predict_one(self, features: dict[str, float]) -> float:
        """Predict for one sample."""
        if not self.has_river:
            return 0.0
        return self.model.predict_one(features)

    def get_metric(self) -> float:
        """Get current metric."""
        if not self.has_river:
            return 0.0
        return self.metric.get()