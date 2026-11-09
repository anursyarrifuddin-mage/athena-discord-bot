"""
Prometheus Metrics - Application metrics for monitoring and alerting.
Exposes /metrics endpoint for Prometheus scraping.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Dict, Optional, Any, Generator
from contextvars import ContextVar

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary, Info, Enum,
        CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
        push_to_gateway, pushadd_to_gateway, delete_from_gateway
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock classes for when prometheus_client is not available
    class _MockMetric:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def dec(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def time(self): return _MockContextManager()
        def info(self, *args, **kwargs): pass
        def __call__(self, *args, **kwargs): return self

    class _MockContextManager:
        def __enter__(self): return self
        def __exit__(self, *args): pass

    Counter = Gauge = Histogram = Summary = Info = Enum = _MockMetric
    CollectorRegistry = _MockMetric
    generate_latest = lambda *args: b""
    CONTENT_TYPE_LATEST = "text/plain"

# Global registry - initialized lazily
_registry: Optional[CollectorRegistry] = None
_registry_lock = threading.Lock()
_metrics: Optional[MetricDefinitions] = None
_metrics_lock = threading.Lock()
_initialized = False

# Context variable for current request labels
_request_labels_var: ContextVar[Dict[str, str]] = ContextVar("request_labels", default={})


def get_metrics_registry() -> CollectorRegistry:
    """Get or create the global metrics registry."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CollectorRegistry()
    return _registry


def set_request_labels(labels: Dict[str, str]) -> None:
    """Set labels for current request context."""
    _request_labels_var.set(labels)


def get_request_labels() -> Dict[str, str]:
    """Get current request labels."""
    return _request_labels_var.get()


class MetricDefinitions:
    """Centralized metric definitions for consistency.
    
    Metrics are created lazily on first access to avoid deadlock during initialization.
    """
    
    def __init__(self, registry: CollectorRegistry):
        self._registry = registry
        self._metrics_cache: Dict[str, Any] = {}
        self._init_lock = threading.Lock()
    
    def _get_or_create(self, name: str, factory: Callable) -> Any:
        """Thread-safe lazy metric creation."""
        if name not in self._metrics_cache:
            with self._init_lock:
                if name not in self._metrics_cache:
                    self._metrics_cache[name] = factory()
        return self._metrics_cache[name]
    
    # Application info
    @property
    def app_info(self) -> 'Info':
        return self._get_or_create("app_info", lambda: Info(
            "athenaa_build_info", "Build information", registry=self._registry
        ))
    
    # HTTP metrics
    @property
    def http_requests_total(self) -> 'Counter':
        return self._get_or_create("http_requests_total", lambda: Counter(
            "athenaa_http_requests_total", "Total HTTP requests",
            ["method", "endpoint", "status"], registry=self._registry
        ))
    
    @property
    def http_request_duration(self) -> 'Histogram':
        return self._get_or_create("http_request_duration", lambda: Histogram(
            "athenaa_http_request_duration_seconds", "HTTP request latency",
            ["method", "endpoint"], buckets=(.01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10),
            registry=self._registry
        ))
    
    @property
    def http_requests_in_progress(self) -> 'Gauge':
        return self._get_or_create("http_requests_in_progress", lambda: Gauge(
            "athenaa_http_requests_in_progress", "HTTP requests currently in progress",
            ["method", "endpoint"], registry=self._registry
        ))
    
    # WebSocket metrics
    @property
    def ws_connections_active(self) -> 'Gauge':
        return self._get_or_create("ws_connections_active", lambda: Gauge(
            "athenaa_ws_connections_active", "Active WebSocket connections",
            ["guild_id"], registry=self._registry
        ))
    
    @property
    def ws_messages_total(self) -> 'Counter':
        return self._get_or_create("ws_messages_total", lambda: Counter(
            "athenaa_ws_messages_total", "Total WebSocket messages",
            ["direction", "type"], registry=self._registry
        ))
    
    # Music metrics
    @property
    def music_tracks_played_total(self) -> 'Counter':
        return self._get_or_create("music_tracks_played_total", lambda: Counter(
            "athenaa_music_tracks_played_total", "Total tracks played",
            ["guild_id", "source_type"], registry=self._registry
        ))
    
    @property
    def music_queue_size(self) -> 'Gauge':
        return self._get_or_create("music_queue_size", lambda: Gauge(
            "athenaa_music_queue_size", "Current queue size",
            ["guild_id"], registry=self._registry
        ))
    
    @property
    def music_playback_duration(self) -> 'Histogram':
        return self._get_or_create("music_playback_duration", lambda: Histogram(
            "athenaa_music_playback_duration_seconds", "Track playback duration",
            ["guild_id", "source_type"], buckets=(10, 30, 60, 120, 180, 300, 600, 1800),
            registry=self._registry
        ))
    
    @property
    def music_autoplay_triggered_total(self) -> 'Counter':
        return self._get_or_create("music_autoplay_triggered_total", lambda: Counter(
            "athenaa_music_autoplay_triggered_total", "Autoplay triggers",
            ["guild_id", "reason"], registry=self._registry
        ))
    
    @property
    def music_stream_extraction_duration(self) -> 'Histogram':
        return self._get_or_create("music_stream_extraction_duration", lambda: Histogram(
            "athenaa_music_stream_extraction_duration_seconds", "Stream extraction latency",
            ["source_type"], buckets=(.1, .25, .5, 1, 2, 5, 10, 30),
            registry=self._registry
        ))
    
    @property
    def music_search_duration(self) -> 'Histogram':
        return self._get_or_create("music_search_duration", lambda: Histogram(
            "athenaa_music_search_duration_seconds", "Music search latency",
            ["source_type"], buckets=(.1, .25, .5, 1, 2, 5, 10),
            registry=self._registry
        ))
    
    # Academic metrics
    @property
    def academic_tasks_total(self) -> 'Counter':
        return self._get_or_create("academic_tasks_total", lambda: Counter(
            "athenaa_academic_tasks_total", "Total academic tasks",
            ["guild_id", "status"], registry=self._registry
        ))
    
    @property
    def academic_reminders_sent_total(self) -> 'Counter':
        return self._get_or_create("academic_reminders_sent_total", lambda: Counter(
            "athenaa_academic_reminders_sent_total", "Reminders sent",
            ["guild_id", "stage"], registry=self._registry
        ))
    
    @property
    def academic_sync_duration(self) -> 'Histogram':
        return self._get_or_create("academic_sync_duration", lambda: Histogram(
            "athenaa_academic_sync_duration_seconds", "Moodle sync duration",
            ["guild_id"], buckets=(1, 5, 10, 30, 60, 120),
            registry=self._registry
        ))
    
    # RPG/Leveling metrics
    @property
    def rpg_exp_gained_total(self) -> 'Counter':
        return self._get_or_create("rpg_exp_gained_total", lambda: Counter(
            "athenaa_rpg_exp_gained_total", "Total EXP gained",
            ["guild_id", "source"], registry=self._registry
        ))
    
    @property
    def rpg_level_ups_total(self) -> 'Counter':
        return self._get_or_create("rpg_level_ups_total", lambda: Counter(
            "athenaa_rpg_level_ups_total", "Total level ups",
            ["guild_id"], registry=self._registry
        ))
    
    # System metrics
    @property
    def process_cpu_seconds(self) -> 'Gauge':
        return self._get_or_create("process_cpu_seconds", lambda: Gauge(
            "athenaa_process_cpu_seconds", "Process CPU time",
            registry=self._registry
        ))
    
    @property
    def process_memory_bytes(self) -> 'Gauge':
        return self._get_or_create("process_memory_bytes", lambda: Gauge(
            "athenaa_process_memory_bytes", "Process memory usage",
            registry=self._registry
        ))
    
    @property
    def process_uptime_seconds(self) -> 'Gauge':
        return self._get_or_create("process_uptime_seconds", lambda: Gauge(
            "athenaa_process_uptime_seconds", "Process uptime",
            registry=self._registry
        ))
    
    # Database metrics
    @property
    def db_queries_total(self) -> 'Counter':
        return self._get_or_create("db_queries_total", lambda: Counter(
            "athenaa_db_queries_total", "Total database queries",
            ["operation", "table"], registry=self._registry
        ))
    
    @property
    def db_query_duration(self) -> 'Histogram':
        return self._get_or_create("db_query_duration", lambda: Histogram(
            "athenaa_db_query_duration_seconds", "Database query latency",
            ["operation"], buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1),
            registry=self._registry
        ))
    
    @property
    def db_connections_active(self) -> 'Gauge':
        return self._get_or_create("db_connections_active", lambda: Gauge(
            "athenaa_db_connections_active", "Active database connections",
            registry=self._registry
        ))
    
    # Cache metrics
    @property
    def cache_hits_total(self) -> 'Counter':
        return self._get_or_create("cache_hits_total", lambda: Counter(
            "athenaa_cache_hits_total", "Cache hits",
            ["cache_name"], registry=self._registry
        ))
    
    @property
    def cache_misses_total(self) -> 'Counter':
        return self._get_or_create("cache_misses_total", lambda: Counter(
            "athenaa_cache_misses_total", "Cache misses",
            ["cache_name"], registry=self._registry
        ))
    
    @property
    def cache_size(self) -> 'Gauge':
        return self._get_or_create("cache_size", lambda: Gauge(
            "athenaa_cache_size", "Cache size",
            ["cache_name"], registry=self._registry
        ))
    
    # Rate limiter metrics
    @property
    def rate_limiter_rejected_total(self) -> 'Counter':
        return self._get_or_create("rate_limiter_rejected_total", lambda: Counter(
            "athenaa_rate_limiter_rejected_total", "Rate limiter rejections",
            ["endpoint"], registry=self._registry
        ))
    
    # Error metrics
    @property
    def errors_total(self) -> 'Counter':
        return self._get_or_create("errors_total", lambda: Counter(
            "athenaa_errors_total", "Total errors",
            ["component", "error_type"], registry=self._registry
        ))
    
    # Bot metrics
    @property
    def bot_guilds_connected(self) -> 'Gauge':
        return self._get_or_create("bot_guilds_connected", lambda: Gauge(
            "athenaa_bot_guilds_connected", "Connected Discord guilds",
            registry=self._registry
        ))
    
    @property
    def bot_voice_connections(self) -> 'Gauge':
        return self._get_or_create("bot_voice_connections", lambda: Gauge(
            "athenaa_bot_voice_connections", "Active voice connections",
            registry=self._registry
        ))
    
    @property
    def bot_latency(self) -> 'Gauge':
        return self._get_or_create("bot_latency", lambda: Gauge(
            "athenaa_bot_latency_seconds", "Discord gateway latency",
            registry=self._registry
        ))


