"""Custom exceptions for Reachy Mini HA Voice.

This module defines application-specific exceptions for better
error handling and debugging.
"""


class ReachyHAError(Exception):
    """Base exception for Reachy HA Voice errors."""
    pass


class RobotConnectionError(ReachyHAError):
    """Error connecting to or communicating with the robot."""

    def __init__(self, message: str = "Robot connection failed", cause: Exception = None):
        super().__init__(message)
        self.cause = cause


class DaemonUnavailableError(ReachyHAError):
    """The Reachy Mini daemon is not available."""

    def __init__(self, message: str = "Daemon unavailable"):
        super().__init__(message)


class ServiceSuspendedError(ReachyHAError):
    """Operation attempted while service is suspended for sleep."""

    def __init__(self, service_name: str):
        super().__init__(f"Service '{service_name}' is suspended")
        self.service_name = service_name


class ResourceUnavailableError(ReachyHAError):
    """A required resource is not available."""

    def __init__(self, resource_name: str, reason: str = None):
        message = f"Resource '{resource_name}' unavailable"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.resource_name = resource_name
        self.reason = reason


class ModelLoadError(ReachyHAError):
    """Error loading an ML model."""

    def __init__(self, model_name: str, cause: Exception = None):
        super().__init__(f"Failed to load model: {model_name}")
        self.model_name = model_name
        self.cause = cause


class ConfigurationError(ReachyHAError):
    """Configuration error."""

    def __init__(self, message: str, key: str = None):
        super().__init__(message)
        self.key = key


class EntityRegistrationError(ReachyHAError):
    """Error registering an ESPHome entity."""

    def __init__(self, entity_name: str, cause: Exception = None):
        super().__init__(f"Failed to register entity: {entity_name}")
        self.entity_name = entity_name
        self.cause = cause
