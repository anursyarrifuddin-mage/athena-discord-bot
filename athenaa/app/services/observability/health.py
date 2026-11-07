"""
Health Checks - Comprehensive health monitoring for all services.
Provides /health, /ready, /live endpoints for Kubernetes-style probes.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SystemHealth:
    """Overall system health summary."""
    status: HealthStatus
    checks: List[HealthCheckResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    uptime_seconds: float = 0
    version: str = "1.0.0"


class HealthChecker:
    """Manages and executes health checks."""
    
    def __init__(self, service_name: str = "athenaa", version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        self._checks: Dict[str, Callable[[], HealthCheckResult]] = {}
        self._start_time = time.time()
        self._last_result: Optional[SystemHealth] = None
    
    def register_check(self, name: str, check_fn: Callable[[], HealthCheckResult]) -> None:
        """Register a health check function."""
        self._checks[name] = check_fn
    
    def run_check(self, name: str) -> HealthCheckResult:
        """Run a single health check by name."""
        check_fn = self._checks.get(name)
        if not check_fn:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Check '{name}' not registered",
            )
        
        start = time.perf_counter()
        try:
            result = check_fn()
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                duration_ms=duration,
            )
    
    def run_all_checks(self) -> SystemHealth:
        """Run all registered health checks."""
        start = time.perf_counter()
        results = []
        
        for name in self._checks:
            results.append(self.run_check(name))
        
        # Determine overall status
        statuses = [r.status for r in results]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        
        health = SystemHealth(
            status=overall,
            checks=results,
            uptime_seconds=time.time() - self._start_time,
            version=self.version,
        )
        
        self._last_result = health
        return health
    
    def get_last_result(self) -> Optional[SystemHealth]:
        """Get last health check result."""
        return self._last_result


# Pre-built health checks
def create_db_health_check(db_path: str) -> Callable[[], HealthCheckResult]:
    """Create a database connectivity health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.execute("SELECT 1")
            conn.close()
            return HealthCheckResult(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
                details={"path": db_path},
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_disk_health_check(path: str = "/", threshold_pct: float = 90) -> Callable[[], HealthCheckResult]:
    """Create a disk space health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            if PSUTIL_AVAILABLE:
                usage = psutil.disk_usage(path)
                free_pct = (usage.free / usage.total) * 100
                used_pct = 100 - free_pct
                
                if used_pct >= threshold_pct:
                    status = HealthStatus.UNHEALTHY
                    message = f"Disk usage critical: {used_pct:.1f}% used"
                elif used_pct >= threshold_pct - 10:
                    status = HealthStatus.DEGRADED
                    message = f"Disk usage high: {used_pct:.1f}% used"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Disk usage OK: {used_pct:.1f}% used"
                
                return HealthCheckResult(
                    name="disk",
                    status=status,
                    message=message,
                    details={
                        "path": path,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "used_percent": round(used_pct, 1),
                    },
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                return HealthCheckResult(
                    name="disk",
                    status=HealthStatus.UNKNOWN,
                    message="psutil not available",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
        except Exception as e:
            return HealthCheckResult(
                name="disk",
                status=HealthStatus.UNHEALTHY,
                message=f"Disk check failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_memory_health_check(threshold_pct: float = 90) -> Callable[[], HealthCheckResult]:
    """Create a memory usage health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            if PSUTIL_AVAILABLE:
                mem = psutil.virtual_memory()
                used_pct = mem.percent
                
                if used_pct >= threshold_pct:
                    status = HealthStatus.UNHEALTHY
                    message = f"Memory usage critical: {used_pct:.1f}% used"
                elif used_pct >= threshold_pct - 10:
                    status = HealthStatus.DEGRADED
                    message = f"Memory usage high: {used_pct:.1f}% used"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Memory usage OK: {used_pct:.1f}% used"
                
                return HealthCheckResult(
                    name="memory",
                    status=status,
                    message=message,
                    details={
                        "total_gb": round(mem.total / (1024**3), 2),
                        "used_gb": round(mem.used / (1024**3), 2),
                        "available_gb": round(mem.available / (1024**3), 2),
                        "used_percent": used_pct,
                    },
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.UNKNOWN,
                    message="psutil not available",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
        except Exception as e:
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"Memory check failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_cpu_health_check(threshold_pct: float = 90) -> Callable[[], HealthCheckResult]:
    """Create a CPU usage health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            if PSUTIL_AVAILABLE:
                # Quick CPU check (non-blocking)
                cpu_pct = psutil.cpu_percent(interval=0.1)
                
                if cpu_pct >= threshold_pct:
                    status = HealthStatus.UNHEALTHY
                    message = f"CPU usage critical: {cpu_pct:.1f}%"
                elif cpu_pct >= threshold_pct - 10:
                    status = HealthStatus.DEGRADED
                    message = f"CPU usage high: {cpu_pct:.1f}%"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"CPU usage OK: {cpu_pct:.1f}%"
                
                return HealthCheckResult(
                    name="cpu",
                    status=status,
                    message=message,
                    details={"cpu_percent": cpu_pct, "cores": psutil.cpu_count()},
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                return HealthCheckResult(
                    name="cpu",
                    status=HealthStatus.UNKNOWN,
                    message="psutil not available",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
        except Exception as e:
            return HealthCheckResult(
                name="cpu",
                status=HealthStatus.UNHEALTHY,
                message=f"CPU check failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_external_service_check(
    name: str, 
    url: str, 
    timeout: float = 5.0,
    expected_status: int = 200
) -> Callable[[], HealthCheckResult]:
    """Create an external service connectivity check."""
    import urllib.request
    
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Athenaa-HealthCheck/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == expected_status:
                    return HealthCheckResult(
                        name=name,
                        status=HealthStatus.HEALTHY,
                        message=f"{name} is reachable",
                        details={"url": url, "status": resp.status},
                        duration_ms=(time.perf_counter() - start) * 1000,
                    )
                else:
                    return HealthCheckResult(
                        name=name,
                        status=HealthStatus.DEGRADED,
                        message=f"{name} returned status {resp.status}",
                        details={"url": url, "status": resp.status},
                        duration_ms=(time.perf_counter() - start) * 1000,
                    )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"{name} unreachable: {e}",
                details={"url": url},
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_bot_health_check(
    bot_getter: Callable[[], Any]
) -> Callable[[], HealthCheckResult]:
    """Create a Discord bot connectivity health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            bot = bot_getter()
            if bot is None:
                return HealthCheckResult(
                    name="discord_bot",
                    status=HealthStatus.UNHEALTHY,
                    message="Bot instance not initialized",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            
            if not hasattr(bot, 'is_ready') or not bot.is_ready():
                return HealthCheckResult(
                    name="discord_bot",
                    status=HealthStatus.DEGRADED,
                    message="Bot not ready",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            
            latency = getattr(bot, 'latency', 0) * 1000  # Convert to ms
            
            if latency > 500:
                status = HealthStatus.DEGRADED
                message = f"Bot ready but high latency: {latency:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = f"Bot ready, latency: {latency:.0f}ms"
            
            return HealthCheckResult(
                name="discord_bot",
                status=status,
                message=message,
                details={
                    "guilds": len(bot.guilds) if hasattr(bot, 'guilds') else 0,
                    "latency_ms": round(latency, 2),
                    "user": str(bot.user) if hasattr(bot, 'user') else "unknown",
                },
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            return HealthCheckResult(
                name="discord_bot",
                status=HealthStatus.UNHEALTHY,
                message=f"Bot check failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


def create_queue_health_check(
    queue_service_getter: Callable[[], Any]
) -> Callable[[], HealthCheckResult]:
    """Create a music queue service health check."""
    def check() -> HealthCheckResult:
        start = time.perf_counter()
        try:
            qs = queue_service_getter()
            if qs is None:
                return HealthCheckResult(
                    name="queue_service",
                    status=HealthStatus.UNHEALTHY,
                    message="Queue service not initialized",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            
            # Check active guilds
            active_guilds = len(getattr(qs, 'active_guilds', {}))
            states = getattr(qs, '_states', {})
            
            total_queued = sum(len(s.queue) for s in states.values())
            playing = sum(1 for s in states.values() if s.is_playing)
            
            return HealthCheckResult(
                name="queue_service",
                status=HealthStatus.HEALTHY,
                message="Queue service operational",
                details={
                    "active_guilds": active_guilds,
                    "total_states": len(states),
                    "total_queued_tracks": total_queued,
                    "currently_playing": playing,
                },
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            return HealthCheckResult(
                name="queue_service",
                status=HealthStatus.UNHEALTHY,
                message=f"Queue check failed: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    return check


# Default health checker setup
def create_default_health_checker(
    service_name: str = "athenaa",
    version: str = "1.0.0",
    db_path: Optional[str] = None,
    bot_getter: Optional[Callable[[], Any]] = None,
    queue_service_getter: Optional[Callable[[], Any]] = None,
) -> HealthChecker:
    """Create a health checker with standard checks."""
    checker = HealthChecker(service_name, version)
    
    # System checks
    checker.register_check("disk", create_disk_health_check())
    checker.register_check("memory", create_memory_health_check())
    checker.register_check("cpu", create_cpu_health_check())
    
    # Database check
    if db_path:
        checker.register_check("database", create_db_health_check(db_path))
    
    # External services
    checker.register_check("discord_api", create_external_service_check(
        "discord_api", "https://discord.com/api/v10/gateway"
    ))
    checker.register_check("youtube", create_external_service_check(
        "youtube", "https://www.youtube.com"
    ))
    checker.register_check("spotify", create_external_service_check(
        "spotify", "https://open.spotify.com"
    ))
    checker.register_check("lrclib", create_external_service_check(
        "lrclib", "https://lrclib.net/api/health"
    ))
    
    # Bot check
    if bot_getter:
        checker.register_check("discord_bot", create_bot_health_check(bot_getter))
    
    # Queue service check
    if queue_service_getter:
        checker.register_check("queue_service", create_queue_health_check(queue_service_getter))
    
    return checker


# FastAPI endpoints
def create_health_endpoints(app, checker: HealthChecker):
    """Add health check endpoints to FastAPI app."""
    
    @app.get("/health")
    async def health():
        """Liveness probe - service is running."""
        health = checker.run_all_checks()
        # For liveness, we only care if service is up
        return {
            "status": health.status.value,
            "service": checker.service_name,
            "version": health.version,
            "uptime_seconds": round(health.uptime_seconds, 1),
        }
    
    @app.get("/ready")
    async def ready():
        """Readiness probe - service can handle requests."""
        health = checker.run_all_checks()
        # For readiness, we need all critical checks to pass
        critical_checks = {"database", "discord_bot", "queue_service"}
        failed_critical = [
            c.name for c in health.checks 
            if c.name in critical_checks and c.status == HealthStatus.UNHEALTHY
        ]
        
        if failed_critical:
            return {
                "ready": False,
                "status": health.status.value,
                "failed_critical": failed_critical,
                "checks": {c.name: c.status.value for c in health.checks},
            }
        
        return {
            "ready": True,
            "status": health.status.value,
            "checks": {c.name: c.status.value for c in health.checks},
        }
    
    @app.get("/live")
    async def live():
        """Liveness probe - service is alive."""
        return {"alive": True, "service": checker.service_name}
    
    @app.get("/health/details")
    async def health_details():
        """Detailed health check results."""
        health = checker.run_all_checks()
        return {
            "status": health.status.value,
            "service": checker.service_name,
            "version": health.version,
            "uptime_seconds": round(health.uptime_seconds, 1),
            "timestamp": health.timestamp,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": round(c.duration_ms, 2),
                }
                for c in health.checks
            ],
        }