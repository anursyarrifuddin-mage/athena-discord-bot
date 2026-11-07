"""
Observability Package - Structured Logging, Metrics, Tracing, and Health Checks.

This package provides comprehensive observability for the Athenaa application:
- structured logging with correlation IDs
- Prometheus metrics
- distributed tracing (OpenTelemetry compatible)
- health checks with Kubernetes-style probes
"""

from __future__ import annotations

from .logging import (
    setup_structured_logging,
    get_logger,
    get_correlation_id,
    set_correlation_id,
    CorrelationContext,
    RequestContext,
    with_correlation_id,
    log_execution_time,
)

from .metrics import (
    init_metrics,
    get_metrics,
    get_metrics_output,
    get_metrics_content_type,
    track_request_metrics,
    track_in_progress,
    record_error,
    track_db_query,
    track_cache_hit,
    track_metrics,
    update_uptime_metrics,
)

from .tracing import (
    init_tracing,
    get_tracer,
    start_span,
    set_span_attribute,
    add_span_event,
    record_exception,
    set_span_status,
    get_trace_context,
    inject_trace_context,
    extract_trace_context,
    trace_function,
    trace_async_function,
    trace_db_query,
    trace_http_request,
    create_tracing_middleware,
    init_default_tracing,
)

from .health import (
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    SystemHealth,
    create_default_health_checker,
    create_health_endpoints,
)

__all__ = [
    # Logging
    "setup_structured_logging",
    "get_logger",
    "get_correlation_id",
    "set_correlation_id",
    "CorrelationContext",
    "RequestContext",
    "with_correlation_id",
    "log_execution_time",
    
    # Metrics
    "init_metrics",
    "get_metrics",
    "get_metrics_output",
    "get_metrics_content_type",
    "track_request_metrics",
    "track_in_progress",
    "record_error",
    "track_db_query",
    "track_cache_hit",
    "track_metrics",
    "update_uptime_metrics",
    
    # Tracing
    "init_tracing",
    "get_tracer",
    "start_span",
    "set_span_attribute",
    "add_span_event",
    "record_exception",
    "set_span_status",
    "get_trace_context",
    "inject_trace_context",
    "extract_trace_context",
    "trace_function",
    "trace_async_function",
    "trace_db_query",
    "trace_http_request",
    "create_tracing_middleware",
    "init_default_tracing",
    
    # Health
    "HealthChecker",
    "HealthStatus",
    "HealthCheckResult",
    "SystemHealth",
    "create_default_health_checker",
    "create_health_endpoints",
]

# Version
__version__ = "1.0.0"