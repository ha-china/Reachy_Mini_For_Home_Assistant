"""Core module for Reachy Mini HA Voice.

This module contains fundamental components:
- SleepAwareService: Base class for services that support resource suspend/resume
- ServiceManager: Manages multiple suspend-aware services
- Config: Centralized configuration management
- Exceptions: Custom exception classes
- SystemDiagnostics: System diagnostics utilities
- Util: Common utility functions
"""

from .config import Config
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
from .service_base import RobustOperationMixin, ServiceManager, ServiceState, SleepAwareService
from .system_diagnostics import get_system_diagnostics
from .util import call_all, get_mac

__all__ = [
    "Config",
    "ConfigurationError",
    "DaemonUnavailableError",
    "EntityRegistrationError",
    "ModelLoadError",
    # Exceptions
    "ReachyHAError",
    "ResourceUnavailableError",
    "RobotConnectionError",
    "RobustOperationMixin",
    "ServiceManager",
    "ServiceState",
    "ServiceSuspendedError",
    "SleepAwareService",
    "call_all",
    # Utilities
    "get_mac",
    # System diagnostics
    "get_system_diagnostics",
]
