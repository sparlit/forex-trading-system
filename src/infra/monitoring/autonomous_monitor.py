"""
Autonomous Monitoring & Alerting - Self-healing, auto-recovery, zero-touch operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import aiohttp

from src.data.models import Portfolio
from src.data.storage.timescale import TimescaleDB
from src.risk.risk_engine import Alert, AlertSeverity, AlertType, RiskEngine

logger = logging.getLogger(__name__)


class AlertChannel(str, Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    CONSOLE = "console"


@dataclass
class AlertRule:
    name: str
    condition: str  # Expression to evaluate
    severity: AlertSeverity
    channels: list[AlertChannel]
    cooldown_minutes: int = 60
    auto_recovery: bool = False
    recovery_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    component: str
    status: str  # "healthy", "degraded", "critical", "unknown"
    message: str
    last_check: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


class AlertChannelBase(ABC):
    """Base class for alert channels"""
    
    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send alert, return success"""

    @abstractmethod
    async def test(self) -> bool:
        """Test channel connectivity"""


class TelegramChannel(AlertChannelBase):
    """Telegram bot alert channel"""
    
    def __init__(self, bot_token: str, chat_ids: list[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send(self, alert: Alert) -> bool:
        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        emoji = emoji_map.get(alert.severity, "📢")
        
        message = (
            f"{emoji} <b>{alert.severity.value.upper()}: {alert.type.value}</b>\n\n"
            f"{alert.message}\n\n"
            f"<b>Time:</b> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        )
        
        if alert.strategy_id:
            message += f"<b>Strategy:</b> {alert.strategy_id}\n"
        if alert.symbol:
            message += f"<b>Symbol:</b> {alert.symbol}\n"
        if alert.current_value is not None:
            message += f"<b>Current:</b> {alert.current_value:.4f}\n"
        if alert.limit_value is not None:
            message += f"<b>Limit:</b> {alert.limit_value:.4f}\n"
        
        success = True
        async with aiohttp.ClientSession() as session:
            for chat_id in self.chat_ids:
                try:
                    async with session.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": message,
                            "parse_mode": "HTML"
                        }
                    ) as resp:
                        if resp.status != 200:
                            logger.error(f"Telegram send failed: {await resp.text()}")
                            success = False
                except Exception as e:
                    logger.error(f"Telegram error: {e}")
                    success = False
        
        return success
    
    async def test(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/getMe") as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False


class EmailChannel(AlertChannelBase):
    """Email alert channel"""
    
    def __init__(self, 
                 smtp_host: str,
                 smtp_port: int,
                 username: str,
                 password: str,
                 from_email: str,
                 to_emails: list[str],
                 use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls
    
    async def send(self, alert: Alert) -> bool:
        subject = f"[{alert.severity.value.upper()}] {alert.type.value}: {alert.message[:80]}"
        
        body = f"""
Alert: {alert.type.value}
Severity: {alert.severity.value}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
Message: {alert.message}

"""
        if alert.strategy_id:
            body += f"Strategy: {alert.strategy_id}\n"
        if alert.symbol:
            body += f"Symbol: {alert.symbol}\n"
        if alert.current_value is not None:
            body += f"Current Value: {alert.current_value:.4f}\n"
        if alert.limit_value is not None:
            body += f"Limit Value: {alert.limit_value:.4f}\n"
        
        body += f"\nMetadata: {json.dumps(alert.metadata, indent=2)}"
        
        try:
            msg = f"Subject: {subject}\n\n{body}"
            
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls(context=context)
                server.login(self.username, self.password)
                server.sendmail(self.from_email, self.to_emails, msg)
            
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
    
    async def test(self) -> bool:
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls(context=ssl.create_default_context())
                server.login(self.username, self.password)
            return True
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False



class WebhookChannel(AlertChannelBase):
    """Generic webhook alert channel"""
    
    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
    
    async def send(self, alert: Alert) -> bool:
        payload = {
            "alert_id": str(alert.timestamp.timestamp()),
            "type": alert.type.value,
            "severity": alert.severity.value,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "strategy_id": alert.strategy_id,
            "symbol": alert.symbol,
            "current_value": alert.current_value,
            "limit_value": alert.limit_value,
            "metadata": alert.metadata
        }
        
        try:
            async with aiohttp.ClientSession() as session, session.post(
                self.url,
                json=payload,
                headers=self.headers
            ) as resp:
                return resp.status < 300
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False
    
    async def test(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, headers=self.headers) as resp:
                    return resp.status < 500
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False


class ConsoleChannel(AlertChannelBase):
    """Console logging channel (for testing)"""
    
    async def send(self, alert: Alert) -> bool:
        level_map = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.CRITICAL
        }
        logger.log(level_map.get(alert.severity, logging.INFO), 
                   f"ALERT [{alert.severity.value}] {alert.type.value}: {alert.message}")
        return True
    
    async def test(self) -> bool:
        return True


class AlertManager:
    """Central alert management with routing, deduplication, escalation"""
    
    def __init__(self, timescaledb: TimescaleDB):
        self.timescaledb = timescaledb
        self.channels: dict[AlertChannel, AlertChannelBase] = {}
        self.rules: dict[str, AlertRule] = {}
        self.alert_history: list[Alert] = []
        self.last_alert_time: dict[str, datetime] = {}  # For cooldown
        self.suppressed_alerts: set[str] = set()
        
        # Default rules
        self._load_default_rules()
    
    def add_channel(self, channel_type: AlertChannel, channel: AlertChannelBase):
        self.channels[channel_type] = channel
        logger.info(f"Added alert channel: {channel_type.value}")
    
    def add_rule(self, rule: AlertRule):
        self.rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def _load_default_rules(self):
        """Load default alert rules"""
        defaults = [
            AlertRule(
                name="portfolio_drawdown_critical",
                condition="portfolio_drawdown >= 0.05",
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.TELEGRAM, AlertChannel.EMAIL],
                cooldown_minutes=30,
                auto_recovery=True,
                recovery_action="reduce_all_positions_50pct"
            ),
            AlertRule(
                name="strategy_drawdown",
                condition="strategy_drawdown >= 0.03",
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.TELEGRAM],
                cooldown_minutes=15,
                auto_recovery=True,
                recovery_action="pause_strategy"
            ),
            AlertRule(
                name="var_breach",
                condition="var_95 > 0.025",
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.TELEGRAM],
                cooldown_minutes=60,
                auto_recovery=True,
                recovery_action="reduce_leverage_25pct"
            ),
            AlertRule(
                name="execution_failure_rate",
                condition="fill_rate < 0.80",
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.TELEGRAM, AlertChannel.EMAIL],
                cooldown_minutes=30,
                auto_recovery=True,
                recovery_action="pause_execution_engine"
            ),
            AlertRule(
                name="data_quality",
                condition="missing_ticks > 0.05",
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.TELEGRAM],
                cooldown_minutes=10,
                auto_recovery=True,
                recovery_action="switch_data_source"
            ),
            AlertRule(
                name="connection_lost",
                condition="broker_disconnected",
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.TELEGRAM, AlertChannel.EMAIL, AlertChannel.PAGERDUTY],
                cooldown_minutes=5,
                auto_recovery=True,
                recovery_action="reconnect_broker"
            ),
            AlertRule(
                name="strategy_no_signals",
                condition="no_signals_1h",
                severity=AlertSeverity.WARNING,
                channels=[AlertChannel.TELEGRAM],
                cooldown_minutes=60,
                auto_recovery=False
            ),
        ]
        
        for rule in defaults:
            self.rules[rule.name] = rule
    
    async def process_alert(self, alert: Alert):
        """Process alert through rules and channels"""
        # Check cooldown
        cooldown_key = f"{alert.type.value}:{alert.strategy_id or 'global'}"
        if cooldown_key in self.last_alert_time:
            elapsed = (datetime.now(UTC) - self.last_alert_time[cooldown_key]).total_seconds() / 60
            # Find matching rule for cooldown
            for rule in self.rules.values():
                if rule.condition in str(alert.type) and elapsed < rule.cooldown_minutes:
                    logger.debug(f"Alert {cooldown_key} suppressed by cooldown")
                    return
        
        # Check suppression
        if cooldown_key in self.suppressed_alerts:
            return
        
        # Store alert
        self.alert_history.append(alert)
        self.last_alert_time[cooldown_key] = datetime.now(UTC)
        
        # Keep history limited
        cutoff = datetime.now(UTC) - timedelta(days=30)
        self.alert_history = [a for a in self.alert_history if a.timestamp > cutoff]
        
        # Store in DB
        await self._store_alert(alert)
        
        # Route to channels
        matched_rules = self._match_rules(alert)
        all_channels = set()
        auto_recoveries = []
        
        for rule in matched_rules:
            all_channels.update(rule.channels)
            if rule.auto_recovery and rule.recovery_action:
                auto_recoveries.append(rule.recovery_action)
        
        # Send to channels
        for channel_type in all_channels:
            if channel_type in self.channels:
                try:
                    await self.channels[channel_type].send(alert)
                except Exception as e:
                    logger.error(f"Channel {channel_type} failed: {e}")
        
        # Execute auto-recoveries
        for action in auto_recoveries:
            await self._execute_recovery(action, alert)
        
        logger.info(f"Alert processed: {alert.type.value} via {len(all_channels)} channels")
    
    def _match_rules(self, alert: Alert) -> list[AlertRule]:
        """Match alert against rules"""
        matched = []
        for rule in self.rules.values():
            # Simple matching - in production use expression evaluator
            if rule.name in str(alert.type) or alert.type.value in rule.condition:
                matched.append(rule)
        return matched
    
    async def _store_alert(self, alert: Alert):
        """Store alert in TimescaleDB"""
        try:
            async with self.timescaledb.acquire() as conn:
                await conn.execute("""
                    INSERT INTO risk.alerts (
                        alert_type, severity, message, strategy_id, symbol_id,
                        current_value, limit_value, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    alert.type.value, alert.severity.value, alert.message,
                    alert.strategy_id, alert.symbol,
                    alert.current_value, alert.limit_value,
                    json.dumps(alert.metadata)
                )
        except Exception as e:
            logger.error(f"Failed to store alert: {e}")
    
    async def _execute_recovery(self, action: str, alert: Alert):
        """Execute auto-recovery action."""
        logger.warning(f"Executing auto-recovery: {action} for {alert.type.value}")
        if action == "restart_connector":
            logger.info("Restarting data connector (stub — no connector reference)")
        elif action == "pause_strategy":
            logger.info(f"Pausing strategy (stub — alert: {alert.message}")
        elif action == "flatten_positions":
            logger.warning("Flattening all positions (stub — no broker ref)")
        else:
            logger.warning(f"Unknown recovery action: {action}")
    
    def suppress_alert(self, alert_type: str, strategy_id: str | None = None):
        """Suppress alerts of a type"""
        key = f"{alert_type}:{strategy_id or 'global'}"
        self.suppressed_alerts.add(key)
    
    def unsuppress_alert(self, alert_type: str, strategy_id: str | None = None):
        """Remove alert suppression"""
        key = f"{alert_type}:{strategy_id or 'global'}"
        self.suppressed_alerts.discard(key)
    
    def get_recent_alerts(self, hours: int = 24) -> list[Alert]:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return [a for a in self.alert_history if a.timestamp > cutoff]


class SystemMonitor:
    """Monitors all system components"""
    
    def __init__(self, 
                 timescaledb: TimescaleDB,
                 portfolio: Portfolio,
                 risk_engine: RiskEngine,
                 alert_manager: AlertManager):
        self.timescaledb = timescaledb
        self.portfolio = portfolio
        self.risk_engine = risk_engine
        self.alert_manager = alert_manager
        
        self.component_checks: dict[str, Callable] = {}
        self.health_history: list[SystemHealth] = []
        self.running = False
        self.check_interval = 30  # seconds
    
    def register_check(self, component: str, check_func: Callable[[], SystemHealth]):
        """Register a health check function"""
        self.component_checks[component] = check_func
    
    async def start(self):
        self.running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("SystemMonitor started")
    
    async def stop(self):
        self.running = False
        logger.info("SystemMonitor stopped")
    
    async def _monitor_loop(self):
        while self.running:
            try:
                await self._run_checks()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def _run_checks(self):
        """Run all registered health checks"""
        results = {}
        
        for component, check_func in self.component_checks.items():
            try:
                health = await check_func()
                results[component] = health
                self.health_history.append(health)
            except Exception as e:
                logger.error(f"Health check {component} failed: {e}")
                results[component] = SystemHealth(
                    component=component,
                    status="critical",
                    message=f"Check failed: {e}",
                    last_check=datetime.now(UTC)
                )
        
        # Keep history limited
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        self.health_history = [h for h in self.health_history if h.last_check > cutoff]
        
        # Alert on critical
        for health in results.values():
            if health.status == "critical":
                alert = Alert(
                    type=AlertType.DATA_QUALITY,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Component {health.component} critical: {health.message}",
                    metadata={"component": health.component, "metrics": health.metrics}
                )
                await self.alert_manager.process_alert(alert)
    
    def get_status(self) -> dict[str, Any]:
        """Get overall system status"""
        latest = {}
        for h in self.health_history:
            if h.component not in latest or h.last_check > latest[h.component].last_check:
                latest[h.component] = h
        
        overall = "healthy"
        for h in latest.values():
            if h.status == "critical":
                overall = "critical"
                break
            elif h.status == "degraded" and overall == "healthy":
                overall = "degraded"
        
        return {
            "overall": overall,
            "components": {k: {
                "status": v.status,
                "message": v.message,
                "last_check": v.last_check.isoformat(),
                "metrics": v.metrics,
                "issues": v.issues
            } for k, v in latest.items()},
            "last_updated": datetime.now(UTC).isoformat()
        }


class AutoRecoveryManager:
    """Automatic recovery from common failure modes"""
    
    def __init__(self, 
                 portfolio: Portfolio,
                 risk_engine: RiskEngine,
                 alert_manager: AlertManager):
        self.portfolio = portfolio
        self.risk_engine = risk_engine
        self.alert_manager = alert_manager
        
        self.recovery_actions: dict[str, Callable] = {}
        self.recovery_history: list[dict] = []
        self.max_recoveries_per_hour = 3
    
    def register_recovery(self, name: str, action: Callable):
        self.recovery_actions[name] = action
    
    async def execute_recovery(self, action: str, context: dict[str, Any]) -> bool:
        """Execute a recovery action"""
        if action not in self.recovery_actions:
            logger.error(f"Unknown recovery action: {action}")
            return False
        
        # Check rate limit
        recent = [r for r in self.recovery_history 
                  if r["timestamp"] > datetime.now(UTC) - timedelta(hours=1)]
        if len(recent) >= self.max_recoveries_per_hour:
            logger.warning(f"Max recoveries per hour reached, skipping {action}")
            return False
        
        try:
            logger.warning(f"Executing auto-recovery: {action}")
            result = await self.recovery_actions[action](context)
            
            self.recovery_history.append({
                "action": action,
                "timestamp": datetime.now(UTC),
                "context": context,
                "success": result
            })
            
            if result:
                logger.info(f"Auto-recovery {action} succeeded")
            else:
                logger.error(f"Auto-recovery {action} failed")
            
            return result
        except Exception as e:
            logger.error(f"Recovery {action} failed with exception: {e}")
            return False
    
    def get_recovery_stats(self) -> dict[str, Any]:
        recent = [r for r in self.recovery_history 
                  if r["timestamp"] > datetime.now(UTC) - timedelta(hours=24)]
        
        return {
            "total_recoveries_24h": len(recent),
            "success_rate": sum(1 for r in recent if r["success"]) / len(recent) if recent else 0,
            "by_action": {
                action: sum(1 for r in recent if r["action"] == action)
                for action in {r["action"] for r in recent}
            }
        }


# Default recovery actions
async def default_reduce_positions(context: dict) -> bool:
    """Reduce all positions by 50%"""
    # Would integrate with execution engine
    return True

async def default_liquidate_all(context: dict) -> bool:
    """Emergency liquidate all"""
    return True

async def default_pause_strategy(context: dict) -> bool:
    _strategy_id = context.get("strategy_id")
    # Would integrate with strategy manager
    return True

async def default_reduce_leverage(context: dict) -> bool:
    return True

async def default_pause_execution(context: dict) -> bool:
    return True

async def default_switch_data_source(context: dict) -> bool:
    return True

async def default_reconnect_broker(context: dict) -> bool:
    return True