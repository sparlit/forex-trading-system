from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

import structlog


def setup_logging() -> None:
    """Configure structured logging with structlog."""

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structlog logger."""
    return structlog.get_logger(name)


# Custom log levels
class LogLevel:
    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


# Trading-specific loggers
trading_logger = get_logger("trading")
risk_logger = get_logger("risk")
execution_logger = get_logger("execution")
data_logger = get_logger("data")
strategy_logger = get_logger("strategy")
backtest_logger = get_logger("backtest")
# General application logger
logger = get_logger("forex_trading_system")


def log_trade(
    action: str,
    symbol: str,
    direction: str,
    volume: float,
    price: float,
    strategy_id: str | None = None,
    order_id: str | None = None,
    **kwargs,
) -> None:
    """Log a trade event."""
    trading_logger.info(
        "trade_event",
        action=action,
        symbol=symbol,
        direction=direction,
        volume=volume,
        price=price,
        strategy_id=strategy_id,
        order_id=order_id,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


def log_signal(
    strategy_id: str,
    symbol: str,
    direction: str,
    strength: float,
    confidence: float,
    signal_type: str,
    **kwargs,
) -> None:
    """Log a signal event."""
    strategy_logger.info(
        "signal_generated",
        strategy_id=strategy_id,
        symbol=symbol,
        direction=direction,
        strength=strength,
        confidence=confidence,
        signal_type=signal_type,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


def log_risk_event(
    event_type: str,
    message: str,
    severity: str = "warning",
    **kwargs,
) -> None:
    """Log a risk event."""
    risk_logger.log(
        getattr(structlog, severity.upper()),
        "risk_event",
        event_type=event_type,
        message=message,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


def log_execution(
    event_type: str,
    order_id: str,
    symbol: str,
    side: str,
    volume: float,
    price: float | None = None,
    **kwargs,
) -> None:
    """Log an execution event."""
    execution_logger.info(
        "execution_event",
        event_type=event_type,
        order_id=order_id,
        symbol=symbol,
        side=side,
        volume=volume,
        price=price,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


def log_data_event(
    event_type: str,
    source: str,
    symbol: str | None = None,
    count: int | None = None,
    **kwargs,
) -> None:
    """Log a data event."""
    data_logger.info(
        "data_event",
        event_type=event_type,
        source=source,
        symbol=symbol,
        count=count,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


def log_backtest(
    strategy_id: str,
    phase: str,
    metric: str | None = None,
    value: float | None = None,
    **kwargs,
) -> None:
    """Log a backtest event."""
    backtest_logger.info(
        "backtest_event",
        strategy_id=strategy_id,
        phase=phase,
        metric=metric,
        value=value,
        timestamp=datetime.now(UTC).isoformat(),
        **kwargs,
    )


# Context managers for adding context to logs
class LogContext:
    """Context manager for adding temporary context to logs."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.tokens = []

    def __enter__(self):
        for key, value in self.kwargs.items():
            token = structlog.contextvars.bind_contextvars(**{key: value})
            self.tokens.append((key, token))
        return self

    def __exit__(self, *args):
        for key, token in self.tokens:
            structlog.contextvars.unbind_contextvars(key)


def with_context(**kwargs):
    """Decorator to add context to a function's logs."""
    def decorator(func):
        def wrapper(*args, **func_kwargs):
            with LogContext(**kwargs):
                return func(*args, **func_kwargs)
        return wrapper
    return decorator