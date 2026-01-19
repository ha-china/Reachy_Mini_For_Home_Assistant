"""Sleep Manager for Reachy Mini HA Voice.

This module coordinates sleep/wake behavior across all services.
It combines daemon state monitoring with service lifecycle management.

Architecture:
    DaemonStateMonitor --> SleepManager --> ServiceManager
           │                    │                 │
           │                    │                 └─> [CameraService]
           │                    │                 └─> [MotionService]
           │                    │                 └─> [AudioService]
           │                    │
           └── on_sleep ────────┼──> suspend_all_services()
           └── on_wake ─────────┼──> wait(30s) + resume_all_services()

The ESPHome server and EntityRegistry are NOT managed by ServiceManager
because they must remain active during sleep for the Wake Up button.
"""

import asyncio
import logging
from typing import Callable, List, Optional

from .daemon_monitor import DaemonState, DaemonStateMonitor
from .service_base import ServiceManager, SleepAwareService

logger = logging.getLogger(__name__)


class SleepManager:
    """Coordinates sleep/wake behavior across the application.

    This class:
    1. Monitors daemon state for sleep/wake transitions
    2. Suspends all registered services when robot sleeps
    3. Resumes services after a configurable delay when robot wakes
    4. Keeps ESPHome server running for Home Assistant control

    Usage:
        sleep_manager = SleepManager(resume_delay=30.0)

        # Register services
        sleep_manager.register_service(camera_service)
        sleep_manager.register_service(motion_service)

        # Start monitoring
        await sleep_manager.start()

        # Later...
        await sleep_manager.stop()
    """

    def __init__(
        self,
        daemon_url: str = "http://127.0.0.1:8000",
        check_interval: float = 2.0,
        resume_delay: float = 30.0,
    ):
        """Initialize the sleep manager.

        Args:
            daemon_url: URL of the Reachy Mini daemon HTTP API
            check_interval: How often to poll daemon status (seconds)
            resume_delay: Delay before resuming services after wake (seconds)
        """
        self._daemon_monitor = DaemonStateMonitor(
            daemon_url=daemon_url,
            check_interval=check_interval,
        )
        self._service_manager = ServiceManager(resume_delay=resume_delay)
        self._resume_delay = resume_delay

        # State
        self._is_sleeping = False
        self._resume_task: Optional[asyncio.Task] = None
        self._running = False

        # Additional callbacks for custom handling
        self._on_sleep_callbacks: List[Callable[[], None]] = []
        self._on_wake_callbacks: List[Callable[[], None]] = []
        self._on_pre_resume_callbacks: List[Callable[[], None]] = []

        # Register daemon monitor callbacks
        self._daemon_monitor.on_sleep(self._handle_sleep)
        self._daemon_monitor.on_wake(self._handle_wake)

    @property
    def is_sleeping(self) -> bool:
        """Check if the system is currently in sleep mode."""
        return self._is_sleeping

    @property
    def daemon_state(self) -> DaemonState:
        """Get the current daemon state."""
        return self._daemon_monitor.current_state

    def register_service(self, service: SleepAwareService) -> None:
        """Register a service to be managed during sleep/wake cycles.

        Args:
            service: A SleepAwareService instance
        """
        self._service_manager.register(service)
        logger.debug(f"Registered service: {service.service_name}")

    def unregister_service(self, service: SleepAwareService) -> None:
        """Unregister a service from sleep/wake management."""
        self._service_manager.unregister(service)

    def on_sleep(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the system enters sleep mode.

        This is called BEFORE services are suspended.
        """
        self._on_sleep_callbacks.append(callback)

    def on_wake(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the system wakes up.

        This is called BEFORE the resume delay.
        """
        self._on_wake_callbacks.append(callback)

    def on_pre_resume(self, callback: Callable[[], None]) -> None:
        """Register a callback for just before services resume.

        This is called AFTER the resume delay but BEFORE services resume.
        Useful for re-initializing robot connection.
        """
        self._on_pre_resume_callbacks.append(callback)

    async def start(self) -> None:
        """Start the sleep manager and begin monitoring daemon state."""
        if self._running:
            logger.warning("SleepManager already running")
            return

        self._running = True
        await self._daemon_monitor.start()
        logger.info("SleepManager started")

    async def stop(self) -> None:
        """Stop the sleep manager and clean up."""
        if not self._running:
            return

        self._running = False

        # Cancel any pending resume task
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()
            try:
                await self._resume_task
            except asyncio.CancelledError:
                pass

        await self._daemon_monitor.stop()
        logger.info("SleepManager stopped")

    async def force_suspend(self) -> None:
        """Force all services to suspend immediately.

        This can be called manually to enter sleep mode without
        waiting for daemon state change.
        """
        if self._is_sleeping:
            return

        logger.info("Forcing system to sleep mode")
        self._is_sleeping = True
        await self._suspend_services()

    async def force_resume(self, delay: Optional[float] = None) -> None:
        """Force all services to resume.

        Args:
            delay: Optional override for resume delay
        """
        if not self._is_sleeping:
            return

        logger.info("Forcing system to resume")
        actual_delay = delay if delay is not None else self._resume_delay

        if actual_delay > 0:
            logger.info(f"Waiting {actual_delay}s before resuming...")
            await asyncio.sleep(actual_delay)

        await self._resume_services()
        self._is_sleeping = False

    def _handle_sleep(self) -> None:
        """Handle sleep event from daemon monitor."""
        if self._is_sleeping:
            return

        logger.info("Robot entering sleep mode")
        self._is_sleeping = True

        # Cancel any pending resume
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()

        # Run sleep handling in the event loop
        asyncio.create_task(self._on_sleep_async())

    def _handle_wake(self) -> None:
        """Handle wake event from daemon monitor."""
        if not self._is_sleeping:
            return

        logger.info("Robot waking up")

        # Schedule delayed resume
        self._resume_task = asyncio.create_task(self._on_wake_async())

    async def _on_sleep_async(self) -> None:
        """Async handler for sleep event."""
        # Call custom sleep callbacks
        for callback in self._on_sleep_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in sleep callback: {e}")

        # Suspend all services
        await self._suspend_services()

    async def _on_wake_async(self) -> None:
        """Async handler for wake event with delay."""
        # Call custom wake callbacks
        for callback in self._on_wake_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in wake callback: {e}")

        # Wait for resume delay
        if self._resume_delay > 0:
            logger.info(f"Waiting {self._resume_delay}s before resuming services...")
            try:
                await asyncio.sleep(self._resume_delay)
            except asyncio.CancelledError:
                logger.debug("Resume cancelled (likely re-entering sleep)")
                return

        # Call pre-resume callbacks
        for callback in self._on_pre_resume_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in pre-resume callback: {e}")

        # Resume all services
        await self._resume_services()
        self._is_sleeping = False

    async def _suspend_services(self) -> None:
        """Suspend all managed services."""
        logger.info("Suspending all services for sleep...")
        await self._service_manager.suspend_all()
        logger.info("All services suspended - system in low-power mode")

    async def _resume_services(self) -> None:
        """Resume all managed services."""
        logger.info("Resuming all services after wake...")
        # Use delay=0 since we already waited
        await self._service_manager.resume_all(delay=0)
        logger.info("All services resumed - system fully operational")
