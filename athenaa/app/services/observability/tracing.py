"""
Distributed Tracing - OpenTelemetry compatible tracing with correlation IDs.
Supports W3C Trace Context standard for interoperability.
"""

from __future__ import annotations

import contextlib
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional, Union
from functools import wraps
from collections import defaultdict

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.zipkin.proto.http import ZipkinExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.propagate import inject, extract, set_global_textmap
    from opentelemetry.propagators.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.propagators.b3 import B3MultiFormat
    from opentelemetry.trace import SpanKind, Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    # Mock classes
    class _MockTracer:
        def start_span(self, *args, **kwargs): return _MockSpan()
        def start_as_current_span(self, *args, **kwargs): return contextlib.nullcontext(_MockSpan())
    
    class _MockSpan:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def set_attribute(self, *args, **kwargs): pass
        def set_status(self, *args, **kwargs): pass
        def record_exception(self, *args, **kwargs): pass
        def end(self): pass
        def add_event(self, *args, **kwargs): pass
    
    trace = type('trace', (), {
        'get_tracer': lambda *args: _MockTracer(),
        'get_current_span': lambda: _MockSpan(),
        'set_span_in_context': lambda span: None,
        'SpanKind': type('SpanKind', (), {'SERVER': 1, 'CLIENT': 2, 'PRODUCER': 3, 'CONSUMER': 4}),
        'Status': type('Status', (), {'__init__': lambda self, code: None}),
        'StatusCode': type('StatusCode', (), {'OK': 1, 'ERROR': 2, 'UNSET': 0}),
    })()
    
    contextlib = contextlib


# Context variables for trace propagation
_current_span_var: ContextVar[Optional[Any]] = ContextVar("current_span", default=None)
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


@dataclass
class SpanData:
    """Span data for manual tracing without OpenTelemetry."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    kind: str
    start_time: float
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"
    error: Optional[str] = None


class ManualTracer:
    """Fallback tracer when OpenTelemetry is not available."""
    
    def __init__(self, service_name: str = "athenaa"):
        self.service_name = service_name
        self._spans: Dict[str, SpanData] = {}
        self._lock = threading.Lock()
        self._current_spans: Dict[int, List[str]] = defaultdict(list)
    
    def start_span(
        self, 
        name: str, 
        kind: str = "internal",
        parent: Optional[SpanData] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanData:
        """Start a new span."""
        trace_id = parent.trace_id if parent else str(uuid.uuid4()).replace("-", "")[:32]
        span_id = str(uuid.uuid4()).replace("-", "")[:16]
        parent_span_id = parent.span_id if parent else None
        
        span = SpanData(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            start_time=time.time(),
            attributes=attributes or {},
        )
        
        with self._lock:
            self._spans[span_id] = span
            thread_id = threading.get_ident()
            self._current_spans[thread_id].append(span_id)
        
        return span
    
    def end_span(self, span: SpanData, status: str = "ok", error: Optional[str] = None) -> None:
        """End a span."""
        span.end_time = time.time()
        span.status = status
        span.error = error
        
        with self._lock:
            thread_id = threading.get_ident()
            if self._current_spans[thread_id] and self._current_spans[thread_id][-1] == span.span_id:
                self._current_spans[thread_id].pop()
    
    def get_current_span(self) -> Optional[SpanData]:
        """Get current span for this thread."""
        thread_id = threading.get_ident()
        if self._current_spans[thread_id]:
            span_id = self._current_spans[thread_id][-1]
            return self._spans.get(span_id)
        return None
    
    def add_event(self, span: SpanData, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add event to span."""
        span.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
    
    def set_attribute(self, span: SpanData, key: str, value: Any) -> None:
        """Set attribute on span."""
        span.attributes[key] = value
    
    def get_trace_context(self, span: SpanData) -> Dict[str, str]:
        """Get trace context for propagation (W3C Trace Context format)."""
        return {
            "traceparent": f"00-{span.trace_id}-{span.span_id}-01",
            "tracestate": f"athenaa={span.trace_id}",
        }


# Global tracer instances
_otel_tracer: Optional[Any] = None
_manual_tracer: Optional[ManualTracer] = None
_tracer_lock = threading.Lock()


def init_tracing(
    service_name: str = "athenaa",
    version: str = "1.0.0",
    exporter_type: str = "console",  # console, otlp, jaeger, zipkin
    exporter_endpoint: Optional[str] = None,
    sample_rate: float = 1.0,
) -> Any:
    """Initialize distributed tracing."""
    global _otel_tracer, _manual_tracer
    
    with _tracer_lock:
        if OTEL_AVAILABLE and exporter_type != "manual":
            # Initialize OpenTelemetry
            resource = Resource.create({
                "service.name": service_name,
                "service.version": version,
            })
            
            provider = TracerProvider(resource=resource)
            
            # Configure exporter
            if exporter_type == "otlp" and exporter_endpoint:
                exporter = OTLPSpanExporter(endpoint=exporter_endpoint, insecure=True)
            elif exporter_type == "jaeger" and exporter_endpoint:
                exporter = JaegerExporter(
                    agent_host_name=exporter_endpoint.split(":")[0],
                    agent_port=int(exporter_endpoint.split(":")[1]) if ":" in exporter_endpoint else 6831,
                )
            elif exporter_type == "zipkin" and exporter_endpoint:
                exporter = ZipkinExporter(endpoint=exporter_endpoint)
            else:
                # Console exporter for development
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter
                exporter = ConsoleSpanExporter()
            
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            
            # Set propagator for W3C Trace Context
            set_global_textmap(TraceContextTextMapPropagator())
            
            # Auto-instrument libraries
            FastAPIInstrumentor.instrument()
            RequestsInstrumentor.instrument()
            HTTPXClientInstrumentor.instrument()
            AioHttpClientInstrumentor.instrument()
            SQLite3Instrumentor.instrument()
            LoggingInstrumentor.instrument(set_logging_format=True)
            
            _otel_tracer = trace.get_tracer(service_name, version)
            return _otel_tracer
        else:
            # Use manual tracer
            _manual_tracer = ManualTracer(service_name)
            return _manual_tracer


def get_tracer() -> Any:
    """Get the current tracer."""
    if _otel_tracer:
        return _otel_tracer
    if _manual_tracer:
        return _manual_tracer
    # Initialize with defaults
    return init_tracing()


def get_current_span() -> Optional[Union[Any, SpanData]]:
    """Get current active span."""
    if OTEL_AVAILABLE and _otel_tracer:
        return trace.get_current_span()
    if _manual_tracer:
        return _manual_tracer.get_current_span()
    return None


@contextlib.contextmanager
def start_span(
    name: str,
    kind: str = "internal",
    attributes: Optional[Dict[str, Any]] = None,
    parent: Optional[Any] = None,
) -> Generator[Any, None, None]:
    """Start a new span as context manager."""
    tracer = get_tracer()
    
    if OTEL_AVAILABLE and _otel_tracer:
        span_kind_map = {
            "server": trace.SpanKind.SERVER,
            "client": trace.SpanKind.CLIENT,
            "producer": trace.SpanKind.PRODUCER,
            "consumer": trace.SpanKind.CONSUMER,
            "internal": trace.SpanKind.INTERNAL,
        }
        span_kind = span_kind_map.get(kind, trace.SpanKind.INTERNAL)
        
        ctx = trace.set_span_in_context(parent) if parent else None
        with tracer.start_as_current_span(name, kind=span_kind, context=ctx, attributes=attributes) as span:
            yield span
    else:
        # Manual tracing
        parent_span = parent if isinstance(parent, SpanData) else None
        span = _manual_tracer.start_span(name, kind, parent_span, attributes)
        try:
            yield span
        finally:
            _manual_tracer.end_span(span)


def set_span_attribute(key: str, value: Any) -> None:
    """Set attribute on current span."""
    span = get_current_span()
    if span:
        if hasattr(span, 'set_attribute'):
            span.set_attribute(key, value)
        elif hasattr(span, 'attributes'):
            span.attributes[key] = value


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add event to current span."""
    span = get_current_span()
    if span:
        if hasattr(span, 'add_event'):
            span.add_event(name, attributes=attributes)
        elif hasattr(span, 'events'):
            span.events.append({
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            })


def record_exception(exc: Exception) -> None:
    """Record exception on current span."""
    span = get_current_span()
    if span:
        if hasattr(span, 'record_exception'):
            span.record_exception(exc)
        elif hasattr(span, 'error'):
            span.error = str(exc)
            span.status = "error"
        
        # Also set error attributes
        set_span_attribute("error.type", type(exc).__name__)
        set_span_attribute("error.message", str(exc))


def set_span_status(status: str, message: Optional[str] = None) -> None:
    """Set span status."""
    span = get_current_span()
    if span:
        if OTEL_AVAILABLE and _otel_tracer:
            status_code = trace.StatusCode.OK if status == "ok" else trace.StatusCode.ERROR
            span.set_status(trace.Status(status_code, message))
        else:
            span.status = status
            if message:
                span.error = message


def get_trace_context() -> Dict[str, str]:
    """Get trace context for propagation (W3C Trace Context)."""
    span = get_current_span()
    if span:
        if hasattr(span, 'get_span_context'):
            ctx = span.get_span_context()
            return {
                "traceparent": f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01",
            }
        elif hasattr(span, 'trace_id'):
            return _manual_tracer.get_trace_context(span) if _manual_tracer else {}
    return {}


def inject_trace_context(headers: Dict[str, str]) -> None:
    """Inject trace context into headers for propagation."""
    if OTEL_AVAILABLE:
        inject(headers)
    else:
        ctx = get_trace_context()
        headers.update(ctx)


def extract_trace_context(headers: Dict[str, str]) -> Optional[Any]:
    """Extract trace context from headers."""
    if OTEL_AVAILABLE:
        return extract(headers)
    # Manual extraction
    traceparent = headers.get("traceparent", "")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 3:
            return {
                "trace_id": parts[1],
                "span_id": parts[2],
                "trace_flags": parts[3] if len(parts) > 3 else "01",
            }
    return None


def trace_function(
    name: Optional[str] = None,
    kind: str = "internal",
    attributes: Optional[Dict[str, Any]] = None,
):
    """Decorator to trace a function."""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            with start_span(span_name, kind, attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    if span:
                        set_span_status("ok")
                    return result
                except Exception as e:
                    record_exception(e)
                    raise
        
        return wrapper
    return decorator


def trace_async_function(
    name: Optional[str] = None,
    kind: str = "internal",
    attributes: Optional[Dict[str, Any]] = None,
):
    """Decorator to trace an async function."""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with start_span(span_name, kind, attributes) as span:
                try:
                    result = await func(*args, **kwargs)
                    if span:
                        set_span_status("ok")
                    return result
                except Exception as e:
                    record_exception(e)
                    raise
        
        return wrapper
    return decorator


# HTTP client instrumentation helpers
def inject_http_headers(headers: Dict[str, str]) -> None:
    """Inject trace context into HTTP headers."""
    inject_trace_context(headers)


def extract_http_context(headers: Dict[str, str]) -> Optional[Any]:
    """Extract trace context from HTTP headers."""
    return extract_trace_context(headers)


# Database query tracing
@contextlib.contextmanager
def trace_db_query(query: str, operation: str = "query", table: Optional[str] = None):
    """Context manager to trace database queries."""
    attrs = {"db.operation": operation, "db.query": query[:1000]}
    if table:
        attrs["db.table"] = table
    
    with start_span(f"db.{operation}", "internal", attrs) as span:
        start = time.perf_counter()
        try:
            yield span
            set_span_attribute("db.duration_ms", (time.perf_counter() - start) * 1000)
            set_span_status("ok")
        except Exception as e:
            set_span_attribute("db.duration_ms", (time.perf_counter() - start) * 1000)
            record_exception(e)
            raise


# HTTP request tracing
@contextlib.contextmanager
def trace_http_request(method: str, url: str, status_code: Optional[int] = None):
    """Context manager to trace HTTP requests."""
    attrs = {"http.method": method, "http.url": url}
    if status_code:
        attrs["http.status_code"] = status_code
    
    with start_span(f"http.{method.lower()}", "client", attrs) as span:
        start = time.perf_counter()
        try:
            yield span
            duration = (time.perf_counter() - start) * 1000
            set_span_attribute("http.duration_ms", duration)
            if status_code:
                set_span_attribute("http.status_code", status_code)
            set_span_status("ok" if not status_code or status_code < 400 else "error")
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            set_span_attribute("http.duration_ms", duration)
            record_exception(e)
            raise


# FastAPI pure ASGI middleware for automatic HTTP request tracing (safe for WebSockets & FileResponse)
def create_tracing_middleware(service_name: str = "athenaa"):
    """Create pure ASGI middleware for automatic HTTP request tracing."""

    class TracingMiddleware:
        def __init__(self, app: Any):
            self.app = app

        async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
            if scope.get("type") != "http":
                await self.app(scope, receive, send)
                return

            raw_headers = {
                k.decode("latin1").lower(): v.decode("latin1")
                for k, v in (scope.get("headers") or [])
            }
            parent_ctx = extract_trace_context(raw_headers)
            method = str(scope.get("method") or "GET")
            path = str(scope.get("path") or "/")
            span_name = f"http.{method.lower()}"
            attrs = {
                "http.method": method,
                "http.scheme": str(scope.get("scheme") or "http"),
                "http.target": path,
            }

            status_code_holder = [200]

            async def send_wrapper(message: Dict[str, Any]) -> None:
                if message.get("type") == "http.response.start":
                    status_code_holder[0] = int(message.get("status") or 200)
                await send(message)

            with start_span(span_name, "server", attrs, parent_ctx) as span:
                start = time.perf_counter()
                try:
                    await self.app(scope, receive, send_wrapper)
                    duration = (time.perf_counter() - start) * 1000
                    if span:
                        code = status_code_holder[0]
                        set_span_attribute("http.status_code", code)
                        set_span_attribute("http.duration_ms", duration)
                        set_span_status("ok" if code < 400 else "error")
                except Exception as e:
                    if span:
                        record_exception(e)
                    raise

    return TracingMiddleware


# Initialize default tracer on module load
def init_default_tracing(service_name: str = "athenaa", version: str = "1.0.0"):
    """Initialize tracing with sensible defaults."""
    return init_tracing(service_name, version, "manual")