"""Base classes for sleep-aware services.

This module provides the SleepAwareService abstract base class that all
services responding to sleep/wake events should implement.

The sleep-aware lifecycle:
1. Service starts in active state
2. When robot sleeps: suspend() is called -> release resources
3. When robot wakes: resume() is called -> restore resources
4. Service can be stopped completely via stop()
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar("T")


class RobustOperationMixin:
    """Mixin that adds automatic error tracking and recovery to services.

    This mixin provides a pattern for executing operations with automatic
    error counting, timeout-based error rate reset, and optional restart
    triggers when error thresholds are exceeded.

    Usage:
        class MyService(RobustOperationMixin):
            def __init__(self):
                super().__init__()
                self._init_error_tracking()

            def do_something(self):
                def operation():
                    # Actual work here
                    pass
                return self._execute_with_recovery(operation)
    """

    # Default configuration (can be overridden per-service)
    _max_consecutive_errors: int = 5
    _error_reset_interval: float = 60.0  # seconds
    _restart_on_max_errors: bool = False

    def _init_error_tracking(
        self,
        max_errors: int = 5,
        reset_interval: float = 60.0,
        restart_on_max_errors: bool = False,
    ) -> None:
        """Initialize error tracking with custom configuration.

        Args:
            max_errors: Maximum consecutive errors before triggering action
            reset_interval: Time in seconds before error count resets
            restart_on_max_errors: Whether to trigger restart on max errors
        """
        self._error_count = 0
        self._last_error_time = 0.0
        self._max_consecutive_errors = max_errors
        self._error_reset_interval = reset_interval
        self._restart_on_max_errors = restart_on_max_errors
        self._restart_callback: Callable | None = None
        self._error_logger = logging.getLogger(f"{__name__}.robust")

    def set_restart_callback(self, callback: Callable) -> None:
        """Set a callback to be called when max errors is reached.

        Args:
            callback: Function to call for service restart/recovery
        """
        self._restart_callback = callback

    def _handle_error(self, error: Exception) -> bool:
        """Track an error and determine if action is needed.

        Args:
            error: The exception that occurred

        Returns:
            True if max errors reached and action should be taken
        """
        now = time.monotonic()

        # Reset error count if enough time has passed since last error
        if now - self._last_error_time > self._error_reset_interval:
            self._error_count = 0

        self._error_count += 1
        self._last_error_time = now

        # Log with frequency limiting
        if self._error_count <= 3 or self._error_count == self._max_consecutive_errors:
            self._error_logger.error(
                "Service error (%d/%d): %s",
                self._error_count,
                self._max_consecutive_errors,
                error,
            )

        return self._error_count >= self._max_consecutive_errors

    def _reset_error_count(self) -> None:
        """Reset the error counter after successful operation."""
        self._error_count = min(self._error_count, 0)

    def _execute_with_recovery(
        self,
        operation: Callable[[], T],
        *args,
        suppress_errors: bool = False,
        default_return: T = None,
        **kwargs,
    ) -> T:
        """Execute an operation with automatic error tracking.

        Args:
            operation: The function to execute
            *args: Arguments to pass to operation
            suppress_errors: If True, return default_return instead of raising
            default_return: Value to return on error if suppress_errors=True
            **kwargs: Keyword arguments to pass to operation

        Returns:
            The operation result, or default_return on suppressed error

        Raises:
            The original exception if not suppressed
        """
        try:
            result = operation(*args, **kwargs)
            self._reset_error_count()
            return result
        except Exception as e:
            should_restart = self._handle_error(e)

            if should_restart and self._restart_on_max_errors:
                if self._restart_callback is not None:
                    self._error_logger.warning("Max errors reached - triggering restart")
                    try:
                        self._restart_callback()
                    except Exception as restart_error:
                        self._error_logger.error("Restart failed: %s", restart_error)

            if suppress_errors:
                return default_return
            raise

    async def _execute_async_with_recovery(
        self,
        operation: Callable[..., Any],
        *args,
        suppress_errors: bool = False,
        default_return: T = None,
        **kwargs,
    ) -> T:
        """Async version of _execute_with_recovery.

        Args:
            operation: The async function to execute
            *args: Arguments to pass to operation
            suppress_errors: If True, return default_return instead of raising
            default_return: Value to return on error if suppress_errors=True
            **kwargs: Keyword arguments to pass to operation

        Returns:
            The operation result, or default_return on suppressed error

        Raises:
            The original exception if not suppressed
        """
        try:
            result = await operation(*args, **kwargs)
            self._reset_error_count()
            return result
        except Exception as e:
            should_restart = self._handle_error(e)

            if should_restart and self._restart_on_max_errors:
                if self._restart_callback is not None:
                    self._error_logger.warning("Max errors reached - triggering restart")
                    try:
                        if asyncio.iscoroutinefunction(self._restart_callback):
                            await self._restart_callback()
                        else:
                            self._restart_callback()
                    except Exception as restart_error:
                        self._error_logger.error("Restart failed: %s", restart_error)

            if suppress_errors:
                return default_return
            raise


class ServiceState(Enum):
    """Represents the state of a sleep-aware service."""

    STOPPED = "stopped"  # Service not started
    STARTING = "starting"  # Service is starting up
    ACTIVE = "active"  # Service is fully operational
    SUSPENDING = "suspending"  # Service is being suspended (sleep)
    SUSPENDED = "suspended"  # Service is suspended (sleeping)
    RESUMING = "resuming"  # Service is resuming from sleep
    STOPPING = "stopping"  # Service is shutting down
    ERROR = "error"  # Service encountered an error


class SleepAwareService(ABC):
    """Abstract base class for services that respond to sleep/wake events.

    Services implementing this interface will have their resources managed
    during robot sleep/wake cycles. When the robot goes to sleep, suspend()
    is called to release resources. When it wakes, resume() restores them.

    Example:
        class CameraService(SleepAwareService):
            @property
            def service_name(self) -> str:
                return "camera"

            async def _do_start(self) -> None:
                self._init_camera()
                self._start_streaming()

            async def _do_suspend(self) -> None:
                self._stop_streaming()
                self._release_camera()

            async def _do_resume(self) -> None:
                self._init_camera()
                self._start_streaming()

            async def _do_stop(self) -> None:
                self._stop_streaming()
                self._release_camera()
    """

    def __init__(self):
        """Initialize the service."""
        self._state = ServiceState.STOPPED
        self._state_lock = asyncio.Lock()
        self._logger = logging.getLogger(f"{__name__}.{self.service_name}")

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of this service for logging and identification."""
        pass

    @property
    def state(self) -> ServiceState:
        """Get the current service state."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Check if the service is currently active."""
        return self._state == ServiceState.ACTIVE

    @property
    def is_suspended(self) -> bool:
        """Check if the service is currently suspended."""
        return self._state == ServiceState.SUSPENDED

    @property
    def is_running(self) -> bool:
        """Check if the service is running (active or suspended)."""
        return self._state in (
            ServiceState.ACTIVE,
            ServiceState.SUSPENDED,
            ServiceState.SUSPENDING,
            ServiceState.RESUMING,
        )

    async def start(self) -> None:
        """Start the service.

        This initializes and activates the service. Should only be called
        when the service is in STOPPED state.
        """
        async with self._state_lock:
            if self._state != ServiceState.STOPPED:
                self._logger.warning(f"Cannot start service in state {self._state.value}")
                return

            self._state = ServiceState.STARTING
            self._logger.info(f"Starting {self.service_name}...")

        try:
            await self._do_start()
            async with self._state_lock:
                self._state = ServiceState.ACTIVE
            self._logger.info(f"{self.service_name} started successfully")
        except Exception as e:
            async with self._state_lock:
                self._state = ServiceState.ERROR
            self._logger.error(f"Failed to start {self.service_name}: {e}")
            raise

    async def stop(self) -> None:
        """Stop the service completely.

        This releases all resources and stops the service. Can be called
        from any running state.
        """
        async with self._state_lock:
            if self._state == ServiceState.STOPPED:
                return
            if self._state == ServiceState.STOPPING:
                self._logger.debug("Service already stopping")
                return

            self._state = ServiceState.STOPPING
            self._logger.info(f"Stopping {self.service_name}...")

        try:
            await self._do_stop()
            async with self._state_lock:
                self._state = ServiceState.STOPPED
            self._logger.info(f"{self.service_name} stopped successfully")
        except Exception as e:
            async with self._state_lock:
                self._state = ServiceState.ERROR
            self._logger.error(f"Error stopping {self.service_name}: {e}")
            raise

    async def suspend(self) -> None:
        """Suspend the service (for robot sleep).

        This releases resources while keeping the service in a resumable state.
        Should only be called when the service is ACTIVE.
        """
        async with self._state_lock:
            if self._state != ServiceState.ACTIVE:
                self._logger.warning(f"Cannot suspend service in state {self._state.value}")
                return

            self._state = ServiceState.SUSPENDING
            self._logger.info(f"Suspending {self.service_name}...")

        try:
            await self._do_suspend()
            async with self._state_lock:
                self._state = ServiceState.SUSPENDED
            self._logger.info(f"{self.service_name} suspended")
        except Exception as e:
            async with self._state_lock:
                self._state = ServiceState.ERROR
            self._logger.error(f"Error suspending {self.service_name}: {e}")
            raise

    async def resume(self) -> None:
        """Resume the service (after robot wake).

        This restores resources and re-activates the service.
        Should only be called when the service is SUSPENDED.
        """
        async with self._state_lock:
            if self._state != ServiceState.SUSPENDED:
                self._logger.warning(f"Cannot resume service in state {self._state.value}")
                return

            self._state = ServiceState.RESUMING
            self._logger.info(f"Resuming {self.service_name}...")

        try:
            await self._do_resume()
            async with self._state_lock:
                self._state = ServiceState.ACTIVE
            self._logger.info(f"{self.service_name} resumed")
        except Exception as e:
            async with self._state_lock:
                self._state = ServiceState.ERROR
            self._logger.error(f"Error resuming {self.service_name}: {e}")
            raise

    @abstractmethod
    async def _do_start(self) -> None:
        """Implementation-specific start logic.

        Subclasses should implement this to initialize and start their
        resources.
        """
        pass

    @abstractmethod
    async def _do_stop(self) -> None:
        """Implementation-specific stop logic.

        Subclasses should implement this to release all resources and
        stop any background tasks.
        """
        pass

    @abstractmethod
    async def _do_suspend(self) -> None:
        """Implementation-specific suspend logic.

        Subclasses should implement this to release resources that are
        not needed during sleep, while keeping the service in a resumable
        state.

        Typical actions:
        - Stop background threads
        - Release ML models from memory
        - Close network connections
        - Stop timers
        """
        pass

    @abstractmethod
    async def _do_resume(self) -> None:
        """Implementation-specific resume logic.

        Subclasses should implement this to restore resources and
        re-activate the service after sleep.

        Typical actions:
        - Restart background threads
        - Reload ML models
        - Re-establish network connections
        - Restart timers
        """
        pass

    async def __aenter__(self) -> "SleepAwareService":
        """Context manager entry - starts the service."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit - stops the service."""
        await self.stop()
        return False


