from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import nats
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, RetentionPolicy, StreamConfig

from src.infra.config.settings import settings
from src.infra.monitoring.logging import get_logger

logger = get_logger("nats")


@dataclass
class NATSConfig:
    servers: list[str] = field(default_factory=lambda: ["nats://localhost:4222"])
    name: str = "forex-trading-system"
    max_reconnect_attempts: int = -1
    reconnect_time_wait: int = 2
    ping_interval: int = 10
    max_outstanding_pings: int = 5


class NATSClientManager:
    """Manages NATS connection and JetStream."""

    def __init__(self, config: NATSConfig = None):
        self.config = config or NATSConfig(
            servers=settings.nats_servers,
            name=settings.nats_name,
            max_reconnect_attempts=settings.nats_max_reconnect_attempts,
            reconnect_time_wait=settings.nats_reconnect_time_wait,
        )
        self._nc: NATSClient | None = None
        self._js: JetStreamContext | None = None
        self._connected = False
        self._subscriptions: dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect to NATS server."""
        try:
            self._nc = await nats.connect(
                servers=self.config.servers,
                name=self.config.name,
                max_reconnect_attempts=self.config.max_reconnect_attempts,
                reconnect_time_wait=self.config.reconnect_time_wait,
                ping_interval=self.config.ping_interval,
                max_outstanding_pings=self.config.max_outstanding_pings,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback,
                closed_cb=self._closed_callback,
            )

            # Create JetStream context
            self._js = self._nc.jetstream()
            self._connected = True

            # Create streams
            await self._create_streams()

            logger.info(f"NATS connected to {self.config.servers}")

        except Exception as e:
            # In development, if NATS is not available, log as warning instead of error
            # since the system is designed to work in degraded mode without external services
            logger.warning(f"NATS connection failed (will operate in degraded mode): {e}")
            # Don't raise - allow application to continue without NATS
            self._connected = False

    async def disconnect(self) -> None:
        """Disconnect from NATS."""
        for sub in self._subscriptions.values():
            try:
                await sub.unsubscribe()
            except Exception as e:
                logger.error(f"Exception occurred: {e}")
        self._subscriptions.clear()

        if self._nc:
            await self._nc.close()
        self._connected = False
        logger.info("NATS disconnected")

    async def _create_streams(self) -> None:
        """Create JetStream streams for different event types."""
        streams = [
            StreamConfig(
                name="MARKET_DATA",
                subjects=["market.tick", "market.tick.>", "market.bar", "market.bar.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=86400,  # 24 hours
                max_bytes=1024 * 1024 * 1024,  # 1 GB
                storage="file",
                num_replicas=1,
            ),
            StreamConfig(
                name="TRADING_EVENTS",
                subjects=["signal", "signal.>", "order", "order.>", "fill", "fill.>", "position", "position.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=604800,  # 7 days
                max_bytes=1024 * 1024 * 1024,  # 1 GB
                storage="file",
                num_replicas=1,
            ),
            StreamConfig(
                name="RISK_EVENTS",
                subjects=["risk", "risk.>", "circuit_breaker", "circuit_breaker.>", "drawdown", "drawdown.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=604800,  # 7 days
                max_bytes=1024 * 1024 * 100,  # 100 MB
                storage="file",
                num_replicas=1,
            ),
            StreamConfig(
                name="SYSTEM_EVENTS",
                subjects=["system", "system.>", "health", "health.>", "metrics", "metrics.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=86400,  # 24 hours
                max_bytes=1024 * 1024 * 100,  # 100 MB
                storage="memory",
                num_replicas=1,
            ),
        ]

        for stream_config in streams:
            try:
                await self._js.add_stream(stream_config)
                logger.info(f"Created stream: {stream_config.name}")
            except Exception as e:
                # Stream might already exist - check if it's a "stream already exists" error
                if "already exists" in str(e).lower() or "stream name already in use" in str(e).lower():
                    logger.debug(f"Stream {stream_config.name} already exists")
                else:
                    logger.error(f"Failed to create stream {stream_config.name}: {e}")

    async def publish(self, subject: str, data: dict[str, Any]) -> None:
        """Publish message to subject - use regular NATS for fire-and-forget, JetStream for persistence."""
        if not self._connected or not self._nc:
            raise RuntimeError("NATS not connected")

        payload = json.dumps(data, default=str).encode()
        try:
            # Use regular NATS publish for fire-and-forget (no consumer needed)
            await self._nc.publish(subject, payload)
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}")
            raise

    async def subscribe(
        self,
        subject: str,
        callback: Callable[[dict[str, Any]], Any],
        durable: str | None = None,
        queue: str | None = None,
    ) -> None:
        """Subscribe to subject with callback."""
        if not self._connected or not self._js:
            raise RuntimeError("NATS not connected")

        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                await callback(data)
                await msg.ack()
            except Exception as e:
                logger.error(f"Error processing message from {subject}: {e}")
                await msg.nak()

        try:
            sub = await self._js.subscribe(
                subject,
                cb=message_handler,
                durable=durable,
                queue=queue,
                manual_ack=True,
            )
            self._subscriptions[subject] = sub
            logger.info(f"Subscribed to {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}")
            raise

    async def subscribe_pull(
        self,
        subject: str,
        batch_size: int = 100,
        timeout: float = 5.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Pull-based subscription for batch processing."""
        if not self._connected or not self._js:
            raise RuntimeError("NATS not connected")

        consumer_name = f"pull_{subject.replace('.', '_').replace('>', 'all')}"

        try:
            consumer = await self._js.add_consumer(
                stream="MARKET_DATA" if subject.startswith("market.") else "TRADING_EVENTS",
                config=ConsumerConfig(
                    durable_name=consumer_name,
                    ack_policy="explicit",
                    max_deliver=3,
                    ack_wait=30,
                    max_ack_pending=1000,
                ),
            )
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            # Consumer might exist
            consumer = await self._js.consumer_info(
                stream="MARKET_DATA" if subject.startswith("market.") else "TRADING_EVENTS",
                consumer=consumer_name,
            )

        while True:
            try:
                messages = await consumer.fetch(batch=batch_size, timeout=timeout)
                for msg in messages:
                    try:
                        data = json.loads(msg.data.decode())
                        yield data
                        await msg.ack()
                    except Exception as e:
                        logger.error(f"Error processing pulled message: {e}")
                        await msg.nak()
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Pull subscription error: {e}")
                await asyncio.sleep(1)

    def is_connected(self) -> bool:
        return self._connected and self._nc and self._nc.is_connected

    @property
    def nc(self) -> NATSClient | None:
        return self._nc

    @property
    def js(self) -> JetStreamContext | None:
        return self._js

    # ============================================
    # CALLBACKS
    # ============================================

    async def _error_callback(self, e: Exception) -> None:
        # In development, log NATS errors as warnings since the system is designed
        # to work in degraded mode without external services
        logger.warning(f"NATS error (operating in degraded mode): {e}")

    async def _disconnected_callback(self) -> None:
        logger.warning("NATS disconnected")
        self._connected = False

    async def _reconnected_callback(self) -> None:
        logger.info("NATS reconnected")
        self._connected = True

    async def _closed_callback(self) -> None:
        logger.info("NATS connection closed")
        self._connected = False


