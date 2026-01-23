"""Robot State Monitor for Reachy Mini.

This module provides a centralized state monitor that tracks the robot's
connection status and daemon availability. When the robot enters sleep mode
or the daemon becomes unavailable, all dependent services are notified to
pause their operations gracefully.

Key features:
- Monitors robot connection via SDK's is_alive status
- Provides callbacks for state changes
- Thread-safe state access
- Supports service pause/resume lifecycle
"""

import logging
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)


class RobotConnectionState(Enum):
    """Robot connection states."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class RobotStateMonitor:
    """Monitors robot connection state and notifies services.

    This class runs a background thread that periodically checks the robot's
    connection status. When the state changes, registered callbacks are invoked
    to allow services to pause or resume their operations.

    Usage:
        monitor = RobotStateMonitor(reachy_mini)
        monitor.on_disconnected(lambda: print("Robot disconnected"))
        monitor.on_connected(lambda: print("Robot reconnected"))
        monitor.start()
    """

    def __init__(
        self,
        reachy_mini: Optional["ReachyMini"] = None,
        check_interval: float = 1.0,
        sleep_interval: float | None = None,
        error_interval: float | None = None,
    ):
        """Initialize the robot state monitor.

        Args:
            reachy_mini: ReachyMini instance to monitor. If None, monitor
                will report as always disconnected.
            check_interval: How often to check connection state (seconds).
            sleep_interval: Polling interval when daemon is sleeping.
            error_interval: Polling interval when daemon is unavailable.
        """
        self._robot = reachy_mini
        self._check_interval_active = check_interval
        self._check_interval_sleep = sleep_interval or check_interval
        self._check_interval_error = error_interval or check_interval
        self._current_interval = check_interval
        self._sleeping = False
        self._daemon_unavailable = False
        logger.debug(
            "Robot state monitor configured: active=%.2fs sleep=%.2fs error=%.2fs",
            self._check_interval_active,
            self._check_interval_sleep,
            self._check_interval_error,
        )

        # Current state
        self._state = RobotConnectionState.UNKNOWN
        self._state_lock = threading.Lock()

        # Callbacks
        self._on_connected_callbacks: list[Callable[[], None]] = []
        self._on_disconnected_callbacks: list[Callable[[], None]] = []
        self._callbacks_lock = threading.Lock()

        # Thread control
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()  # Event-driven connection waiting
        self._thread: threading.Thread | None = None

        # State tracking
        self._last_state_change_time = 0.0
        self._reconnect_count = 0

    @property
    def state(self) -> RobotConnectionState:
        """Get current robot connection state (thread-safe)."""
        with self._state_lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        """Check if robot is currently connected."""
        return self.state == RobotConnectionState.CONNECTED

    def on_connected(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when robot connects.

        Args:
            callback: Function to call when robot becomes connected.
        """
        with self._callbacks_lock:
            self._on_connected_callbacks.append(callback)

    def on_disconnected(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when robot disconnects.

        Args:
            callback: Function to call when robot becomes disconnected.
        """
        with self._callbacks_lock:
            self._on_disconnected_callbacks.append(callback)

    def set_sleeping(self, sleeping: bool) -> None:
        """Update monitor sleep state to adjust polling interval."""
        self._sleeping = sleeping
        self._update_interval()

    def set_daemon_unavailable(self, unavailable: bool) -> None:
        """Update daemon availability to adjust polling interval."""
        self._daemon_unavailable = unavailable
        self._update_interval()

    def _update_interval(self) -> None:
        """Recompute polling interval based on current flags."""
        if self._daemon_unavailable:
            self._current_interval = self._check_interval_error
        elif self._sleeping:
            self._current_interval = self._check_interval_sleep
        else:
            self._current_interval = self._check_interval_active
        logger.debug("Robot state polling interval set to %.2fs", self._current_interval)

    def start(self) -> None:
        """Start the state monitoring thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Robot state monitor already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="RobotStateMonitor",
        )
        self._thread.start()
        logger.info("Robot state monitor started (check interval: %.1fs)",
                    self._current_interval)

    def stop(self) -> None:
        """Stop the state monitoring thread."""
        if self._thread is None or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("Robot state monitor thread did not stop in time")
        else:
            logger.info("Robot state monitor stopped")

    def _check_robot_state(self) -> RobotConnectionState:
        """Check the current robot connection state.

        Returns:
            Current connection state based on SDK status.
        """
        if self._robot is None:
            return RobotConnectionState.DISCONNECTED

        if self._sleeping:
            return self._state

        try:
            # Check the SDK's internal _is_alive flag
            # This is set by the background check_alive thread in ZenohClient
            client = getattr(self._robot, 'client', None)
            if client is None:
                return RobotConnectionState.DISCONNECTED

            is_alive = getattr(client, '_is_alive', False)
            if not is_alive:
                return RobotConnectionState.DISCONNECTED

            # Also check if we can access the media system
            # During sleep mode, the client may report alive but media is unavailable
            try:
                media = getattr(self._robot, 'media', None)
                if media is not None:
                    audio = getattr(media, 'audio', None)
                    if audio is None:
                        return RobotConnectionState.DISCONNECTED
            except Exception:
                # If we can't access media, consider it disconnected
                return RobotConnectionState.DISCONNECTED

            return RobotConnectionState.CONNECTED

        except Exception as e:
            logger.debug("Error checking robot state: %s", e)
            return RobotConnectionState.DISCONNECTED

    def _set_state(self, new_state: RobotConnectionState) -> None:
        """Set state and invoke callbacks if changed.

        Args:
            new_state: The new connection state.
        """
        old_state = None
        with self._state_lock:
            if self._state == new_state:
                return
            old_state = self._state
            self._state = new_state
            self._last_state_change_time = time.monotonic()

        # Update connected event for event-driven waiting
        if new_state == RobotConnectionState.CONNECTED:
            self._connected_event.set()
        else:
            self._connected_event.clear()

        # State changed, invoke callbacks outside the lock
        if old_state == RobotConnectionState.CONNECTED and new_state == RobotConnectionState.DISCONNECTED:
            logger.warning("Robot connection lost - pausing services")
            self._invoke_disconnected_callbacks()
        elif new_state == RobotConnectionState.CONNECTED:
            if old_state == RobotConnectionState.DISCONNECTED:
                self._reconnect_count += 1
                logger.info("Robot connection restored (reconnect #%d) - resuming services",
                           self._reconnect_count)
            else:
                logger.info("Robot connected - starting services")
            self._invoke_connected_callbacks()

    def _invoke_connected_callbacks(self) -> None:
        """Invoke all registered connection callbacks."""
        with self._callbacks_lock:
            callbacks = self._on_connected_callbacks.copy()

        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("Error in connected callback: %s", e)

    def _invoke_disconnected_callbacks(self) -> None:
        """Invoke all registered disconnection callbacks."""
        with self._callbacks_lock:
            callbacks = self._on_disconnected_callbacks.copy()

        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("Error in disconnected callback: %s", e)

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.debug("Robot state monitor loop started")

        while not self._stop_event.is_set():
            try:
                # Check current state
                current_state = self._check_robot_state()
                self._set_state(current_state)

            except Exception as e:
                logger.error("Error in state monitor loop: %s", e)

            # Wait for next check or stop signal
            self._stop_event.wait(timeout=self._current_interval)

        logger.debug("Robot state monitor loop stopped")

    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for robot to become connected.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if connected within timeout, False otherwise.
        """
        # Use event-driven waiting instead of polling
        if self.is_connected:
            return True
        return self._connected_event.wait(timeout=timeout)
