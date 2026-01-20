"""Memory usage monitoring for Reachy Mini.

This module provides memory monitoring capabilities to detect
memory leaks and high memory usage conditions.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import psutil for detailed memory info
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.debug("psutil not available, using basic memory monitoring")


@dataclass
class MemoryStats:
    """Memory usage statistics."""

    # RSS (Resident Set Size) - actual physical memory used
    rss_bytes: int = 0
    rss_mb: float = 0.0

    # VMS (Virtual Memory Size) - total virtual memory
    vms_bytes: int = 0
    vms_mb: float = 0.0

    # Percentage of system memory
    percent: float = 0.0

    # System-wide stats (if available)
    system_total_mb: float = 0.0
    system_available_mb: float = 0.0
    system_percent: float = 0.0

    # Timestamp
    timestamp: float = 0.0


class MemoryMonitor:
    """Monitors memory usage of the current process.

    Usage:
        monitor = MemoryMonitor(
            warning_threshold_mb=500,
            critical_threshold_mb=800,
        )
        monitor.start()
        # ...
        stats = monitor.get_current_stats()
        if monitor.is_warning():
            logger.warning("High memory usage!")
    """

    def __init__(
        self,
        warning_threshold_mb: float = 500.0,
        critical_threshold_mb: float = 800.0,
        check_interval: float = 60.0,
        on_warning: Callable[[MemoryStats], None] | None = None,
        on_critical: Callable[[MemoryStats], None] | None = None,
    ):
        """Initialize memory monitor.

        Args:
            warning_threshold_mb: Warning threshold in MB
            critical_threshold_mb: Critical threshold in MB
            check_interval: Check interval in seconds
            on_warning: Callback when warning threshold exceeded
            on_critical: Callback when critical threshold exceeded
        """
        self._warning_threshold = warning_threshold_mb
        self._critical_threshold = critical_threshold_mb
        self._check_interval = check_interval
        self._on_warning = on_warning
        self._on_critical = on_critical

        self._current_stats = MemoryStats()
        self._history: list[MemoryStats] = []
        self._max_history = 60  # Keep last 60 samples

        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Process handle for psutil
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

    @property
    def current_stats(self) -> MemoryStats:
        """Get current memory stats."""
        with self._lock:
            return self._current_stats

    @property
    def history(self) -> list[MemoryStats]:
        """Get memory history."""
        with self._lock:
            return self._history.copy()

    def sample_now(self) -> MemoryStats:
        """Take a memory sample now."""
        stats = MemoryStats(timestamp=time.monotonic())

        if PSUTIL_AVAILABLE and self._process:
            try:
                # Process memory
                mem_info = self._process.memory_info()
                stats.rss_bytes = mem_info.rss
                stats.rss_mb = mem_info.rss / (1024 * 1024)
                stats.vms_bytes = mem_info.vms
                stats.vms_mb = mem_info.vms / (1024 * 1024)
                stats.percent = self._process.memory_percent()

                # System memory
                sys_mem = psutil.virtual_memory()
                stats.system_total_mb = sys_mem.total / (1024 * 1024)
                stats.system_available_mb = sys_mem.available / (1024 * 1024)
                stats.system_percent = sys_mem.percent

            except Exception as e:
                logger.debug("Error getting memory info: %s", e)
        else:
            # Fallback: try to read from /proc on Linux
            try:
                with open('/proc/self/statm') as f:
                    parts = f.read().split()
                    page_size = os.sysconf('SC_PAGE_SIZE')
                    stats.rss_bytes = int(parts[1]) * page_size
                    stats.rss_mb = stats.rss_bytes / (1024 * 1024)
                    stats.vms_bytes = int(parts[0]) * page_size
                    stats.vms_mb = stats.vms_bytes / (1024 * 1024)
            except Exception:
                pass  # Not on Linux or can't read

        with self._lock:
            self._current_stats = stats
            self._history.append(stats)
            if len(self._history) > self._max_history:
                self._history.pop(0)

        return stats

    def is_warning(self) -> bool:
        """Check if memory usage is at warning level."""
        return self._current_stats.rss_mb >= self._warning_threshold

    def is_critical(self) -> bool:
        """Check if memory usage is at critical level."""
        return self._current_stats.rss_mb >= self._critical_threshold

    def get_trend(self) -> float:
        """Get memory trend (MB per minute).

        Returns:
            Positive value = increasing, negative = decreasing
        """
        with self._lock:
            if len(self._history) < 2:
                return 0.0

            first = self._history[0]
            last = self._history[-1]

            time_diff = last.timestamp - first.timestamp
            if time_diff <= 0:
                return 0.0

            mem_diff = last.rss_mb - first.rss_mb
            # Convert to per-minute rate
            return (mem_diff / time_diff) * 60.0

    def start(self) -> None:
        """Start memory monitoring."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="memory-monitor",
        )
        self._thread.start()
        logger.info("Memory monitor started (warning: %.0f MB, critical: %.0f MB)",
                   self._warning_threshold, self._critical_threshold)

    def stop(self) -> None:
        """Stop memory monitoring."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Memory monitor stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        was_warning = False
        was_critical = False

        while self._running:
            stats = self.sample_now()

            # Check thresholds and trigger callbacks
            is_critical = self.is_critical()
            is_warning = self.is_warning()

            if is_critical and not was_critical:
                logger.warning("CRITICAL: Memory usage at %.1f MB (threshold: %.1f MB)",
                             stats.rss_mb, self._critical_threshold)
                if self._on_critical:
                    try:
                        self._on_critical(stats)
                    except Exception as e:
                        logger.error("Error in critical callback: %s", e)

            elif is_warning and not was_warning:
                logger.warning("WARNING: Memory usage at %.1f MB (threshold: %.1f MB)",
                             stats.rss_mb, self._warning_threshold)
                if self._on_warning:
                    try:
                        self._on_warning(stats)
                    except Exception as e:
                        logger.error("Error in warning callback: %s", e)

            was_critical = is_critical
            was_warning = is_warning

            # Log periodic status (every 10 samples when high)
            if is_warning and len(self._history) % 10 == 0:
                trend = self.get_trend()
                trend_str = f"+{trend:.1f}" if trend > 0 else f"{trend:.1f}"
                logger.info("Memory: %.1f MB (trend: %s MB/min, system: %.1f%%)",
                          stats.rss_mb, trend_str, stats.system_percent)

            # Wait for interval or stop
            if self._stop_event.wait(timeout=self._check_interval):
                break

    def get_summary(self) -> dict:
        """Get memory monitoring summary."""
        stats = self.current_stats
        return {
            "rss_mb": round(stats.rss_mb, 1),
            "vms_mb": round(stats.vms_mb, 1),
            "percent": round(stats.percent, 1),
            "system_percent": round(stats.system_percent, 1),
            "is_warning": self.is_warning(),
            "is_critical": self.is_critical(),
            "trend_mb_per_min": round(self.get_trend(), 2),
        }


# Global memory monitor instance
_memory_monitor: MemoryMonitor | None = None


def get_memory_monitor() -> MemoryMonitor:
    """Get or create global memory monitor."""
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor
