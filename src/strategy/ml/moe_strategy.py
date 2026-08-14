from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import torch
import torch.nn.functional as F
from loguru import logger
from torch import nn

from src.data.models import Bar, Direction, Signal, SignalType, Timeframe
from src.strategy.base.strategy import Strategy, StrategyConfig
from src.strategy.ml.models import FeatureEngineer, ModelConfig


class Expert(nn.Module):
    """Individual expert network."""
    
    def __init__(self, input_dim: int, hidden_size: int, output_dim: int, dropout: float = 0.1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, output_dim),
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class GatingNetwork(nn.Module):
    """Gating network for Mixture of Experts."""
    
    def __init__(self, input_dim: int, num_experts: int, hidden_size: int, temperature: float = 1.0):
        super().__init__()
        self.num_experts = num_experts
        self.temperature = temperature
        
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, num_experts),
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.net(x)
        # Temperature scaling for sharper/softer routing
        gates = F.softmax(logits / self.temperature, dim=-1)
        return gates


class MixtureOfExperts(nn.Module):
    """Mixture of Experts model for specialized market regime handling."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.input_dim = len(config.input_features)
        self.hidden_size = config.hidden_size
        self.num_experts = getattr(config, 'num_experts', 8)
        self.expert_output_dim = 1  # Return prediction
        
        # Gating network
        self.gating = GatingNetwork(
            self.input_dim, 
            self.num_experts, 
            config.hidden_size,
            temperature=getattr(config, 'gate_temperature', 1.0)
        )
        
        # Expert networks
        self.experts = nn.ModuleList([
            Expert(self.input_dim, config.hidden_size, self.expert_output_dim, config.dropout)
            for _ in range(self.num_experts)
        ])
        
        # Specialized heads
        self.direction_head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Linear(config.hidden_size // 2, 3)  # up, down, sideways
        )
        
        self.confidence_head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Linear(config.hidden_size // 2, 1),
            nn.Sigmoid()
        )
        
        # Load balancing loss coefficient
        self.load_balance_coef = getattr(config, 'load_balance_coef', 0.01)
        
    def forward(self, x: torch.Tensor) -> dict:
        x.size(0)
        
        # Get gating weights
        gates = self.gating(x)  # (batch, num_experts)
        
        # Get expert outputs
        expert_outputs = []
        for expert in self.experts:
            expert_outputs.append(expert(x))  # (batch, 1)
        
        expert_outputs = torch.stack(expert_outputs, dim=1)  # (batch, num_experts, 1)
        
        # Weighted combination
        weighted_output = (gates.unsqueeze(-1) * expert_outputs).sum(dim=1)  # (batch, 1)
        
        # Get expert features for direction/confidence heads
        # Use gated combination of expert hidden states (simplified)
        expert_features = expert_outputs.squeeze(-1)  # (batch, num_experts)
        (gates * expert_features).sum(dim=1)  # (batch)
        
        # Direction prediction
        direction_logits = self.direction_head(
            expert_outputs.squeeze(-1)  # (batch, num_experts)
        )
        
        # Confidence from gate entropy (low entropy = high confidence)
        gate_entropy = -(gates * (gates + 1e-8).log()).sum(dim=1)
        max_entropy = np.log(self.num_experts)
        confidence = 1 - (gate_entropy / max_entropy)
        
        return {
            'return': weighted_output.squeeze(-1),
            'direction': direction_logits,
            'confidence': confidence,
            'gates': gates,
            'expert_outputs': expert_outputs.squeeze(-1),
            'load_balance_loss': gates.mean(0).mul(gates.mean(0).log()).sum() * self.load_balance_coef
        }
    
    def get_expert_specialization(self, x: torch.Tensor) -> dict:
        """Analyze which expert handles which regime."""
        with torch.no_grad():
            gates = self.gating(x)
            expert_outputs = torch.stack([expert(x) for expert in self.experts], dim=1)
            
            # Find dominant expert per sample
            dominant_expert = gates.argmax(dim=1)
            
            return {
                'gates': gates.cpu().numpy(),
                'dominant_expert': dominant_expert.cpu().numpy(),
                'expert_outputs': expert_outputs.squeeze(-1).cpu().numpy()
            }


class MoEStrategy(Strategy):
    """Mixture of Experts Strategy with regime-specialized experts."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model: MixtureOfExperts | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False
        self.num_experts = config.parameters.get("num_experts", 8)
        self.regime_labels = [
            "trending_up", "trending_down", "ranging", "volatile",
            "breakout_up", "breakout_down", "mean_reverting", "low_vol"
        ]
        
    async def _initialize(self) -> None:
        """Initialize MoE model."""
        model_config = ModelConfig(
            model_type="moe",
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
        model_config.num_experts = self.num_experts
        model_config.gate_temperature = self.config.parameters.get("gate_temperature", 1.0)
        model_config.load_balance_coef = self.config.parameters.get("load_balance_coef", 0.01)
        
        self.feature_engineer = FeatureEngineer(model_config)
        self.model = MixtureOfExperts(model_config).to(self.device)
        
        from src.infra.config.settings import settings
        model_path = Path(settings.strategy_ml_models_path) / "moe_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self._model_loaded = True
                logger.info(f"Loaded MoE model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load MoE model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using MoE model."""
        signals = []
        
        if not self._model_loaded or self.model is None:
            return signals
            
        self._bar_buffer.append(bar)
        lookback = self.config.parameters.get("lookback", 100)
        if len(self._bar_buffer) < lookback:
            return signals
            
        self._bar_buffer = self._bar_buffer[-lookback:]
        
        try:
            df = self._bars_to_dataframe(self._bar_buffer)
            df = self.feature_engineer.create_features(df)
            feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
            
            X = df[feature_cols].tail(1).to_numpy()
            X_tensor = torch.FloatTensor(X).unsqueeze(0).to(self.device)
            
            # Predict
            with torch.no_grad():
                pred = self.model(X_tensor)
                
            predicted_return = pred['return'].item()
            direction_logits = pred['direction'][0].cpu().numpy()
            confidence = pred['confidence'].item()
            gates = pred['gates'][0].cpu().numpy()
            
            # Direction from logits
            direction_idx = np.argmax(direction_logits)
            direction_map = {0: Direction.SHORT, 1: Direction.FLAT, 2: Direction.LONG}
            direction = direction_map.get(direction_idx, Direction.FLAT)
            
            if direction == Direction.FLAT:
                return signals
                
            # Use gate confidence
            confidence = confidence * (1 - gates.max()) + 0.5 * gates.max()  # Blend
            confidence = min(max(confidence, 0), 1)
            
            if confidence < self.config.parameters.get("min_confidence", 0.55):
                return signals
                
            # Dominant expert for interpretability
            dominant_expert = int(gates.argmax())
            expert_regime = self.regime_labels[dominant_expert] if dominant_expert < len(self.regime_labels) else "unknown"
            
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
                    "model": "moe",
                    "predicted_return": predicted_return,
                    "direction_logits": direction_logits.tolist(),
                    "confidence": confidence,
                    "gates": gates.tolist(),
                    "dominant_expert": dominant_expert,
                    "expert_regime": expert_regime,
                    "atr": atr,
                    "load_balance_loss": pred.get('load_balance_loss', 0).item() if 'load_balance_loss' in pred else 0,
                }
            )
            
            signals.append(signal)
            await self.on_signal_generated(signal)
            
        except Exception as e:
            logger.error(f"MoEStrategy error: {e}")
            
        return signals
    
    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
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


def create_moe_strategy(config: StrategyConfig) -> Strategy:
    return MoEStrategy(config)
