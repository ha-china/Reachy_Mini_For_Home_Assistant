"""Daemon State Monitor for Reachy Mini.

This module monitors the Reachy Mini daemon state via HTTP API,
providing callbacks for state transitions including sleep/wake detection.

The daemon exposes /api/daemon/status which returns DaemonStatus with states:
- not_initialized: Daemon not yet started
- starting: Daemon is starting up (waking)
- running: Daemon is fully operational
- stopping: Daemon is stopping (going to sleep)
- stopped: Daemon has stopped (sleeping)
- error: Daemon encountered an error
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class DaemonState(Enum):
    """Represents the state of the Reachy Mini daemon.

    Maps directly to the daemon's internal DaemonState enum.
    """
    NOT_INITIALIZED = "not_initialized"
    STARTING = "starting"  # Waking up
    RUNNING = "running"    # Fully operational
    STOPPING = "stopping"  # Going to sleep
    STOPPED = "stopped"    # Sleeping
    ERROR = "error"
    UNAVAILABLE = "unavailable"  # Cannot connect to daemon


@dataclass
class DaemonStatus:
    """Status information from the daemon API."""
    state: DaemonState
    robot_name: str = ""
    version: str | None = None
    error: str | None = None

    @property
    def is_sleeping(self) -> bool:
        """Check if robot is in sleep state."""
        return self.state in (DaemonState.STOPPED, DaemonState.STOPPING)

    @property
    def is_awake(self) -> bool:
        """Check if robot is fully awake and operational."""
        return self.state == DaemonState.RUNNING

    @property
    def is_waking(self) -> bool:
        """Check if robot is in the process of waking up."""
        return self.state == DaemonState.STARTING


class DaemonStateMonitor:
    """Monitors the Reachy Mini daemon state and provides callbacks for state changes.

    This monitor polls the daemon's HTTP API at regular intervals and triggers
    callbacks when the state changes. It's particularly useful for detecting
    sleep/wake transitions.

    Usage:
        monitor = DaemonStateMonitor()
        monitor.on_sleep(lambda: print("Robot going to sleep"))
        monitor.on_wake(lambda: print("Robot waking up"))
        await monitor.start()
    """

    DEFAULT_DAEMON_URL = "http://127.0.0.1:8000"
    DEFAULT_CHECK_INTERVAL = 2.0  # seconds
    DEFAULT_SLEEP_INTERVAL = 8.0  # seconds
    DEFAULT_ERROR_INTERVAL = 6.0  # seconds
    DEFAULT_MAX_BACKOFF = 15.0  # seconds
    DEFAULT_BACKOFF_MULTIPLIER = 1.5
    DEFAULT_BACKOFF_ERROR_THRESHOLD = 2

    def __init__(
        self,
        daemon_url: str = DEFAULT_DAEMON_URL,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        sleep_interval: float = DEFAULT_SLEEP_INTERVAL,
        error_interval: float = DEFAULT_ERROR_INTERVAL,
        max_backoff_interval: float = DEFAULT_MAX_BACKOFF,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        backoff_error_threshold: int = DEFAULT_BACKOFF_ERROR_THRESHOLD,
        connection_timeout: float = 5.0,
    ):
        """Initialize the daemon state monitor.

        Args:
            daemon_url: Base URL of the daemon HTTP API
            check_interval: How often to poll the daemon status (seconds)
            sleep_interval: Polling interval when daemon is sleeping
            error_interval: Base interval when daemon is unavailable
            max_backoff_interval: Upper bound for backoff interval
            backoff_multiplier: Multiplier for backoff growth
            backoff_error_threshold: Consecutive errors before backoff
            connection_timeout: HTTP timeout for daemon polling
        """
        self._daemon_url = daemon_url
        self._check_interval_active = check_interval
        self._check_interval_sleep = sleep_interval
        self._check_interval_error = error_interval
        self._max_backoff_interval = max_backoff_interval
        self._backoff_multiplier = backoff_multiplier
        self._backoff_error_threshold = backoff_error_threshold
        self._connection_timeout = connection_timeout
        self._current_interval = check_interval
        self._consecutive_errors = 0
        logger.debug(
            "Daemon monitor configured: active=%.2fs sleep=%.2fs error=%.2fs max_backoff=%.2fs timeout=%.2fs",
            self._check_interval_active,
            self._check_interval_sleep,
            self._check_interval_error,
            self._max_backoff_interval,
            self._connection_timeout,
        )

        # State tracking
        self._current_state = DaemonState.UNAVAILABLE
        self._last_status: DaemonStatus | None = None
        self._state_lock = threading.Lock()

        # Callbacks
        self._on_sleep_callbacks: list[Callable[[], None]] = []
        self._on_wake_callbacks: list[Callable[[], None]] = []
        self._on_state_change_callbacks: list[Callable[[DaemonState, DaemonState], None]] = []
        self._on_unavailable_callbacks: list[Callable[[], None]] = []

        # Control
        self._running = False
        self._stop_event = asyncio.Event()
        self._monitor_task: asyncio.Task | None = None

        # Session management
        self._session: aiohttp.ClientSession | None = None

    @property
    def current_state(self) -> DaemonState:
        """Get the current daemon state."""
        with self._state_lock:
            return self._current_state

    @property
    def last_status(self) -> DaemonStatus | None:
        """Get the last received daemon status."""
        with self._state_lock:
            return self._last_status

    @property
    def is_sleeping(self) -> bool:
        """Check if the robot is currently sleeping."""
        return self.current_state in (DaemonState.STOPPED, DaemonState.STOPPING)

    @property
    def is_awake(self) -> bool:
        """Check if the robot is fully awake."""
        return self.current_state == DaemonState.RUNNING

    def on_sleep(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the robot goes to sleep.

        The callback is triggered when state changes to STOPPING or STOPPED
        from a non-sleep state.
        """
        self._on_sleep_callbacks.append(callback)

    def on_wake(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the robot wakes up.

        The callback is triggered when state changes to RUNNING
        from a sleep or unavailable state.
        """
        self._on_wake_callbacks.append(callback)

    def on_state_change(self, callback: Callable[[DaemonState, DaemonState], None]) -> None:
        """Register a callback for any state change.

        Args:
            callback: Function that receives (old_state, new_state)
        """
        self._on_state_change_callbacks.append(callback)

    def on_unavailable(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the daemon becomes unavailable."""
        self._on_unavailable_callbacks.append(callback)

    async def start(self) -> None:
        """Start monitoring the daemon state."""
        if self._running:
            logger.warning("DaemonStateMonitor already running")
            return

        self._running = True
        self._stop_event.clear()

        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        self._current_interval = self._check_interval_active
        self._consecutive_errors = 0

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("DaemonStateMonitor started")

    async def stop(self) -> None:
        """Stop monitoring the daemon state."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        # Cancel and wait for monitor task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None

        logger.info("DaemonStateMonitor stopped")

    async def check_once(self) -> DaemonStatus:
        """Perform a single status check and return the result.

        This can be used for one-off checks without starting the monitor loop.
        """
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await self._fetch_status(session)
        return await self._fetch_status(self._session)

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that polls daemon status."""
        logger.debug("Daemon monitor loop started")

        while self._running and not self._stop_event.is_set():
            logger.debug(
                "Daemon poll interval: %.2fs (errors=%d)",
                self._current_interval,
                self._consecutive_errors,
            )
            try:
                status = await self._fetch_status(self._session)
                self._process_status(status)
                self._consecutive_errors = 0
                self._current_interval = self._interval_for_state(status.state)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daemon monitor loop: {e}")
                self._handle_unavailable()
                self._consecutive_errors += 1
                self._current_interval = self._interval_for_error()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._current_interval
                )
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue monitoring

        logger.debug("Daemon monitor loop ended")

    def _interval_for_state(self, state: DaemonState) -> float:
        """Choose polling interval based on daemon state."""
        if state in (DaemonState.STOPPED, DaemonState.STOPPING):
            return self._check_interval_sleep
        return self._check_interval_active

    def _interval_for_error(self) -> float:
        """Compute backoff interval for consecutive errors."""
        if self._consecutive_errors < self._backoff_error_threshold:
            return self._check_interval_error
        backoff = self._check_interval_error * (
            self._backoff_multiplier ** (self._consecutive_errors - self._backoff_error_threshold + 1)
        )
        return min(self._max_backoff_interval, backoff)

    async def _fetch_status(self, session: aiohttp.ClientSession) -> DaemonStatus:
        """Fetch the current daemon status from the API."""
        url = f"{self._daemon_url}/api/daemon/status"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    state_str = data.get("state", "unavailable")
                    try:
                        state = DaemonState(state_str)
                    except ValueError:
                        logger.warning(f"Unknown daemon state: {state_str}")
                        state = DaemonState.UNAVAILABLE

                    return DaemonStatus(
                        state=state,
                        robot_name=data.get("robot_name", ""),
                        version=data.get("version"),
                        error=data.get("error"),
                    )
                else:
                    logger.warning(f"Daemon status API returned {response.status}")
                    return DaemonStatus(state=DaemonState.UNAVAILABLE)
        except aiohttp.ClientError as e:
            logger.debug(f"Cannot connect to daemon: {e}")
            return DaemonStatus(state=DaemonState.UNAVAILABLE)
        except Exception as e:
            logger.error(f"Error fetching daemon status: {e}")
            return DaemonStatus(state=DaemonState.UNAVAILABLE)

    def _process_status(self, status: DaemonStatus) -> None:
        """Process a new status and trigger callbacks if needed."""
        with self._state_lock:
            old_state = self._current_state
            new_state = status.state
            self._current_state = new_state
            self._last_status = status

        if old_state == new_state:
            return

        logger.info(f"Daemon state changed: {old_state.value} -> {new_state.value}")

        # Trigger state change callbacks
        for callback in self._on_state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

        # Check for sleep transition
        was_sleeping = old_state in (DaemonState.STOPPED, DaemonState.STOPPING)
        is_sleeping = new_state in (DaemonState.STOPPED, DaemonState.STOPPING)

        if is_sleeping and not was_sleeping:
            logger.info("Robot is going to sleep")
            for callback in self._on_sleep_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in sleep callback: {e}")

        # Check for wake transition
        if new_state == DaemonState.RUNNING and old_state != DaemonState.RUNNING:
            logger.info("Robot has woken up")
            for callback in self._on_wake_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in wake callback: {e}")

        # Check for unavailable transition
        if new_state == DaemonState.UNAVAILABLE and old_state != DaemonState.UNAVAILABLE:
            self._handle_unavailable()

    def _handle_unavailable(self) -> None:
        """Handle daemon becoming unavailable."""
        with self._state_lock:
            if self._current_state != DaemonState.UNAVAILABLE:
                self._current_state = DaemonState.UNAVAILABLE

        logger.warning("Daemon is unavailable")
        for callback in self._on_unavailable_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in unavailable callback: {e}")
