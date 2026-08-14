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


class PPOActorCritic(nn.Module):
    """PPO Actor-Critic network for trading."""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_size: int = 256):
        super().__init__()
        
        # Shared feature extractor
        self.shared = nn.Sequential(
            nn.Linear(state_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
        )
        
        # Actor head (policy)
        self.actor = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, action_dim),
        )
        
        # Critic head (value function)
        self.critic = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1),
        )
        
        # Action log std (learnable)
        self.log_std = nn.Parameter(torch.zeros(action_dim))
        
    def forward(self, state: torch.Tensor) -> tuple:
        features = self.shared(state)
        action_mean = self.actor(features)
        action_std = torch.exp(self.log_std.clamp(-20, 2))
        value = self.critic(features)
        return action_mean, action_std, value
    
    def act(self, state: torch.Tensor, deterministic: bool = False) -> tuple:
        action_mean, action_std, value = self.forward(state)
        
        if deterministic:
            action = action_mean
            log_prob = None
        else:
            dist = torch.distributions.Normal(action_mean, action_std)
            action = dist.sample()
            log_prob = dist.log_prob(action).sum(dim=-1)
            
        # Tanh squashing for bounded actions
        action = torch.tanh(action)
        return action, log_prob, value


class SACActor(nn.Module):
    """SAC Actor network (policy)."""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_size: int = 256, log_std_min: float = -20, log_std_max: float = 2):
        super().__init__()
        self.log_std_min = log_std_min
        self.log_std_max = log_std_max
        
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
        )
        
        self.mean_head = nn.Linear(hidden_size, action_dim)
        self.log_std_head = nn.Linear(hidden_size, action_dim)
        
    def forward(self, state: torch.Tensor) -> tuple:
        x = self.net(state)
        mean = self.mean_head(x)
        log_std = self.log_std_head(x).clamp(self.log_std_min, self.log_std_max)
        return mean, log_std
    
    def sample(self, state: torch.Tensor) -> tuple:
        mean, log_std = self.forward(state)
        std = log_std.exp()
        
        # Reparameterization trick
        normal = torch.distributions.Normal(mean, std)
        x_t = normal.rsample()
        y_t = torch.tanh(x_t)
        action = y_t
        
        log_prob = normal.log_prob(x_t)
        log_prob -= torch.log(1 - y_t.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        
        return action, log_prob, torch.tanh(mean)


class SACCritic(nn.Module):
    """SAC Critic network (twin Q-functions)."""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_size: int = 256):
        super().__init__()
        
        # Q1
        self.q1 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )
        
        # Q2
        self.q2 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )
        
    def forward(self, state: torch.Tensor, action: torch.Tensor) -> tuple:
        sa = torch.cat([state, action], dim=-1)
        q1 = self.q1(sa)
        q2 = self.q2(sa)
        return q1, q2