class ServiceManager:
    """Manages multiple SleepAwareService instances.

    Provides coordinated suspend/resume for all registered services,
    ensuring proper ordering and error handling.

    Usage:
        manager = ServiceManager()
        manager.register(camera_service)
        manager.register(motion_service)

        # Suspend all services
        await manager.suspend_all()

        # Resume all services after delay
        await asyncio.sleep(30)
        await manager.resume_all()
    """

    def __init__(self, resume_delay: float = 30.0):
        """Initialize the service manager.

        Args:
            resume_delay: Delay in seconds before resuming services after wake
        """
        self._services: list[SleepAwareService] = []
        self._resume_delay = resume_delay
        self._is_suspended = False
        self._logger = logging.getLogger(__name__)

    def register(self, service: SleepAwareService) -> None:
        """Register a service to be managed."""
        if service not in self._services:
            self._services.append(service)
            self._logger.debug(f"Registered service: {service.service_name}")

    def unregister(self, service: SleepAwareService) -> None:
        """Unregister a service."""
        if service in self._services:
            self._services.remove(service)
            self._logger.debug(f"Unregistered service: {service.service_name}")

    @property
    def is_suspended(self) -> bool:
        """Check if all services are suspended."""
        return self._is_suspended

    async def start_all(self) -> None:
        """Start all registered services."""
        self._logger.info(f"Starting {len(self._services)} services...")
        for service in self._services:
            try:
                await service.start()
            except Exception as e:
                self._logger.error(f"Failed to start {service.service_name}: {e}")

    async def stop_all(self) -> None:
        """Stop all registered services."""
        self._logger.info(f"Stopping {len(self._services)} services...")
        # Stop in reverse order (LIFO)
        for service in reversed(self._services):
            try:
                await service.stop()
            except Exception as e:
                self._logger.error(f"Failed to stop {service.service_name}: {e}")

    async def suspend_all(self) -> None:
        """Suspend all active services."""
        if self._is_suspended:
            self._logger.debug("Services already suspended")
            return

        self._logger.info("Suspending all services for sleep...")
        for service in self._services:
            if service.is_active:
                try:
                    await service.suspend()
                except Exception as e:
                    self._logger.error(f"Failed to suspend {service.service_name}: {e}")

        self._is_suspended = True
        self._logger.info("All services suspended")

    async def resume_all(self, delay: float | None = None) -> None:
        """Resume all suspended services.

        Args:
            delay: Optional override for resume delay. If None, uses default.
        """
        if not self._is_suspended:
            self._logger.debug("Services not suspended")
            return

        actual_delay = delay if delay is not None else self._resume_delay
        if actual_delay > 0:
            self._logger.info(f"Waiting {actual_delay}s before resuming services...")
            await asyncio.sleep(actual_delay)

        self._logger.info("Resuming all services after wake...")
        for service in self._services:
            if service.is_suspended:
                try:
                    await service.resume()
                except Exception as e:
                    self._logger.error(f"Failed to resume {service.service_name}: {e}")

        self._is_suspended = False
        self._logger.info("All services resumed")
