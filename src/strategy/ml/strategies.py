from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
from loguru import logger

from src.data.models import Bar
from src.infra.config.settings import settings
from src.strategy.base.signal import Direction, Signal, SignalType
from src.strategy.base.strategy import Strategy, StrategyConfig
from src.strategy.ml.models import FeatureEngineer, MLModelTrainer, ModelConfig, OnlineLearner
from src.strategy.technical.indicators import MarketRegime, TechnicalIndicators


class EnsembleStrategy(Strategy):
    """Ensemble strategy combining ML models and technical analysis."""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ml_trainer: MLModelTrainer | None = None
        self.feature_engineer: FeatureEngineer | None = None
        self.online_learner: OnlineLearner | None = None
        self.current_regime = 0
        self.regime_history: list[int] = []
        self._bar_buffer: list[Bar] = []
        self._model_loaded = False

    async def _initialize(self) -> None:
        """Initialize ML models and feature engineering."""
        # Build model config from strategy parameters
        model_config = ModelConfig(
            model_type=self.config.parameters.get("model_type", "lstm"),
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
            dropout=self.config.parameters.get("dropout", 0.2),
            learning_rate=self.config.parameters.get("learning_rate", 0.001),
        )

        self.feature_engineer = FeatureEngineer(model_config)
        self.ml_trainer = MLModelTrainer(model_config)

        # Initialize online learner for adaptive updates
        self.online_learner = OnlineLearner("linear")

        # Try to load existing model
        model_path = Path(settings.strategy_ml_models_path) / f"{model_config.model_type}_best.pt"
        if model_path.exists():
            try:
                self.ml_trainer.load_model(model_path)
                self._model_loaded = True
                logger.info(f"Loaded ML model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")

    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        """Generate signals using ensemble of ML and technical analysis."""
        signals = []

        # Add bar to buffer
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) > self.config.parameters.get("lookback", 100) + 50:
            self._bar_buffer.pop(0)

        # Need minimum bars for analysis
        min_bars = self.config.parameters.get("lookback", 100)
        if len(self._bar_buffer) < min_bars:
            return signals

        # Convert buffer to DataFrame
        df = self._bars_to_dataframe(self._bar_buffer)

        # Create features
        df_features = self.feature_engineer.create_features(df)

        # Detect market regime
        returns = df_features["log_return"].drop_nulls().to_numpy()
        if len(returns) > 50:
            regime = MarketRegime.detect_regime_volatility(returns)[-1]
            self.current_regime = regime
            self.regime_history.append(regime)
            if len(self.regime_history) > 100:
                self.regime_history.pop(0)

        # Generate ML signal if model is loaded
        ml_signal = await self._generate_ml_signal(df_features, bar)
        if ml_signal:
            signals.append(ml_signal)

        # Generate technical signal
        tech_signal = await self._generate_technical_signal(df_features, bar)
        if tech_signal:
            signals.append(tech_signal)

        # Combine signals (ensemble)
        if len(signals) > 1:
            combined = self._combine_signals(signals)
            if combined:
                return [combined]
        elif len(signals) == 1:
            return signals

        return []

    async def _generate_ml_signal(self, df: pl.DataFrame, bar: Bar) -> Signal | None:
        """Generate signal from ML model."""
        if not self._model_loaded or self.ml_trainer is None:
            return None

        try:
            # Prepare sequences for prediction
            X, _ = self.feature_engineer.prepare_sequences(df)
            if len(X) == 0:
                return None

            # Use latest sequence
            latest_X = X[-1:]

            # Predict
            prediction = self.ml_trainer.predict(latest_X)
            pred_value = float(prediction[0][0])

            # Convert prediction to signal
            current_price = float(df["close"][-1])

            # Determine direction and strength
            if pred_value > 0.001:  # Positive return predicted
                direction = Direction.LONG
                strength = min(abs(pred_value) * 100, 1.0)  # Scale to 0-1
            elif pred_value < -0.001:
                direction = Direction.SHORT
                strength = min(abs(pred_value) * 100, 1.0)
            else:
                return None

            # Calculate entry, SL, TP
            atr = float(df["atr_14"][-1]) if "atr_14" in df.columns else current_price * 0.001
            entry_price = Decimal(str(current_price))

            if direction == Direction.LONG:
                stop_loss = Decimal(str(current_price - 2 * atr))
                take_profit = Decimal(str(current_price + 3 * atr))
            else:
                stop_loss = Decimal(str(current_price + 2 * atr))
                take_profit = Decimal(str(current_price - 3 * atr))

            # Confidence based on model uncertainty (simplified)
            confidence = min(strength * 1.2, 0.95)

            return Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=f"{self.config.name}_ml",
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strength=strength,
                confidence=confidence,
                timeframe=bar.timeframe,
                metadata={
                    "model_type": self.ml_trainer.config.model_type,
                    "prediction": pred_value,
                    "regime": self.current_regime,
                    "regime_name": MarketRegime.get_regime_name(self.current_regime),
                },
            )

        except Exception as e:
            logger.error(f"ML signal generation error: {e}")
            return None

    async def _generate_technical_signal(self, df: pl.DataFrame, bar: Bar) -> Signal | None:
        """Generate signal from technical analysis."""
        try:
            # Get latest indicator values
            latest = df.row(-1, named=True)

            # Multi-indicator consensus
            signals = []

            # RSI
            rsi = latest.get("rsi_14", 50)
            if rsi < 30:
                signals.append(("rsi", Direction.LONG, 0.7))
            elif rsi > 70:
                signals.append(("rsi", Direction.SHORT, 0.7))

            # MACD
            macd = latest.get("macd", 0)
            macd_signal = latest.get("macd_signal", 0)
            if macd > macd_signal and macd > 0:
                signals.append(("macd", Direction.LONG, 0.6))
            elif macd < macd_signal and macd < 0:
                signals.append(("macd", Direction.SHORT, 0.6))

            # Bollinger Bands
            close = latest.get("close", 0)
            bb_upper = latest.get("bb_upper_20", 0)
            bb_lower = latest.get("bb_lower_20", 0)
            if close < bb_lower:
                signals.append(("bb", Direction.LONG, 0.5))
            elif close > bb_upper:
                signals.append(("bb", Direction.SHORT, 0.5))

            # ADX Trend Strength
            adx = latest.get("adx_14", 0)
            plus_di = latest.get("plus_di_14", 0)
            minus_di = latest.get("minus_di_14", 0)
            if adx > 25 and plus_di > minus_di:
                signals.append(("adx", Direction.LONG, 0.6))
            elif adx > 25 and minus_di > plus_di:
                signals.append(("adx", Direction.SHORT, 0.6))

            # EMA Trend
            ema_20 = latest.get("ema_20", 0)
            ema_50 = latest.get("ema_50", 0)
            if ema_20 > ema_50 and close > ema_20:
                signals.append(("ema", Direction.LONG, 0.5))
            elif ema_20 < ema_50 and close < ema_20:
                signals.append(("ema", Direction.SHORT, 0.5))

            # Consensus
            if not signals:
                return None

            long_votes = sum(s[2] for s in signals if s[1] == Direction.LONG)
            short_votes = sum(s[2] for s in signals if s[1] == Direction.SHORT)

            if long_votes > short_votes and long_votes > 1.5:
                direction = Direction.LONG
                strength = min(long_votes / 3.0, 1.0)
            elif short_votes > long_votes and short_votes > 1.5:
                direction = Direction.SHORT
                strength = min(short_votes / 3.0, 1.0)
            else:
                return None

            # Calculate SL/TP using ATR
            atr = latest.get("atr_14", close * 0.001)
            current_price = Decimal(str(close))

            if direction == Direction.LONG:
                stop_loss = Decimal(str(close - 2 * atr))
                take_profit = Decimal(str(close + 3 * atr))
            else:
                stop_loss = Decimal(str(close + 2 * atr))
                take_profit = Decimal(str(close - 3 * atr))

            confidence = strength * 0.8  # Technical analysis slightly lower confidence

            return Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=f"{self.config.name}_technical",
                symbol=bar.symbol,
                direction=direction,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strength=strength,
                confidence=confidence,
                timeframe=bar.timeframe,
                metadata={
                    "indicators": {s[0]: {"direction": s[1].value, "weight": s[2]} for s in signals},
                    "regime": self.current_regime,
                },
            )

        except Exception as e:
            logger.error(f"Technical signal generation error: {e}")
            return None

    def _combine_signals(self, signals: list[Signal]) -> Signal | None:
        """Combine multiple signals using weighted average."""
        if not signals:
            return None

        # Weight by confidence
        total_weight = sum(s.confidence for s in signals)
        if total_weight == 0:
            return None

        # Weighted direction
        long_weight = sum(s.confidence for s in signals if s.direction == Direction.LONG)
        short_weight = sum(s.confidence for s in signals if s.direction == Direction.SHORT)

        if long_weight > short_weight:
            direction = Direction.LONG
            strength = long_weight / total_weight
        elif short_weight > long_weight:
            direction = Direction.SHORT
            strength = short_weight / total_weight
        else:
            return None

        # Average entry/SL/TP
        entry_prices = [float(s.entry_price) for s in signals if s.entry_price]
        stop_losses = [float(s.stop_loss) for s in signals if s.stop_loss]
        take_profits = [float(s.take_profit) for s in signals if s.take_profit]

        if not entry_prices:
            return None

        avg_entry = Decimal(str(np.mean(entry_prices)))
        avg_sl = Decimal(str(np.mean(stop_losses))) if stop_losses else None
        avg_tp = Decimal(str(np.mean(take_profits))) if take_profits else None

        avg_confidence = np.mean([s.confidence for s in signals])

        # Use first signal as base
        base = signals[0]

        return Signal(
            signal_id=base.signal_id,
            strategy_id=self.strategy_id,
            strategy_name=f"{self.config.name}_ensemble",
            symbol=base.symbol,
            timestamp=datetime.now(UTC),
            signal_type=SignalType.ENTRY,
            direction=direction,
            strength=strength,
            entry_price=avg_entry,
            stop_loss=avg_sl,
            take_profit=avg_tp,
            confidence=avg_confidence,
            timeframe=base.timeframe,
            metadata={
                "ensemble": True,
                "component_signals": len(signals),
                "long_weight": long_weight,
                "short_weight": short_weight,
            },
            expires_at=base.expires_at,
        )

    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        """Convert bars to Polars DataFrame."""
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
            "spread": [float(b.spread) for b in bars],
            "symbol": [b.symbol for b in bars],
        }
        return pl.DataFrame(data).sort("timestamp")


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy using Bollinger Bands and RSI."""

    async def _initialize(self) -> None:
        self._bar_buffer: list[Bar] = []

    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < 50:
            return signals

        df = self._bars_to_dataframe(self._bar_buffer[-50:])
        df = TechnicalIndicators.add_all_indicators_polars(df)

        latest = df.row(-1, named=True)

        close = latest["close"]
        bb_upper = latest.get("bb_upper_20", 0)
        bb_lower = latest.get("bb_lower_20", 0)
        bb_middle = latest.get("bb_middle_20", 0)
        rsi = latest.get("rsi_14", 50)
        atr = latest.get("atr_14", close * 0.001)

        # Mean reversion: buy at lower band, sell at upper band
        if close < bb_lower and rsi < 35:
            direction = Direction.LONG
            strength = min((bb_lower - close) / (bb_upper - bb_lower) * 2, 1.0) if bb_upper != bb_lower else 0.5
            entry = Decimal(str(close))
            sl = Decimal(str(close - 2 * atr))
            tp = Decimal(str(bb_middle))  # Target middle band

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.65,
                timeframe=bar.timeframe,
                metadata={"type": "mean_reversion", "bb_position": "lower"},
            ))

        elif close > bb_upper and rsi > 65:
            direction = Direction.SHORT
            strength = min((close - bb_upper) / (bb_upper - bb_lower) * 2, 1.0) if bb_upper != bb_lower else 0.5
            entry = Decimal(str(close))
            sl = Decimal(str(close + 2 * atr))
            tp = Decimal(str(bb_middle))

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.65,
                timeframe=bar.timeframe,
                metadata={"type": "mean_reversion", "bb_position": "upper"},
            ))

        return signals

    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
            "spread": [float(b.spread) for b in bars],
            "symbol": [b.symbol for b in bars],
        }
        return pl.DataFrame(data).sort("timestamp")


class TrendFollowingStrategy(Strategy):
    """Trend following strategy using EMA crossover and ADX."""

    async def _initialize(self) -> None:
        """Initialize strategy state."""
        self._bar_buffer = []
        logger.info(f"TrendFollowingStrategy initialized: {self.strategy_id}")

    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < 100:
            return signals

        df = self._bars_to_dataframe(self._bar_buffer[-100:])
        df = TechnicalIndicators.add_all_indicators_polars(df)

        latest = df.row(-1, named=True)
        prev = df.row(-2, named=True) if len(df) > 1 else latest

        close = latest["close"]
        ema_fast = latest.get("ema_20", 0)
        ema_slow = latest.get("ema_50", 0)
        ema_fast_prev = prev.get("ema_20", 0)
        ema_slow_prev = prev.get("ema_50", 0)
        adx = latest.get("adx_14", 0)
        atr = latest.get("atr_14", close * 0.001)

        # EMA crossover with ADX filter
        if ema_fast > ema_slow and ema_fast_prev <= ema_slow_prev and adx > 20:
            # Golden cross
            direction = Direction.LONG
            strength = min(adx / 50, 1.0)
            entry = Decimal(str(close))
            sl = Decimal(str(close - 2 * atr))
            tp = Decimal(str(close + 3 * atr))

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.7,
                timeframe=bar.timeframe,
                metadata={"type": "trend_following", "signal": "golden_cross"},
            ))

        elif ema_fast < ema_slow and ema_fast_prev >= ema_slow_prev and adx > 20:
            # Death cross
            direction = Direction.SHORT
            strength = min(adx / 50, 1.0)
            entry = Decimal(str(close))
            sl = Decimal(str(close + 2 * atr))
            tp = Decimal(str(close - 3 * atr))

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.7,
                timeframe=bar.timeframe,
                metadata={"type": "trend_following", "signal": "death_cross"},
            ))

        return signals

    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
            "spread": [float(b.spread) for b in bars],
            "symbol": [b.symbol for b in bars],
        }
        return pl.DataFrame(data).sort("timestamp")


class BreakoutStrategy(Strategy):
    """Breakout strategy using Donchian channels."""

    async def _initialize(self) -> None:
        raise NotImplementedError("Not implemented")

    async def _generate_signals(self, bar: Bar) -> list[Signal]:
        signals = []
        period = self.config.parameters.get("donchian_period", 20)
        self._bar_buffer.append(bar)
        if len(self._bar_buffer) < period + 5:
            return signals

        df = self._bars_to_dataframe(self._bar_buffer[-(period + 5):])

        # Donchian channels
        high_max = df["high"].rolling_max(window_size=period)
        low_min = df["low"].rolling_min(window_size=period)

        df = df.with_columns([
            high_max.alias("donchian_high"),
            low_min.alias("donchian_low"),
            ((high_max + low_min) / 2).alias("donchian_mid"),
        ])

        latest = df.row(-1, named=True)
        close = latest["close"]
        donchian_high = latest.get("donchian_high", 0)
        donchian_low = latest.get("donchian_low", 0)
        donchian_mid = latest.get("donchian_mid", (donchian_high + donchian_low) / 2)
        _atr = latest.get("atr_14", close * 0.001)

        # Breakout above Donchian high
        if close > donchian_high:
            direction = Direction.LONG
            strength = 0.7
            entry = Decimal(str(close))
            sl = Decimal(str(donchian_mid))  # Stop at middle
            tp = Decimal(str(close + 2 * (close - donchian_low)))  # 2x range

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.6,
                timeframe=bar.timeframe,
                metadata={"type": "breakout", "signal": "donchian_breakout_up"},
            ))

        # Breakdown below Donchian low
        elif close < donchian_low:
            direction = Direction.SHORT
            strength = 0.7
            entry = Decimal(str(close))
            sl = Decimal(str(donchian_mid))
            tp = Decimal(str(close - 2 * (donchian_high - close)))

            signals.append(Signal.create_entry(
                strategy_id=self.strategy_id,
                strategy_name=self.config.name,
                symbol=bar.symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                strength=strength,
                confidence=0.6,
                timeframe=bar.timeframe,
                metadata={"type": "breakout", "signal": "donchian_breakout_down"},
            ))

        return signals

    def _bars_to_dataframe(self, bars: list[Bar]) -> pl.DataFrame:
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
            "spread": [float(b.spread) for b in bars],
            "symbol": [b.symbol for b in bars],
        }
        return pl.DataFrame(data).sort("timestamp")


# Register all strategies
from src.strategy.base.strategy import strategy_registry

strategy_registry.register_class("ensemble", EnsembleStrategy)
strategy_registry.register_class("mean_reversion", MeanReversionStrategy)
strategy_registry.register_class("trend_following", TrendFollowingStrategy)
strategy_registry.register_class("breakout", BreakoutStrategy)