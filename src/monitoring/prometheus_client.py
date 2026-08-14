"""Simple Prometheus client wrapper.
Provides gauges for key EAQTS metrics: live positions, PnL, execution latency.
If the `prometheus_client` package is unavailable, the functions become no‑ops.
"""

try:
    from prometheus_client import Counter, Gauge, start_http_server  # type: ignore
except Exception:  # pragma: no cover
    # Define dummy classes that swallow calls when Prometheus is not installed.
    class _Dummy:
        def __init__(self, *_, **__):
            pass
        def set(self, *_, **__):
            pass
        def inc(self, *_, **__):
            pass
        def dec(self, *_, **__):
            pass
        def observe(self, *_, **__):
            pass
    Gauge = Counter = _Dummy
    def start_http_server(port: int):
        """Dummy HTTP server starter – does nothing when Prometheus is missing."""

# Define metrics (will be real when prometheus_client is installed)
LIVE_POSITIONS = Gauge("eaqts_live_positions", "Current number of live positions")
TOTAL_PNL = Gauge("eaqts_total_pnl", "Cumulative profit and loss")
EXEC_LATENCY = Gauge("eaqts_execution_latency_seconds", "Execution latency in seconds")
TRADE_COUNT = Counter("eaqts_trade_count_total", "Total number of trades executed")
# TCA metrics
TCA_SLIPPAGE = Gauge("eaqts_tca_slippage_seconds", "Average slippage per trade")
TCA_FILL_RATE = Gauge("eaqts_tca_fill_rate", "Fill rate (filled trades / total trades)")

def init_metrics(port: int = 8000) -> None:
    """Start a Prometheus metrics HTTP endpoint.
    In production this runs a background thread exposing `/metrics`.
    """
    start_http_server(port)

def record_position(count: int) -> None:
    LIVE_POSITIONS.set(count)

def record_pnl(pnl: float) -> None:
    TOTAL_PNL.set(pnl)

def record_execution_latency(seconds: float) -> None:
    EXEC_LATENCY.set(seconds)

def inc_trade_count() -> None:
    TRADE_COUNT.inc()

def record_tca_metrics(slippage: float, fill_rate: float) -> None:
    TCA_SLIPPAGE.set(slippage)
    TCA_FILL_RATE.set(fill_rate)
