"""Core module for Reachy Mini HA Voice.

This module contains fundamental components:
- DaemonStateMonitor: Monitors robot daemon state including sleep detection
- SleepAwareService: Base class for services that respond to sleep/wake
- ServiceManager: Manages multiple SleepAwareService instances
- SleepManager: Coordinates sleep/wake behavior across the application
- Config: Centralized configuration management
- Exceptions: Custom exception classes
- HealthMonitor: Service health monitoring
- MemoryMonitor: Memory usage monitoring
"""

from .daemon_monitor import DaemonState, DaemonStateMonitor, DaemonStatus
from .service_base import SleepAwareService, ServiceManager, ServiceState, RobustOperationMixin
from .sleep_manager import SleepManager
from .config import Config
from .exceptions import (
    ReachyHAError,
    RobotConnectionError,
    DaemonUnavailableError,
    ServiceSuspendedError,
    ResourceUnavailableError,
    ModelLoadError,
    ConfigurationError,
    EntityRegistrationError,
)
from .health_monitor import (
    HealthStatus,
    ServiceHealth,
    HealthChecker,
    HealthMonitor,
    get_health_monitor,
)
from .memory_monitor import (
    MemoryStats,
    MemoryMonitor,
    get_memory_monitor,
)

__all__ = [
    "DaemonState",
    "DaemonStateMonitor",
    "DaemonStatus",
    "SleepAwareService",
    "ServiceManager",
    "ServiceState",
    "RobustOperationMixin",
    "SleepManager",
    "Config",
    # Exceptions
    "ReachyHAError",
    "RobotConnectionError",
    "DaemonUnavailableError",
    "ServiceSuspendedError",
    "ResourceUnavailableError",
    "ModelLoadError",
    "ConfigurationError",
    "EntityRegistrationError",
    # Health monitoring
    "HealthStatus",
    "ServiceHealth",
    "HealthChecker",
    "HealthMonitor",
    "get_health_monitor",
    # Memory monitoring
    "MemoryStats",
    "MemoryMonitor",
    "get_memory_monitor",
]
