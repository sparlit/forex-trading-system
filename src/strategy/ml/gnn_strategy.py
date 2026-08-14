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


class GraphConvolution(nn.Module):
    """Graph Convolutional Network layer."""
    
    def __init__(self, in_features: int, out_features: int, bias: bool = True):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        if bias:
            self.bias = nn.Parameter(torch.FloatTensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()
        
    def reset_parameters(self):
        stdv = 1. / np.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)
            
    def forward(self, x, adj):
        # x: (batch, n_nodes, in_features)
        # adj: (n_nodes, n_nodes) - adjacency matrix
        support = torch.matmul(x, self.weight)  # (batch, n_nodes, out_features)
        output = torch.matmul(adj.unsqueeze(0), support)  # (batch, n_nodes, out_features)
        if self.bias is not None:
            output = output + self.bias
        return output


class GraphAttentionLayer(nn.Module):
    """Graph Attention Network layer."""
    
    def __init__(self, in_features: int, out_features: int, dropout: float = 0.1, alpha: float = 0.2, concat: bool = True):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.dropout = dropout
        self.alpha = alpha
        self.concat = concat
        
        self.W = nn.Parameter(torch.zeros(size=(in_features, out_features)))
        nn.init.xavier_uniform_(self.W.data, gain=1.414)
        self.a = nn.Parameter(torch.zeros(size=(2 * out_features, 1)))
        nn.init.xavier_uniform_(self.a.data, gain=1.414)
        
        self.leakyrelu = nn.LeakyReLU(self.alpha)
        
    def forward(self, h, adj):
        # h: (batch, n_nodes, in_features)
        # adj: (n_nodes, n_nodes)
        Wh = torch.matmul(h, self.W)  # (batch, n_nodes, out_features)
        batch_size, n_nodes, _ = Wh.size()
        
        # Compute attention coefficients
        a_input = torch.cat([
            Wh.repeat(1, 1, n_nodes).view(batch_size, n_nodes * n_nodes, -1),
            Wh.repeat(1, n_nodes, 1)
        ], dim=-1).view(batch_size, n_nodes, n_nodes, 2 * self.out_features)
        
        e = self.leakyrelu(torch.matmul(a_input, self.a).squeeze(-1))  # (batch, n_nodes, n_nodes)
        
        # Mask with adjacency matrix
        zero_vec = -9e15 * torch.ones_like(e)
        attention = torch.where(adj.unsqueeze(0) > 0, e, zero_vec)
        attention = torch.softmax(attention, dim=-1)
        attention = torch.dropout(attention, self.dropout, train=self.training)
        
        h_prime = torch.matmul(attention, Wh)  # (batch, n_nodes, out_features)
        
        if self.concat:
            return torch.elu(h_prime)
        else:
            return h_prime


class GNNModel(nn.Module):
    """Graph Neural Network for multi-asset price prediction."""
    
    def __init__(self, config: ModelConfig, n_assets: int):
        super().__init__()
        self.config = config
        self.n_assets = n_assets
        self.hidden_size = config.hidden_size
        
        # Asset-specific feature encoders
        self.asset_encoders = nn.ModuleList([
            nn.Sequential(
                nn.Linear(len(config.input_features), config.hidden_size),
                nn.ReLU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.hidden_size, config.hidden_size),
            )
            for _ in range(n_assets)
        ])
        
        # Graph layers
        self.gat1 = GraphAttentionLayer(config.hidden_size, config.hidden_size, config.dropout)
        self.gat2 = GraphAttentionLayer(config.hidden_size, config.hidden_size, config.dropout, concat=False)
        
        # Cross-asset correlation learning
        self.correlation_net = nn.Sequential(
            nn.Linear(config.hidden_size * 2, config.hidden_size),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size, n_assets),  # Predict correlations
        )
        
        # Output heads per asset
        self.return_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(config.hidden_size, config.hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.hidden_size // 2, 1)
            )
            for _ in range(n_assets)
        ])
        
        self.direction_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(config.hidden_size, config.hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.hidden_size // 2, 3)  # long, short, flat
            )
            for _ in range(n_assets)
        ])
        
        self.confidence_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(config.hidden_size, config.hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.hidden_size // 2, 1),
                nn.Sigmoid()
            )
            for _ in range(n_assets)
        ])
        
    def forward(self, x, adj_matrix):
        """
        x: (batch, n_assets, seq_len, n_features)
        adj_matrix: (n_assets, n_assets) - learned or static correlation matrix
        """
        _batch_size, n_assets, _seq_len, _n_features = x.size()
        
        # Encode each asset's time series independently
        asset_embeddings = []
        for i in range(n_assets):
            # Take last timestep for each asset
            asset_seq = x[:, i, :, :]  # (batch, seq_len, n_features)
            # Use a simple LSTM or take mean
            encoded = self.asset_encoders[i](asset_seq.mean(dim=1))  # (batch, hidden_size)
            asset_embeddings.append(encoded)
            
        # Stack: (batch, n_assets, hidden_size)
        h = torch.stack(asset_embeddings, dim=1)
        
        # Apply graph attention layers
        h = self.gat1(h, adj_matrix)
        h = self.gat2(h, adj_matrix)
        
        # Generate outputs for each asset
        returns = []
        directions = []
        confidences = []
        
        for i in range(n_assets):
            asset_h = h[:, i, :]  # (batch, hidden_size)
            returns.append(self.return_heads[i](asset_h))
            directions.append(self.direction_heads[i](asset_h))
            confidences.append(self.confidence_heads[i](asset_h))
            
        return {
            'returns': torch.cat(returns, dim=-1),  # (batch, n_assets)
            'directions': torch.stack(directions, dim=1),  # (batch, n_assets, 3)
            'confidences': torch.cat(confidences, dim=-1),  # (batch, n_assets)
            'embeddings': h
        }


