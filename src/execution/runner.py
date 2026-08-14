from __future__ import annotations

import asyncio
import signal
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from loguru import logger

from src.data.models import Direction, Signal
from src.data.storage.redis_cache import redis_cache
from src.data.storage.timescale import timescaledb
from src.execution.algorithms.execution_algorithms import ExecutionAlgorithm, create_algorithm
from src.execution.brokers.ccxt_broker import CCXTBrokerAdapter
from src.execution.brokers.mt5_broker import MT5BrokerAdapter
from src.execution.order_manager import (
    ExecutionConfig,
    ExecutionEngine,
    Order,
)
from src.infra.config.settings import settings
from src.infra.messaging.nats_client import nats_client
from src.infra.monitoring.logging import setup_logging
from src.risk import circuit_breaker_manager, drawdown_guard, portfolio_risk_manager, position_sizer


class ExecutionRunner:
    """Main execution runner coordinating all components."""

    def __init__(self):
        self.engine = ExecutionEngine(ExecutionConfig(
            algorithm=ExecutionAlgorithm(settings.execution_default_algorithm),
            max_slippage_bps=settings.execution_max_slippage_bps,
            partial_fill_timeout=settings.execution_partial_fill_timeout,
            max_order_age=settings.execution_max_order_age_seconds,
            retry_attempts=settings.execution_retry_attempts,
            retry_delay=settings.execution_retry_delay_seconds,
            use_smart_routing=settings.execution_use_smart_routing,
            min_order_size=settings.execution_min_order_size,
            max_order_size=settings.execution_max_order_size,
        ))
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize all components."""
        setup_logging()
        logger.info("Initializing execution runner...")

        # Connect to databases
        await timescaledb.connect()
        await redis_cache.connect()
        await nats_client.connect()

        # Register brokers
        if settings.mt5_enabled:
            mt5_broker = MT5BrokerAdapter()
            await mt5_broker.connect()
            self.engine.register_broker(mt5_broker)

        if settings.ccxt_enabled:
            ccxt_broker = CCXTBrokerAdapter()
            await ccxt_broker.connect()
            self.engine.register_broker(ccxt_broker)

        # Connect execution engine
        await self.engine.connect_all()

        # Register algorithm callbacks
        for algorithm_type in ExecutionAlgorithm:
            algo = create_algorithm(algorithm_type, self.engine.config)
            algo.register_callback(self._on_algorithm_slice)
            # Store algorithms (in practice, would use a registry)
            setattr(self, f"_algo_{algorithm_type.value}", algo)

        # Subscribe to signals
        await nats_client.subscribe("signals")
        self._signal_task = asyncio.create_task(self._process_signals())

        # Start order monitoring
        self._monitor_task = asyncio.create_task(self.engine.monitor_orders())

        # Start risk monitoring
        self._risk_task = asyncio.create_task(self._monitor_risk())

        logger.info("Execution runner initialized")

    async def _on_algorithm_slice(self, slice_order: Order) -> None:
        """Handle slice order from algorithm."""
        # Place slice order through engine
        broker = self.engine.brokers.get(slice_order.broker)
        if broker:
            try:
                placed = await broker.place_order(slice_order)
                self.engine.order_manager.update_order(placed)
            except Exception as e:
                logger.error(f"Failed to place slice order: {e}")

    async def _process_signals(self) -> None:
        """Process incoming signals from NATS."""
        async for msg in nats_client.listen():
            try:
                signal_data = msg
                signal = self._parse_signal(signal_data)

                if signal:
                    await self.execute_signal(signal)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing signal: {e}")

    def _parse_signal(self, data: dict) -> Signal | None:
        """Parse signal from NATS message."""
        try:
            from src.data.models import Timeframe
            from src.strategy.base.signal import Signal, SignalType

            return Signal(
                signal_id=UUID(data["signal_id"]),
                strategy_id=data["strategy_id"],
                strategy_name=data.get("strategy_name", ""),
                symbol=data["symbol"],
                symbol_id=data.get("symbol_id", 0),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                signal_type=SignalType(data["signal_type"]),
                direction=Direction(data["direction"]),
                strength=data["strength"],
                confidence=data.get("confidence", 0.5),
                entry_price=Decimal(str(data["entry_price"])) if data.get("entry_price") else None,
                stop_loss=Decimal(str(data["stop_loss"])) if data.get("stop_loss") else None,
                take_profit=Decimal(str(data["take_profit"])) if data.get("take_profit") else None,
                position_size=Decimal(str(data["position_size"])) if data.get("position_size") else None,
                timeframe=Timeframe(data.get("timeframe", "1h")),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            logger.error(f"Failed to parse signal: {e}")
            return None

    async def execute_signal(self, signal: Signal) -> list[Order]:
        """Execute a trading signal with full risk checks."""
        orders = []

        # Check circuit breakers
        if circuit_breaker_manager.is_any_open():
            open_breakers = circuit_breaker_manager.get_open_breakers()
            logger.warning(f"Circuit breakers open, rejecting signal: {open_breakers}")
            return orders

        # Check drawdown guard
        dd_status = drawdown_guard.get_status()
        if dd_status["trading_stopped"]:
            logger.warning("Drawdown guard: trading stopped, rejecting signal")
            return orders

        # Get current portfolio state
        account_info = {}
        for broker in self.engine.brokers.values():
            info = await broker.get_account_info()
            account_info[broker.broker_type.value] = info

        # Use first account for equity (in production, aggregate)
        equity = Decimal(0)
        margin_used = Decimal(0)
        for info in account_info.values():
            equity += info.get("equity", Decimal(0))
            margin_used += info.get("margin", Decimal(0))

        # Get current positions
        all_positions = {}
        for broker in self.engine.brokers.values():
            positions = await broker.get_positions()
            for pos in positions:
                all_positions[pos.symbol] = pos

        # Get symbol info
        symbol_info = await self._get_symbol_info(signal.symbol)
        if not symbol_info:
            logger.error(f"Symbol info not found for {signal.symbol}")
            return orders

        # Calculate position size with pyramiding multiplier
        # Build a multiplier dict: for each symbol, if all current positions are in profit,
        # we allow a pyramiding factor (e.g., 1 + 0.5 * number_of_profitable_positions).
        # This overrides the global max‑open‑positions limit for that symbol.
        symbol_multiplier: dict[str, Decimal] = {}
        # Aggregate profit status per symbol
        profit_counts: dict[str, int] = {}
        for pos_symbol, pos in all_positions.items():
            # Assume Position has attribute `unrealized_pnl` (Decimal) – if not, fallback to 0
            pnl = getattr(pos, "unrealized_pnl", Decimal(0))
            if pnl > 0:
                profit_counts[pos_symbol] = profit_counts.get(pos_symbol, 0) + 1
        for sym, cnt in profit_counts.items():
            # Example multiplier: each profitable position adds 0.5x to the base size
            symbol_multiplier[sym] = Decimal(1) + Decimal(cnt) * Decimal("0.5")

        sizing_result = position_sizer.calculate_position_size(
            signal=signal,
            symbol=symbol_info,
            equity=equity,
            current_positions=all_positions,
            account_balance=equity,
            free_margin=equity - margin_used,
            symbol_multiplier=symbol_multiplier,
        )

        # Validate with portfolio risk manager
        risk_ok, risk_errors = portfolio_risk_manager.validate_new_position(
            signal=signal,
            symbol=symbol_info,
            position_size=sizing_result.size,
            equity=equity,
            positions=all_positions,
            symbols={signal.symbol: symbol_info},
            margin_used=margin_used,
        )

        if not risk_ok:
            logger.warning(f"Risk check failed for {signal.symbol}: {risk_errors}")
            return orders

        # Apply drawdown reduction
        if dd_status["reduce_position"]:
            sizing_result.size = sizing_result.size * Decimal(str(dd_status["position_multiplier"]))
            sizing_result.size = symbol_info.normalize_volume(sizing_result.size)
            logger.info(f"Drawdown guard: reduced position size to {sizing_result.size}")

        # Update signal with calculated size
        signal.position_size = sizing_result.size

        # Execute through engine
        placed_orders = await self.engine.execute_signal(signal)
        orders.extend(placed_orders)

        # Store signal and orders
        await self._store_execution(signal, orders)

        return orders

    async def _get_symbol_info(self, symbol: str):
        """Get symbol info from any broker."""
        for broker in self.engine.brokers.values():
            info = await broker.get_symbol_info(symbol)
            if info:
                from src.data.models import Symbol
                return Symbol(
                    symbol_id=0,
                    symbol=symbol,
                    base_currency=info.get("currency_base", ""),
                    quote_currency=info.get("currency_profit", ""),
                    contract_size=info.get("contract_size", Decimal(1)),
                    tick_size=info.get("tick_size", Decimal("0.00001")),
                    tick_value=info.get("tick_value", Decimal(1)),
                    min_volume=info.get("volume_min", Decimal("0.01")),
                    max_volume=info.get("volume_max", Decimal(100)),
                    volume_step=info.get("volume_step", Decimal("0.01")),
                    swap_long=info.get("swap_long", Decimal(0)),
                    swap_short=info.get("swap_short", Decimal(0)),
                    margin_currency=info.get("currency_margin", "USD"),
                    margin_rate=info.get("margin_initial", Decimal("0.01")),
                    is_active=True,
                )
        return None

    async def _store_execution(self, signal: Signal, orders: list[Order]) -> None:
        """Store signal and orders to database."""
        # Store signal
        # In production, would store to TimescaleDB

    async def _monitor_risk(self) -> None:
        """Monitor portfolio risk periodically."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Get account info
                total_equity = Decimal(0)
                total_margin = Decimal(0)
                all_positions = {}

                for broker in self.engine.brokers.values():
                    info = await broker.get_account_info()
                    total_equity += info.get("equity", Decimal(0))
                    total_margin += info.get("margin", Decimal(0))

                    positions = await broker.get_positions()
                    for pos in positions:
                        all_positions[pos.symbol] = pos

                # Update equity curve
                portfolio_risk_manager.update_equity(total_equity)

                # Update drawdown guard
                dd_status = drawdown_guard.update(total_equity)
                if dd_status["stop_trading"]:
                    logger.critical("DRAWDOWN GUARD: Stopping all trading!")
                    # Cancel all open orders
                    active_orders = self.engine.order_manager.get_active_orders()
                    for order in active_orders:
                        await self.engine.cancel_order(order.order_id)

                # Check circuit breakers
                metrics = {
                    "daily_loss": float(portfolio_risk_manager._daily_pnl_history[-1][1]) if portfolio_risk_manager._daily_pnl_history else 0,
                    "drawdown": dd_status["current_drawdown"],
                    "consecutive_losses": 0,  # Would track this
                    "volatility_spike": 1.0,  # Would get from volatility monitor
                    "correlation_breakdown": 0.0,
                    "margin_call": float(total_margin / total_equity * 100) if total_equity > 0 else 0,
                }
                circuit_breaker_manager.check_all(metrics)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down execution runner...")
        self._running = False
        self._shutdown_event.set()

        # Cancel tasks
        for task in [self._signal_task, self._monitor_task, self._risk_task]:
            if task:
                task.cancel()

        await asyncio.gather(
            self._signal_task, self._monitor_task, self._risk_task,
            return_exceptions=True
        )

        # Stop order monitoring
        self.engine.stop_monitoring()

        # Disconnect brokers
        await self.engine.disconnect_all()

        # Disconnect databases
        await timescaledb.disconnect()
        await redis_cache.disconnect()
        await nats_client.disconnect()

        logger.info("Execution runner shutdown complete")

    async def run(self) -> None:
        """Run the execution runner."""
        self._running = True
        await self._shutdown_event.wait()


async def run_execution_worker():
    """Entry point for execution worker."""
    runner = ExecutionRunner()

    # Signal handling
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, runner._shutdown_event.set)

    try:
        await runner.initialize()
        await runner.run()
    except Exception as e:
        logger.error(f"Execution runner error: {e}")
    finally:
        await runner.shutdown()


if __name__ == "__main__":
    asyncio.run(run_execution_worker())