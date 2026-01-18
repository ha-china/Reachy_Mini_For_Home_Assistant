"""System Diagnostics for Home Assistant.

This module provides system diagnostic sensors using psutil to monitor
CPU, memory, disk, and network usage on the Reachy Mini robot.

All sensors are registered with entity_category=2 (diagnostic) so they
appear in the Diagnostics section in Home Assistant.
"""

import logging
import time
from typing import Optional, TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SystemDiagnostics:
    """System diagnostics provider using psutil.

    This class provides getter methods for various system metrics that can
    be used with SensorEntity's value_getter parameter.

    Metrics are cached briefly to avoid excessive system calls when multiple
    entities are updated in quick succession.
    """

    def __init__(self, cache_ttl: float = 1.0):
        """Initialize system diagnostics.

        Args:
            cache_ttl: Cache time-to-live in seconds. Metrics are cached
                to avoid excessive system calls.
        """
        self._cache_ttl = cache_ttl
        self._cache: dict = {}
        self._cache_time: dict = {}

        # Get initial disk path (root partition)
        self._disk_path = "/" if psutil.POSIX else "C:\\"

        logger.info("SystemDiagnostics initialized")

    def _get_cached(self, key: str, getter) -> any:
        """Get a cached value or compute it.

        Args:
            key: Cache key
            getter: Callable to get fresh value

        Returns:
            Cached or fresh value
        """
        now = time.monotonic()
        if key in self._cache:
            if now - self._cache_time.get(key, 0) < self._cache_ttl:
                return self._cache[key]

        try:
            value = getter()
            self._cache[key] = value
            self._cache_time[key] = now
            return value
        except Exception as e:
            logger.debug("Error getting %s: %s", key, e)
            return self._cache.get(key, 0.0)

    # =========================================================================
    # CPU Metrics
    # =========================================================================

    def get_cpu_percent(self) -> float:
        """Get CPU usage percentage (0-100)."""
        return self._get_cached(
            "cpu_percent",
            lambda: psutil.cpu_percent(interval=None)
        )

    def get_cpu_temperature(self) -> float:
        """Get CPU temperature in Celsius.

        Note: May not be available on all platforms.
        Returns 0.0 if temperature sensors are not available.
        """
        def _get_temp():
            temps = psutil.sensors_temperatures()
            if not temps:
                return 0.0

            # Try common sensor names
            for name in ["coretemp", "cpu_thermal", "cpu-thermal", "k10temp", "zenpower"]:
                if name in temps and temps[name]:
                    return temps[name][0].current

            # Fallback: first available sensor
            for sensors in temps.values():
                if sensors:
                    return sensors[0].current

            return 0.0

        return self._get_cached("cpu_temperature", _get_temp)

    def get_cpu_count(self) -> float:
        """Get number of CPU cores."""
        return float(psutil.cpu_count() or 1)

    # =========================================================================
    # Memory Metrics
    # =========================================================================

    def get_memory_percent(self) -> float:
        """Get memory usage percentage (0-100)."""
        return self._get_cached(
            "memory_percent",
            lambda: psutil.virtual_memory().percent
        )

    def get_memory_used_gb(self) -> float:
        """Get used memory in GB."""
        return self._get_cached(
            "memory_used_gb",
            lambda: psutil.virtual_memory().used / (1024 ** 3)
        )

    def get_memory_total_gb(self) -> float:
        """Get total memory in GB."""
        return self._get_cached(
            "memory_total_gb",
            lambda: psutil.virtual_memory().total / (1024 ** 3)
        )

    def get_memory_available_gb(self) -> float:
        """Get available memory in GB."""
        return self._get_cached(
            "memory_available_gb",
            lambda: psutil.virtual_memory().available / (1024 ** 3)
        )

    # =========================================================================
    # Disk Metrics
    # =========================================================================

    def get_disk_percent(self) -> float:
        """Get disk usage percentage (0-100)."""
        return self._get_cached(
            "disk_percent",
            lambda: psutil.disk_usage(self._disk_path).percent
        )

    def get_disk_used_gb(self) -> float:
        """Get used disk space in GB."""
        return self._get_cached(
            "disk_used_gb",
            lambda: psutil.disk_usage(self._disk_path).used / (1024 ** 3)
        )

    def get_disk_total_gb(self) -> float:
        """Get total disk space in GB."""
        return self._get_cached(
            "disk_total_gb",
            lambda: psutil.disk_usage(self._disk_path).total / (1024 ** 3)
        )

    def get_disk_free_gb(self) -> float:
        """Get free disk space in GB."""
        return self._get_cached(
            "disk_free_gb",
            lambda: psutil.disk_usage(self._disk_path).free / (1024 ** 3)
        )

    # =========================================================================
    # Network Metrics
    # =========================================================================

    def get_network_bytes_sent_mb(self) -> float:
        """Get total bytes sent since boot in MB."""
        return self._get_cached(
            "network_bytes_sent_mb",
            lambda: psutil.net_io_counters().bytes_sent / (1024 ** 2)
        )

    def get_network_bytes_recv_mb(self) -> float:
        """Get total bytes received since boot in MB."""
        return self._get_cached(
            "network_bytes_recv_mb",
            lambda: psutil.net_io_counters().bytes_recv / (1024 ** 2)
        )

    # =========================================================================
    # Process Metrics (this process)
    # =========================================================================

    def get_process_cpu_percent(self) -> float:
        """Get CPU usage of this process (0-100)."""
        return self._get_cached(
            "process_cpu_percent",
            lambda: psutil.Process().cpu_percent(interval=None)
        )

    def get_process_memory_mb(self) -> float:
        """Get memory usage of this process in MB."""
        return self._get_cached(
            "process_memory_mb",
            lambda: psutil.Process().memory_info().rss / (1024 ** 2)
        )

    def get_process_threads(self) -> float:
        """Get number of threads in this process."""
        return self._get_cached(
            "process_threads",
            lambda: float(psutil.Process().num_threads())
        )

    # =========================================================================
    # System Metrics
    # =========================================================================

    def get_uptime_hours(self) -> float:
        """Get system uptime in hours."""
        return self._get_cached(
            "uptime_hours",
            lambda: (time.time() - psutil.boot_time()) / 3600
        )

    def get_load_average_1m(self) -> float:
        """Get 1-minute load average.

        Note: Returns 0.0 on Windows.
        """
        def _get_load():
            try:
                return psutil.getloadavg()[0]
            except (AttributeError, OSError):
                # Windows doesn't support getloadavg
                return 0.0

        return self._get_cached("load_average_1m", _get_load)


# Singleton instance for easy access
_diagnostics_instance: Optional[SystemDiagnostics] = None


def get_system_diagnostics() -> SystemDiagnostics:
    """Get or create the singleton SystemDiagnostics instance."""
    global _diagnostics_instance
    if _diagnostics_instance is None:
        _diagnostics_instance = SystemDiagnostics()
    return _diagnostics_instance