class RLStrategy(Strategy):
    """Reinforcement Learning Strategy (PPO + SAC) for adaptive trading."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ppo_model: PPOActorCritic | None = None
        self.sac_actor: SACActor | None = None
        self.sac_critic: SACCritic | None = None
        self.sac_critic_target: SACCritic | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False
        self.algorithm = config.parameters.get("algorithm", "ppo")  # "ppo" or "sac"
        self.state_dim = config.parameters.get("state_dim", 50)
        self.action_dim = 3  # [position_size, stop_loss_mult, take_profit_mult]
        self.hidden_size = config.parameters.get("hidden_size", 256)
        
        # Training buffers
        self.ppo_buffer: list[dict] = []
        self.sac_buffer: list[dict] = []
        self.ppo_update_frequency = config.parameters.get("ppo_update_frequency", 2048)
        self.sac_batch_size = config.parameters.get("sac_batch_size", 256)
        
        # PPO hyperparameters
        self.ppo_clip_eps = config.parameters.get("ppo_clip_eps", 0.2)
        self.ppo_epochs = config.parameters.get("ppo_epochs", 10)
        self.ppo_lr = config.parameters.get("ppo_lr", 3e-4)
        
        # SAC hyperparameters
        self.sac_lr = config.parameters.get("sac_lr", 3e-4)
        self.sac_gamma = config.parameters.get("sac_gamma", 0.99)
        self.sac_tau = config.parameters.get("sac_tau", 0.005)
        self.sac_alpha = config.parameters.get("sac_alpha", 0.2)
        self.target_entropy = -self.action_dim
        
    async def _initialize(self) -> None:
        """Initialize RL models."""
        model_config = ModelConfig(
            model_type="rl",
            input_features=self.config.parameters.get("input_features", [
                "return_1", "return_5", "log_return", "volatility_20",
                "price_to_sma20", "volume_ratio", "spread_pct", "hl_range_pct",
                "rsi_14", "macd", "bb_upper_20", "bb_lower_20", "atr_14",
                "stoch_k_14", "adx_14", "hour", "weekday"
            ]),
            target=self.config.parameters.get("target", "future_return"),
            lookback=self.config.parameters.get("lookback", 100),
            prediction_horizon=self.config.parameters.get("prediction_horizon", 1),
            hidden_size=self.hidden_size,
            num_layers=self.config.parameters.get("num_layers", 3),
            dropout=self.config.parameters.get("dropout", 0.1),
            learning_rate=self.ppo_lr,
        )
        
        self.feature_engineer = FeatureEngineer(model_config)
        
        if self.algorithm == "ppo":
            self.ppo_model = PPOActorCritic(self.state_dim, self.action_dim, self.hidden_size).to(self.device)
            self.ppo_optimizer = torch.optim.Adam(self.ppo_model.parameters(), lr=self.ppo_lr)
        else:
            self.sac_actor = SACActor(self.state_dim, self.action_dim, self.hidden_size).to(self.device)
            self.sac_critic = SACCritic(self.state_dim, self.action_dim, self.hidden_size).to(self.device)
            self.sac_critic_target = SACCritic(self.state_dim, self.action_dim, self.hidden_size).to(self.device)
            self.sac_critic_target.load_state_dict(self.sac_critic.state_dict())
            
            self.sac_actor_optimizer = torch.optim.Adam(self.sac_actor.parameters(), lr=self.sac_lr)
            self.sac_critic_optimizer = torch.optim.Adam(self.sac_critic.parameters(), lr=self.sac_lr)
            self.log_alpha = torch.tensor(np.log(self.sac_alpha), requires_grad=True, device=self.device)
            self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=self.sac_lr)
        
        # Try to load existing model
        from src.infra.config.settings import settings
        model_path = Path(settings.strategy_ml_models_path) / f"{self.algorithm}_best.pt"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                if self.algorithm == "ppo":
                    self.ppo_model.load_state_dict(checkpoint['model_state_dict'])
                else:
                    self.sac_actor.load_state_dict(checkpoint['actor_state_dict'])
                    self.sac_critic.load_state_dict(checkpoint['critic_state_dict'])
                    self.sac_critic_target.load_state_dict(checkpoint['critic_target_state_dict'])
                self._model_loaded = True
                logger.info(f"Loaded {self.algorithm.upper()} model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load {self.algorithm.upper()} model: {e}")
                
    @property
    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.M15, Timeframe.H1]
    
    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    
    def _compute_reward(self, action: np.ndarray, next_bar: Bar, prev_bar: Bar) -> float:
        """Compute reward from action and price movement."""
        position_size, _sl_mult, _tp_mult = action
        
        # Price change
        price_change = (next_bar.close - prev_bar.close) / prev_bar.close
        
        # Reward = PnL - risk penalty
        pnl = position_size * price_change
        
        # Risk penalty (large positions penalized)
        risk_penalty = -0.1 * abs(position_size)
        
        # Transaction cost
        tc = -0.0001 * abs(position_size)
        
        return pnl + risk_penalty + tc
    
    def _state_from_bar(self, bar: Bar) -> np.ndarray:
        """Extract state features from bar."""
        df = self._bars_to_dataframe([bar])
        df = self.feature_engineer.create_features(df)
        feature_cols = [c for c in df.columns if c not in ["timestamp", "open", "high", "low", "close", "volume", "spread", "target"]]
        return df[feature_cols].iloc[-1].to_numpy().astype(np.float32)
    
    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using RL policy."""
        signals = []
        
        if not self._model_loaded:
            return signals
            
        self._bar_buffer.append(bar)
        lookback = self.config.parameters.get("lookback", 100)
        if len(self._bar_buffer) < lookback:
            return signals
            
        self._bar_buffer = self._bar_buffer[-lookback:]
        
        try:
            # Get current state
            state = self._state_from_bar(bar)
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            
            if self.algorithm == "ppo" and self.ppo_model:
                self.ppo_model.eval()
                with torch.no_grad():
                    action, _, _ = self.ppo_model.act(state_tensor, deterministic=True)
                    action = action.cpu().numpy().flatten()
            elif self.algorithm == "sac" and self.sac_actor:
                self.sac_actor.eval()
                with torch.no_grad():
                    action, _, _ = self.sac_actor.sample(state_tensor)
                    action = action.cpu().numpy().flatten()
            else:
                return signals
            
            position_size, sl_mult, tp_mult = action
            position_size = np.clip(position_size, -1, 1)
            sl_mult = np.clip(sl_mult, 0.5, 5.0)
            tp_mult = np.clip(tp_mult, 0.5, 10.0)
            
            # Determine direction
            if position_size > 0.1:
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            elif position_size < -0.1:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
            else:
                return signals
            
            # Confidence from action magnitude
            confidence = min(abs(position_size) + 0.3, 0.95)
            
            current_price = bar.close
            atr = self._calculate_atr(self._bar_buffer[-14:])
            
            if direction == Direction.LONG:
                entry = current_price
                stop_loss = entry - atr * sl_mult
                take_profit = entry + atr * tp_mult
            else:
                entry = current_price
                stop_loss = entry + atr * sl_mult
                take_profit = entry - atr * tp_mult
                
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
                    "model": self.algorithm.upper(),
                    "position_size": position_size,
                    "sl_mult": sl_mult,
                    "tp_mult": tp_mult,
                    "confidence": confidence,
                    "atr": atr,
                }
            )
            
            signals.append(signal)
            await self.on_signal_generated(signal)
            
            # Store transition for training
            self._store_transition(bar, action)
            
        except Exception as e:
            logger.error(f"RLStrategy error: {e}")
            
        return signals
    
    def _store_transition(self, bar: Bar, action: np.ndarray):
        """Store transition for training."""
        if len(self._bar_buffer) < 2:
            return
            
        prev_bar = self._bar_buffer[-2]
        reward = self._compute_reward(action, bar, prev_bar)
        
        state = self._state_from_bar(prev_bar)
        next_state = self._state_from_bar(bar)
        
        transition = {
            'state': state,
            'action': action,
            'reward': reward,
            'next_state': next_state,
            'done': False,
        }
        
        if self.algorithm == "ppo":
            self.ppo_buffer.append(transition)
        else:
            self.sac_buffer.append(transition)
    
    async def _train_step(self):
        """Perform training step."""
        if self.algorithm == "ppo" and len(self.ppo_buffer) >= self.ppo_update_frequency:
            await self._ppo_update()
        elif self.algorithm == "sac" and len(self.sac_buffer) >= self.sac_batch_size:
            await self._sac_update()
    
    async def _ppo_update(self):
        """PPO update step."""
        if not self.ppo_model:
            return
            
        self.ppo_model.train()
        
        # Prepare batch
        states = torch.FloatTensor([t['state'] for t in self.ppo_buffer]).to(self.device)
        actions = torch.FloatTensor([t['action'] for t in self.ppo_buffer]).to(self.device)
        rewards = torch.FloatTensor([t['reward'] for t in self.ppo_buffer]).to(self.device)
        next_states = torch.FloatTensor([t['next_state'] for t in self.ppo_buffer]).to(self.device)
        
        # Compute returns and advantages
        with torch.no_grad():
            _, _, values = self.ppo_model(states)
            _, _, next_values = self.ppo_model(next_states)
            
        returns = rewards + 0.99 * next_values.squeeze()
        advantages = returns - values.squeeze()
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # PPO epochs
        for _ in range(self.ppo_epochs):
            action_means, action_stds, values = self.ppo_model(states)
            dist = torch.distributions.Normal(action_means, action_stds)
            log_probs = dist.log_prob(actions).sum(dim=-1)
            
            # Old log probs (approximate)
            with torch.no_grad():
                old_dist = torch.distributions.Normal(action_means.detach(), action_stds.detach())
                old_log_probs = old_dist.log_prob(actions).sum(dim=-1)
            
            ratio = (log_probs - old_log_probs).exp()
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.ppo_clip_eps, 1 + self.ppo_clip_eps) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()
            critic_loss = F.mse_loss(values.squeeze(), returns)
            
            loss = actor_loss + 0.5 * critic_loss
            
            self.ppo_optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.ppo_model.parameters(), 0.5)
            self.ppo_optimizer.step()
            
        self.ppo_buffer.clear()
    
    async def _sac_update(self):
        """SAC update step."""
        if not self.sac_actor or not self.sac_critic:
            return
            
        # Sample batch
        batch = np.random.choice(len(self.sac_buffer), self.sac_batch_size, replace=False)
        batch_data = [self.sac_buffer[i] for i in batch]
        
        states = torch.FloatTensor([t['state'] for t in batch_data]).to(self.device)
        actions = torch.FloatTensor([t['action'] for t in batch_data]).to(self.device)
        rewards = torch.FloatTensor([t['reward'] for t in batch_data]).to(self.device)
        next_states = torch.FloatTensor([t['next_state'] for t in batch_data]).to(self.device)
        
        # Update critic
        with torch.no_grad():
            next_actions, next_log_probs, _ = self.sac_actor.sample(next_states)
            q1_next, q2_next = self.sac_critic_target(next_states, next_actions)
            q_next = torch.min(q1_next, q2_next) - self.log_alpha.exp() * next_log_probs
            target_q = rewards.unsqueeze(-1) + 0.99 * q_next
        
        q1, q2 = self.sac_critic(states, actions)
        critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)
        
        self.sac_critic_optimizer.zero_grad()
        critic_loss.backward()
        self.sac_critic_optimizer.step()
        
        # Update actor
        new_actions, log_probs, _ = self.sac_actor.sample(states)
        q1_new, q2_new = self.sac_critic(states, new_actions)
        q_new = torch.min(q1_new, q2_new)
        
        actor_loss = (self.log_alpha.exp() * log_probs - q_new).mean()
        
        self.sac_actor_optimizer.zero_grad()
        actor_loss.backward()
        self.sac_actor_optimizer.step()
        
        # Update alpha
        alpha_loss = -(self.log_alpha.exp() * (log_probs + self.target_entropy).detach()).mean()
        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()
        
        # Update target networks
        with torch.no_grad():
            for param, target_param in zip(self.sac_critic.parameters(), self.sac_critic_target.parameters()):
                target_param.data.copy_(self.sac_tau * param.data + (1 - self.sac_tau) * target_param.data)
    
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


def create_rl_strategy(config: StrategyConfig) -> Strategy:
    return RLStrategy(config)
