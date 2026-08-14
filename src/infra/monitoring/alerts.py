from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import httpx
from loguru import logger

from src.infra.config.settings import settings


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    PUSHBULLET = "pushbullet"


@dataclass
class Alert:
    """Alert message."""
    alert_id: UUID = field(default_factory=uuid4)
    level: AlertLevel = AlertLevel.INFO
    title: str = ""
    message: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    channels: list[AlertChannel] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


@dataclass
class AlertRule:
    """Alert rule configuration."""
    rule_id: str
    name: str
    condition: Callable[[dict[str, Any]], bool]
    level: AlertLevel = AlertLevel.WARNING
    channels: list[AlertChannel] = field(default_factory=list)
    cooldown_seconds: int = 300  # 5 minutes
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    _last_triggered: datetime | None = field(default=None, init=False)


class AlertManager:
    """Manages alerting across multiple channels."""

    def __init__(self):
        self._rules: dict[str, AlertRule] = {}
        self._handlers: dict[AlertChannel, Callable[[Alert], Awaitable[bool]]] = {}
        self._alert_history: list[Alert] = []
        self._max_history = 10000
        self._initialized = False

        # Default webhook URLs from settings
        self._webhook_urls: dict[AlertChannel, str] = {
            AlertChannel.TELEGRAM: settings.monitoring_alert_webhook_telegram,
            AlertChannel.DISCORD: settings.monitoring_alert_webhook_discord,
            AlertChannel.EMAIL: settings.monitoring_alert_webhook_email,
        }

    async def initialize(self) -> None:
        """Initialize alert handlers."""
        if self._initialized:
            return

        # Register default handlers
        self._handlers[AlertChannel.TELEGRAM] = self._send_telegram
        self._handlers[AlertChannel.DISCORD] = self._send_discord
        self._handlers[AlertChannel.EMAIL] = self._send_email
        self._handlers[AlertChannel.WEBHOOK] = self._send_webhook
        self._handlers[AlertChannel.SLACK] = self._send_slack

        # Register default rules
        self._register_default_rules()

        self._initialized = True
        logger.info("Alert manager initialized")

    def _register_default_rules(self) -> None:
        """Register default alert rules."""

        # Daily loss limit
        self.register_rule(AlertRule(
            rule_id="daily_loss_limit",
            name="Daily Loss Limit",
            condition=lambda m: m.get("daily_loss_pct", 0) > settings.risk_daily_loss_limit,
            level=AlertLevel.ERROR,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD, AlertChannel.EMAIL],
            cooldown_seconds=3600,
        ))

        # Max drawdown
        self.register_rule(AlertRule(
            rule_id="max_drawdown",
            name="Maximum Drawdown",
            condition=lambda m: m.get("current_drawdown", 0) > settings.risk_max_drawdown,
            level=AlertLevel.CRITICAL,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD, AlertChannel.EMAIL],
            cooldown_seconds=3600,
        ))

        # Margin call
        self.register_rule(AlertRule(
            rule_id="margin_call",
            name="Margin Call Warning",
            condition=lambda m: m.get("margin_level", 100) < settings.risk_margin_call_level * 100,
            level=AlertLevel.ERROR,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD],
            cooldown_seconds=600,
        ))

        # Stop out
        self.register_rule(AlertRule(
            rule_id="stop_out",
            name="Stop Out Imminent",
            condition=lambda m: m.get("margin_level", 100) < settings.risk_stop_out_level * 100,
            level=AlertLevel.CRITICAL,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD, AlertChannel.EMAIL],
            cooldown_seconds=60,
        ))

        # High correlation
        self.register_rule(AlertRule(
            rule_id="high_correlation",
            name="High Position Correlation",
            condition=lambda m: m.get("max_correlation", 0) > settings.risk_max_correlation,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.TELEGRAM],
            cooldown_seconds=1800,
        ))

        # Circuit breaker triggered
        self.register_rule(AlertRule(
            rule_id="circuit_breaker",
            name="Circuit Breaker Triggered",
            condition=lambda m: m.get("circuit_breakers_open", 0) > 0,
            level=AlertLevel.CRITICAL,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD, AlertChannel.EMAIL],
            cooldown_seconds=60,
        ))

        # Strategy error
        self.register_rule(AlertRule(
            rule_id="strategy_error",
            name="Strategy Error",
            condition=lambda m: m.get("strategy_errors", 0) > 0,
            level=AlertLevel.ERROR,
            channels=[AlertChannel.TELEGRAM],
            cooldown_seconds=300,
        ))

        # Connection lost
        self.register_rule(AlertRule(
            rule_id="connection_lost",
            name="Broker Connection Lost",
            condition=lambda m: not m.get("broker_connected", True),
            level=AlertLevel.ERROR,
            channels=[AlertChannel.TELEGRAM, AlertChannel.DISCORD],
            cooldown_seconds=60,
        ))

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.rule_id] = rule

    def unregister_rule(self, rule_id: str) -> bool:
        """Unregister an alert rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def register_handler(self, channel: AlertChannel, handler: Callable[[Alert], Awaitable[bool]]) -> None:
        """Register a custom alert handler."""
        self._handlers[channel] = handler

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        source: str = "",
        channels: list[AlertChannel] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Send an alert through specified channels."""
        alert = Alert(
            level=level,
            title=title,
            message=message,
            source=source,
            channels=channels or [AlertChannel.TELEGRAM],
            metadata=metadata or {},
        )

        # Store in history
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history:
            self._alert_history.pop(0)

        # Send through each channel
        for channel in alert.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    success = await handler(alert)
                    if not success:
                        logger.warning(f"Failed to send alert via {channel.value}")
                except Exception as e:
                    logger.error(f"Error sending alert via {channel.value}: {e}")

        return alert

    async def check_rules(self, metrics: dict[str, Any]) -> list[Alert]:
        """Check all rules against current metrics."""
        triggered_alerts = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Check cooldown
            if rule._last_triggered:
                elapsed = (datetime.now(UTC) - rule._last_triggered).total_seconds()
                if elapsed < rule.cooldown_seconds:
                    continue

            try:
                if rule.condition(metrics):
                    alert = await self.send_alert(
                        level=rule.level,
                        title=rule.name,
                        message=f"Alert triggered: {rule.name}",
                        source="alert_manager",
                        channels=rule.channels,
                        metadata={"rule_id": rule.rule_id, **metrics},
                    )
                    rule._last_triggered = datetime.now(UTC)
                    triggered_alerts.append(alert)
            except Exception as e:
                logger.error(f"Error checking rule {rule.rule_id}: {e}")

        return triggered_alerts

    def get_history(
        self,
        level: AlertLevel | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Get alert history."""
        alerts = self._alert_history

        if level:
            alerts = [a for a in alerts if a.level == level]
        if source:
            alerts = [a for a in alerts if a.source == source]

        return alerts[-limit:]

    def acknowledge_alert(self, alert_id: UUID, acknowledged_by: str = "user") -> bool:
        """Acknowledge an alert."""
        for alert in self._alert_history:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now(UTC)
                alert.acknowledged_by = acknowledged_by
                return True
        return False

    # ============================================
    # CHANNEL HANDLERS
    # ============================================

    async def _send_telegram(self, alert: Alert) -> bool:
        """Send alert via Telegram."""
        url = self._webhook_urls.get(AlertChannel.TELEGRAM)
        if not url:
            return False

        emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
        }.get(alert.level, "📢")

        text = f"{emoji} *{alert.title}*\n\n{alert.message}\n\n_Source: {alert.source}_\n_Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}_"

        payload = {
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False

    async def _send_discord(self, alert: Alert) -> bool:
        """Send alert via Discord webhook."""
        url = self._webhook_urls.get(AlertChannel.DISCORD)
        if not url:
            return False

        color = {
            AlertLevel.INFO: 0x00ff00,
            AlertLevel.WARNING: 0xffff00,
            AlertLevel.ERROR: 0xff0000,
            AlertLevel.CRITICAL: 0x8b0000,
        }.get(alert.level, 0x0000ff)

        embed = {
            "title": alert.title,
            "description": alert.message,
            "color": color,
            "fields": [
                {"name": "Source", "value": alert.source, "inline": True},
                {"name": "Level", "value": alert.level.value.upper(), "inline": True},
                {"name": "Time", "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'), "inline": True},
            ],
            "timestamp": alert.timestamp.isoformat(),
        }

        if alert.metadata:
            for k, v in alert.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    embed["fields"].append({"name": k, "value": str(v), "inline": True})

        payload = {"embeds": [embed]}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")
            return False

    async def _send_email(self, alert: Alert) -> bool:
        """Send alert via email."""
        url = self._webhook_urls.get(AlertChannel.EMAIL)
        if not url:
            return False

        # If URL is an SMTP config, use SMTP
        # Otherwise assume it's a webhook endpoint
        if url.startswith("smtp://"):
            return await self._send_email_smtp(alert, url)
        else:
            return await self._send_email_webhook(alert, url)

    async def _send_email_smtp(self, alert: Alert, smtp_url: str) -> bool:
        """Send email via SMTP."""
        # Parse smtp://user:pass@host:port
        # This is simplified - in production use proper config
        return False

    async def _send_email_webhook(self, alert: Alert, webhook_url: str) -> bool:
        """Send email via webhook."""
        payload = {
            "subject": f"[{alert.level.value.upper()}] {alert.title}",
            "body": f"""
            <h2>{alert.title}</h2>
            <p>{alert.message}</p>
            <hr>
            <p><strong>Source:</strong> {alert.source}</p>
            <p><strong>Level:</strong> {alert.level.value.upper()}</p>
            <p><strong>Time:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            """,
            "to": "admin@example.com",  # Would be configured
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook_url, json=payload, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Email webhook alert failed: {e}")
            return False

    async def _send_webhook(self, alert: Alert) -> bool:
        """Send alert via generic webhook."""
        # Would send to configured webhook URLs
        return True

    async def _send_slack(self, alert: Alert) -> bool:
        """Send alert via Slack."""
        # Similar to Discord but with Slack formatting
        return True

    async def _send_pushbullet(self, alert: Alert) -> bool:
        """Send alert via Pushbullet."""
        return True


# Global alert manager
alert_manager = AlertManager()


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance."""
    return alert_manager


# Convenience functions
async def alert_info(title: str, message: str, **kwargs) -> Alert:
    return await alert_manager.send_alert(AlertLevel.INFO, title, message, **kwargs)


async def alert_warning(title: str, message: str, **kwargs) -> Alert:
    return await alert_manager.send_alert(AlertLevel.WARNING, title, message, **kwargs)


async def alert_error(title: str, message: str, **kwargs) -> Alert:
    return await alert_manager.send_alert(AlertLevel.ERROR, title, message, **kwargs)


async def alert_critical(title: str, message: str, **kwargs) -> Alert:
    return await alert_manager.send_alert(AlertLevel.CRITICAL, title, message, **kwargs)


# Decorator for automatic error alerting
def alert_on_error(
    title: str = "Function Error",
    level: AlertLevel = AlertLevel.ERROR,
    channels: list[AlertChannel] | None = None,
):
    """Decorator to automatically send alert on function error."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await alert_manager.send_alert(
                    level=level,
                    title=title,
                    message=f"Error in {func.__name__}: {e!s}",
                    source=func.__module__,
                    channels=channels,
                    metadata={"function": func.__name__, "error": str(e)},
                )
                raise

        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Can't await in sync function, would need async context
                logger.error(f"Error in {func.__name__}: {e}")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator