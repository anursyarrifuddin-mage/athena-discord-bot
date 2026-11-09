"""
Structured Logging - JSON formatted logs with correlation IDs.
Compatible with ELK stack, Loki, Datadog, CloudWatch, etc.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

# Context variable for correlation ID (thread-safe, async-safe)
_correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_request_context_var: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


def get_correlation_id() -> str:
    """Get current correlation ID, generate if not exists."""
    cid = _correlation_id_var.get()
    if cid is None:
        cid = str(uuid.uuid4())[:8]
        _correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set correlation ID for current context."""
    _correlation_id_var.set(cid)


def clear_correlation_id() -> None:
    """Clear correlation ID."""
    _correlation_id_var.set(None)


def get_request_context() -> Dict[str, Any]:
    """Get current request context."""
    return _request_context_var.get()


def set_request_context(ctx: Dict[str, Any]) -> None:
    """Set request context."""
    _request_context_var.set(ctx)


def clear_request_context() -> None:
    """Clear request context."""
    _request_context_var.set({})


class StructuredLogFormatter(logging.Formatter):
    """JSON log formatter with correlation ID and structured fields."""
    
    def __init__(self, service_name: str = "athenaa", include_extra: bool = True):
        super().__init__()
        self.service_name = service_name
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "correlation_id": get_correlation_id(),
        }
        
        # Add request context if available
        req_ctx = get_request_context()
        if req_ctx:
            log_entry["request"] = req_ctx
        
        # Add standard fields
        if record.module:
            log_entry["module"] = record.module
        if record.funcName:
            log_entry["function"] = record.funcName
        if record.lineno:
            log_entry["line"] = record.lineno
        
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields (custom fields passed via logger.extra)
        if self.include_extra:
            extra_fields = {
                k: v for k, v in record.__dict__.items()
                if k not in {
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "msg", "name", "pathname", "process",
                    "processName", "relativeCreated", "thread", "threadName",
                    "exc_info", "exc_text", "stack_info"
                }
            }
            if extra_fields:
                log_entry["fields"] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class CorrelationFilter(logging.Filter):
    """Filter to add correlation ID to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


def setup_structured_logging(
    level: Union[int, str] = logging.INFO,
    service_name: str = "athenaa",
    output: str = "stdout",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Configure structured logging for the application."""
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = StructuredLogFormatter(service_name=service_name)
    
    # Console handler
    if output in ("stdout", "both"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(CorrelationFilter())
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_file or output in ("file", "both"):
        import os
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
        else:
            log_file = "logs/athenaa.log"
            os.makedirs("logs", exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(CorrelationFilter())
        root_logger.addHandler(file_handler)
    
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get logger with structured formatting."""
    return logging.getLogger(name)


# Context managers for correlation ID
class CorrelationContext:
    """Context manager for correlation ID."""
    
    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.previous_id: Optional[str] = None
    
    def __enter__(self) -> str:
        self.previous_id = _correlation_id_var.get()
        _correlation_id_var.set(self.correlation_id)
        return self.correlation_id
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.previous_id is not None:
            _correlation_id_var.set(self.previous_id)
        else:
            _correlation_id_var.set(None)


class RequestContext:
    """Context manager for request context (user_id, guild_id, etc.)."""
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.previous_context: Dict[str, Any] = {}
    
    def __enter__(self) -> Dict[str, Any]:
        self.previous_context = _request_context_var.get()
        _request_context_var.set(self.context)
        return self.context
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.previous_context:
            _request_context_var.set(self.previous_context)
        else:
            _request_context_var.set({})


# Decorator for automatic correlation ID
def with_correlation_id(func: Callable) -> Callable:
    """Decorator to ensure correlation ID exists for function."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with CorrelationContext():
            return func(*args, **kwargs)
    return wrapper


def log_execution_time(logger: logging.Logger, operation: str):
    """Decorator to log function execution time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    f"Operation completed",
                    extra={"operation": operation, "duration_ms": round(duration_ms, 2), "status": "success"}
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    f"Operation failed",
                    extra={"operation": operation, "duration_ms": round(duration_ms, 2), "status": "error", "error": str(e)},
                    exc_info=True
                )
                raise
        return wrapper
    return decorator