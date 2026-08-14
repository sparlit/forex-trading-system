"""
Distributed Tracing Module
==========================

Provides OpenTelemetry-based distributed tracing with Jaeger exporter.
Integrates with FastAPI, HTTP clients, database, and message queues.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from loguru import logger
from opentelemetry import trace

try:
    from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
except ImportError:
    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    except ImportError:
        JaegerExporter = None
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagators.composite import CompositePropagator

try:
    from opentelemetry.propagators.jaeger import JaegerFormat
except ImportError:
    JaegerFormat = None
try:
    from opentelemetry.propagators.w3c import W3CBaggageFormat, W3CTraceFormat
except ImportError:
    # W3C propagators might be in a different location or not available
    W3CBaggageFormat = None
    W3CTraceFormat = None
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from src.infra.config.settings import settings

T = TypeVar("T")


class TracingConfig:
    """Tracing configuration."""
    
    def __init__(
        self,
        service_name: str = "forex-trading-system",
        service_version: str = "0.1.0",
        environment: str = "development",
        jaeger_endpoint: str | None = None,
        otlp_endpoint: str | None = None,
        sample_rate: float = 1.0,
        console_export: bool = False,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.jaeger_endpoint = jaeger_endpoint or os.environ.get("JAEGER_ENDPOINT")
        self.otlp_endpoint = otlp_endpoint or os.environ.get("OTLP_ENDPOINT")
        self.sample_rate = sample_rate
        self.console_export = console_export


class TracingManager:
    """
    Centralized distributed tracing management.
    
    Features:
    - OpenTelemetry SDK setup with Jaeger/OTLP exporters
    - Auto-instrumentation for FastAPI, HTTP clients, DB, Redis, etc.
    - B3, W3C, and Jaeger propagation formats
    - Custom span attributes and events
    - Context propagation across async boundaries
    """
    
    def __init__(self, config: TracingConfig | None = None):
        self.config = config or TracingConfig(
            service_name=settings.app_name,
            environment=settings.environment,
        )
        self._tracer_provider: trace.TracerProvider | None = None
        self._tracer: trace.Tracer | None = None
        self._initialized = False
    
    def initialize(self) -> trace.Tracer:
        """Initialize tracing system."""
        if self._initialized:
            return self._tracer
        
        # Create resource
        resource = Resource.create({
            "service.name": self.config.service_name,
            "service.version": self.config.service_version,
            "deployment.environment": self.config.environment,
        })
        
        # Create tracer provider
        self._tracer_provider = TracerProvider(
            resource=resource,
            sampler=trace.sampling.ParentBasedTraceIdRatioBased(self.config.sample_rate),
        )
        
        # Set global tracer provider
        trace.set_tracer_provider(self._tracer_provider)
        
        # Setup exporters
        self._setup_exporters()
        
        # Set global propagator (B3 + W3C + Jaeger)
        propagators = [
            TraceContextTextMapPropagator(),
            B3MultiFormat(),
        ]
        if W3CTraceFormat is not None:
            propagators.append(W3CTraceFormat())
        if JaegerFormat is not None:
            propagators.append(JaegerFormat())
        set_global_textmap(CompositePropagator(propagators))
        
        # Get tracer
        self._tracer = trace.get_tracer(
            self.config.service_name,
            version=self.config.service_version,
        )
        
        # Auto-instrument libraries
        self._instrument_libraries()
        
        self._initialized = True
        logger.info(f"Distributed tracing initialized: {self.config.service_name}")
        
        return self._tracer
    
    def _setup_exporters(self) -> None:
        """Setup span exporters."""
        processors = []
        
        # Jaeger exporter
        if self.config.jaeger_endpoint and JaegerExporter is not None:
            try:
                # New JaegerExporter API (protobuf-based)
                jaeger_exporter = JaegerExporter(
                    collector_endpoint=f"http://{self.config.jaeger_endpoint}/api/traces",
                )
                processors.append(BatchSpanProcessor(jaeger_exporter))
                logger.info(f"Jaeger exporter configured: {self.config.jaeger_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to setup Jaeger exporter: {e}")
        
        # OTLP exporter
        if self.config.otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=True,
                )
                processors.append(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OTLP exporter configured: {self.config.otlp_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to setup OTLP exporter: {e}")
        
        # Console exporter (for development)
        if self.config.console_export:
            try:
                console_exporter = ConsoleSpanExporter()
                processors.append(BatchSpanProcessor(console_exporter))
                logger.info("Console exporter enabled")
            except Exception as e:
                logger.warning(f"Failed to setup console exporter: {e}")
        
        # Add processors to provider
        if self._tracer_provider:
            for processor in processors:
                self._tracer_provider.add_span_processor(processor)
        
        # Add default console if no exporters configured
        if not processors and self.config.console_export:
            try:
                console_exporter = ConsoleSpanExporter()
                self._tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
            except Exception as e:
                logger.error(f"Exception occurred: {e}")
    
    def _instrument_libraries(self) -> None:
        """Auto-instrument common libraries."""
        try:
            # FastAPI
            FastAPIInstrumentor().instrument(app=self._app)
        except Exception as e:
            logger.error(f"FastAPI instrumentation failed: {e}")
            raise

        try:
            # HTTP clients
            HTTPXClientInstrumentor().instrument()
        except Exception as e:
            logger.error(f"HTTPX instrumentation failed: {e}")
            raise

        try:
            # Asyncio
            from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor  # type: ignore
            AsyncioInstrumentor().instrument()
        except Exception as e:
            logger.debug(f"Asyncio instrumentation skipped: {e}")

    def get_tracer(self) -> trace.Tracer:
        """Get tracer instance."""
        if not self._initialized:
            self.initialize()
        return self._tracer
    
    def shutdown(self) -> None:
        """Shutdown tracing."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        logger.info("Tracing shutdown complete")


