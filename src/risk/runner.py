from __future__ import annotations

import asyncio
import signal
from decimal import Decimal

from loguru import logger

from src.data.storage.redis_cache import redis_cache
from src.data.storage.timescale import timescaledb
from src.infra.messaging.nats_client import (
    nats_client,
    publish_circuit_breaker,
    publish_drawdown,
    publish_risk_metrics,
)
from src.infra.monitoring.logging import setup_logging
from src.infra.monitoring.metrics import metrics_collector
from src.risk import (
    circuit_breaker_manager,
    drawdown_guard,
    portfolio_risk_manager,
    volatility_monitor,
)


class RiskRunner:
    """Main risk management runner."""

    def __init__(self):
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._check_interval = 10  # seconds

    async def initialize(self) -> None:
        """Initialize all components."""
        setup_logging()
        logger.info("Initializing risk runner...")

        # Connect to infrastructure
        await timescaledb.connect()
        await redis_cache.connect()
        await nats_client.connect()

        # Initialize metrics
        metrics_collector.init_metrics()

        # Subscribe to relevant events
        await nats_client.subscribe("fill.new", self._on_fill)
        await nats_client.subscribe("position.update", self._on_position_update)
        await nats_client.subscribe("market.bar.1m", self._on_market_data)

        logger.info("Risk runner initialized")

    async def _on_fill(self, data: dict) -> None:
        """Handle fill event."""
        # Update portfolio risk manager with fill

    async def _on_position_update(self, data: dict) -> None:
        """Handle position update."""

    async def _on_market_data(self, data: dict) -> None:
        """Handle market data for volatility monitoring."""
        symbol = data.get("symbol")
        close = data.get("close")
        if symbol and close:
            vol_status = volatility_monitor.update(Decimal(str(close)))
            if vol_status.get("is_spike"):
                logger.warning(f"Volatility spike detected for {symbol}: {vol_status['spike_ratio']:.2f}x")
                await publish_risk_metrics({
                    "event": "volatility_spike",
                    "symbol": symbol,
                    "spike_ratio": vol_status["spike_ratio"],
                    "current_vol": vol_status["current_volatility"],
                    "baseline_vol": vol_status["baseline_volatility"],
                })

    async def run(self) -> None:
        """Main risk monitoring loop."""
        self._running = True

        while self._running:
            try:
                await self._check_risk()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(5)

    async def _check_risk(self) -> None:
        """Perform comprehensive risk checks."""
        try:
            # Get account info from brokers (simplified - would aggregate)
            total_equity = Decimal(125000)  # Would fetch from brokers
            total_balance = Decimal(123000)
            total_margin = Decimal(15000)

            # Get positions (would fetch from brokers)
            positions = {}  # Would fetch from brokers

            # Get symbols info
            symbols = {}  # Would fetch from database

            # Update equity curve
            portfolio_risk_manager.update_equity(total_equity)

            # Update drawdown guard
            dd_status = drawdown_guard.update(total_equity)

            # Get risk metrics
            risk_metrics = portfolio_risk_manager.get_risk_metrics(
                equity=total_equity,
                balance=total_balance,
                positions=positions,
                symbols=symbols,
                margin_used=total_margin,
            )

            # Check circuit breakers
            metrics = {
                "daily_loss_pct": float(risk_metrics.daily_pnl / total_equity * 100) if total_equity > 0 else 0,
                "current_drawdown": dd_status["current_drawdown"],
                "consecutive_losses": 0,  # Would track
                "volatility_spike": 1.0,  # From volatility monitor
                "correlation_breakdown": risk_metrics.max_correlation,
                "margin_call": risk_metrics.margin_level,
                "circuit_breakers_open": len(circuit_breaker_manager.get_open_breakers()),
                "strategy_errors": 0,  # Would track
                "broker_connected": True,  # Would check
            }

            triggered = circuit_breaker_manager.check_all(metrics)

            # Publish risk metrics
            await publish_risk_metrics({
                "equity": float(total_equity),
                "balance": float(total_balance),
                "margin_used": float(total_margin),
                "free_margin": float(total_equity - total_margin),
                "margin_level": risk_metrics.margin_level,
                "leverage": risk_metrics.leverage,
                "unrealized_pnl": float(risk_metrics.total_unrealized_pnl),
                "realized_pnl": float(risk_metrics.total_realized_pnl),
                "daily_pnl": float(risk_metrics.daily_pnl),
                "weekly_pnl": float(risk_metrics.weekly_pnl),
                "monthly_pnl": float(risk_metrics.monthly_pnl),
                "current_drawdown": risk_metrics.current_drawdown,
                "max_drawdown": risk_metrics.max_drawdown,
                "var_95": float(risk_metrics.portfolio_var_95),
                "var_99": float(risk_metrics.portfolio_var_99),
                "es_95": float(risk_metrics.portfolio_es_95),
                "es_99": float(risk_metrics.portfolio_es_99),
                "max_correlation": risk_metrics.max_correlation,
                "sector_exposures": risk_metrics.sector_exposures,
                "open_positions": risk_metrics.open_positions,
                "circuit_breakers": circuit_breaker_manager.get_status(),
                "drawdown_guard": dd_status,
                "volatility": volatility_monitor.get_status(),
            })

            # Update Prometheus metrics
            metrics_collector.update_equity(float(total_equity))
            metrics_collector.update_pnl(
                float(risk_metrics.total_unrealized_pnl),
                float(risk_metrics.total_realized_pnl),
            )
            metrics_collector.update_drawdown(risk_metrics.current_drawdown, risk_metrics.max_drawdown)
            metrics_collector.update_margin(
                float(total_margin),
                float(total_equity - total_margin),
                risk_metrics.margin_level,
                risk_metrics.leverage,
            )
            metrics_collector.update_var(
                float(risk_metrics.portfolio_var_95),
                float(risk_metrics.portfolio_var_99),
                float(risk_metrics.portfolio_es_95),
                float(risk_metrics.portfolio_es_99),
            )
            metrics_collector.update_correlation(risk_metrics.max_correlation)
            for sector, exposure in risk_metrics.sector_exposures.items():
                metrics_collector.update_sector_exposure(sector, exposure)
            metrics_collector.update_loss_limits(
                float(risk_metrics.daily_pnl / total_equity * 100) if total_equity > 0 else 0,
                float(risk_metrics.weekly_pnl / total_equity * 100) if total_equity > 0 else 0,
                float(risk_metrics.monthly_pnl / total_equity * 100) if total_equity > 0 else 0,
            )

            # Check for critical conditions
            if dd_status["stop_trading"]:
                logger.critical("DRAWDOWN GUARD: Trading stopped!")
                await publish_drawdown(
                    drawdown_pct=dd_status["current_drawdown"],
                    peak_equity=dd_status.get("peak_equity", 0),
                    current_equity=float(total_equity),
                )

            if dd_status["warning"]:
                logger.warning(f"DRAWDOWN GUARD: Warning - {dd_status['current_drawdown']:.2%}")

            if triggered:
                for bt in triggered:
                    breaker = circuit_breaker_manager.get_breaker(bt)
                    await publish_circuit_breaker(
                        breaker_type=bt.value,
                        state=breaker.state.value,
                        value=metrics.get(bt.value, 0),
                    )

        except Exception as e:
            logger.error(f"Risk check failed: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down risk runner...")
        self._running = False
        self._shutdown_event.set()

        # Disconnect infrastructure
        await timescaledb.disconnect()
        await redis_cache.disconnect()
        await nats_client.disconnect()

        logger.info("Risk runner shutdown complete")


async def run_risk_worker():
    """Entry point for risk worker."""
    runner = RiskRunner()

    # Signal handling
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, runner._shutdown_event.set)

    try:
        await runner.initialize()
        await runner.run()
    except Exception as e:
        logger.error(f"Risk runner error: {e}")
    finally:
        await runner.shutdown()


if __name__ == "__main__":
    asyncio.run(run_risk_worker())