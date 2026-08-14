"""
Regime Detection - HMM-based market regime detection for dynamic allocation.
"""

from __future__ import annotations

import asyncio
import logging
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn import hmm

from src.data.storage.timescale import TimescaleDB

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Market regime types"""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGE_BOUND = "range_bound"
    HIGH_VOL = "high_vol"
    CRISIS = "crisis"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current regime state with confidence"""
    primary: MarketRegime = MarketRegime.UNKNOWN
    confidence: float = 0.0
    secondary: MarketRegime | None = None
    secondary_confidence: float = 0.0
    features: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expected_duration_days: float = 0.0
    transition_probabilities: dict[MarketRegime, float] = field(default_factory=dict)


@dataclass
class RegimeConfig:
    """Configuration for regime detection"""
    lookback_days: int = 252
    n_regimes: int = 5
    n_features: int = 10
    retrain_frequency_days: int = 30
    min_confidence: float = 0.6
    feature_lookback: int = 60
    use_garch_vol: bool = True
    covariance_method: str = "ledoit_wolf"


class FeatureExtractor:
    """Extract regime-relevant features from market data"""
    
    def __init__(self, config: RegimeConfig):
        self.config = config
        self.feature_names = [
            "returns_mean",
            "returns_std",
            "returns_skew",
            "returns_kurtosis",
            "volatility_level",
            "volatility_trend",
            "trend_strength",
            "trend_direction",
            "correlation_avg",
            "correlation_dispersion",
            "volume_trend",
            "spread_avg",
            "rsi_level",
            "macd_signal",
        ]
    
    def extract(self, 
                price_data: dict[str, np.ndarray],
                volume_data: dict[str, np.ndarray] | None = None) -> np.ndarray:
        """Extract features for all assets, return aggregated feature vector"""
        if not price_data:
            return np.zeros(len(self.feature_names))
        
        all_features = []
        
        for symbol, prices in price_data.items():
            if len(prices) < 60:
                continue
            
            # Returns
            returns = np.diff(np.log(prices))
            
            # Basic return stats
            ret_mean = np.mean(returns)
            ret_std = np.std(returns)
            ret_skew = self._skewness(returns)
            ret_kurt = self._kurtosis(returns)
            
            # Volatility
            vol = ret_std * np.sqrt(252)
            vol_trend = self._volatility_trend(returns)
            
            # Trend
            trend_str, trend_dir = self._trend_features(prices)
            
            # Volume features
            vol_trend_val = 0.0
            if volume_data and symbol in volume_data:
                vol_trend_val = self._volume_trend(volume_data[symbol])
            
            # Correlation features (need multi-asset)
            # Will be calculated separately
            
            features = np.array([
                ret_mean, ret_std, ret_skew, ret_kurt,
                vol, vol_trend,
                trend_str, trend_dir,
                0.0, 0.0,  # correlation placeholders
                vol_trend_val,
                0.0, 0.0  # spread, rsi placeholders
            ])
            
            all_features.append(features)
        
        # Aggregate across assets
        if all_features:
            return np.nanmean(np.array(all_features), axis=0)
        
        return np.zeros(len(self.feature_names))
    
    def _skewness(self, x: np.ndarray) -> float:
        if len(x) < 10:
            return 0.0
        mean = np.mean(x)
        std = np.std(x)
        if std == 0:
            return 0.0
        return float(np.mean(((x - mean) / std) ** 3))
    
    def _kurtosis(self, x: np.ndarray) -> float:
        if len(x) < 10:
            return 0.0
        mean = np.mean(x)
        std = np.std(x)
        if std == 0:
            return 0.0
        return float(np.mean(((x - mean) / std) ** 4) - 3)
    
    def _volatility_trend(self, returns: np.ndarray) -> float:
        """Trend in volatility (GARCH-style)"""
        if len(returns) < 50:
            return 0.0
        
        # Rolling volatility
        window = 20
        rolling_vol = pd.Series(returns).rolling(window).std().dropna().values
        
        if len(rolling_vol) < 10:
            return 0.0
        
        # Linear trend
        x = np.arange(len(rolling_vol))
        slope = np.polyfit(x, rolling_vol, 1)[0]
        return float(slope * 252)  # Annualized trend
    
    def _trend_features(self, prices: np.ndarray) -> tuple[float, float]:
        """Trend strength and direction"""
        if len(prices) < 50:
            return 0.0, 0.0
        
        # ADX-style trend strength
        _high = prices  # Simplified
        _low = prices
        close = prices
        
        # Simple trend: regression slope
        x = np.arange(min(50, len(prices)))
        y = close[-len(x):]
        slope = np.polyfit(x, y, 1)[0]
        
        # Normalize
        trend_strength = abs(slope) / np.mean(y) * np.sqrt(252)
        trend_direction = 1.0 if slope > 0 else -1.0
        
        return float(trend_strength), float(trend_direction)
    
    def _volume_trend(self, volumes: np.ndarray) -> float:
        if len(volumes) < 20:
            return 0.0
        vol_sma = pd.Series(volumes).rolling(20).mean().dropna().values
        if len(vol_sma) < 10:
            return 0.0
        x = np.arange(len(vol_sma))
        slope = np.polyfit(x, vol_sma, 1)[0]
        return float(slope / np.mean(vol_sma))


