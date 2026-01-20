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

    def __init__(
        self,
        daemon_url: str = DEFAULT_DAEMON_URL,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
    ):
        """Initialize the daemon state monitor.

        Args:
            daemon_url: Base URL of the daemon HTTP API
            check_interval: How often to poll the daemon status (seconds)
        """
        self._daemon_url = daemon_url
        self._check_interval = check_interval

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
        timeout = aiohttp.ClientTimeout(total=5.0)
        self._session = aiohttp.ClientSession(timeout=timeout)

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
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await self._fetch_status(session)
        return await self._fetch_status(self._session)

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that polls daemon status."""
        logger.debug("Daemon monitor loop started")

        while self._running and not self._stop_event.is_set():
            try:
                status = await self._fetch_status(self._session)
                self._process_status(status)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daemon monitor loop: {e}")
                self._handle_unavailable()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._check_interval
                )
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue monitoring

        logger.debug("Daemon monitor loop ended")

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
