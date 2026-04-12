"""Core module for Reachy Mini HA Voice.

This module contains fundamental components:
- DaemonStateMonitor: Monitors robot daemon state
- SleepAwareService: Base class for services that support resource suspend/resume
- ServiceManager: Manages multiple suspend-aware services
- Config: Centralized configuration management
- Exceptions: Custom exception classes
- HealthMonitor: Service health monitoring
- MemoryMonitor: Memory usage monitoring
- RobotStateMonitor: Robot connection state tracking
- SystemDiagnostics: System diagnostics utilities
- Util: Common utility functions
"""

from .config import Config
from .daemon_monitor import DaemonState, DaemonStateMonitor, DaemonStatus
from .exceptions import (
    ConfigurationError,
    DaemonUnavailableError,
    EntityRegistrationError,
    ModelLoadError,
    ReachyHAError,
    ResourceUnavailableError,
    RobotConnectionError,
    ServiceSuspendedError,
)
from .health_monitor import (
    HealthChecker,
    HealthMonitor,
    HealthStatus,
    ServiceHealth,
    get_health_monitor,
)
from .memory_monitor import (
    MemoryMonitor,
    MemoryStats,
    get_memory_monitor,
)
from .robot_state_monitor import RobotStateMonitor
from .service_base import RobustOperationMixin, ServiceManager, ServiceState, SleepAwareService
from .system_diagnostics import get_system_diagnostics
from .util import call_all, get_mac

__all__ = [
    "Config",
    "ConfigurationError",
    "DaemonState",
    "DaemonStateMonitor",
    "DaemonStatus",
    "DaemonUnavailableError",
    "EntityRegistrationError",
    "HealthChecker",
    "HealthMonitor",
    # Health monitoring
    "HealthStatus",
    "MemoryMonitor",
    # Memory monitoring
    "MemoryStats",
    "ModelLoadError",
    # Exceptions
    "ReachyHAError",
    "ResourceUnavailableError",
    "RobotConnectionError",
    # Robot state
    "RobotStateMonitor",
    "RobustOperationMixin",
    "ServiceHealth",
    "ServiceManager",
    "ServiceState",
    "ServiceSuspendedError",
    "SleepAwareService",
    "call_all",
    "get_health_monitor",
    # Utilities
    "get_mac",
    "get_memory_monitor",
    # System diagnostics
    "get_system_diagnostics",
]