# Global tracing manager
_tracing_manager: TracingManager | None = None


def get_tracing_manager() -> TracingManager:
    """Get or create global tracing manager."""
    global _tracing_manager
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    return _tracing_manager


def init_tracing(
    service_name: str = "forex-trading-system",
    service_version: str = "0.1.0",
    environment: str = "development",
    jaeger_endpoint: str | None = None,
    otlp_endpoint: str | None = None,
    sample_rate: float = 1.0,
    console_export: bool = False,
) -> trace.Tracer:
    """Initialize global tracing."""
    global _tracing_manager
    config = TracingConfig(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        jaeger_endpoint=jaeger_endpoint,
        otlp_endpoint=otlp_endpoint,
        sample_rate=1.0 if environment == "development" else 0.1,
        console_export=False,
    )
    _tracing_manager = TracingManager(config)
    return _tracing_manager.initialize()


def get_tracer(name: str | None = None) -> trace.Tracer:
    """Get tracer instance."""
    manager = get_tracing_manager()
    return manager.get_tracer()


# Decorators for tracing
def trace_function(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict | None = None,
):
    """
    Decorator to trace a function.
    
    Usage:
        @trace_function("my_operation")
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            _tracer = get_tracer()
            span_name = name or f"{func.__module__}.{func.__qualname__}"
            
            with get_tracer().start_as_current_span(
                span_name,
                kind=kind,
            ) as span:
                if attributes:
                    span.set_attributes(attributes)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            _tracer = get_tracer()
            span_name = name or f"{func.__module__}.{func.__qualname__}"
            
            with get_tracer().start_as_current_span(
                span_name,
                kind=kind,
            ) as span:
                if attributes:
                    span.set_attributes(attributes)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def trace_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict | None = None,
) -> trace.Span:
    """Create a new span manually."""
    return get_tracer().start_span(name, kind=kind, attributes=attributes)


@contextmanager
def trace_context(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict | None = None,
):
    """Context manager for manual span management."""
    tracer = get_tracer()
    span = tracer.start_span(name, kind=kind, attributes=attributes)
    try:
        yield span
    except Exception as e:
        span.set_status(Status(StatusCode.ERROR, str(e)))
        span.record_exception(e)
        raise
    finally:
        span.end()


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attributes(attributes)


def add_span_event(name: str, attributes: dict | None = None) -> None:
    """Add event to current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes=attributes)


