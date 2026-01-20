"""Service health monitoring for Reachy Mini.

This module provides health checking and monitoring capabilities
for all services in the system.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status of a service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health information for a single service."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: float = 0.0
    last_healthy_time: float = 0.0
    error_count: int = 0
    last_error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self.status == HealthStatus.HEALTHY

    def mark_healthy(self, now: float | None = None) -> None:
        """Mark service as healthy."""
        now = now or time.monotonic()
        self.status = HealthStatus.HEALTHY
        self.last_check_time = now
        self.last_healthy_time = now
        self.error_count = 0
        self.last_error = None

    def mark_unhealthy(self, error: str, now: float | None = None) -> None:
        """Mark service as unhealthy."""
        now = now or time.monotonic()
        self.status = HealthStatus.UNHEALTHY
        self.last_check_time = now
        self.error_count += 1
        self.last_error = error

    def mark_degraded(self, reason: str, now: float | None = None) -> None:
        """Mark service as degraded (partially working)."""
        now = now or time.monotonic()
        self.status = HealthStatus.DEGRADED
        self.last_check_time = now
        self.last_error = reason


class HealthChecker:
    """Health checker for a single service.

    Usage:
        checker = HealthChecker(
            name="camera_server",
            check_func=lambda: camera_server.is_running,
            interval=30.0,
        )
        checker.start()
        # ...
        health = checker.get_health()
    """

    def __init__(
        self,
        name: str,
        check_func: Callable[[], bool],
        interval: float = 30.0,
        timeout: float = 5.0,
        on_unhealthy: Callable[[ServiceHealth], None] | None = None,
    ):
        """Initialize health checker.

        Args:
            name: Service name
            check_func: Function that returns True if healthy
            interval: Check interval in seconds
            timeout: Timeout for health check
            on_unhealthy: Callback when service becomes unhealthy
        """
        self.name = name
        self._check_func = check_func
        self._interval = interval
        self._timeout = timeout
        self._on_unhealthy = on_unhealthy

        self._health = ServiceHealth(name=name)
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def health(self) -> ServiceHealth:
        """Get current health status."""
        with self._lock:
            return self._health

    def check_now(self) -> ServiceHealth:
        """Perform immediate health check."""
        now = time.monotonic()

        try:
            is_healthy = self._check_func()

            with self._lock:
                if is_healthy:
                    self._health.mark_healthy(now)
                else:
                    self._health.mark_unhealthy("Health check returned False", now)
                    if self._on_unhealthy:
                        self._on_unhealthy(self._health)

        except Exception as e:
            with self._lock:
                self._health.mark_unhealthy(str(e), now)
                if self._on_unhealthy:
                    self._on_unhealthy(self._health)

        return self._health

    def start(self) -> None:
        """Start periodic health checking."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._check_loop,
            daemon=True,
            name=f"health-{self.name}",
        )
        self._thread.start()
        logger.debug("Health checker started for %s", self.name)

    def stop(self) -> None:
        """Stop health checking."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.debug("Health checker stopped for %s", self.name)

    def _check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            self.check_now()

            # Wait for interval or stop signal
            if self._stop_event.wait(timeout=self._interval):
                break


class HealthMonitor:
    """Central health monitoring for all services.

    Usage:
        monitor = HealthMonitor()
        monitor.register_checker("camera", lambda: camera.is_running)
        monitor.register_checker("motion", lambda: motion.is_running)
        monitor.start()
        # ...
        status = monitor.get_overall_health()
    """

    def __init__(self, default_interval: float = 30.0):
        """Initialize health monitor.

        Args:
            default_interval: Default check interval for services
        """
        self._default_interval = default_interval
        self._checkers: dict[str, HealthChecker] = {}
        self._lock = threading.Lock()
        self._running = False

    def register_checker(
        self,
        name: str,
        check_func: Callable[[], bool],
        interval: float | None = None,
        on_unhealthy: Callable[[ServiceHealth], None] | None = None,
    ) -> None:
        """Register a health checker for a service.

        Args:
            name: Service name
            check_func: Function that returns True if healthy
            interval: Check interval (uses default if None)
            on_unhealthy: Callback when service becomes unhealthy
        """
        checker = HealthChecker(
            name=name,
            check_func=check_func,
            interval=interval or self._default_interval,
            on_unhealthy=on_unhealthy,
        )

        with self._lock:
            # Stop existing checker if any
            if name in self._checkers:
                self._checkers[name].stop()

            self._checkers[name] = checker

            # Start if monitor is running
            if self._running:
                checker.start()

        logger.info("Registered health checker for: %s", name)

    def unregister_checker(self, name: str) -> None:
        """Unregister a health checker."""
        with self._lock:
            if name in self._checkers:
                self._checkers[name].stop()
                del self._checkers[name]
                logger.info("Unregistered health checker for: %s", name)

    def start(self) -> None:
        """Start all health checkers."""
        with self._lock:
            self._running = True
            for checker in self._checkers.values():
                checker.start()
        logger.info("Health monitor started with %d checkers", len(self._checkers))

    def stop(self) -> None:
        """Stop all health checkers."""
        with self._lock:
            self._running = False
            for checker in self._checkers.values():
                checker.stop()
        logger.info("Health monitor stopped")

    def get_service_health(self, name: str) -> ServiceHealth | None:
        """Get health status for a specific service."""
        with self._lock:
            if name in self._checkers:
                return self._checkers[name].health
        return None

    def get_all_health(self) -> dict[str, ServiceHealth]:
        """Get health status for all services."""
        with self._lock:
            return {name: checker.health for name, checker in self._checkers.items()}

    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status.

        Returns HEALTHY if all services healthy,
        DEGRADED if some services unhealthy,
        UNHEALTHY if critical services down.
        """
        all_health = self.get_all_health()

        if not all_health:
            return HealthStatus.UNKNOWN

        unhealthy_count = sum(
            1 for h in all_health.values()
            if h.status == HealthStatus.UNHEALTHY
        )

        if unhealthy_count == 0:
            return HealthStatus.HEALTHY
        elif unhealthy_count < len(all_health):
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNHEALTHY

    def check_all_now(self) -> dict[str, ServiceHealth]:
        """Perform immediate health check on all services."""
        with self._lock:
            return {
                name: checker.check_now()
                for name, checker in self._checkers.items()
            }


# Global health monitor instance
_health_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    """Get or create global health monitor."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
