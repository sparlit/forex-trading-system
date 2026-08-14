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


class MultiHeadAttention(nn.Module):
    """Multi-head attention mechanism for time series."""
    
    def __init__(self, d_model: int, n_heads: int, dropout: float = 0.1):
        super().__init__()
        assert d_model % n_heads == 0
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        
        self.w_q = nn.Linear(d_model, d_model)
        self.w_k = nn.Linear(d_model, d_model)
        self.w_v = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, query, key, value, mask=None):
        batch_size = query.size(0)
        
        # Linear projections
        Q = self.w_q(query).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        K = self.w_k(key).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        V = self.w_v(value).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        
        # Scaled dot-product attention
        scores = torch.matmul(Q, K.transpose(-2, -1)) / np.sqrt(self.d_k)
        
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
            
        attn = torch.softmax(scores, dim=-1)
        attn = self.dropout(attn)
        
        context = torch.matmul(attn, V)
        context = context.transpose(1, 2).contiguous().view(batch_size, -1, self.d_model)
        
        return self.w_o(context)


class TransformerEncoderLayer(nn.Module):
    """Single transformer encoder layer."""
    
    def __init__(self, d_model: int, n_heads: int, d_ff: int, dropout: float = 0.1):
        super().__init__()
        self.attention = MultiHeadAttention(d_model, n_heads, dropout)
        self.feed_forward = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model),
        )
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x, mask=None):
        # Self-attention with residual connection
        attn_out = self.attention(x, x, x, mask)
        x = self.norm1(x + self.dropout(attn_out))
        
        # Feed forward with residual connection
        ff_out = self.feed_forward(x)
        x = self.norm2(x + self.dropout(ff_out))
        
        return x


class TransformerModel(nn.Module):
    """Transformer model for financial time series prediction."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.d_model = config.hidden_size
        self.n_heads = getattr(config, 'n_heads', 8)
        self.n_layers = config.num_layers
        self.dropout = config.dropout
        
        # Input projection
        self.input_proj = nn.Linear(len(config.input_features), self.d_model)
        
        # Positional encoding
        self.pos_encoding = PositionalEncoding(self.d_model, config.lookback, config.dropout)
        
        # Transformer encoder layers
        self.encoder_layers = nn.ModuleList([
            TransformerEncoderLayer(self.d_model, self.n_heads, self.d_model * 4, config.dropout)
            for _ in range(self.n_layers)
        ])
        
        # Output heads
        self.return_head = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(self.d_model // 2, 1)
        )
        
        self.direction_head = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(self.d_model // 2, 3)  # long, short, flat
        )
        
        self.confidence_head = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(self.d_model // 2, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x):
        # x shape: (batch, seq_len, n_features)
        x = self.input_proj(x)
        x = self.pos_encoding(x)
        
        # Transformer encoder
        for layer in self.encoder_layers:
            x = layer(x)
            
        # Use last token for prediction
        x = x[:, -1, :]
        
        return {
            'return': self.return_head(x),
            'direction': self.direction_head(x),
            'confidence': self.confidence_head(x)
        }


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding."""
    
    def __init__(self, d_model: int, max_len: int, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        
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


class TransformerStrategy(Strategy):
    """Transformer-based trading strategy for multi-horizon prediction."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model: TransformerModel | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False
        
    async def _initialize(self) -> None:
        """Initialize transformer model."""
        model_config = ModelConfig(
            model_type="transformer",
            input_features=self.config.parameters.get("input_features", [
                "return_1", "return_5", "log_return", "volatility_20",
                "price_to_sma20", "volume_ratio", "spread_pct", "hl_range_pct",
                "rsi_14", "macd", "bb_upper_20", "bb_lower_20", "atr_14",
                "stoch_k_14", "adx_14", "hour", "weekday"
            ]),
            target=self.config.parameters.get("target", "future_return"),
            lookback=self.config.parameters.get("lookback", 100),
            prediction_horizon=self.config.parameters.get("prediction_horizon", 10),
            hidden_size=self.config.parameters.get("hidden_size", 256),
            num_layers=self.config.parameters.get("num_layers", 4),
            dropout=self.config.parameters.get("dropout", 0.1),
            learning_rate=self.config.parameters.get("learning_rate", 0.0001),
        )
        
        self.feature_engineer = FeatureEngineer(model_config)
        self.model = TransformerModel(model_config).to(self.device)
        
        # Try to load existing model
        model_path = Path(settings.strategy_ml_models_path) / "transformer_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self._model_loaded = True
                logger.info(f"Loaded Transformer model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load Transformer model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using Transformer model."""
        signals = []
        
        if not self._model_loaded or self.model is None:
            return signals
            
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < self.config.parameters.get("lookback", 100):
            return signals
            
        # Keep only recent bars
        self._bar_buffer = self._bar_buffer[-self.config.parameters.get("lookback", 100):]
        
        # Convert to DataFrame and create features
        try:
            df = self._bars_to_dataframe(self._bar_buffer)
            if len(df) < self.config.parameters.get("lookback", 100):
                return signals
                
            df = self.feature_engineer.create_features(df)
            feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
            
            # Prepare input tensor
            X = df[feature_cols].to_numpy()
            X = torch.FloatTensor(X).unsqueeze(0).to(self.device)  # (1, seq_len, n_features)
            
            # Predict
            with torch.no_grad():
                predictions = self.model(X)
                
            predicted_return = predictions['return'].item()
            direction_logits = predictions['direction'][0]
            confidence = predictions['confidence'].item()
            
            direction_idx = torch.argmax(direction_logits).item()
            direction_map = {0: Direction.SHORT, 1: Direction.FLAT, 2: Direction.LONG}
            direction = direction_map.get(direction_idx, Direction.FLAT)
            
            if direction == Direction.FLAT or confidence < self.config.parameters.get("min_confidence", 0.6):
                return signals
                
            # Calculate entry, SL, TP
            current_price = bar.close
            atr = self._calculate_atr(self._bar_buffer[-14:])
            
            if direction == Direction.LONG:
                entry = current_price
                stop_loss = entry - atr * 2.0
                take_profit = entry + atr * 3.0
                signal_type = SignalType.ENTRY_LONG
            else:
                entry = current_price
                stop_loss = entry + atr * 2.0
                take_profit = entry - atr * 3.0
                signal_type = SignalType.ENTRY_SHORT
                
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
                    "model": "transformer",
                    "predicted_return": predicted_return,
                    "direction_logits": direction_logits.tolist(),
                    "confidence": confidence,
                    "atr": atr,
                }
            )
            
            signals.append(signal)
            await self.on_signal_generated(signal)
            
        except Exception as e:
            logger.error(f"TransformerStrategy error: {e}")
            
        return signals
    
    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        """Convert bars to polars DataFrame."""
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


# Register the strategy
def create_transformer_strategy(config: StrategyConfig) -> Strategy:
    return TransformerStrategy(config)
