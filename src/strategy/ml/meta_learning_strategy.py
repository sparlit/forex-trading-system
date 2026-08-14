from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import torch
from loguru import logger
from torch import nn

from src.data.models import Bar, Direction, Signal, SignalType, Timeframe
from src.infra.config.settings import settings
from src.strategy.base.strategy import Strategy, StrategyConfig
from src.strategy.ml.models import FeatureEngineer, ModelConfig


class MAMLModel(nn.Module):
    """Model-Agnostic Meta-Learning (MAML) for fast adaptation to new market regimes."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.input_size = len(config.input_features)
        self.hidden_size = config.hidden_size
        self.output_size = 1  # return prediction
        
        # Base learner (shared across tasks)
        self.base_network = nn.Sequential(
            nn.Linear(self.input_size, self.hidden_size),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(self.hidden_size, self.hidden_size),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(self.hidden_size, self.output_size),
        )
        
        # Task-specific adaptation layers (small)
        self.task_adapters = nn.ModuleDict()
        
    def forward(self, x, task_id: str = "default"):
        # Base prediction
        base_out = self.base_network(x)
        
        # Task-specific adaptation
        if task_id in self.task_adapters:
            adapted = self.task_adapters[task_id](base_out)
            return base_out + adapted
        return base_out
    
    def add_task_adapter(self, task_id: str):
        """Add a new task-specific adapter."""
        self.task_adapters[task_id] = nn.Sequential(
            nn.Linear(self.output_size, self.hidden_size // 4),
            nn.ReLU(),
            nn.Linear(self.hidden_size // 4, self.output_size),
        )
    
    def meta_parameters(self):
        """Parameters for meta-optimization (base network only)."""
        return self.base_network.parameters()
    
    def task_parameters(self, task_id: str):
        """Parameters for task-specific adaptation."""
        if task_id in self.task_adapters:
            return self.task_adapters[task_id].parameters()
        return []


class MetaLearningStrategy(Strategy):
    """Meta-learning strategy that rapidly adapts to new market conditions."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model: MAMLModel | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False
        self.current_regime: str = "unknown"
        self.regime_adapters: dict[str, dict] = {}  # Store adapted params per regime
        self.adaptation_steps = config.parameters.get("adaptation_steps", 5)
        self.meta_lr = config.parameters.get("meta_lr", 0.001)
        self.task_lr = config.parameters.get("task_lr", 0.01)
        
    async def _initialize(self) -> None:
        """Initialize MAML model."""
        model_config = ModelConfig(
            model_type="maml",
            input_features=self.config.parameters.get("input_features", [
                "return_1", "return_5", "log_return", "volatility_20",
                "price_to_sma20", "volume_ratio", "spread_pct", "hl_range_pct",
                "rsi_14", "macd", "bb_upper_20", "bb_lower_20", "atr_14",
                "stoch_k_14", "adx_14", "hour", "weekday"
            ]),
            target=self.config.parameters.get("target", "future_return"),
            lookback=self.config.parameters.get("lookback", 100),
            prediction_horizon=self.config.parameters.get("prediction_horizon", 10),
            hidden_size=self.config.parameters.get("hidden_size", 128),
            num_layers=self.config.parameters.get("num_layers", 2),
            dropout=self.config.parameters.get("dropout", 0.1),
            learning_rate=self.meta_lr,
        )
        
        self.feature_engineer = FeatureEngineer(model_config)
        self.model = MAMLModel(model_config).to(self.device)
        
        # Try to load existing model
        model_path = Path(settings.strategy_ml_models_path) / "maml_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                if 'regime_adapters' in checkpoint:
                    self.regime_adapters = checkpoint['regime_adapters']
                self._model_loaded = True
                logger.info(f"Loaded MAML model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load MAML model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.M15, Timeframe.H1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    
    def _detect_regime(self, bars: list[Bar]) -> str:
        """Detect current market regime."""
        if len(bars) < 20:
            return "unknown"
            
        closes = np.array([b.close for b in bars])
        returns = np.diff(np.log(closes))
        
        # Simple regime detection
        recent_vol = np.std(returns[-20:])
        trend = (closes[-1] - closes[-20]) / closes[-20]
        
        if recent_vol > np.std(returns) * 1.5:
            if abs(trend) > 0.01:
                return "volatile_trending"
            return "volatile_ranging"
        elif abs(trend) > 0.02:
            return "trending"
        return "ranging"
    
    def _adapt_to_regime(self, regime: str, bars: list[Bar]):
        """Fast adaptation to new regime using few gradient steps."""
        if self.model is None or regime in self.regime_adapters:
            return
            
        self.model.add_task_adapter(regime)
        self.model.train()
        
        # Create adaptation data from recent bars
        if len(bars) < self.config.parameters.get("lookback", 100):
            return
            
        df = self._bars_to_dataframe(bars)
        df = self.feature_engineer.create_features(df)
        feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
        
        # Prepare recent data for adaptation
        X = df[feature_cols].tail(50).to_numpy()
        y = df["target"].tail(50).to_numpy() if "target" in df.columns else np.zeros(50)
        
        # Create synthetic target from future returns
        if "target" not in df.columns:
            close_prices = df["close"].to_numpy()
            future_returns = np.zeros(len(close_prices))
            for i in range(len(close_prices) - 10):
                future_returns[i] = (close_prices[i+10] - close_prices[i]) / close_prices[i]
            y = future_returns
            
        X_tensor = torch.FloatTensor(X).to(self.device)
        y_tensor = torch.FloatTensor(y).unsqueeze(-1).to(self.device)
        
        # Fast adaptation (inner loop)
        task_params = list(self.model.task_parameters(regime))
        optimizer = torch.optim.SGD(task_params, lr=self.task_lr)
        
        self.model.train()
        for step in range(self.adaptation_steps):
            optimizer.zero_grad()
            pred = self.model(X_tensor, task_id=regime)
            loss = torch.nn.functional.mse_loss(pred, y_tensor)
            loss.backward()
            optimizer.step()
            
        # Store adapted parameters
        adapted_state = {}
        for name, param in self.model.task_adapters[regime].named_parameters():
            adapted_state[name] = param.data.clone()
        self.regime_adapters[regime] = adapted_state
        
        self.model.eval()
        
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using MAML model with regime adaptation."""
        signals = []
        
        if not self._model_loaded or self.model is None:
            return signals
            
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < self.config.parameters.get("lookback", 100):
            return signals
            
        # Keep buffer size
        self._bar_buffer = self._bar_buffer[-self.config.parameters.get("lookback", 100):]
        
        # Detect regime and adapt if needed
        regime = self._detect_regime(self._bar_buffer)
        if regime != self.current_regime:
            logger.info(f"Regime changed: {self.current_regime} -> {regime}")
            self.current_regime = regime
            self._adapt_to_regime(regime, self._bar_buffer)
            
        try:
            df = self._bars_to_dataframe(self._bar_buffer)
            df = self.feature_engineer.create_features(df)
            feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
            
            X = df[feature_cols].tail(1).to_numpy()
            X_tensor = torch.FloatTensor(X).unsqueeze(0).to(self.device)
            
            # Predict with regime-specific adapter
            with torch.no_grad():
                pred = self.model(X_tensor, task_id=regime)
                predicted_return = pred.item()
                
            # Simple direction logic
            if predicted_return > 0.0001:
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            elif predicted_return < -0.0001:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
            else:
                return signals
                
            confidence = min(abs(predicted_return) * 100, 1.0)
            if confidence < self.config.parameters.get("min_confidence", 0.55):
                return signals
                
            current_price = bar.close
            atr = self._calculate_atr(self._bar_buffer[-14:])
            
            if direction == Direction.LONG:
                entry = current_price
                stop_loss = entry - atr * 2.0
                take_profit = entry + atr * 3.0
            else:
                entry = current_price
                stop_loss = entry + atr * 2.0
                take_profit = entry - atr * 3.0
                
            signal = Signal(
                strategy_id=self.strategy_id,
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                signal_type=signal_type,
                direction=direction,
                strength=confidence,
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "model": "maml",
                    "predicted_return": predicted_return,
                    "regime": regime,
                    "confidence": confidence,
                    "atr": atr,
                    "adapted": regime in self.regime_adapters,
                }
            )
            
            signals.append(signal)
            await self.on_signal_generated(signal)
            
        except Exception as e:
            logger.error(f"MetaLearningStrategy error: {e}")
            
        return signals
    
    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        """Convert bars to polars DataFrame."""
        import polars as pl
        data = []
        for b in bars:
            data.append({
                "timestamp": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "spread": getattr(b, 'spread', 0.0),
            })
        return pl.DataFrame(data)
    
    def _calculate_atr(self, bars: list[Bar]) -> float:
        """Calculate Average True Range."""
        if len(bars) < 2:
            return 0.0
        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        return float(np.mean(true_ranges)) if true_ranges else 0.0


def create_meta_learning_strategy(config: StrategyConfig) -> Strategy:
    return MetaLearningStrategy(config)