# Global metrics instance
_metrics: Optional[MetricDefinitions] = None
_metrics_lock = threading.Lock()
_initialized = False


def get_metrics() -> MetricDefinitions:
    """Get global metrics instance, initializing if needed."""
    global _metrics, _initialized
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                registry = get_metrics_registry()
                _metrics = MetricDefinitions(registry)
                _initialized = True
    return _metrics


def init_metrics(service_name: str = "athenaa", version: str = "1.0.0") -> MetricDefinitions:
    """Initialize metrics with app info."""
    metrics = get_metrics()
    metrics.app_info.info({"version": version, "service": service_name})
    return metrics


# Helper functions for common operations
def increment_counter(name: str, labels: Optional[Dict[str, str]] = None, value: float = 1) -> None:
    """Increment a counter metric."""
    metrics = get_metrics()
    counter = getattr(metrics, name, None)
    if counter and hasattr(counter, 'labels'):
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)


def set_gauge(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge metric."""
    metrics = get_metrics()
    gauge = getattr(metrics, name, None)
    if gauge and hasattr(gauge, 'labels'):
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)


def observe_histogram(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
    """Observe a histogram metric."""
    metrics = get_metrics()
    histogram = getattr(metrics, name, None)
    if histogram and hasattr(histogram, 'labels'):
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)


def time_operation(name: str, labels: Optional[Dict[str, str]] = None):
    """Context manager to time an operation."""
    return getattr(get_metrics(), name).labels(**(labels or {})).time()


def track_request_metrics(
    method: str, 
    endpoint: str, 
    status_code: int, 
    duration: float
) -> None:
    """Track HTTP request metrics."""
    labels = {"method": method, "endpoint": endpoint, "status": str(status_code)}
    increment_counter("http_requests_total", labels)
    observe_histogram("http_request_duration", duration, {"method": method, "endpoint": endpoint})


@contextmanager
def track_in_progress(method: str, endpoint: str):
    """Context manager to track in-progress requests."""
    labels = {"method": method, "endpoint": endpoint}
    gauge = getattr(get_metrics(), "http_requests_in_progress")
    if gauge and hasattr(gauge, 'labels'):
        gauge.labels(**labels).inc()
    try:
        yield
    finally:
        if gauge and hasattr(gauge, 'labels'):
            gauge.labels(**labels).dec()


def record_error(component: str, error_type: str) -> None:
    """Record an error metric."""
    increment_counter("errors_total", {"component": component, "error_type": error_type})


def track_db_query(operation: str, table: str, duration: float) -> None:
    """Track database query metrics."""
    increment_counter("db_queries_total", {"operation": operation, "table": table})
    observe_histogram("db_query_duration", duration, {"operation": operation})


def track_cache_hit(cache_name: str, hit: bool) -> None:
    """Track cache hit/miss."""
    if hit:
        increment_counter("cache_hits_total", {"cache_name": cache_name})
    else:
        increment_counter("cache_misses_total", {"cache_name": cache_name})


# Decorators for automatic metrics
def track_metrics(metric_name: str, labels_fn: Optional[Callable] = None):
    """Decorator to track function metrics."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            labels = labels_fn(*args, **kwargs) if labels_fn else {}
            try:
                result = func(*args, **kwargs)
                observe_histogram(metric_name, time.perf_counter() - start, labels)
                return result
            except Exception as e:
                observe_histogram(metric_name, time.perf_counter() - start, labels)
                record_error(func.__module__ or "unknown", type(e).__name__)
                raise
        return wrapper
    return decorator


# Metrics endpoint for Prometheus
def get_metrics_output() -> bytes:
    """Get metrics in Prometheus format."""
    if PROMETHEUS_AVAILABLE:
        return generate_latest(get_metrics_registry())
    return b"# Prometheus client not available"


def get_metrics_content_type() -> str:
    """Get content type for metrics endpoint."""
    return CONTENT_TYPE_LATEST


# Push gateway support (for batch jobs)
def push_metrics(gateway_url: str, job_name: str, grouping_key: Optional[Dict[str, str]] = None) -> None:
    """Push metrics to Prometheus Pushgateway."""
    if PROMETHEUS_AVAILABLE:
        push_to_gateway(gateway_url, job=job_name, registry=get_metrics_registry(), grouping_key=grouping_key)


def delete_metrics(gateway_url: str, job_name: str, grouping_key: Optional[Dict[str, str]] = None) -> None:
    """Delete metrics from Pushgateway."""
    if PROMETHEUS_AVAILABLE:
        delete_from_gateway(gateway_url, job=job_name, grouping_key=grouping_key)


# Startup time tracking
_start_time = time.time()


def update_uptime_metrics() -> None:
    """Update uptime and process metrics."""
    try:
        import psutil
        process = psutil.Process()
        set_gauge("process_cpu_seconds", process.cpu_times().user + process.cpu_times().system)
        set_gauge("process_memory_bytes", process.memory_info().rss)
    except ImportError:
        pass
    set_gauge("process_uptime_seconds", time.time() - _start_time)