def set_span_status(status_code: StatusCode, description: str = "") -> None:
    """Set status on current span."""
    span = trace.get_current_span()
    if span:
        span.set_status(Status(status_code, description))


def get_current_span_context() -> SpanContext | None:
    """Get current span context for propagation."""
    span = trace.get_current_span()
    if span and span.get_span_context():
        return span.get_span_context()
    return None


def inject_context(carrier: dict[str, str]) -> None:
    """Inject trace context into carrier for propagation."""
    from opentelemetry.propagate import inject
    inject(carrier)


def extract_context(carrier: dict[str, str]) -> trace.SpanContext:
    """Extract trace context from carrier."""
    from opentelemetry.propagate import extract
    ctx = extract(carrier)
    return trace.get_current_span(ctx).get_span_context()


# FastAPI integration
def instrument_fastapi(app, tracer_provider=None) -> None:
    """Instrument FastAPI app with tracing."""
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="/health,/metrics,/ready,/live",
    )


# Database tracing helpers
def trace_db_operation(
    operation: str,
    table: str | None = None,
    query: str | None = None,
):
    """Decorator to trace database operations."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            with trace_context(
                f"db.{operation}",
                kind=SpanKind.CLIENT,
                attributes={
                    "db.operation": operation,
                    "db.table": table or "unknown",
                    "db.system": "postgresql",
                },
            ):
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            with trace_context(
                f"db.{operation}",
                kind=SpanKind.CLIENT,
                attributes={
                    "db.operation": operation,
                    "db.table": table or "unknown",
                    "db.system": "postgresql",
                },
            ):
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# HTTP client tracing
def trace_http_request(
    method: str,
    url: str,
    status_code: int | None = None,
):
    """Create span for HTTP request."""
    return trace_context(
        f"http.{method.lower()}",
        kind=SpanKind.CLIENT,
        attributes={
            "http.method": method,
            "http.url": url,
            "http.status_code": status_code,
        },
    )


# Message queue tracing
def trace_mq_operation(
    operation: str,
    queue: str,
    message_id: str | None = None,
):
    """Decorator to trace message queue operations."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            with trace_context(
                f"mq.{operation}",
                kind=SpanKind.CONSUMER if operation == "consume" else SpanKind.PRODUCER,
                attributes={
                    "messaging.system": "nats",
                    "messaging.destination": queue,
                    "messaging.operation": operation,
                    "messaging.message_id": message_id,
                },
            ):
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            with trace_context(
                f"mq.{operation}",
                kind=SpanKind.CONSUMER if operation == "consume" else SpanKind.PRODUCER,
                attributes={
                    "messaging.system": "nats",
                    "messaging.destination": queue,
                    "messaging.operation": operation,
                    "messaging.message_id": message_id,
                },
            ):
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Initialize tracing
def setup_tracing() -> trace.Tracer:
    """Setup tracing with settings."""
    return init_tracing(
        service_name=settings.app_name,
        service_version="0.1.0",
        environment=settings.environment,
        jaeger_endpoint=os.environ.get("JAEGER_ENDPOINT"),
        otlp_endpoint=os.environ.get("OTLP_ENDPOINT"),
        sample_rate=1.0 if settings.environment == "development" else 0.1,
        console_export=settings.environment == "development",
    )


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize tracing
        _tracer = setup_tracing()
        
        @trace_function("example_operation")
        async def my_operation():
            with trace_context("sub_operation") as span:
                span.set_attribute("key", "value")
                span.add_event("processing")
                await asyncio.sleep(0.1)
                return "done"
        
        # Test tracing
        result = await my_operation()
        print(f"Result: {result}")
        
        # Manual span
        with trace_context("manual_span") as span:
            span.set_attribute("manual", True)
            span.add_event("custom_event")
            time.sleep(0.05)
        
        print("Tracing complete")
    
    asyncio.run(example())