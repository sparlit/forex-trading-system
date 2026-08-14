"""
Model Persistence & Registry
============================

Provides persistent model storage with versioning, metadata, and automatic loading.
Models are saved to disk and loaded on startup to avoid retraining.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from loguru import logger
from torch import nn

from src.infra.config.settings import settings
from src.strategy.ml.models import (
    MLModelTrainer,
    ModelConfig,
)


@dataclass
class ModelMetadata:
    """Metadata for a trained model."""
    model_id: str
    model_type: str
    symbol: str
    timeframe: str
    version: str
    created_at: datetime
    updated_at: datetime
    training_samples: int
    validation_loss: float
    training_loss: float
    config: dict[str, Any]
    metrics: dict[str, float]
    feature_names: list[str]
    tags: list[str] = None
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        d["tags"] = self.tags or []
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> ModelMetadata:
        d = d.copy()
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["updated_at"] = datetime.fromisoformat(d["updated_at"])
        d["tags"] = d.get("tags") or []
        return cls(**d)


class ModelRegistry:
    """
    Centralized model registry with versioning and persistence.
    
    Features:
    - Model versioning with semantic versioning
    - Automatic best model selection
    - Model metadata storage
    - Symbol/timeframe specific models
    - Automatic cleanup of old versions
    """
    
    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path or settings.strategy_ml_models_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self._models: dict[str, nn.Module] = {}
        self._metadata: dict[str, ModelMetadata] = {}
        self._load_registry()
    
    def _get_model_key(self, model_type: str, symbol: str, timeframe: str) -> str:
        return f"{model_type}_{symbol}_{timeframe}"
    
    def _get_model_dir(self, model_type: str, symbol: str, timeframe: str) -> Path:
        key = self._get_model_key(model_type, symbol, timeframe)
        return self.base_path / key
    
    def _get_version_path(self, model_dir: Path, version: str) -> Path:
        return model_dir / f"v{version}"
    
    def _load_registry(self) -> None:
        """Load all model metadata from disk."""
        for model_dir in self.base_path.iterdir():
            if not model_dir.is_dir():
                continue
            
            meta_file = model_dir / "metadata.json"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        data = json.load(f)
                    metadata = ModelMetadata.from_dict(data)
                    self._metadata[metadata.model_id] = metadata
                    logger.info(f"Loaded model metadata: {metadata.model_id} v{metadata.version}")
                except Exception as e:
                    logger.warning(f"Failed to load metadata from {model_dir}: {e}")
    
    def register_model(
        self,
        trainer: MLModelTrainer,
        symbol: str,
        timeframe: str,
        version: str,
        training_samples: int,
        metrics: dict[str, float],
        tags: list[str] | None = None,
    ) -> ModelMetadata:
        """
        Register a trained model with versioning.
        
        Args:
            trainer: Trained MLModelTrainer instance
            symbol: Trading symbol
            timeframe: Timeframe string
            version: Semantic version (e.g., "1.0.0")
            training_samples: Number of training samples used
            metrics: Validation/training metrics
            tags: Optional tags for categorization
            
        Returns:
            ModelMetadata for the registered model
        """
        model_type = trainer.config.model_type
        model_dir = self._get_model_dir(model_type, symbol, timeframe)
        model_dir.mkdir(parents=True, exist_ok=True)
        
        version_path = self._get_version_path(model_dir, version)
        version_path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = version_path / "model.pt"
        trainer.save_model(model_path)
        
        # Save feature engineer
        _fe_path = version_path / "feature_engineer.pkl"
        trainer.feature_engineer.save_scalers(version_path)
        
        # Create metadata
        metadata = ModelMetadata(
            model_id=f"{model_type}_{symbol}_{timeframe}",
            model_type=model_type,
            symbol=symbol,
            timeframe=timeframe,
            version=version,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            training_samples=training_samples,
            validation_loss=metrics.get("val_loss", float("inf")),
            training_loss=metrics.get("train_loss", float("inf")),
            config=trainer.config.__dict__,
            metrics=metrics,
            feature_names=trainer.config.input_features,
            tags=tags or [],
        )
        
        # Save metadata
        meta_file = version_path / "metadata.json"
        with open(meta_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        # Update registry
        self._metadata[metadata.model_id] = metadata
        
        # Create/update latest symlink
        latest_path = model_dir / "latest"
        if latest_path.exists() or latest_path.is_symlink():
            latest_path.unlink()
        latest_path.symlink_to(version_path.name)
        
        logger.info(f"Registered model: {metadata.model_id} v{version}")
        return metadata
    
    def get_best_model(self, model_type: str, symbol: str, timeframe: str) -> ModelMetadata | None:
        """Get the best model for a symbol/timeframe based on validation loss."""
        key = f"{model_type}_{symbol}_{timeframe}"
        candidates = [m for m in self._metadata.values() if m.model_id == key]
        
        if not candidates:
            return None
        
        # Return model with lowest validation loss
        return min(candidates, key=lambda m: m.validation_loss)
    
    def load_model(
        self,
        model_type: str,
        symbol: str,
        timeframe: str,
        version: str = "latest",
    ) -> MLModelTrainer | None:
        """
        Load a trained model.
        
        Args:
            model_type: "lstm" or "transformer"
            symbol: Trading symbol
            timeframe: Timeframe string
            version: Version string or "latest"
            
        Returns:
            MLModelTrainer with loaded model, or None if not found
        """
        key = f"{model_type}_{symbol}_{timeframe}"
        model_dir = self._get_model_dir(model_type, symbol, timeframe)
        
        if version == "latest":
            latest_path = model_dir / "latest"
            if not latest_path.exists():
                logger.warning(f"No latest model found for {key}")
                return None
            version_path = latest_path
        else:
            version_path = self._get_version_path(model_dir, version)
            if not version_path.exists():
                logger.warning(f"Model version {version} not found for {key}")
                return None
        
        model_path = version_path / "model.pt"
        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return None
        
        # Load metadata
        meta_file = version_path / "metadata.json"
        if not meta_file.exists():
            logger.warning(f"Metadata not found: {meta_file}")
            return None
        
        with open(meta_file) as f:
            metadata_dict = json.load(f)
        metadata = ModelMetadata.from_dict(metadata_dict)
        
        # Create trainer with config
        config = ModelConfig(**metadata.config)
        trainer = MLModelTrainer(config)
        
        # Build model with correct input size
        input_size = len(config.input_features)
        trainer.build_model(input_size)
        
        # Load model weights
        checkpoint = torch.load(model_path, map_location=trainer.device)
        trainer.model.load_state_dict(checkpoint["model_state_dict"])
        trainer.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        trainer.model.to(trainer.device)
        trainer.model.eval()
        
        # Load feature engineer
        fe_path = version_path / "feature_engineer.pkl"
        if fe_path.exists():
            trainer.feature_engineer.load_scalers(version_path)
        
        logger.info(f"Loaded model: {key} v{metadata.version}")
        return trainer
    
    def list_models(self, model_type: str | None = None) -> list[ModelMetadata]:
        """List all registered models, optionally filtered by type."""
        models = list(self._metadata.values())
        if model_type:
            models = [m for m in models if m.model_type == model_type]
        return sorted(models, key=lambda m: (m.symbol, m.timeframe, m.version))
    
    def delete_model(self, model_type: str, symbol: str, timeframe: str, version: str) -> bool:
        """Delete a specific model version."""
        model_dir = self._get_model_dir(model_type, symbol, timeframe)
        version_path = self._get_version_path(model_dir, version)
        
        if not version_path.exists():
            return False
        
        # Don't delete if it's the latest
        latest_path = model_dir / "latest"
        if latest_path.exists() and latest_path.readlink() == version_path.name:
            logger.warning(f"Cannot delete {version}, it's the latest version")
            return False
        
        shutil.rmtree(version_path)
        
        # Remove from metadata
        key = f"{model_type}_{symbol}_{timeframe}"
        if key in self._metadata:
            del self._metadata[key]
        
        logger.info(f"Deleted model: {key} v{version}")
        return True
    
    def cleanup_old_versions(self, keep: int = 5) -> int:
        """Clean up old model versions, keeping only the most recent N versions per model."""
        deleted = 0
        
        # Group by model_id
        by_model: dict[str, list[ModelMetadata]] = {}
        for metadata in self._metadata.values():
            if metadata.model_id not in by_model:
                by_model[metadata.model_id] = []
            by_model[metadata.model_id].append(metadata)
        
        for versions in by_model.values():
            # Sort by version (assuming semantic versioning)
            versions.sort(key=lambda v: tuple(map(int, v.version.split("."))), reverse=True)
            
            # Delete old versions beyond keep limit
            for old_version in versions[keep:]:
                parts = old_version.model_id.split("_")
                if len(parts) == 3:
                    self.delete_model(parts[0], parts[1], parts[2], old_version.version)
                    deleted += 1
        
        return deleted


# Global registry instance
_model_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get or create global model registry."""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry


def init_model_registry(base_path: str | None = None) -> ModelRegistry:
    """Initialize global model registry."""
    global _model_registry
    _model_registry = ModelRegistry(base_path)
    return _model_registry


async def train_and_register_model(
    model_type: str,
    symbol: str,
    timeframe: str,
    training_data: Any,
    config: ModelConfig | None = None,
    version: str | None = None,
) -> ModelMetadata:
    """
    Convenience function to train and register a model in one call.
    
    Args:
        model_type: "lstm" or "transformer"
        symbol: Trading symbol
        timeframe: Timeframe string
        training_data: DataFrame with training data
        config: Optional model config
        version: Version string (auto-generated if not provided)
        
    Returns:
        ModelMetadata for the registered model
    """
    registry = get_model_registry()
    
    if config is None:
        config = ModelConfig(
            model_type=model_type,
            input_features=settings.strategy_feature_lookback,
            target="future_return",
            lookback=settings.strategy_feature_lookback,
            prediction_horizon=settings.strategy_prediction_horizon,
        )
    
    if version is None:
        # Generate version from timestamp
        version = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    
    trainer = MLModelTrainer(config)
    trainer.build_model(len(config.input_features))
    
    # Prepare training data
    X, y = trainer.feature_engineer.prepare_sequences(
        training_data,
        lookback=config.lookback,
        horizon=config.prediction_horizon,
    )
    
    if len(X) == 0:
        raise ValueError("Insufficient training data")
    
    # Split train/val
    split_idx = int(len(X) * 0.8)
    train_X, val_X = X[:split_idx], X[split_idx:]
    train_y, val_y = y[:split_idx], y[split_idx:]
    
    from torch.utils.data import DataLoader, TensorDataset
    
    train_dataset = TensorDataset(torch.FloatTensor(train_X), torch.FloatTensor(train_y))
    val_dataset = TensorDataset(torch.FloatTensor(val_X), torch.FloatTensor(val_y))
    
    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=config.batch_size, shuffle=False)
    
    # Train
    history = trainer.train(train_loader, val_loader)
    
    # Register
    metrics = {
        "train_loss": history["train_loss"][-1] if history["train_loss"] else float("inf"),
        "val_loss": history["val_loss"][-1] if history["val_loss"] else float("inf"),
    }
    
    return registry.register_model(
        trainer=trainer,
        symbol=symbol,
        timeframe=timeframe,
        version=version,
        training_samples=len(X),
        metrics=metrics,
        tags=[model_type, timeframe],
    )


# Example usage
if __name__ == "__main__":
    import asyncio

    
    async def example():
        registry = get_model_registry()
        
        # List existing models
        models = registry.list_models()
        for m in models:
            print(f"{m.model_id} v{m.version} - val_loss: {m.validation_loss:.6f}")
        
        # Load a model
        trainer = registry.load_model("lstm", "EURUSD", "5m", "latest")
        if trainer:
            print("Model loaded successfully")
    
    asyncio.run(example())