class HMMRegimeDetector:
    """Hidden Markov Model for regime detection"""
    
    def __init__(self, config: RegimeConfig):
        self.config = config
        self.model: hmm.GaussianHMM | None = None
        self.feature_extractor = FeatureExtractor(config)
        self.scaler_mean: np.ndarray | None = None
        self.scaler_std: np.ndarray | None = None
        self.is_fitted = False
        self.regime_labels = {
            0: MarketRegime.TRENDING_BULL,
            1: MarketRegime.TRENDING_BEAR,
            2: MarketRegime.RANGE_BOUND,
            3: MarketRegime.HIGH_VOL,
            4: MarketRegime.CRISIS,
        }
        self.last_training: datetime | None = None
    
    def fit(self, features_history: np.ndarray):
        """Train HMM on historical features"""
        if len(features_history) < 100:
            logger.warning("Insufficient data for HMM training")
            return
        
        # Scale features
        self.scaler_mean = np.nanmean(features_history, axis=0)
        self.scaler_std = np.nanstd(features_history, axis=0)
        self.scaler_std[self.scaler_std == 0] = 1.0
        
        scaled = (features_history - self.scaler_mean) / self.scaler_std
        scaled = np.nan_to_num(scaled, nan=0.0, posinf=3.0, neginf=-3.0)
        
        # Fit HMM
        n_components = self.config.n_regimes
        
        self.model = hmm.GaussianHMM(
            n_components=n_components,
            covariance_type="full",
            n_iter=100,
            tol=1e-4,
            random_state=42,
            init_params="stmc"
        )
        
        try:
            self.model.fit(scaled)
            # Map states to regime labels
            self.regime_labels = {
                0: MarketRegime.TRENDING_BULL,
                1: MarketRegime.TRENDING_BEAR,
                2: MarketRegime.RANGE_BOUND,
                3: MarketRegime.HIGH_VOL,
                4: MarketRegime.CRISIS,
            }
            self._map_states_to_regimes()
            logger.info(f"HMM trained with {n_components} regimes")
        except Exception as e:
            logger.error(f"HMM training failed: {e}")
            self.is_fitted = False
    
    def _map_states_to_regimes(self):
        """Map HMM states to interpretable regimes based on features"""
        if not self.model:
            return
        
        # Get state means in original feature space
        state_means = self.model.means_ * self.scaler_std + self.scaler_mean
        
        # Features: [ret_mean, ret_std, ret_skew, ret_kurt, vol, vol_trend, 
        #            trend_str, trend_dir, corr_avg, corr_disp, vol_trend, spread, rsi, macd]
        
        for i in range(self.config.n_regimes):
            _mean_ret = state_means[i, 0]
            mean_vol = state_means[i, 4]
            mean_trend_str = state_means[i, 6]
            mean_trend_dir = state_means[i, 7]
            mean_vol_trend = state_means[i, 5]
            
            # Simple heuristic mapping
            if mean_vol > np.percentile(state_means[:, 4], 80) and mean_vol_trend > 0:
                self.regime_labels[i] = MarketRegime.CRISIS
            elif mean_vol > np.percentile(state_means[:, 4], 60):
                self.regime_labels[i] = MarketRegime.HIGH_VOL
            elif mean_trend_str > np.percentile(state_means[:, 6], 60):
                if mean_trend_dir > 0:
                    self.regime_labels[i] = MarketRegime.TRENDING_BULL
                else:
                    self.regime_labels[i] = MarketRegime.TRENDING_BEAR
            else:
                self.regime_labels[i] = MarketRegime.RANGE_BOUND
    
    def predict(self, features: np.ndarray) -> RegimeState:
        """Predict current regime"""
        if not self.is_fitted or not self.model:
            return RegimeState(primary=MarketRegime.UNKNOWN, confidence=0.0)
        
        # Scale features
        scaled = (features - self.scaler_mean) / self.scaler_std
        scaled = np.nan_to_num(scaled, nan=0.0, posinf=3.0, neginf=-3.0).reshape(1, -1)
        
        # Predict state probabilities
        try:
            _logprob, posteriors = self.model.score_samples(scaled)
            state_probs = posteriors[0]
            most_likely = np.argmax(state_probs)
            confidence = state_probs[most_likely]
            
            # Secondary regime
            sorted_probs = np.sort(state_probs)[::-1]
            secondary_idx = np.argsort(state_probs)[::-1][1] if len(state_probs) > 1 else most_likely
            secondary_conf = sorted_probs[1] if len(sorted_probs) > 1 else 0.0
            
            primary = self.regime_labels.get(most_likely, MarketRegime.UNKNOWN)
            secondary = self.regime_labels.get(secondary_idx, MarketRegime.UNKNOWN)
            
            # Expected duration (inverse of self-transition probability)
            transmat = self.model.transmat_
            expected_duration = 1.0 / (1.0 - transmat[most_likely, most_likely]) if transmat[most_likely, most_likely] < 1 else 100
            
            return RegimeState(
                primary=primary,
                confidence=float(confidence),
                secondary=secondary,
                secondary_confidence=float(secondary_conf),
                timestamp=datetime.now(UTC),
                expected_duration_days=expected_duration,
                transition_probabilities={
                    self.symbole_labels[j]: float(transmat[most_likely, j]) 
                    for j in range(self.config.n_regimes)
                }
            )
        except Exception as e:
            logger.error(f"Regime prediction failed: {e}")
            return RegimeState(primary=MarketRegime.UNKNOWN, confidence=0.0)
    
    def save(self, path: str):
        """Save model to disk"""
        if self.model:
            with open(path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'scaler_mean': self.scaler_mean,
                    'scaler_std': self.scaler_std,
                    'is_fitted': self.is_fitted,
                    'symbole_labels': self.symbole_labels,
                    'last_training': self.last_training,
                    'config': self.config
                }, f)
    
    def load(self, path: str):
        """Load model from disk"""
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            self.model = data['model']
            self.scaler_mean = data['scaler_mean']
            self.scaler_std = data['scaler_std']
            self.is_fitted = data['is_fitted']
            self.symbole_labels = data['symbole_labels']
            self.last_training = data['last_training']
            logger.info(f"HMM model loaded from {path}")
        except Exception as e:
            logger.error(f"Failed to load HMM model: {e}")