# Global NATS client
nats_client = NATSClientManager()


# Convenience functions for common publishing patterns
async def publish_tick(symbol: str, bid: float, ask: float, last: float | None = None, volume: float | None = None, timestamp: datetime | None = None, source: str = "mt5") -> None:
    """Publish tick data."""
    await nats_client.publish("market.tick", {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "last": last,
        "volume": volume,
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        "source": source,
    })


async def publish_bar(symbol: str, timeframe: str, open_: float, high: float, low: float, close: float, volume: float, spread: float = 0, timestamp: datetime | None = None, source: str = "mt5") -> None:
    """Publish bar data."""
    await nats_client.publish(f"market.bar.{timeframe}", {
        "symbol": symbol,
        "timeframe": timeframe,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "spread": spread,
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        "source": source,
    })


async def publish_signal(signal: dict[str, Any]) -> None:
    """Publish trading signal."""
    await nats_client.publish("signal.entry", signal)


async def publish_order(order: dict[str, Any]) -> None:
    """Publish order event."""
    await nats_client.publish(f"order.{order.get('status', 'new')}", order)


async def publish_fill(fill: dict[str, Any]) -> None:
    """Publish fill event."""
    await nats_client.publish("fill.new", fill)


async def publish_position_update(position: dict[str, Any]) -> None:
    """Publish position update."""
    await nats_client.publish("position.update", position)


async def publish_risk_metrics(metrics: dict[str, Any]) -> None:
    """Publish risk metrics."""
    await nats_client.publish("risk.metrics", metrics)


async def publish_circuit_breaker(breaker_type: str, state: str, value: float) -> None:
    """Publish circuit breaker event."""
    await nats_client.publish(f"circuit_breaker.{breaker_type}", {
        "breaker_type": breaker_type,
        "state": state,
        "value": value,
        "timestamp": datetime.now(UTC).isoformat(),
    })


async def publish_drawdown(drawdown_pct: float, peak_equity: float, current_equity: float) -> None:
    """Publish drawdown event."""
    await nats_client.publish("drawdown.update", {
        "drawdown_pct": drawdown_pct,
        "peak_equity": peak_equity,
        "current_equity": current_equity,
        "timestamp": datetime.now(UTC).isoformat(),
    })


async def publish_system_health(component: str, healthy: bool, details: dict | None = None) -> None:
    """Publish system health."""
    await nats_client.publish(f"health.{component}", {
        "component": component,
        "healthy": healthy,
        "details": details or {},
        "timestamp": datetime.now(UTC).isoformat(),
    })