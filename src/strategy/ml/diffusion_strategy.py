from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import torch
from loguru import logger
from torch import nn

from src.data.models import Bar, Direction, Signal, SignalType, Timeframe
from src.strategy.base.strategy import Strategy, StrategyConfig
from src.strategy.ml.models import FeatureEngineer, ModelConfig


class SinusoidalPositionEmbeddings(nn.Module):
    """Sinusoidal positional embeddings for diffusion timesteps."""
    
    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim
        
    def forward(self, t: torch.Tensor) -> torch.Tensor:
        device = t.device
        half_dim = self.dim // 2
        emb = np.log(10000) / (half_dim - 1)
        emb = torch.exp(torch.arange(half_dim, device=device) * -emb)
        emb = t[:, None] * emb[None, :]
        emb = torch.cat([emb.sin(), emb.cos()], dim=-1)
        return emb


class ResidualBlock(nn.Module):
    """Residual block for diffusion model."""
    
    def __init__(self, in_channels: int, out_channels: int, time_emb_dim: int, dropout: float = 0.1):
        super().__init__()
        self.time_mlp = nn.Sequential(
            nn.SiLU(),
            nn.Linear(time_emb_dim, out_channels)
        )
        
        self.block1 = nn.Sequential(
            nn.GroupNorm(8, in_channels),
            nn.SiLU(),
            nn.Conv1d(in_channels, out_channels, 3, padding=1)
        )
        
        self.block2 = nn.Sequential(
            nn.GroupNorm(8, out_channels),
            nn.SiLU(),
            nn.Dropout(dropout),
            nn.Conv1d(out_channels, out_channels, 3, padding=1)
        )
        
        self.residual_conv = nn.Conv1d(in_channels, out_channels, 1) if in_channels != out_channels else nn.Identity()
        
    def forward(self, x: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        h = self.block1(x)
        time_emb = self.time_mlp(t).unsqueeze(-1)
        h = h + time_emb
        h = self.block2(h)
        return h + self.residual_conv(x)


class DiffusionModel(nn.Module):
    """Denoising Diffusion Probabilistic Model for price prediction."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.input_dim = len(config.input_features)
        self.hidden_size = config.hidden_size
        self.n_timesteps = getattr(config, 'diffusion_timesteps', 100)
        
        # Time embedding
        self.time_mlp = nn.Sequential(
            SinusoidalPositionEmbeddings(config.hidden_size),
            nn.Linear(config.hidden_size, config.hidden_size * 4),
            nn.SiLU(),
            nn.Linear(config.hidden_size * 4, config.hidden_size),
        )
        
        # Input projection
        self.input_proj = nn.Conv1d(self.input_dim, config.hidden_size, 1)
        
        # Downsampling
        self.downs = nn.ModuleList([
            ResidualBlock(config.hidden_size, config.hidden_size, config.hidden_size),
            ResidualBlock(config.hidden_size, config.hidden_size * 2, config.hidden_size),
            ResidualBlock(config.hidden_size * 2, config.hidden_size * 2, config.hidden_size),
        ])
        
        # Middle
        self.mid = ResidualBlock(config.hidden_size * 2, config.hidden_size * 2, config.hidden_size)
        
        # Upsampling
        self.ups = nn.ModuleList([
            ResidualBlock(config.hidden_size * 4, config.hidden_size * 2, config.hidden_size),
            ResidualBlock(config.hidden_size * 4, config.hidden_size, config.hidden_size),
            ResidualBlock(config.hidden_size * 2, config.hidden_size, config.hidden_size),
        ])
        
        # Output projection
        self.output_proj = nn.Conv1d(config.hidden_size, self.input_dim, 1)
        
        # Prediction heads
        self.return_head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.SiLU(),
            nn.Linear(config.hidden_size // 2, 1)
        )
        
        self.direction_head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.SiLU(),
            nn.Linear(config.hidden_size // 2, 3)  # up, down, sideways
        )
        
        self.confidence_head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.SiLU(),
            nn.Linear(config.hidden_size // 2, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x: torch.Tensor, t: torch.Tensor) -> dict:
        # x: (batch, seq_len, n_features) -> (batch, n_features, seq_len)
        x = x.transpose(1, 2)
        
        # Time embedding
        t_emb = self.time_mlp(t)
        
        # Input projection
        h = self.input_proj(x)
        
        # Encoder
        skip_connections = []
        for down in self.downs:
            h = down(h, t_emb)
            skip_connections.append(h)
            
        # Middle
        h = self.mid(h, t_emb)
        
        # Decoder
        for up in self.ups:
            skip = skip_connections.pop()
            h = torch.cat([h, skip], dim=1)
            h = up(h, t_emb)
            
        # Output
        denoised = self.output_proj(h)
        
        # Global features for prediction heads
        h.mean(dim=-1)  # (batch, hidden_size*2)
        
        return {
            'denoised': denoised.transpose(1, 2),  # (batch, seq_len, n_features)
            'return': self.return_head(h).squeeze(-1),
            'direction': self.direction_head(h),
            'confidence': self.confidence_head(h).squeeze(-1)
        }


class DiffusionStrategy(Strategy):
    """Diffusion model strategy for probabilistic price prediction."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model: DiffusionModel | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False
        self.n_timesteps = config.parameters.get("diffusion_timesteps", 100)
        self.sampling_steps = config.parameters.get("sampling_steps", 20)
        
    async def _initialize(self) -> None:
        """Initialize diffusion model."""
        model_config = ModelConfig(
            model_type="diffusion",
            input_features=self.config.parameters.get("input_features", [
                "return_1", "return_5", "log_return", "volatility_20",
                "price_to_sma20", "volume_ratio", "spread_pct", "hl_range_pct",
                "rsi_14", "macd", "bb_upper_20", "bb_lower_20", "atr_14",
                "stoch_k_14", "adx_14", "hour", "weekday"
            ]),
            target=self.config.parameters.get("target", "future_return"),
            lookback=self.config.parameters.get("lookback", 100),
            prediction_horizon=self.config.parameters.get("prediction_horizon", 1),
            hidden_size=self.config.parameters.get("hidden_size", 256),
            num_layers=self.config.parameters.get("num_layers", 3),
            dropout=self.config.parameters.get("dropout", 0.1),
            learning_rate=self.config.parameters.get("learning_rate", 0.0001),
        )
        model_config.diffusion_timesteps = self.n_timesteps
        
        self.feature_engineer = FeatureEngineer(model_config)
        self.model = DiffusionModel(model_config).to(self.device)
        
        from src.infra.config.settings import settings
        model_path = Path(settings.strategy_ml_models_path) / "diffusion_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self._model_loaded = True
                logger.info(f"Loaded Diffusion model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load Diffusion model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    
    def _sample(self, x_noisy: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        """DDIM sampling step."""
        with torch.no_grad():
            pred = self.model(x_noisy, t)
            # Simplified DDIM step
            alpha = 1 - (t / self.n_timesteps).float().view(-1, 1, 1)
            x_prev = x_noisy * alpha + pred['denoised'] * (1 - alpha)
        return x_prev
    
    def _generate_samples(self, n_samples: int = 10) -> torch.Tensor:
        """Generate samples from the diffusion model."""
        shape = (n_samples, self.config.parameters.get("lookback", 100), len(self.feature_engineer.config.input_features))
        x = torch.randn(shape, device=self.device)
        
        # DDIM sampling
        timesteps = torch.linspace(self.n_timesteps - 1, 0, self.sampling_steps, device=self.device).long()
        
        for i in range(len(timesteps) - 1):
            t = timesteps[i:i+1].repeat(n_samples)
            x = self._sample(x, t)
            
        return x
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using diffusion model."""
        signals = []
        
        if not self._model_loaded or self.model is None:
            return signals
            
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < self.config.parameters.get("lookback", 100):
            return signals
            
        # Keep buffer size
        self._bar_buffer = self._bar_buffer[-self.config.parameters.get("lookback", 100):]
        
        try:
            df = self._bars_to_dataframe(self._bar_buffer)
            df = self.feature_engineer.create_features(df)
            feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
            
            X = df[feature_cols].tail(1).to_numpy()
            torch.FloatTensor(X).unsqueeze(0).to(self.device)  # (1, 1, n_features)
            
            # Generate multiple samples for uncertainty quantification
            n_samples = 20
            samples = self._generate_samples(n_samples)
            
            # Aggregate predictions
            pred_returns = samples[:, -1, 0].cpu().numpy()  # Last timestep, first feature (return)
            mean_return = np.mean(pred_returns)
            std_return = np.std(pred_returns)
            
            # Direction from mean return
            if mean_return > 0.0001:
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            elif mean_return < -0.0001:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
            else:
                return signals
                
            # Confidence based on prediction consistency
            consistency = 1 - (std_return / (abs(mean_return) + 1e-6))
            consistency = max(0, min(1, consistency))
            
            # Probability of direction
            if direction == Direction.LONG:
                prob = np.mean(pred_returns > 0)
            else:
                prob = np.mean(pred_returns < 0)
                
            confidence = consistency * prob
            
            if confidence < self.config.parameters.get("min_confidence", 0.6):
                return signals
                
            # Calculate entry, SL, TP
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
                    "model": "diffusion",
                    "mean_return": mean_return,
                    "std_return": std_return,
                    "consistency": consistency,
                    "direction_prob": prob,
                    "confidence": confidence,
                    "atr": atr,
                    "n_samples": n_samples,
                }
            )
            
            signals.append(signal)
            await self.on_signal_generated(signal)
            
        except Exception as e:
            logger.error(f"DiffusionStrategy error: {e}")
            
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


def create_diffusion_strategy(config: StrategyConfig) -> Strategy:
    return DiffusionStrategy(config)
