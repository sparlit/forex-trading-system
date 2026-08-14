from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime
from decimal import Decimal

from loguru import logger

from src.data.models import Timeframe
from src.data.storage.redis_cache import redis_cache
from src.data.storage.timescale import timescaledb
from src.infra.messaging.nats_client import nats_client
from src.infra.monitoring.logging import setup_logging
from src.infra.monitoring.metrics import metrics_collector
from src.strategy.base.strategy import StrategyConfig, strategy_registry


class StrategyRunner:
    """Main strategy runner."""

    def __init__(self):
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._bar_subscriptions: dict[str, asyncio.Task] = {}

    async def initialize(self) -> None:
        """Initialize all components."""
        setup_logging()
        logger.info("Initializing strategy runner...")

        # Connect to infrastructure
        await timescaledb.connect()
        await redis_cache.connect()
        await nats_client.connect()

        # Initialize metrics
        metrics_collector.init_metrics()

        # Create and register strategies
        await self._create_strategies()

        # Initialize all strategies
        await strategy_registry.initialize_all()

        # Subscribe to market data
        await self._subscribe_market_data()

        # Register signal handler
        await nats_client.subscribe("signal.entry", self._on_signal)

        logger.info("Strategy runner initialized")

    async def _create_strategies(self) -> None:
        """Create strategy instances."""
        # Ensemble ML Strategy
        ensemble_config = StrategyConfig(
            strategy_id="ensemble_ml",
            name="Ensemble ML",
            description="ML ensemble combining LSTM, Transformer, and technical analysis",
            version="1.0.0",
            asset_classes=["forex", "metals", "crypto"],
            timeframes=[Timeframe.H1, Timeframe.H4],
            parameters={
                "model_type": "lstm",
                "lookback": 100,
                "prediction_horizon": 10,
                "hidden_size": 128,
                "num_layers": 2,
                "dropout": 0.2,
                "learning_rate": 0.001,
                "min_confidence": 0.6,
            },
            is_paper=True,
            max_positions=10,
        )
        strategy_registry.create_strategy("ensemble", ensemble_config)

        # Mean Reversion Strategy
        mr_config = StrategyConfig(
            strategy_id="mean_reversion",
            name="Mean Reversion",
            description="Bollinger Bands + RSI mean reversion",
            version="1.0.0",
            asset_classes=["forex", "metals"],
            timeframes=[Timeframe.M15, Timeframe.H1],
            parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
            },
            is_paper=True,
            max_positions=5,
        )
        strategy_registry.create_strategy("mean_reversion", mr_config)

        # Trend Following Strategy
        tf_config = StrategyConfig(
            strategy_id="trend_following",
            name="Trend Following",
            description="EMA crossover with ADX filter",
            version="1.0.0",
            asset_classes=["forex", "metals", "crypto"],
            timeframes=[Timeframe.H1, Timeframe.H4],
            parameters={
                "ema_fast": 20,
                "ema_slow": 50,
                "adx_period": 14,
                "adx_threshold": 20,
            },
            is_paper=True,
            max_positions=5,
        )
        strategy_registry.create_strategy("trend_following", tf_config)

        # Breakout Strategy
        bo_config = StrategyConfig(
            strategy_id="breakout",
            name="Breakout",
            description="Donchian channel breakout",
            version="1.0.0",
            asset_classes=["forex", "crypto"],
            timeframes=[Timeframe.H1, Timeframe.H4],
            parameters={
                "donchian_period": 20,
                "atr_period": 14,
                "atr_multiplier": 2.0,
            },
            is_paper=True,
            max_positions=5,
        )
        strategy_registry.create_strategy("breakout", bo_config)

        logger.info(f"Created {len(strategy_registry.get_all())} strategies")

    async def _subscribe_market_data(self) -> None:
        """Subscribe to market data for all strategies."""
        # Get all unique symbols and timeframes from strategies
        all_symbols = set()
        all_timeframes = set()

        for strategy in strategy_registry.get_all():
            all_symbols.update(strategy.config.symbols)
            all_timeframes.update(strategy.config.timeframes)

        # If no specific symbols, subscribe to major pairs
        if not all_symbols:
            all_symbols = {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"}

        # Subscribe to bars for each timeframe
        for tf in all_timeframes:
            subject = f"market.bar.{tf.value}"
            task = asyncio.create_task(self._consume_bars(subject, list(all_symbols), tf))
            self._bar_subscriptions[subject] = task

        logger.info(f"Subscribed to market data for {len(all_symbols)} symbols across {len(all_timeframes)} timeframes")

    async def _consume_bars(self, subject: str, symbols: list[str], timeframe) -> None:
        """Consume bars from NATS and process through strategies."""
        async def handler(data: dict):
            try:
                symbol = data.get("symbol")
                if symbol not in symbols:
                    return

                # Convert to Bar object
                from src.data.models import Bar, Timeframe
                bar = Bar(
                    symbol_id=data.get("symbol_id", 0),
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    timeframe=Timeframe(data["timeframe"]),
                    open=Decimal(str(data["open"])),
                    high=Decimal(str(data["high"])),
                    low=Decimal(str(data["low"])),
                    close=Decimal(str(data["close"])),
                    volume=Decimal(str(data["volume"])),
                    spread=Decimal(str(data.get("spread", 0))),
                    source=data.get("source", "mt5"),
                )

                # Process through relevant strategies
                for strategy in strategy_registry.get_all():
                    if not strategy.is_active:
                        continue
                    if strategy.config.symbols and symbol not in strategy.config.symbols:
                        continue
                    if timeframe not in strategy.config.timeframes:
                        continue

                    start_time = datetime.now(UTC)
                    signals = await strategy.on_bar(bar)
                    latency = (datetime.now(UTC) - start_time).total_seconds()

                    # Record metrics
                    metrics_collector.record_signal(
                        strategy=strategy.strategy_id,
                        symbol=symbol,
                        signal_type="entry",
                        direction=signals[0].direction.value if signals else "none",
                        latency=latency,
                    )

                    # Publish signals
                    for signal in signals:
                        await nats_client.publish("signal.entry", signal.to_dict())

            except Exception as e:
                logger.error(f"Error processing bar: {e}")
                metrics_collector.record_error("strategy_runner", "bar_processing")

        await nats_client.subscribe(subject, handler, durable="strategy_runner", queue="strategies")

    async def _on_signal(self, data: dict) -> None:
        """Handle incoming signal (for monitoring/logging)."""
        logger.info(f"Signal received: {data.get('strategy_id')} - {data.get('symbol')} {data.get('direction')}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down strategy runner...")
        self._running = False
        self._shutdown_event.set()

        # Cancel subscriptions
        for task in self._bar_subscriptions.values():
            task.cancel()
        await asyncio.gather(*self._bar_subscriptions.values(), return_exceptions=True)

        # Stop strategies
        await strategy_registry.stop_all()

        # Disconnect infrastructure
        await timescaledb.disconnect()
        await redis_cache.disconnect()
        await nats_client.disconnect()

        logger.info("Strategy runner shutdown complete")

    async def run(self) -> None:
        """Run the strategy runner."""
        self._running = True
        await self._shutdown_event.wait()


async def run_strategy_worker():
    """Entry point for strategy worker."""
    runner = StrategyRunner()

    # Signal handling
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, runner._shutdown_event.set)

    try:
        await runner.initialize()
        await runner.run()
    except Exception as e:
        logger.error(f"Strategy runner error: {e}")
    finally:
        await runner.shutdown()


if __name__ == "__main__":
    asyncio.run(run_strategy_worker())