class GNNStrategy(Strategy):
    """Graph Neural Network strategy for cross-asset arbitrage and correlation trading."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model: GNNModel | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffers: dict[str, list[Bar]] = {}
        self._model_loaded = False
        self.adj_matrix: torch.Tensor | None = None
        
    async def _initialize(self) -> None:
        """Initialize GNN model."""
        symbols = self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"])
        n_assets = len(symbols)
        
        model_config = ModelConfig(
            model_type="gnn",
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
            learning_rate=self.config.parameters.get("learning_rate", 0.001),
        )
        
        self.feature_engineer = FeatureEngineer(model_config)
        self.model = GNNModel(model_config, n_assets).to(self.device)
        
        # Initialize adjacency matrix from historical correlations
        self.adj_matrix = self._initialize_adjacency(symbols).to(self.device)
        
        # Try to load existing model
        model_path = Path(settings.strategy_ml_models_path) / "gnn_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                if 'adj_matrix' in checkpoint:
                    self.adj_matrix = checkpoint['adj_matrix'].to(self.device)
                self._model_loaded = True
                logger.info(f"Loaded GNN model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load GNN model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.H1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"])
    
    def _initialize_adjacency(self, symbols: list[str]) -> torch.Tensor:
        """Initialize adjacency matrix from known currency relationships."""
        n = len(symbols)
        adj = torch.eye(n)  # Start with identity
        
        # Add known currency relationships
        # e.g., EURUSD and GBPUSD share USD, so they're correlated
        base_currencies = [s[:3] for s in symbols]
        quote_currencies = [s[3:] for s in symbols]
        
        for i in range(n):
            for j in range(i+1, n):
                # Same base currency
                if base_currencies[i] == base_currencies[j]:
                    adj[i, j] = adj[j, i] = 0.8
                # Same quote currency
                elif quote_currencies[i] == quote_currencies[j]:
                    adj[i, j] = adj[j, i] = 0.7
                # Major pairs
                elif base_currencies[i] in ["EUR", "GBP", "AUD"] and base_currencies[j] in ["EUR", "GBP", "AUD"]:
                    adj[i, j] = adj[j, i] = 0.5
                    
        return adj
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using GNN model."""
        signals = []
        
        if not self._model_loaded or self.model is None:
            return signals
            
        symbol = bar.symbol
        if symbol not in self.required_symbols:
            return signals
            
        # Update buffer
        if symbol not in self._bar_buffers:
            self._bar_buffers[symbol] = []
        self._bar_buffers[symbol].append(bar)
        
        lookback = self.config.parameters.get("lookback", 100)
        if len(self._bar_buffers[symbol]) > lookback:
            self._bar_buffers[symbol] = self._bar_buffers[symbol][-lookback:]
            
        # Check if all symbols have enough data
        min_bars = min(len(self._bar_buffers.get(s, [])) for s in self.required_symbols)
        if min_bars < lookback:
            return signals
            
        try:
            # Build multi-asset input tensor
            X = self._build_multi_asset_tensor()
            if X is None:
                return signals
                
            X = X.to(self.device)
            
            # Predict
            with torch.no_grad():
                predictions = self.model(X, self.adj_matrix)
                
            returns = predictions['returns'][0].cpu().numpy()  # (n_assets,)
            direction_logits = predictions['directions'][0].cpu().numpy()  # (n_assets, 3)
            confidences = predictions['confidences'][0].cpu().numpy()  # (n_assets,)
            
            # Generate signals for each asset
            for idx, sym in enumerate(self.required_symbols):
                predicted_return = returns[idx]
                direction_idx = np.argmax(direction_logits[idx])
                confidence = confidences[idx]
                
                direction_map = {0: Direction.SHORT, 1: Direction.FLAT, 2: Direction.LONG}
                direction = direction_map.get(direction_idx, Direction.FLAT)
                
                if direction == Direction.FLAT or confidence < self.config.parameters.get("min_confidence", 0.55):
                    continue
                    
                # Get current price and ATR for this symbol
                current_price = self._bar_buffers[sym][-1].close
                atr = self._calculate_atr(self._bar_buffers[sym][-14:])
                
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
                    symbol=sym,
                    timeframe=Timeframe.H1,
                    signal_type=signal_type,
                    direction=direction,
                    strength=confidence,
                    entry_price=entry,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "model": "gnn",
                        "predicted_return": predicted_return,
                        "direction_logits": direction_logits[idx].tolist(),
                        "confidence": confidence,
                        "atr": atr,
                        "cross_asset_embeddings": predictions.get('embeddings', [])[0, idx].tolist() if 'embeddings' in predictions else [],
                    }
                )
                
                signals.append(signal)
                await self.on_signal_generated(signal)
                
        except Exception as e:
            logger.error(f"GNNStrategy error: {e}")
            
        return signals
    
    def _build_multi_asset_tensor(self) -> torch.Tensor | None:
        """Build input tensor of shape (1, n_assets, seq_len, n_features)."""
        
        asset_tensors = []
        for sym in self.required_symbols:
            bars = self._bar_buffers.get(sym, [])
            if len(bars) < self.config.parameters.get("lookback", 100):
                return None
                
            df = self._bars_to_dataframe(bars)
            df = self.feature_engineer.create_features(df)
            feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
            
            X = df[feature_cols].to_numpy()  # (seq_len, n_features)
            asset_tensors.append(X)
            
        # Stack: (n_assets, seq_len, n_features)
        X = np.stack(asset_tensors, axis=0)
        return torch.FloatTensor(X).unsqueeze(0)  # (1, n_assets, seq_len, n_features)
    
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


def create_gnn_strategy(config: StrategyConfig) -> Strategy:
    return GNNStrategy(config)
