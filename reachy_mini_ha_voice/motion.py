"""Reachy Mini motion control integration."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional
import numpy as np

_LOGGER = logging.getLogger(__name__)


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant.

    All public motion methods (on_*) are non-blocking. They submit motion
    tasks to a background thread pool, allowing the caller to continue
    immediately without waiting for the motion to complete.
    """

    def __init__(self, reachy_mini=None):
        self.reachy_mini = reachy_mini
        self._is_speaking = False
        self._lock = threading.Lock()
        # Single-worker thread pool ensures motions execute sequentially
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="motion")
        self._current_motion: Optional[Future] = None

    def set_reachy_mini(self, reachy_mini):
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    def shutdown(self):
        """Shutdown the motion executor. Call this when stopping the service."""
        self._executor.shutdown(wait=False)

    # -------------------------------------------------------------------------
    # Public non-blocking motion methods
    # -------------------------------------------------------------------------

    def on_wakeup(self, doa_angle_deg: Optional[float] = None):
        """Called when wake word is detected - turn to sound source and nod.

        Non-blocking: motion executes in background thread.

        Args:
            doa_angle_deg: Direction of arrival angle in degrees (0=front, positive=right, negative=left)
        """
        _LOGGER.debug("on_wakeup called with doa_angle_deg=%s, reachy_mini=%s", doa_angle_deg, self.reachy_mini)
        if not self.reachy_mini:
            _LOGGER.warning("on_wakeup: reachy_mini is None, skipping motion")
            return
        self._submit_motion(self._do_wakeup, doa_angle_deg)

    def on_listening(self):
        """Called when listening for speech - tilt head slightly.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._submit_motion(self._do_listening)

    def on_thinking(self):
        """Called when processing speech - look up slightly.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._submit_motion(self._do_thinking)

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._is_speaking = True
        self._submit_motion(self._do_speaking_start)

    def on_speaking_end(self):
        """Called when TTS ends - stop speech-reactive motion.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._is_speaking = False
        self._submit_motion(self._do_speaking_end)

    def on_idle(self):
        """Called when returning to idle state.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._is_speaking = False
        self._submit_motion(self._do_idle)

    def on_timer_finished(self):
        """Called when a timer finishes - alert animation.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._submit_motion(self._do_timer_finished)

    def on_error(self):
        """Called on error - shake head.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._submit_motion(self._do_error)

    def wiggle_antennas(self, happy: bool = True):
        """Wiggle antennas to show emotion.

        Non-blocking: motion executes in background thread.
        """
        if not self.reachy_mini:
            return
        self._submit_motion(self._do_wiggle_antennas, happy)

    # -------------------------------------------------------------------------
    # Internal: motion submission
    # -------------------------------------------------------------------------

    def _submit_motion(self, func, *args):
        """Submit a motion function to the executor.

        If a motion is already running, the new motion will be queued
        (since we use a single-worker thread pool).
        """
        try:
            self._current_motion = self._executor.submit(func, *args)
        except RuntimeError:
            # Executor might be shut down
            _LOGGER.warning("Motion executor is shut down, cannot submit motion")

    # -------------------------------------------------------------------------
    # Internal: actual motion implementations (run in background thread)
    # -------------------------------------------------------------------------

    def _do_wakeup(self, doa_angle_deg: Optional[float] = None):
        """Actual wakeup motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                _LOGGER.info("_do_wakeup: doa_angle_deg=%s", doa_angle_deg)
                if doa_angle_deg is not None:
                    _LOGGER.info("Turning to sound source at %s degrees", doa_angle_deg)
                    self._turn_to_sound_source(doa_angle_deg)
                else:
                    _LOGGER.warning("DOA angle is None, skipping turn to sound source")
                self._nod(count=1, amplitude=10, duration=0.3)
                _LOGGER.debug("Reachy Mini: Wake up nod (DOA: %s)", doa_angle_deg)
            except Exception as e:
                _LOGGER.error("Motion error on wakeup: %s", e)

    def _do_listening(self):
        """Actual listening motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._look_at_user()
                _LOGGER.debug("Reachy Mini: Listening pose")
            except Exception as e:
                _LOGGER.error("Motion error on listening: %s", e)

    def _do_thinking(self):
        """Actual thinking motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._think_pose()
                _LOGGER.debug("Reachy Mini: Thinking pose")
            except Exception as e:
                _LOGGER.error("Motion error on thinking: %s", e)

    def _do_speaking_start(self):
        """Actual speaking start motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._start_speech_motion()
                _LOGGER.debug("Reachy Mini: Speaking started")
            except Exception as e:
                _LOGGER.error("Motion error on speaking start: %s", e)

    def _do_speaking_end(self):
        """Actual speaking end motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._stop_speech_motion()
                _LOGGER.debug("Reachy Mini: Speaking ended")
            except Exception as e:
                _LOGGER.error("Motion error on speaking end: %s", e)

    def _do_idle(self):
        """Actual idle motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._stop_speech_motion()
                self._return_to_neutral()
                _LOGGER.debug("Reachy Mini: Idle pose")
            except Exception as e:
                _LOGGER.error("Motion error on idle: %s", e)

    def _do_timer_finished(self):
        """Actual timer finished motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._shake(count=2, amplitude=15, duration=0.4)
                _LOGGER.debug("Reachy Mini: Timer finished animation")
            except Exception as e:
                _LOGGER.error("Motion error on timer finished: %s", e)

    def _do_error(self):
        """Actual error motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                self._shake(count=1, amplitude=10, duration=0.3)
                _LOGGER.debug("Reachy Mini: Error animation")
            except Exception as e:
                _LOGGER.error("Motion error on error: %s", e)

    def _do_wiggle_antennas(self, happy: bool = True):
        """Actual antenna wiggle motion (blocking, runs in thread pool)."""
        with self._lock:
            try:
                import math
                if happy:
                    self.reachy_mini.goto_target(antennas=[math.radians(-30), math.radians(30)], duration=0.2)
                else:
                    self.reachy_mini.goto_target(antennas=[math.radians(20), math.radians(-20)], duration=0.2)
            except Exception as e:
                _LOGGER.error("Antenna wiggle error: %s", e)

    # -------------------------------------------------------------------------
    # Low-level motion methods (blocking, called from thread pool)
    # -------------------------------------------------------------------------

    def _nod(self, count: int = 1, amplitude: float = 15, duration: float = 0.5):
        """Nod head up and down."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            for _ in range(count):
                # Nod down
                pose_down = np.eye(4)
                pose_down[:3, :3] = R.from_euler('xyz', [amplitude, 0, 0], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_down, duration=duration / 2)

                # Nod up
                pose_up = np.eye(4)
                pose_up[:3, :3] = R.from_euler('xyz', [-amplitude / 2, 0, 0], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_up, duration=duration / 2)

            # Return to neutral
            self._return_to_neutral()
        except Exception as e:
            _LOGGER.error("Nod error: %s", e)

    def _shake(self, count: int = 1, amplitude: float = 20, duration: float = 0.5):
        """Shake head left and right."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            for _ in range(count):
                # Shake left
                pose_left = np.eye(4)
                pose_left[:3, :3] = R.from_euler('xyz', [0, 0, -amplitude], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_left, duration=duration / 2)

                # Shake right
                pose_right = np.eye(4)
                pose_right[:3, :3] = R.from_euler('xyz', [0, 0, amplitude], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_right, duration=duration / 2)

            # Return to neutral
            self._return_to_neutral()
        except Exception as e:
            _LOGGER.error("Shake error: %s", e)

    def _look_at_user(self):
        """Look at user (neutral forward position)."""
        if not self.reachy_mini:
            return

        try:
            pose = np.eye(4)
            self.reachy_mini.goto_target(head=pose, duration=0.3)
        except Exception as e:
            _LOGGER.error("Look at user error: %s", e)

    def _think_pose(self):
        """Thinking pose - look up slightly."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [-10, 0, 5], degrees=True).as_matrix()
            self.reachy_mini.goto_target(head=pose, duration=0.4)
        except Exception as e:
            _LOGGER.error("Think pose error: %s", e)

    def _return_to_neutral(self):
        """Return to neutral position."""
        if not self.reachy_mini:
            return

        try:
            pose = np.eye(4)
            self.reachy_mini.goto_target(head=pose, duration=0.5)
        except Exception as e:
            _LOGGER.error("Return to neutral error: %s", e)

    def _start_speech_motion(self):
        """Start subtle speech-reactive motion - gentle nod."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            # Gentle nod down to indicate speaking
            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [5, 0, 0], degrees=True).as_matrix()
            self.reachy_mini.goto_target(head=pose, duration=0.3)
        except Exception as e:
            _LOGGER.error("Start speech motion error: %s", e)

    def _stop_speech_motion(self):
        """Stop speech-reactive motion - return to neutral."""
        pass  # Will return to neutral in on_idle()

    def _turn_to_sound_source(self, doa_angle_deg: float):
        """Turn head to face the sound source based on DOA angle.

        Args:
            doa_angle_deg: Direction of arrival angle in degrees.
                           The DOA from ReSpeaker is in radians where:
                           0 = left, π/2 = front/back, π = right
                           We convert to head yaw where:
                           0 = front, positive = right, negative = left
        """
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            # Clamp the angle to reasonable head rotation limits
            yaw_deg = max(-60, min(60, doa_angle_deg))

            # Create head pose with yaw rotation
            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [0, 0, yaw_deg], degrees=True).as_matrix()

            # Turn head to face the sound source
            self.reachy_mini.goto_target(head=pose, duration=0.4)
            _LOGGER.debug("Reachy Mini: Turned to sound source at %s degrees", yaw_deg)
        except Exception as e:
            _LOGGER.error("Turn to sound source error: %s", e)
