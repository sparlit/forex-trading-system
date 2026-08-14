"""
Operational Risk Monitoring
===========================

Provides lightweight system‑level metrics that complement the trading
risk metrics.  The module is intentionally minimal – it samples CPU,
memory and disk usage using ``psutil`` and exposes the data via a
simple dataclass.

In production these values would be pushed to Prometheus via the
``infra.monitoring.metrics`` module; this implementation can be used in
environments where Prometheus is not available (e.g. local development
or air‑gapped test runs).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore

from loguru import logger


@dataclass
class OperationalMetrics:
    """Snapshot of operational health."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    open_file_descriptors: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def collect_metrics() -> OperationalMetrics:
    """Collect a snapshot of system metrics.

    If ``psutil`` is unavailable the function returns a metrics object
    filled with zeros and logs a warning.
    """
    if psutil is None:  # pragma: no cover - defensive
        logger.warning("psutil not installed – operational metrics unavailable")
        return OperationalMetrics()

    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        fds = len(psutil.Process().open_files()) if psutil.Process else 0
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Operational metric collection failed: {exc}")
        return OperationalMetrics()

    return OperationalMetrics(
        cpu_percent=cpu,
        memory_percent=mem,
        disk_percent=disk,
        open_file_descriptors=fds,
    )
