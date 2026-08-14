"""
Monitoring Package
==================

Comprehensive monitoring stack:
- Metrics (Prometheus)
- Alerting
- Logging
- Tracing (OpenTelemetry)
- Circuit Breaker
- Graceful Shutdown
- Backup & Recovery
"""

from src.infra.monitoring.alerts import (
    AlertLevel,
    AlertManager,
    AlertRule,
    get_alert_manager,
)
from src.infra.monitoring.backup import (
    BackupConfig,
    BackupResult,
    RecoveryTestResult,
    TimescaleDBBackupManager,
    get_backup_manager,
    init_backup_manager,
)
from src.infra.monitoring.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    check_circuit_breaker_health,
    circuit_breaker,
    get_all_circuit_breaker_stats,
    get_ccxt_circuit_breaker,
    get_circuit_breaker,
    get_circuit_breaker_registry,
    get_mt5_circuit_breaker,
    get_rest_circuit_breaker,
)
from src.infra.monitoring.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownHook,
    ShutdownPhase,
    ShutdownResult,
    get_shutdown_manager,
    init_shutdown_manager,
    register_shutdown_hook,
    shutdown_hook,
    wait_for_shutdown,
)
from src.infra.monitoring.logging import (
    get_logger,
    setup_logging,
)
from src.infra.monitoring.metrics import (
    MetricsCollector,
    get_metrics_collector,
)
from src.infra.monitoring.tracing import (
    TracingManager,
    get_tracer,
    get_tracing_manager,
    init_tracing,
    setup_tracing,
    trace_context,
    trace_function,
    trace_span,
)

__all__ = [
    "AlertLevel",
    # Alerts
    "AlertManager",
    "AlertRule",
    "BackupConfig",
    "BackupResult",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitBreakerRegistry",
    # Graceful Shutdown
    "GracefulShutdownManager",
    # Metrics
    "MetricsCollector",
    "RecoveryTestResult",
    "ShutdownHook",
    "ShutdownPhase",
    "ShutdownResult",
    # Backup
    "TimescaleDBBackupManager",
    # Tracing
    "TracingManager",
    "check_circuit_breaker_health",
    "circuit_breaker",
    "get_alert_manager",
    "get_all_circuit_breaker_stats",
    "get_backup_manager",
    "get_ccxt_circuit_breaker",
    "get_circuit_breaker",
    "get_circuit_breaker_registry",
    "get_logger",
    "get_metrics_collector",
    "get_mt5_circuit_breaker",
    "get_rest_circuit_breaker",
    "get_shutdown_manager",
    "get_tracer",
    "get_tracing_manager",
    "init_backup_manager",
    "init_shutdown_manager",
    "init_tracing",
    "register_shutdown_hook",
    # Logging
    "setup_logging",
    "setup_tracing",
    "shutdown_hook",
    "trace_context",
    "trace_function",
    "trace_span",
    "wait_for_shutdown",
]