class RegimeDetector:
    """Main regime detection service"""
    
    def __init__(self, config: RegimeConfig, timescaledb: TimescaleDB):
        self.config = config
        self.timescaledb = timescaledb
        self.hmm_detector = HMMRegimeDetector(config)
        self.feature_extractor = FeatureExtractor(config)
        
        self.current_regime = RegimeState()
        self.regime_history: list[RegimeState] = []
        
        # Strategy weights per regime
        self.regime_weights = {
            MarketRegime.TRENDING_BULL: {
                "trend_following": 0.6,
                "mean_reversion": 0.1,
                "carry_trade": 0.3,
            },
            MarketRegime.TRENDING_BEAR: {
                "trend_following": 0.5,
                "volatility": 0.3,
                "hedge": 0.2,
            },
            MarketRegime.RANGE_BOUND: {
                "mean_reversion": 0.5,
                "stat_arb": 0.3,
                "carry_trade": 0.2,
            },
            MarketRegime.HIGH_VOL: {
                "volatility": 0.5,
                "trend_following": 0.2,
                "hedge": 0.3,
            },
            MarketRegime.CRISIS: {
                "hedge": 0.6,
                "cash": 0.3,
                "volatility": 0.1,
            },
        }
        
        self.running = False
        self.update_interval = 3600  # 1 hour
    
    async def start(self):
        """Start regime detection service"""
        # Load historical data and train
        await self._initial_training()
        
        self.running = True
        asyncio.create_task(self._detection_loop())
        logger.info("RegimeDetector started")
    
    async def stop(self):
        self.running = False
        # Save model
        self.hmm_detector.save("models/regime_hmm.pkl")
        logger.info("RegimeDetector stopped")
    
    async def _initial_training(self):
        """Train HMM on historical data"""
        logger.info("Training HMM on historical data...")
        
        try:
            # Get historical price data
            features_history = await self._get_historical_features()
            
            if len(features_history) > 200:
                self.hmm_detector.fit(features_history)
                logger.info("Initial HMM training complete")
            else:
                logger.warning("Insufficient data for initial training")
        except Exception as e:
            logger.error(f"Initial training failed: {e}")
    
    async def _get_historical_features(self) -> np.ndarray:
        """Get historical features for training"""
        try:
            # Get symbols
            async with self.timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT symbol_id FROM market_data.bars
                    WHERE timeframe = '1h' AND is_complete = TRUE
                    AND time > NOW() - INTERVAL '2 years'
                """)
                symbol_ids = [r['symbol_id'] for r in rows]
            
            all_features = []
            
            for symbol_id in symbol_ids[:20]:  # Limit for training speed
                async with self.timescaledb.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT close, time FROM market_data.bars
                        WHERE symbol_id = $1 AND timeframe = '1h' AND is_complete = TRUE
                        ORDER BY time ASC
                    """, symbol_id)
                
                if len(rows) > 200:
                    prices = np.array([float(r['close']) for r in rows])
                    features = self.feature_extractor.extract({f"sym_{symbol_id}": prices})
                    all_features.append(features)
            
            if all_features:
                return np.array(all_features)
            return np.array([])
        except Exception as e:
            logger.error(f"Failed to get historical features: {e}")
            return np.array([])
    
    async def _detection_loop(self):
        """Main detection loop"""
        while self.running:
            try:
                await self._detect_regime()
            except Exception as e:
                logger.error(f"Regime detection error: {e}")
            
            await asyncio.sleep(self.update_interval)
    
    async def _detect_regime(self):
        """Detect current regime"""
        try:
            # Get current market features
            features = await self._get_current_features()
            
            if len(features) > 0:
                regime_state = self.hmm_detector.predict(features)
                
                # Only update if confidence is sufficient
                if regime_state.confidence >= self.config.min_confidence:
                    self.current_regime = regime_state
                    self.regime_history.append(regime_state)
                    
                    # Keep history limited
                    if len(self.regime_history) > 1000:
                        self.regime_history = self.regime_history[-1000:]
                    
                    logger.info(f"Regime: {regime_state.primary.value} (conf: {regime_state.confidence:.2f})")
        except Exception as e:
            logger.error(f"Regime detection failed: {e}")
    
    async def _get_current_features(self) -> np.ndarray:
        """Get current market features"""
        try:
            # Get recent 1h bars for major symbols
            async with self.timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT s.symbol, b.close
                    FROM market_data.bars b
                    JOIN market_data.symbols s ON b.symbol_id = s.symbol_id
                    WHERE b.timeframe = '1h' 
                      AND b.is_complete = TRUE
                      AND b.time > NOW() - INTERVAL '60 days'
                      AND s.asset_class IN ('forex', 'crypto')
                    ORDER BY s.symbol, b.time
                """)
            
            # Group by symbol
            price_data = {}
            for row in rows:
                sym = row['symbol']
                if sym not in price_data:
                    price_data[sym] = []
                price_data[sym].append(float(row['close']))
            
            # Convert to arrays
            for sym in price_data:
                price_data[sym] = np.array(price_data[sym])
            
            return self.feature_extractor.extract(price_data)
        except Exception as e:
            logger.error(f"Failed to get current features: {e}")
            return np.array([])
    
    def get_strategy_weights(self) -> dict[str, float]:
        """Get strategy weights for current regime"""
        weights = self.regime_weights.get(self.current_regime.primary, 
                                          self.regime_weights[MarketRegime.RANGE_BOUND])
        
        # Blend with secondary regime if significant
        if self.current_regime.secondary and self.current_regime.secondary_confidence > 0.3:
            secondary_weights = self.regime_weights.get(self.current_regime.secondary, {})
            alpha = self.current_regime.secondary_confidence
            for k in weights:
                weights[k] = weights[k] * (1 - alpha) + secondary_weights.get(k, 0) * alpha
        
        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        
        return weights
    
    def get_status(self) -> dict[str, Any]:
        return {
            "current_regime": self.current_regime.primary.value,
            "confidence": self.current_regime.confidence,
            "secondary_regime": self.current_regime.secondary.value if self.current_regime.secondary else None,
            "secondary_confidence": self.current_regime.secondary_confidence,
            "expected_duration_days": self.current_regime.expected_duration_days,
            "transition_probabilities": {k.value: v for k, v in self.current_regime.transition_probabilities.items()},
            "strategy_weights": self.get_strategy_weights(),
            "model_fitted": self.hmm_detector.is_fitted,
            "last_training": self.hmm_detector.last_training.isoformat() if self.hmm_detector.last_training else None,
            "history_length": len(self.regime_history)
        }