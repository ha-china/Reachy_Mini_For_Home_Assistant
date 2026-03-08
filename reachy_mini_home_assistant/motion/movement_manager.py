"""
Unified Movement Manager for Reachy Mini.

This module provides a centralized control system for robot movements,
inspired by the reachy_mini_conversation_app architecture.

Key features:
- Configurable control loop frequency (default 50Hz)
- Command queue pattern (thread-safe external API)
- Error throttling (prevents log explosion)
- JSON-driven animation system (conversation state animations)
- Graceful shutdown
- Pose change detection (skip sending if no significant change)
- Robust connection recovery (faster reconnection attempts)
- Proper pose composition using SDK's compose_world_offset (same as conversation_app)
- Antenna freeze during listening mode with smooth blend back
"""

import json
import logging
import math
import random
import threading
import time
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

import numpy as np

from ..audio.doa_tracker import DOAConfig, DOATracker
from ..core.config import Config
from .animation_player import AnimationPlayer
from .antenna import AntennaController
from .emotion_moves import EmotionMove, is_emotion_available
from .pose_composer import (
    clamp_body_yaw,
    compose_poses,
    create_head_pose_matrix,
    extract_yaw_from_pose,
)
from .state_machine import (
    STATE_ANIMATION_MAP,
    MovementState,
    PendingAction,
    RobotState,
)

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Control loop defaults (actual values come from Config.motion)
DEFAULT_CONTROL_LOOP_FREQUENCY_HZ = 100

# Animation suppression when face detected
FACE_DETECTED_THRESHOLD = 0.001  # Minimum offset magnitude to consider face detected
ANIMATION_BLEND_DURATION = 0.5  # Seconds to blend animation back when face lost
IDLE_ACTION_ANIMATION_BLEND_DURATION = 0.25  # Seconds to fade idle animation during queued idle actions

# Pose epsilon constants are kept for compatibility with existing motion logic.
POSE_EPS = 1e-3  # Max element delta in 4x4 pose matrix
ANTENNA_EPS = 0.005  # Radians (~0.29 deg)
BODY_YAW_EPS = 0.005  # Radians (~0.29 deg)
IDLE_POSE_EPS = 0.0018  # Slightly relaxed pose deadband in quiet idle
IDLE_BODY_YAW_EPS = 0.01  # Slightly relaxed body yaw deadband in quiet idle
IDLE_ANTENNA_EPS = 0.012  # Larger idle antenna deadband to reduce tiny updates
IDLE_HEAD_POSE_HOLD_EPS = 0.0012  # Hold tiny idle head pose deltas to reduce motor chatter
IDLE_BODY_YAW_HOLD_EPS = 0.005  # Hold tiny idle body yaw deltas to reduce motor chatter
IDLE_RELATIVE_YAW_LIMIT_DEG = 120.0  # Safety: cap |head_yaw - body_yaw| during random idle

# Idle look-around behavior parameters
IDLE_LOOK_AROUND_MIN_INTERVAL = 6.0  # Minimum seconds between look-arounds
IDLE_LOOK_AROUND_MAX_INTERVAL = 14.0  # Maximum seconds between look-arounds
IDLE_LOOK_AROUND_YAW_RANGE = 15.0  # Maximum yaw angle in degrees
IDLE_LOOK_AROUND_PITCH_RANGE = 6.0  # Maximum pitch angle in degrees
IDLE_LOOK_AROUND_DURATION = 2.0  # Duration of look-around action in seconds
IDLE_INACTIVITY_THRESHOLD = 6.0  # Seconds of inactivity before look-around starts
IDLE_LOOK_AROUND_PROBABILITY = 0.8  # Otherwise keep breathing-only cycle

_ANIMATION_CONFIG_FILE = Path(__file__).resolve().parent.parent / "animations" / "conversation_animations.json"


class MovementManager:
    """
    Unified movement manager with configurable control loop.

    All external interactions go through the command queue,
    ensuring thread safety and preventing race conditions.
    """

    def __init__(self, reachy_mini: "ReachyMini"):
        self.robot = reachy_mini
        self._now = time.monotonic

        # Command queue - all external threads communicate through this (size limit 100)
        self._command_queue: Queue[tuple[str, Any]] = Queue(maxsize=100)

        # Internal state (only modified by control loop)
        self.state = MovementState()
        self.state.last_activity_time = self._now()
        self.state.idle_start_time = self._now()

        # Animation player (JSON-driven animations)
        self._animation_player = AnimationPlayer()

        # Thread control
        self._stop_event = threading.Event()
        self._draining_event = threading.Event()  # Thread-safe graceful shutdown flag
        self._emotion_playing_event = threading.Event()  # Pause when emotion animation playing
        self._robot_paused_event = threading.Event()  # Pause when robot disconnected/sleeping
        self._robot_resumed_event = threading.Event()  # Signal when robot resumes (for event-driven wait)
        self._robot_resumed_event.set()  # Start in resumed state
        self._thread: threading.Thread | None = None

        # Error throttling
        self._last_error_time = 0.0
        self._error_interval = 2.0  # Log at most once per 2 seconds in error mode
        self._suppressed_errors = 0

        # Connection health tracking
        self._connection_lost = False
        self._last_successful_command = self._now()
        self._connection_timeout = 3.0
        self._reconnect_backoff_initial = max(0.2, float(Config.motion.reconnect_backoff_initial_s))
        self._reconnect_backoff_max = max(self._reconnect_backoff_initial, float(Config.motion.reconnect_backoff_max_s))
        self._reconnect_backoff_multiplier = max(1.0, float(Config.motion.reconnect_backoff_multiplier))
        self._reconnect_attempt_interval = self._reconnect_backoff_initial
        self._last_reconnect_attempt = 0.0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

        # Pending action
        self._pending_action: PendingAction | None = None
        self._action_start_time: float = 0.0
        self._action_start_pose: dict[str, float] = {}
        self._idle_action_queue: deque[PendingAction] = deque()
        self._idle_action_animation_suppression = 0.0

        # Face tracking offsets (from camera worker)
        self._face_tracking_offsets: tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self._face_tracking_lock = threading.Lock()

        # Last sent pose for change detection (reduce daemon load)
        self._last_sent_head_pose: np.ndarray | None = None
        self._last_sent_antennas: tuple[float, float] | None = None
        self._last_sent_body_yaw: float | None = None
        self._last_send_time = 0.0

        # Idle antenna smoothing state
        self._idle_antenna_smoothed: tuple[float, float] | None = None
        self._last_idle_antenna_update = 0.0

        # Command send pacing (separate from control loop frequency)
        control_rate = max(1.0, float(Config.motion.control_rate_hz or DEFAULT_CONTROL_LOOP_FREQUENCY_HZ))
        self._control_loop_hz = control_rate
        self._target_period = 1.0 / control_rate
        # Body yaw smoothing state (rate-limited)
        self._body_yaw_smoothed: float | None = None
        self._last_body_yaw_update = 0.0

        # Camera server reference for face tracking
        self._camera_server = None

        # Face tracking smoothing - DISABLED to match reference project
        # Reference project applies face tracking offsets directly without smoothing
        # Smoothing causes "lag" and "trailing" that looks unnatural
        # Only smooth interpolation when face is lost (handled in camera_server.py)
        self._smoothed_face_offsets: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        # self._face_smoothing_factor = 0.3  # DISABLED - direct application instead

        # Emotion move playback state
        self._emotion_move: EmotionMove | None = None
        self._emotion_start_time: float = 0.0
        self._emotion_move_lock = threading.Lock()

        # DOA (Direction of Arrival) sound tracking
        self._doa_tracker = DOATracker(
            movement_callback=self._on_doa_turn,
            config=DOAConfig(),
        )
        self._doa_enabled = True  # Can be disabled via entity

        # Idle look-around behavior toggle (exposed via ESPHome switch)
        # Default OFF to prioritize long-running stability.
        self._idle_motion_enabled = False
        # Idle antenna animation toggle (exposed via ESPHome switch)
        self._idle_antenna_enabled = False
        # Idle random actions toggle (pure movement, no audio)
        self._idle_random_actions_enabled = False
        self._idle_random_actions_probability = IDLE_LOOK_AROUND_PROBABILITY
        self._idle_random_actions_min_interval = IDLE_LOOK_AROUND_MIN_INTERVAL
        self._idle_random_actions_max_interval = IDLE_LOOK_AROUND_MAX_INTERVAL
        self._idle_random_duration_min_s = 0.9
        self._idle_random_duration_max_s = 1.8
        self._idle_random_yaw_bounds_deg = (-18.0, 18.0)
        self._idle_random_pitch_bounds_deg = (-14.0, 14.0)
        self._idle_random_roll_bounds_deg = (-10.0, 10.0)
        self._idle_random_x_bounds_m = (-0.015, 0.015)
        self._idle_random_y_bounds_m = (-0.02, 0.02)
        self._idle_random_z_bounds_m = (-0.015, 0.015)
        self._idle_random_max_step_yaw_deg = 12.0
        self._idle_random_max_step_pitch_deg = 9.0
        self._idle_random_max_step_roll_deg = 8.0
        self._idle_random_max_step_x_m = 0.008
        self._idle_random_max_step_y_m = 0.01
        self._idle_random_max_step_z_m = 0.008
        self._idle_random_anchor_pull = 0.35
        self._idle_random_anchor_pose: dict[str, float] = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
        }
        self._load_idle_random_actions_config()

        # Antenna controller (handles freeze/unfreeze for listening mode)
        self._antenna_controller = AntennaController(time_func=self._now)

        logger.info("MovementManager initialized with AnimationPlayer and DOA tracking")

    # =========================================================================
    # Thread-safe public API (called from any thread)
    # =========================================================================

    def set_state(self, new_state: RobotState) -> None:
        """Thread-safe: Set robot state."""
        try:
            self._command_queue.put(("set_state", new_state), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_state command")

    def set_listening(self, listening: bool) -> None:
        """Thread-safe: Set listening state."""
        state = RobotState.LISTENING if listening else RobotState.IDLE
        try:
            self._command_queue.put(("set_state", state), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_listening command")

    def set_thinking(self) -> None:
        """Thread-safe: Set thinking state."""
        try:
            self._command_queue.put(("set_state", RobotState.THINKING), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_thinking command")

    def set_speaking(self, speaking: bool) -> None:
        """Thread-safe: Set speaking state."""
        state = RobotState.SPEAKING if speaking else RobotState.IDLE
        try:
            self._command_queue.put(("set_state", state), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_speaking command")

    def set_idle(self) -> None:
        """Thread-safe: Return to idle state."""
        self._command_queue.put(("set_state", RobotState.IDLE))

    def pause_for_emotion(self) -> None:
        """Thread-safe: Pause control loop while emotion animation is playing.

        DEPRECATED: Use queue_emotion_move() instead, which integrates emotion
        playback into the control loop without needing to pause.
        """
        self._emotion_playing_event.set()
        logger.debug("MovementManager paused for emotion animation")

    def resume_after_emotion(self) -> None:
        """Thread-safe: Resume control loop after emotion animation completes.

        DEPRECATED: Use queue_emotion_move() instead.
        """
        self._emotion_playing_event.clear()
        logger.debug("MovementManager resumed after emotion animation")

    def pause_for_robot_disconnect(self) -> None:
        """Thread-safe: Pause control loop when robot is disconnected.

        Called by robot state monitor when connection is lost (e.g., sleep mode).
        The control loop will skip sending commands while paused.
        """
        if not self._robot_paused_event.is_set():
            self._robot_paused_event.set()
            self._robot_resumed_event.clear()  # Clear resume signal
            # Reset connection tracking state
            self._connection_lost = False
            self._consecutive_errors = 0
            self._suppressed_errors = 0
            logger.info("MovementManager paused - robot disconnected")

    def resume_after_robot_connect(self) -> None:
        """Thread-safe: Resume control loop when robot reconnects.

        Called by robot state monitor when connection is restored.
        """
        if self._robot_paused_event.is_set():
            self._robot_paused_event.clear()
            self._robot_resumed_event.set()  # Signal resume to wake waiting threads
            self._last_successful_command = self._now()
            logger.info("MovementManager resumed - robot reconnected")

    def suspend(self) -> None:
        """Suspend the movement manager for sleep mode.

        This stops the control loop thread to release CPU resources.
        The service can be resumed later with resume().
        """
        if not self.is_running:
            logger.debug("MovementManager not running, nothing to suspend")
            return

        logger.info("Suspending MovementManager for sleep...")

        # First pause the robot operations
        self.pause_for_robot_disconnect()

        # Then stop the control loop thread to release CPU
        self._draining_event.set()
        time.sleep(0.05)  # Wait for in-flight commands
        self._stop_event.set()

        # Wait for thread to finish
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                logger.warning("MovementManager thread did not stop cleanly during suspend")

        # Clear events for next start
        self._draining_event.clear()
        self._stop_event.clear()

        logger.info("MovementManager suspended - CPU released")

    def resume_from_suspend(self) -> None:
        """Resume the movement manager after sleep.

        This restarts the control loop thread.
        """
        if self.is_running:
            logger.debug("MovementManager already running")
            return

        logger.info("Resuming MovementManager from sleep...")

        # Resume robot operations
        self.resume_after_robot_connect()

        # Restart the control loop thread
        self._stop_event.clear()
        self._draining_event.clear()

        # Reset idle animation state
        self._animation_player.set_animation("idle")
        self.state.robot_state = RobotState.IDLE
        self.state.idle_start_time = self._now()

        # Start thread
        self._thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name="MovementManager",
        )
        self._thread.start()

        logger.info("MovementManager resumed from sleep")

    def queue_emotion_move(self, emotion_name: str) -> bool:
        """Thread-safe: Queue an emotion move to be played by the control loop.

        This method uses the SDK's RecordedMoves.evaluate(t) API to sample
        emotion poses in the control loop, which avoids conflicts with
        set_target() calls that would cause "a move is currently running" warnings.

        Args:
            emotion_name: Name of the emotion (e.g., "happy1", "sad1")

        Returns:
            True if emotion was queued successfully, False otherwise
        """
        try:
            self._command_queue.put(("emotion_move", emotion_name), timeout=0.1)
            return True
        except Exception:
            logger.warning("Command queue full, dropping emotion_move command")
            return False

    def queue_action(self, action: PendingAction) -> None:
        """Thread-safe: Queue a motion action."""
        try:
            self._command_queue.put(("action", action), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping action command")

    def turn_to_angle(self, yaw_deg: float, duration: float = 0.8) -> None:
        """Thread-safe: Turn head to face a direction."""
        action = PendingAction(
            name="turn_to",
            target_yaw=math.radians(yaw_deg),
            duration=duration,
        )
        try:
            self._command_queue.put(("action", action), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping turn_to command")

    def nod(self, amplitude_deg: float = 15, duration: float = 0.5) -> None:
        """Thread-safe: Perform a nod gesture."""
        try:
            self._command_queue.put(("nod", (amplitude_deg, duration)), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping nod command")

    def shake(self, amplitude_deg: float = 20, duration: float = 0.5) -> None:
        """Thread-safe: Perform a head shake gesture."""
        try:
            self._command_queue.put(("shake", (amplitude_deg, duration)), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping shake command")

    def set_speech_sway(self, x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> None:
        """Thread-safe: Set speech-driven sway offsets.

        These offsets are applied on top of the current animation
        to create audio-synchronized head motion during TTS playback.

        Args:
            x, y, z: Position offsets in meters
            roll, pitch, yaw: Orientation offsets in radians
        """
        try:
            self._command_queue.put(("speech_sway", (x, y, z, roll, pitch, yaw)), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping speech_sway command")

    def reset_to_neutral(self, duration: float = 0.5) -> None:
        """Thread-safe: Reset to neutral position."""
        action = PendingAction(
            name="neutral",
            target_pitch=0.0,
            target_yaw=0.0,
            target_roll=0.0,
            target_x=0.0,
            target_y=0.0,
            target_z=0.0,
            duration=duration,
        )
        self._command_queue.put(("action", action))

    def set_camera_server(self, camera_server) -> None:
        """Set the camera server for face tracking offsets.

        Args:
            camera_server: MJPEGCameraServer instance with face tracking
        """
        self._camera_server = camera_server
        logger.info("Camera server set for face tracking")

    # =========================================================================
    # DOA (Direction of Arrival) Sound Tracking API
    # =========================================================================

    def set_doa_enabled(self, enabled: bool) -> None:
        """Enable or disable DOA sound tracking.

        Args:
            enabled: True to enable, False to disable
        """
        self._doa_enabled = enabled
        self._doa_tracker.enabled = enabled
        logger.info("DOA tracking %s", "enabled" if enabled else "disabled")

    def get_idle_motion_enabled(self) -> bool:
        """Get whether idle look-around behavior is enabled."""
        return self._idle_motion_enabled

    def set_idle_motion_enabled(self, enabled: bool) -> None:
        """Thread-safe: Enable or disable idle look-around behavior."""
        try:
            self._command_queue.put(("set_idle_motion", enabled), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_idle_motion command")

    def get_idle_antenna_enabled(self) -> bool:
        """Get whether idle antenna animation is enabled."""
        return self._idle_antenna_enabled

    def set_idle_antenna_enabled(self, enabled: bool) -> None:
        """Thread-safe: Enable or disable idle antenna animation."""
        try:
            self._command_queue.put(("set_idle_antenna", enabled), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_idle_antenna command")

    def get_idle_random_actions_enabled(self) -> bool:
        """Get whether idle random actions are enabled."""
        return self._idle_random_actions_enabled

    def set_idle_random_actions_enabled(self, enabled: bool) -> None:
        """Thread-safe: Enable or disable idle random actions."""
        try:
            self._command_queue.put(("set_idle_random_actions", enabled), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_idle_random_actions command")

    def get_idle_random_interval_seconds(self) -> float:
        """Get idle random trigger interval (seconds)."""
        return max(2.0, (self._idle_random_actions_min_interval + self._idle_random_actions_max_interval) / 2.0)

    def set_idle_random_interval_seconds(self, seconds: float) -> None:
        """Thread-safe: Set idle random trigger interval (seconds)."""
        try:
            self._command_queue.put(("set_idle_random_interval", float(seconds)), timeout=0.1)
        except Exception:
            logger.warning("Command queue full, dropping set_idle_random_interval command")

    def update_doa(self, angle_deg: float, energy: float) -> bool:
        """Update DOA tracker with new sound direction data.

        This should be called from the audio processing loop with data
        from the ReSpeaker microphone array.

        Args:
            angle_deg: Direction of arrival in degrees (-180 to 180)
            energy: Sound energy level (0 to 1)

        Returns:
            True if a turn was triggered, False otherwise
        """
        if not self._doa_enabled:
            return False

        # Update face detection state for DOA tracker
        self._doa_tracker.set_face_detected(self.state.face_detected)

        # Update conversation state
        in_conversation = self.state.robot_state in (
            RobotState.LISTENING,
            RobotState.THINKING,
            RobotState.SPEAKING,
        )
        self._doa_tracker.set_conversation_mode(in_conversation)

        return self._doa_tracker.update(angle_deg, energy)

    def _on_doa_turn(self, yaw_degrees: float, duration: float) -> None:
        """Callback from DOATracker when a turn should be executed.

        Args:
            yaw_degrees: Target yaw angle in degrees
            duration: Duration of the turn in seconds
        """
        # Create a look action similar to idle look-around
        action = PendingAction(
            name="doa_turn",
            target_yaw=math.radians(yaw_degrees),
            target_pitch=0.0,  # Keep pitch neutral for DOA turns
            duration=duration,
        )
        try:
            self._command_queue.put(("action", action), timeout=0.1)
            logger.debug("DOA turn queued: %.1f° over %.1fs", yaw_degrees, duration)
        except Exception:
            logger.warning("Command queue full, dropping doa_turn command")

    def set_face_tracking_offsets(self, offsets: tuple[float, float, float, float, float, float]) -> None:
        """Thread-safe: Update face tracking offsets manually.

        Args:
            offsets: Tuple of (x, y, z, roll, pitch, yaw) in meters/radians
        """
        with self._face_tracking_lock:
            self._face_tracking_offsets = offsets

    def set_target_pose(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        roll: float | None = None,
        pitch: float | None = None,
        yaw: float | None = None,
        antenna_left: float | None = None,
        antenna_right: float | None = None,
    ) -> None:
        """Thread-safe: Set target pose components.

        Only provided values will be updated. Values are in meters for position
        and radians for angles.

        Note: body_yaw is calculated automatically based on head yaw in _compose_final_pose().

        Args:
            x, y, z: Head position in meters
            roll, pitch, yaw: Head orientation in radians
            antenna_left, antenna_right: Antenna angles in radians
        """
        try:
            self._command_queue.put(
                (
                    "set_pose",
                    {
                        "x": x,
                        "y": y,
                        "z": z,
                        "roll": roll,
                        "pitch": pitch,
                        "yaw": yaw,
                        "antenna_left": antenna_left,
                        "antenna_right": antenna_right,
                    },
                ),
                timeout=0.1,
            )
        except Exception:
            logger.warning("Command queue full, dropping set_pose command")

    # =========================================================================
    # Internal: Command processing (runs in control loop)
    # =========================================================================

    @staticmethod
    def _parse_numeric_range(value: Any, default_min: float, default_max: float) -> tuple[float, float]:
        """Parse a numeric range from config value."""
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                min_v = float(value[0])
                max_v = float(value[1])
                if min_v > max_v:
                    min_v, max_v = max_v, min_v
                return min_v, max_v
            except (TypeError, ValueError):
                return default_min, default_max

        if value is None:
            return default_min, default_max

        try:
            span = abs(float(value))
            return -span, span
        except (TypeError, ValueError):
            return default_min, default_max

    def _schedule_next_idle_action_time(self, now: float) -> None:
        """Schedule the next idle action trigger time."""
        interval = random.uniform(self._idle_random_actions_min_interval, self._idle_random_actions_max_interval)
        self.state.next_look_around_time = now + interval

    @staticmethod
    def _sample_axis_with_step(current: float, bounds: tuple[float, float], max_step: float) -> float:
        """Sample a random target within bounds and with a capped step from current."""
        min_bound, max_bound = bounds
        local_min = max(min_bound, current - abs(max_step))
        local_max = min(max_bound, current + abs(max_step))
        if local_min > local_max:
            return max(min_bound, min(max_bound, current))
        return random.uniform(local_min, local_max)

    @staticmethod
    def _sample_axis_with_anchor(
        current: float,
        anchor: float,
        bounds: tuple[float, float],
        max_step: float,
        anchor_pull: float,
    ) -> float:
        """Sample with anchor guidance and capped step for continuity/safety."""
        min_bound, max_bound = bounds
        pull = max(0.0, min(1.0, anchor_pull))
        guided_center = current + (anchor - current) * pull

        # Candidate band around guided center
        band_min = guided_center - abs(max_step)
        band_max = guided_center + abs(max_step)

        # Enforce absolute bounds and step continuity from current
        local_min = max(min_bound, current - abs(max_step), band_min)
        local_max = min(max_bound, current + abs(max_step), band_max)
        if local_min > local_max:
            return max(min_bound, min(max_bound, current))
        return random.uniform(local_min, local_max)

    def _generate_fully_random_idle_action(self) -> PendingAction:
        """Generate one fully random idle action within conservative safe bounds."""
        current_yaw_deg = math.degrees(self.state.target_yaw)
        current_pitch_deg = math.degrees(self.state.target_pitch)
        current_roll_deg = math.degrees(self.state.target_roll)

        target_yaw_deg = self._sample_axis_with_anchor(
            current=current_yaw_deg,
            anchor=math.degrees(self._idle_random_anchor_pose["yaw"]),
            bounds=self._idle_random_yaw_bounds_deg,
            max_step=self._idle_random_max_step_yaw_deg,
            anchor_pull=self._idle_random_anchor_pull,
        )
        target_pitch_deg = self._sample_axis_with_anchor(
            current=current_pitch_deg,
            anchor=math.degrees(self._idle_random_anchor_pose["pitch"]),
            bounds=self._idle_random_pitch_bounds_deg,
            max_step=self._idle_random_max_step_pitch_deg,
            anchor_pull=self._idle_random_anchor_pull,
        )
        target_roll_deg = self._sample_axis_with_anchor(
            current=current_roll_deg,
            anchor=math.degrees(self._idle_random_anchor_pose["roll"]),
            bounds=self._idle_random_roll_bounds_deg,
            max_step=self._idle_random_max_step_roll_deg,
            anchor_pull=self._idle_random_anchor_pull,
        )

        # Coupled safety: avoid extreme opposite twists between head and body.
        body_yaw_ref = (
            self._body_yaw_smoothed
            if self._body_yaw_smoothed is not None
            else (self._last_sent_body_yaw if self._last_sent_body_yaw is not None else 0.0)
        )
        body_yaw_deg = math.degrees(body_yaw_ref)
        relative_yaw = target_yaw_deg - body_yaw_deg
        if relative_yaw > IDLE_RELATIVE_YAW_LIMIT_DEG:
            target_yaw_deg = body_yaw_deg + IDLE_RELATIVE_YAW_LIMIT_DEG
        elif relative_yaw < -IDLE_RELATIVE_YAW_LIMIT_DEG:
            target_yaw_deg = body_yaw_deg - IDLE_RELATIVE_YAW_LIMIT_DEG

        # Keep final yaw within configured bounds after coupled safety clamp.
        target_yaw_deg = max(
            self._idle_random_yaw_bounds_deg[0], min(self._idle_random_yaw_bounds_deg[1], target_yaw_deg)
        )

        target_x = self._sample_axis_with_anchor(
            current=self.state.target_x,
            anchor=self._idle_random_anchor_pose["x"],
            bounds=self._idle_random_x_bounds_m,
            max_step=self._idle_random_max_step_x_m,
            anchor_pull=self._idle_random_anchor_pull,
        )
        target_y = self._sample_axis_with_anchor(
            current=self.state.target_y,
            anchor=self._idle_random_anchor_pose["y"],
            bounds=self._idle_random_y_bounds_m,
            max_step=self._idle_random_max_step_y_m,
            anchor_pull=self._idle_random_anchor_pull,
        )
        target_z = self._sample_axis_with_anchor(
            current=self.state.target_z,
            anchor=self._idle_random_anchor_pose["z"],
            bounds=self._idle_random_z_bounds_m,
            max_step=self._idle_random_max_step_z_m,
            anchor_pull=self._idle_random_anchor_pull,
        )

        # Larger move => longer duration, reducing jerk on slow servos.
        yaw_factor = abs(target_yaw_deg - current_yaw_deg) / max(1e-3, self._idle_random_max_step_yaw_deg)
        pitch_factor = abs(target_pitch_deg - current_pitch_deg) / max(1e-3, self._idle_random_max_step_pitch_deg)
        roll_factor = abs(target_roll_deg - current_roll_deg) / max(1e-3, self._idle_random_max_step_roll_deg)
        spatial_factor = max(
            abs(target_x - self.state.target_x) / max(1e-4, self._idle_random_max_step_x_m),
            abs(target_y - self.state.target_y) / max(1e-4, self._idle_random_max_step_y_m),
            abs(target_z - self.state.target_z) / max(1e-4, self._idle_random_max_step_z_m),
        )
        effort = max(yaw_factor, pitch_factor, roll_factor, spatial_factor)
        effort = max(0.0, min(1.0, effort))
        duration = self._idle_random_duration_min_s + (
            (self._idle_random_duration_max_s - self._idle_random_duration_min_s) * effort
        )

        return PendingAction(
            name="idle_action:fully_random_safe",
            target_yaw=math.radians(target_yaw_deg),
            target_pitch=math.radians(target_pitch_deg),
            target_roll=math.radians(target_roll_deg),
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
            duration=max(0.2, duration),
        )

    def _load_idle_random_actions_config(self) -> None:
        """Load idle random action definitions from animation config."""
        self._idle_random_actions_min_interval = IDLE_LOOK_AROUND_MIN_INTERVAL
        self._idle_random_actions_max_interval = IDLE_LOOK_AROUND_MAX_INTERVAL
        self._idle_random_actions_probability = IDLE_LOOK_AROUND_PROBABILITY

        if not _ANIMATION_CONFIG_FILE.exists():
            logger.debug("Idle random actions config file not found: %s", _ANIMATION_CONFIG_FILE)
            return

        try:
            with open(_ANIMATION_CONFIG_FILE, encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning("Failed to read idle random actions config: %s", e)
            return

        section = config.get("idle_random_actions")
        if not isinstance(section, dict):
            return

        try:
            min_interval = float(section.get("min_interval_s", IDLE_LOOK_AROUND_MIN_INTERVAL))
            max_interval = float(section.get("max_interval_s", IDLE_LOOK_AROUND_MAX_INTERVAL))
            if min_interval > max_interval:
                min_interval, max_interval = max_interval, min_interval
            self._idle_random_actions_min_interval = max(0.5, min_interval)
            self._idle_random_actions_max_interval = max(self._idle_random_actions_min_interval, max_interval)
        except (TypeError, ValueError):
            self._idle_random_actions_min_interval = IDLE_LOOK_AROUND_MIN_INTERVAL
            self._idle_random_actions_max_interval = IDLE_LOOK_AROUND_MAX_INTERVAL

        try:
            probability = float(section.get("trigger_probability", IDLE_LOOK_AROUND_PROBABILITY))
        except (TypeError, ValueError):
            probability = IDLE_LOOK_AROUND_PROBABILITY
        self._idle_random_actions_probability = max(0.0, min(1.0, probability))

        try:
            anchor_pull = float(section.get("anchor_pull", self._idle_random_anchor_pull))
            self._idle_random_anchor_pull = max(0.0, min(1.0, anchor_pull))
        except (TypeError, ValueError):
            pass

        try:
            duration_min = float(section.get("duration_min_s", self._idle_random_duration_min_s))
            duration_max = float(section.get("duration_max_s", self._idle_random_duration_max_s))
            if duration_min > duration_max:
                duration_min, duration_max = duration_max, duration_min
            self._idle_random_duration_min_s = max(0.2, duration_min)
            self._idle_random_duration_max_s = max(self._idle_random_duration_min_s, duration_max)
        except (TypeError, ValueError):
            pass

        bounds = section.get("safe_bounds", {})
        if not isinstance(bounds, dict):
            bounds = {}

        self._idle_random_yaw_bounds_deg = self._parse_numeric_range(
            bounds.get("yaw_range_deg", section.get("yaw_range_deg")),
            self._idle_random_yaw_bounds_deg[0],
            self._idle_random_yaw_bounds_deg[1],
        )
        self._idle_random_pitch_bounds_deg = self._parse_numeric_range(
            bounds.get("pitch_range_deg", section.get("pitch_range_deg")),
            self._idle_random_pitch_bounds_deg[0],
            self._idle_random_pitch_bounds_deg[1],
        )
        self._idle_random_roll_bounds_deg = self._parse_numeric_range(
            bounds.get("roll_range_deg", section.get("roll_range_deg")),
            self._idle_random_roll_bounds_deg[0],
            self._idle_random_roll_bounds_deg[1],
        )
        self._idle_random_x_bounds_m = self._parse_numeric_range(
            bounds.get("x_range_m", section.get("x_range_m")),
            self._idle_random_x_bounds_m[0],
            self._idle_random_x_bounds_m[1],
        )
        self._idle_random_y_bounds_m = self._parse_numeric_range(
            bounds.get("y_range_m", section.get("y_range_m")),
            self._idle_random_y_bounds_m[0],
            self._idle_random_y_bounds_m[1],
        )
        self._idle_random_z_bounds_m = self._parse_numeric_range(
            bounds.get("z_range_m", section.get("z_range_m")),
            self._idle_random_z_bounds_m[0],
            self._idle_random_z_bounds_m[1],
        )

        step_limits = section.get("max_step", {})
        if not isinstance(step_limits, dict):
            step_limits = {}

        try:
            self._idle_random_max_step_yaw_deg = max(
                1.0,
                float(step_limits.get("yaw_deg", self._idle_random_max_step_yaw_deg)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self._idle_random_max_step_pitch_deg = max(
                1.0,
                float(step_limits.get("pitch_deg", self._idle_random_max_step_pitch_deg)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self._idle_random_max_step_roll_deg = max(
                1.0,
                float(step_limits.get("roll_deg", self._idle_random_max_step_roll_deg)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self._idle_random_max_step_x_m = max(
                0.001,
                float(step_limits.get("x_m", self._idle_random_max_step_x_m)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self._idle_random_max_step_y_m = max(
                0.001,
                float(step_limits.get("y_m", self._idle_random_max_step_y_m)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self._idle_random_max_step_z_m = max(
                0.001,
                float(step_limits.get("z_m", self._idle_random_max_step_z_m)),
            )
        except (TypeError, ValueError):
            pass

    def _poll_commands(self) -> None:
        """Process all pending commands from the queue."""
        while True:
            try:
                cmd, payload = self._command_queue.get_nowait()
            except Empty:
                break

            self._handle_command(cmd, payload)

    def _handle_command(self, cmd: str, payload: Any) -> None:
        """Handle a single command."""
        if cmd == "set_state":
            old_state = self.state.robot_state
            self.state.robot_state = payload
            self.state.last_activity_time = self._now()

            # Update animation based on state
            if payload == RobotState.IDLE and not self._idle_motion_enabled:
                animation_name = "none"
                self._animation_player.stop()
            else:
                animation_name = STATE_ANIMATION_MAP.get(payload.value, "idle")
                self._animation_player.set_animation(animation_name)

            # State transition logic
            if payload == RobotState.IDLE and old_state != RobotState.IDLE:
                self.state.idle_start_time = self._now()
                self._idle_random_anchor_pose = {
                    "x": self.state.target_x,
                    "y": self.state.target_y,
                    "z": self.state.target_z,
                    "roll": self.state.target_roll,
                    "pitch": self.state.target_pitch,
                    "yaw": self.state.target_yaw,
                }
                # Unfreeze antennas when returning to idle
                self._start_antenna_unfreeze()
                # Reset idle antenna smoothing state
                self._idle_antenna_smoothed = None
                self._last_idle_antenna_update = 0.0

            # Freeze antennas when entering listening mode
            if payload == RobotState.LISTENING:
                self._freeze_antennas()
            elif old_state == RobotState.LISTENING and payload != RobotState.LISTENING:
                # Start unfreezing when leaving listening mode
                self._start_antenna_unfreeze()

            if payload != RobotState.IDLE:
                self._idle_antenna_smoothed = None
                self._last_idle_antenna_update = 0.0

            logger.debug("State changed: %s -> %s, animation: %s", old_state.value, payload.value, animation_name)

        elif cmd == "action":
            self._start_action(payload)

        elif cmd == "nod":
            amplitude_deg, duration = payload
            self._do_nod(amplitude_deg, duration)

        elif cmd == "shake":
            amplitude_deg, duration = payload
            self._do_shake(amplitude_deg, duration)

        elif cmd == "set_pose":
            # Update target pose from external control (e.g., Home Assistant)
            if payload.get("x") is not None:
                self.state.target_x = payload["x"]
            if payload.get("y") is not None:
                self.state.target_y = payload["y"]
            if payload.get("z") is not None:
                self.state.target_z = payload["z"]
            if payload.get("roll") is not None:
                self.state.target_roll = payload["roll"]
            if payload.get("pitch") is not None:
                self.state.target_pitch = payload["pitch"]
            if payload.get("yaw") is not None:
                self.state.target_yaw = payload["yaw"]
            # Note: body_yaw is calculated in _compose_final_pose based on head yaw
            if payload.get("antenna_left") is not None:
                self.state.target_antenna_left = payload["antenna_left"]
            if payload.get("antenna_right") is not None:
                self.state.target_antenna_right = payload["antenna_right"]
            logger.debug("External pose update: %s", payload)

        elif cmd == "speech_sway":
            # Update speech-driven sway offsets
            x, y, z, roll, pitch, yaw = payload
            self.state.sway_x = x
            self.state.sway_y = y
            self.state.sway_z = z
            self.state.sway_roll = roll
            self.state.sway_pitch = pitch
            self.state.sway_yaw = yaw

        elif cmd == "emotion_move":
            # Start playing an emotion move
            self._start_emotion_move(payload)

        elif cmd == "set_idle_motion":
            enabled = bool(payload)
            self._idle_motion_enabled = enabled
            if not enabled:
                if not self._idle_random_actions_enabled:
                    self.state.next_look_around_time = 0.0
                    self.state.look_around_in_progress = False
                    self._idle_action_queue.clear()
                    if self._pending_action and self._pending_action.name.startswith("idle_action"):
                        self._pending_action = None
                if self.state.robot_state == RobotState.IDLE:
                    self._animation_player.stop()
                    self.state.anim_pitch = 0.0
                    self.state.anim_yaw = 0.0
                    self.state.anim_roll = 0.0
                    self.state.anim_x = 0.0
                    self.state.anim_y = 0.0
                    self.state.anim_z = 0.0
                    self.state.anim_antenna_left = 0.0
                    self.state.anim_antenna_right = 0.0
            elif self.state.robot_state == RobotState.IDLE:
                self._animation_player.set_animation("idle")
            logger.info("Idle motion %s", "enabled" if enabled else "disabled")

        elif cmd == "set_idle_random_actions":
            enabled = bool(payload)
            self._idle_random_actions_enabled = enabled
            if not enabled:
                if not self._idle_motion_enabled:
                    self.state.next_look_around_time = 0.0
                    self.state.look_around_in_progress = False
                self._idle_action_queue.clear()
                if self._pending_action and self._pending_action.name.startswith("idle_action"):
                    self._pending_action = None
            logger.info("Idle random actions %s", "enabled" if enabled else "disabled")

        elif cmd == "set_idle_random_interval":
            interval_seconds = max(2.0, min(60.0, float(payload)))
            self._idle_random_actions_min_interval = max(0.5, interval_seconds * 0.6)
            self._idle_random_actions_max_interval = max(
                self._idle_random_actions_min_interval,
                interval_seconds * 1.4,
            )
            logger.info(
                "Idle random interval updated: %.1fs (range %.1f~%.1fs)",
                interval_seconds,
                self._idle_random_actions_min_interval,
                self._idle_random_actions_max_interval,
            )

        elif cmd == "set_idle_antenna":
            enabled = bool(payload)
            self._idle_antenna_enabled = enabled

            if not enabled:
                self.state.anim_antenna_left = 0.0
                self.state.anim_antenna_right = 0.0
                self._idle_antenna_smoothed = None
                self._last_idle_antenna_update = 0.0

            logger.info("Idle antenna animation %s", "enabled" if enabled else "disabled")

    def _start_emotion_move(self, emotion_name: str) -> None:
        """Start playing an emotion move.

        Creates an EmotionMove and sets it as the active emotion, which will
        be sampled in the control loop via _update_emotion_move().
        """
        if not is_emotion_available():
            logger.warning("Cannot play emotion '%s': emotion library not available", emotion_name)
            return

        try:
            emotion_move = EmotionMove(emotion_name)
            with self._emotion_move_lock:
                self._emotion_move = emotion_move
                self._emotion_start_time = self._now()
            logger.info("Started emotion move: %s (duration=%.2fs)", emotion_name, emotion_move.duration)
        except Exception as e:
            logger.error("Failed to start emotion '%s': %s", emotion_name, e)

    def _start_action(self, action: PendingAction) -> None:
        """Start a new motion action."""
        self._pending_action = action
        self._action_start_time = self._now()
        self._action_start_pose = {
            "pitch": self.state.target_pitch,
            "yaw": self.state.target_yaw,
            "roll": self.state.target_roll,
            "x": self.state.target_x,
            "y": self.state.target_y,
            "z": self.state.target_z,
        }
        logger.debug("Starting action: %s", action.name)

    def _do_nod(self, amplitude_deg: float, duration: float) -> None:
        """Execute nod gesture (blocking in control loop context)."""
        # This is simplified - in production, use action queue
        amplitude_rad = math.radians(amplitude_deg)
        half_duration = duration / 2

        # Nod down
        action_down = PendingAction(
            name="nod_down",
            target_pitch=amplitude_rad,
            duration=half_duration,
        )
        self._start_action(action_down)

    def _do_shake(self, amplitude_deg: float, duration: float) -> None:
        """Execute shake gesture (blocking in control loop context)."""
        amplitude_rad = math.radians(amplitude_deg)
        half_duration = duration / 2

        # Shake left
        action_left = PendingAction(
            name="shake_left",
            target_yaw=-amplitude_rad,
            duration=half_duration,
        )
        self._start_action(action_left)

    # =========================================================================
    # Internal: Motion updates (runs in control loop)
    # =========================================================================

    def _update_action(self, dt: float) -> None:
        """Update pending action interpolation."""
        if self._pending_action is None:
            if self._idle_action_queue:
                self._start_action(self._idle_action_queue.popleft())
            else:
                self.state.look_around_in_progress = False
            return

        elapsed = self._now() - self._action_start_time
        progress = min(1.0, elapsed / self._pending_action.duration)

        # Smooth interpolation (smootherstep, C2 continuous)
        t = progress * progress * progress * (progress * (progress * 6 - 15) + 10)

        # Interpolate pose
        start = self._action_start_pose
        action = self._pending_action

        self.state.target_pitch = start["pitch"] + t * (action.target_pitch - start["pitch"])
        self.state.target_yaw = start["yaw"] + t * (action.target_yaw - start["yaw"])
        self.state.target_roll = start["roll"] + t * (action.target_roll - start["roll"])
        self.state.target_x = start["x"] + t * (action.target_x - start["x"])
        self.state.target_y = start["y"] + t * (action.target_y - start["y"])
        self.state.target_z = start["z"] + t * (action.target_z - start["z"])

        # Action complete
        if progress >= 1.0:
            completed_action = self._pending_action

            if completed_action.callback:
                try:
                    completed_action.callback()
                except Exception as e:
                    logger.error("Action callback error: %s", e)

            self._pending_action = None

            # Keep idle action state active until the full idle action queue is drained
            if completed_action.name.startswith("idle_action") and self._idle_action_queue:
                self._start_action(self._idle_action_queue.popleft())
            elif completed_action.name.startswith("idle_action") or completed_action.name == "look_around":
                self.state.look_around_in_progress = False

    def _update_animation(self, dt: float) -> None:
        """Update animation offsets from AnimationPlayer."""
        dt_safe = max(0.0, dt)
        idle_queue_action_active = (
            self.state.robot_state == RobotState.IDLE
            and self.state.look_around_in_progress
            and (
                (self._pending_action is not None and self._pending_action.name.startswith("idle_action"))
                or len(self._idle_action_queue) > 0
            )
        )

        fade_duration = max(1e-3, IDLE_ACTION_ANIMATION_BLEND_DURATION)
        fade_step = dt_safe / fade_duration
        target_suppression = 1.0 if idle_queue_action_active else 0.0
        if target_suppression > self._idle_action_animation_suppression:
            self._idle_action_animation_suppression = min(
                target_suppression,
                self._idle_action_animation_suppression + fade_step,
            )
        else:
            self._idle_action_animation_suppression = max(
                target_suppression,
                self._idle_action_animation_suppression - fade_step,
            )

        if self.state.robot_state == RobotState.IDLE and not self._idle_motion_enabled:
            self.state.anim_pitch = 0.0
            self.state.anim_yaw = 0.0
            self.state.anim_roll = 0.0
            self.state.anim_x = 0.0
            self.state.anim_y = 0.0
            self.state.anim_z = 0.0
            self.state.anim_antenna_left = 0.0
            self.state.anim_antenna_right = 0.0
            self._idle_action_animation_suppression = 0.0
            return

        offsets = self._animation_player.get_offsets(dt)
        idle_animation_scale = 1.0 - self._idle_action_animation_suppression

        self.state.anim_pitch = offsets["pitch"] * idle_animation_scale
        self.state.anim_yaw = offsets["yaw"] * idle_animation_scale
        self.state.anim_roll = offsets["roll"] * idle_animation_scale
        self.state.anim_x = offsets["x"] * idle_animation_scale
        self.state.anim_y = offsets["y"] * idle_animation_scale
        self.state.anim_z = offsets["z"] * idle_animation_scale
        if self._idle_antenna_enabled:
            self.state.anim_antenna_left = offsets["antenna_left"] * idle_animation_scale
            self.state.anim_antenna_right = offsets["antenna_right"] * idle_animation_scale
        else:
            self.state.anim_antenna_left = 0.0
            self.state.anim_antenna_right = 0.0

    def _freeze_antennas(self) -> None:
        """Freeze antennas at current position (for listening mode)."""
        current_left = self.state.target_antenna_left + self.state.anim_antenna_left
        current_right = self.state.target_antenna_right + self.state.anim_antenna_right
        self._antenna_controller.freeze(current_left, current_right)

    def _start_antenna_unfreeze(self) -> None:
        """Start unfreezing antennas (smooth blend back to normal)."""
        self._antenna_controller.start_unfreeze()

    def _update_antenna_blend(self, dt: float) -> None:
        """Update antenna blend state for smooth unfreezing."""
        self._antenna_controller.update(dt)

    def _update_animation_blend(self) -> None:
        """Update animation blend factor when face is lost.

        When face is detected, animation_blend is set to 0 immediately.
        When face is lost, we smoothly blend animation back to 1.0.
        """
        # Face tracking no longer suppresses idle animation.
        # Keep blend fixed at full strength to match reference behavior.
        self.state.animation_blend = 1.0

    def _update_face_tracking(self) -> None:
        """Get face tracking offsets from camera server.

        Reference project applies face tracking offsets directly without
        smoothing. Smooth interpolation when face is lost is handled by
        the camera_server.py's _process_face_lost_interpolation().

        Also updates face detection state for animation suppression.
        """
        if self._camera_server is not None:
            try:
                # Get offsets directly - no EMA smoothing (matches reference project)
                raw_offsets = self._camera_server.get_face_tracking_offsets()

                # Apply face tracking offsets directly when face tracking is enabled.
                # Idle motion toggle should not disable face tracking behavior.
                offsets_for_motion = raw_offsets

                with self._face_tracking_lock:
                    self._face_tracking_offsets = offsets_for_motion

                # Check if face is detected (any offset is non-zero)
                offset_magnitude = sum(abs(o) for o in raw_offsets)
                face_now_detected = offset_magnitude > FACE_DETECTED_THRESHOLD

                # Update face detection state
                if face_now_detected:
                    if not self.state.face_detected:
                        logger.debug("Face detected")
                    self.state.face_detected = True
                else:
                    if self.state.face_detected:
                        logger.debug("Face lost")
                    self.state.face_detected = False

            except Exception as e:
                logger.debug("Error getting face tracking offsets: %s", e)

    def _update_idle_look_around(self) -> None:
        """Trigger random look-around behavior when idle for a while.

        This adds life-like behavior to the robot by occasionally looking around
        when not engaged in conversation. Similar to conversation_app's idle behaviors.
        """
        if not self._idle_motion_enabled and not self._idle_random_actions_enabled:
            self.state.next_look_around_time = 0.0
            self.state.look_around_in_progress = False
            return

        # Only trigger when in IDLE state
        if self.state.robot_state != RobotState.IDLE:
            # Reset timing when not idle
            self.state.next_look_around_time = 0.0
            self.state.look_around_in_progress = False
            return

        # Check if we have an action in progress
        if self._pending_action is not None:
            return

        now = self._now()
        idle_duration = now - self.state.idle_start_time

        # Only start look-around after sufficient inactivity
        if idle_duration < IDLE_INACTIVITY_THRESHOLD:
            return

        # Schedule next look-around if not scheduled
        if self.state.next_look_around_time == 0.0:
            self._schedule_next_idle_action_time(now)
            return

        # Check if it's time for look-around
        if now >= self.state.next_look_around_time and not self.state.look_around_in_progress:
            if self._idle_random_actions_enabled:
                if random.random() > self._idle_random_actions_probability:
                    self._schedule_next_idle_action_time(now)
                    return

                idle_action = self._generate_fully_random_idle_action()

                self._idle_action_queue.append(idle_action)
                self.state.look_around_in_progress = True
                queued_duration = sum(max(0.0, float(item.duration)) for item in self._idle_action_queue)
                self.state.next_look_around_time = now + queued_duration
                self._schedule_next_idle_action_time(self.state.next_look_around_time)
                return

            # Keep legacy behavior when random actions are disabled.
            if not self._idle_motion_enabled:
                self._schedule_next_idle_action_time(now)
                return

            # Random alternation between breathing-only and look-around.
            # Breathing animation is always active in idle; skipping look-around
            # for this cycle shows breathing-only behavior.
            if random.random() > IDLE_LOOK_AROUND_PROBABILITY:
                self._schedule_next_idle_action_time(now)
                return

            # Generate random look direction
            target_yaw = random.uniform(-IDLE_LOOK_AROUND_YAW_RANGE, IDLE_LOOK_AROUND_YAW_RANGE)
            target_pitch = random.uniform(-IDLE_LOOK_AROUND_PITCH_RANGE, IDLE_LOOK_AROUND_PITCH_RANGE)

            # Create look-around action
            action = PendingAction(
                name="look_around",
                target_yaw=math.radians(target_yaw),
                target_pitch=math.radians(target_pitch),
                duration=IDLE_LOOK_AROUND_DURATION,
            )

            # Start the action
            self._idle_action_queue.append(action)
            self.state.look_around_in_progress = True

            # Schedule return to center and next look-around
            queued_duration = sum(max(0.0, float(item.duration)) for item in self._idle_action_queue)
            self.state.next_look_around_time = now + queued_duration
            self._schedule_next_idle_action_time(self.state.next_look_around_time)

            logger.debug("Starting look-around: yaw=%.1f°, pitch=%.1f°", target_yaw, target_pitch)

    def _update_emotion_move(self) -> tuple[np.ndarray, tuple[float, float], float] | None:
        """Update emotion move playback and return pose if active.

        When an emotion move is playing, this method samples the pose from
        the emotion's evaluate(t) method and returns it. The control loop
        should use this pose directly instead of composing from other sources.

        Returns:
            Tuple of (head_pose, (antenna_right, antenna_left), body_yaw) if
            emotion is playing, None otherwise.
        """
        with self._emotion_move_lock:
            if self._emotion_move is None:
                return None

            # Calculate time since emotion started
            elapsed = self._now() - self._emotion_start_time

            # Check if emotion is complete
            if elapsed >= self._emotion_move.duration:
                emotion_name = self._emotion_move.emotion_name
                self._emotion_move = None
                logger.info("Emotion move complete: %s", emotion_name)
                return None

            # Sample pose from emotion move
            try:
                head_pose, antennas, body_yaw = self._emotion_move.evaluate(elapsed)

                # Convert antennas to tuple (right, left) format
                if isinstance(antennas, np.ndarray):
                    antenna_tuple = (float(antennas[0]), float(antennas[1]))
                else:
                    antenna_tuple = (float(antennas[0]), float(antennas[1]))

                # Clamp body_yaw to safe range to prevent IK collision warnings
                # SDK's inverse_kinematics_safe limits body_yaw to ±160°
                clamped_body_yaw = clamp_body_yaw(float(body_yaw))

                return (head_pose, antenna_tuple, clamped_body_yaw)

            except Exception as e:
                logger.error("Error sampling emotion pose: %s", e)
                self._emotion_move = None
                return None

    def is_emotion_playing(self) -> bool:
        """Check if an emotion move is currently playing."""
        with self._emotion_move_lock:
            return self._emotion_move is not None

    def _compose_final_pose(self) -> tuple[np.ndarray, tuple[float, float], float]:
        """Compose final pose from all sources using pose_composer utilities.

        Body yaw follows head yaw to enable natural head tracking with body rotation.
        When head turns beyond a threshold, body rotates to follow it.

        Returns:
            Tuple of (head_pose_4x4, (antenna_right, antenna_left), body_yaw)
        """
        # Build primary head pose from target state (using pose_composer utility)
        primary_head = create_head_pose_matrix(
            x=self.state.target_x,
            y=self.state.target_y,
            z=self.state.target_z,
            roll=self.state.target_roll,
            pitch=self.state.target_pitch,
            yaw=self.state.target_yaw,
        )

        # Build secondary pose from animation + face tracking + speech sway
        with self._face_tracking_lock:
            face_offsets = self._face_tracking_offsets

        # Apply animation blend factor (0 when face detected, 1 when no face)
        anim_blend = self.state.animation_blend
        secondary_x = self.state.anim_x * anim_blend + self.state.sway_x + face_offsets[0]
        secondary_y = self.state.anim_y * anim_blend + self.state.sway_y + face_offsets[1]
        secondary_z = self.state.anim_z * anim_blend + self.state.sway_z + face_offsets[2]
        secondary_roll = self.state.anim_roll * anim_blend + self.state.sway_roll + face_offsets[3]
        secondary_pitch = self.state.anim_pitch * anim_blend + self.state.sway_pitch + face_offsets[4]
        secondary_yaw = self.state.anim_yaw * anim_blend + self.state.sway_yaw + face_offsets[5]

        # Build secondary pose and compose with primary (using pose_composer utilities)
        secondary_head = create_head_pose_matrix(
            x=secondary_x,
            y=secondary_y,
            z=secondary_z,
            roll=secondary_roll,
            pitch=secondary_pitch,
            yaw=secondary_yaw,
        )
        final_head = compose_poses(primary_head, secondary_head)

        # Antenna pose with freeze blending (using AntennaController)
        anim_antenna_left = self.state.anim_antenna_left * anim_blend
        anim_antenna_right = self.state.anim_antenna_right * anim_blend

        target_antenna_left = self.state.target_antenna_left + anim_antenna_left
        target_antenna_right = self.state.target_antenna_right + anim_antenna_right

        # Apply antenna freeze blending via controller
        antenna_left, antenna_right = self._antenna_controller.get_blended_positions(
            target_antenna_left, target_antenna_right
        )

        if self.state.robot_state != RobotState.IDLE:
            self._idle_antenna_smoothed = None
            self._last_idle_antenna_update = 0.0

        # Calculate body_yaw to follow head yaw (using pose_composer utilities)
        final_head_yaw = extract_yaw_from_pose(final_head)
        target_body_yaw = clamp_body_yaw(final_head_yaw)
        if self.state.robot_state == RobotState.IDLE:
            target_body_yaw = 0.0

        # Rate-limit body yaw for smooth, continuous turning
        now = self._now()
        if self._body_yaw_smoothed is None:
            self._body_yaw_smoothed = target_body_yaw
            self._last_body_yaw_update = now
        else:
            dt = max(1e-6, now - self._last_body_yaw_update)
            max_rate_rad_s = math.radians(Config.motion.body_yaw_max_rate_deg_s)
            max_step = max_rate_rad_s * dt
            delta = target_body_yaw - self._body_yaw_smoothed
            if abs(delta) > Config.motion.body_yaw_deadband_rad:
                step = max(-max_step, min(max_step, delta))
                self._body_yaw_smoothed = clamp_body_yaw(self._body_yaw_smoothed + step)
            self._last_body_yaw_update = now

        return final_head, (antenna_right, antenna_left), self._body_yaw_smoothed

    # =========================================================================
    # Internal: Robot control (runs in control loop)
    # =========================================================================

    def _issue_control_command(self, head_pose: np.ndarray, antennas: tuple[float, float], body_yaw: float) -> None:
        """Send control command to robot with error throttling and connection health tracking.

        Body yaw follows head yaw for natural tracking. The SDK's automatic_body_yaw
        mechanism (inverse_kinematics_safe) handles collision prevention.

        Args:
            head_pose: 4x4 head pose matrix
            antennas: Tuple of (right_angle, left_angle) in radians
            body_yaw: Body yaw angle (follows head yaw for natural tracking)
        """
        # Skip sending commands during graceful shutdown drain phase
        # This prevents partial command transmission that can crash daemon
        if self._draining_event.is_set():
            return

        # Skip sending commands while emotion animation is playing
        # This prevents "a move is currently running" warning spam
        if self._emotion_playing_event.is_set():
            return

        # Skip sending commands while robot is paused (disconnected/sleeping)
        # Double-check here to catch race conditions during sleep transition
        if self._robot_paused_event.is_set():
            return

        now = self._now()

        # In quiet idle breathing, avoid sending tiny head/body micro-adjustments
        # that can produce audible servo chatter, while still sending antennas.
        quiet_idle = (
            self.state.robot_state == RobotState.IDLE
            and self._pending_action is None
            and not self.state.look_around_in_progress
            and not self.state.face_detected
            and abs(self.state.sway_x) < 1e-4
            and abs(self.state.sway_y) < 1e-4
            and abs(self.state.sway_z) < 1e-4
            and abs(self.state.sway_roll) < 1e-4
            and abs(self.state.sway_pitch) < 1e-4
            and abs(self.state.sway_yaw) < 1e-4
        )
        if quiet_idle and self._last_sent_head_pose is not None and self._last_sent_body_yaw is not None:
            pose_delta = float(np.max(np.abs(head_pose - self._last_sent_head_pose)))
            if pose_delta < IDLE_HEAD_POSE_HOLD_EPS:
                head_pose = self._last_sent_head_pose.copy()

            body_yaw_delta = abs(body_yaw - self._last_sent_body_yaw)
            if body_yaw_delta < IDLE_BODY_YAW_HOLD_EPS:
                body_yaw = self._last_sent_body_yaw

        # Check if we should skip due to connection loss (but always try periodically)
        if self._connection_lost:
            if now - self._last_reconnect_attempt < self._reconnect_attempt_interval:
                # Skip sending commands to reduce error spam
                return
            # Time to try reconnecting
            self._last_reconnect_attempt = now
            logger.debug("Attempting to send command after connection loss...")

        try:
            # Pass calculated body_yaw to set_target
            # Body yaw is calculated in _compose_final_pose based on head yaw
            self.robot.set_target(
                head=head_pose,
                antennas=list(antennas),
                body_yaw=body_yaw,
            )

            # Command succeeded - update connection health
            self._last_successful_command = now
            self._consecutive_errors = 0  # Reset error counter

            # Update last sent pose for change detection
            self._last_sent_head_pose = head_pose.copy()
            self._last_sent_antennas = antennas
            self._last_sent_body_yaw = body_yaw
            self._last_send_time = now

            if self._connection_lost:
                logger.info("✓ Connection to robot restored")
                self._connection_lost = False
                self._reconnect_attempt_interval = self._reconnect_backoff_initial
                self._suppressed_errors = 0

        except Exception as e:
            error_msg = str(e)
            self._consecutive_errors += 1

            # Check if this is a connection error
            is_connection_error = "Lost connection" in error_msg

            if is_connection_error:
                if not self._connection_lost:
                    # First time detecting connection loss
                    if self._consecutive_errors >= self._max_consecutive_errors:
                        logger.warning(f"Connection unstable after {self._consecutive_errors} errors: {error_msg}")
                        logger.warning("  Will retry connection every %.1fs...", self._reconnect_attempt_interval)
                        self._connection_lost = True
                        self._last_reconnect_attempt = now
                    else:
                        # Transient error, log but don't mark as lost yet
                        err_cnt = self._consecutive_errors
                        max_err = self._max_consecutive_errors
                        self._log_error_throttled(f"Transient connection error ({err_cnt}/{max_err}): {error_msg}")
                else:
                    # Already in lost state, use throttled logging
                    self._log_error_throttled(f"Connection still lost: {error_msg}")
                    self._reconnect_attempt_interval = min(
                        self._reconnect_backoff_max,
                        self._reconnect_attempt_interval * self._reconnect_backoff_multiplier,
                    )
            else:
                # Non-connection error - log but don't affect connection state
                self._log_error_throttled(f"Failed to set robot target: {error_msg}")

    def _log_error_throttled(self, message: str) -> None:
        """Log error with throttling to prevent log explosion."""
        now = self._now()
        if now - self._last_error_time >= self._error_interval:
            if self._suppressed_errors > 0:
                message += f" (suppressed {self._suppressed_errors} repeats)"
                self._suppressed_errors = 0
            logger.error(message)
            self._last_error_time = now
        else:
            self._suppressed_errors += 1

    # =========================================================================
    # Control loop
    # =========================================================================

    def _control_loop(self) -> None:
        """Main control loop."""
        logger.info("Movement manager control loop started (%.1f Hz)", self._control_loop_hz)

        last_time = self._now()

        while not self._stop_event.is_set():
            loop_start = self._now()
            dt = loop_start - last_time
            last_time = loop_start

            try:
                # 1. Process commands from queue (always process to clear queue)
                self._poll_commands()

                # 2. Check if robot is paused (disconnected/sleeping)
                if self._robot_paused_event.is_set():
                    # Robot is disconnected, skip all control commands
                    # Wait for resume signal (event-driven, wakes immediately on resume)
                    self._robot_resumed_event.wait(timeout=0.5)
                    continue

                # 3. Check if emotion move is playing - takes priority over other motions
                emotion_pose = self._update_emotion_move()
                if emotion_pose is not None:
                    # Emotion move is active - use its pose directly
                    head_pose, antennas, body_yaw = emotion_pose
                    self._issue_control_command(head_pose, antennas, body_yaw)
                    # Skip other updates when emotion is playing
                else:
                    # Normal motion updates
                    # 4. Update action interpolation
                    self._update_action(dt)

                    # 5. Update animation offsets (JSON-driven)
                    self._update_animation(dt)

                    # 6. Update antenna blend (listening mode freeze/unfreeze)
                    self._update_antenna_blend(dt)

                    # 7. Update face tracking offsets from camera server
                    self._update_face_tracking()

                    # 8. Update animation blend (suppress when face detected)
                    self._update_animation_blend()

                    # 9. Update idle look-around behavior
                    self._update_idle_look_around()

                    # 10. Compose final pose (returns head_pose matrix, antennas tuple, body_yaw)
                    head_pose, antennas, body_yaw = self._compose_final_pose()

                    # 11. Send to robot with body_yaw for automatic adjustment
                    self._issue_control_command(head_pose, antennas, body_yaw)

            except Exception as e:
                self._log_error_throttled(f"Control loop error: {e}")

            # Adaptive sleep
            elapsed = self._now() - loop_start
            sleep_time = max(0.0, self._target_period - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info("Movement manager control loop stopped")

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def start(self) -> None:
        """Start the control loop."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Movement manager already running")
            return

        self._stop_event.clear()

        # Reset to neutral position first (handles restart after crash/disconnect)
        # This ensures head returns to center on app startup
        self.reset_to_neutral(duration=0.5)
        logger.info("Reset to neutral position on startup")

        # Initialize idle animation immediately so breathing starts on launch
        # This matches the reference project's behavior where BreathingMove
        # starts after idle_inactivity_delay (0.3s)
        self._animation_player.set_animation("idle")
        self.state.robot_state = RobotState.IDLE
        self.state.idle_start_time = self._now()
        logger.info("Initialized with idle animation on startup")

        self._thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name="MovementManager",
        )
        self._thread.start()
        logger.info("Movement manager started")

    def stop(self) -> None:
        """Stop the control loop and reset robot.

        Implements graceful shutdown to prevent daemon crashes:
        1. Stop sending new commands to robot (drain mode)
        2. Wait for current command cycle to complete
        3. Signal control loop to stop
        4. Wait for thread to finish cleanly
        """
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping movement manager...")

        # Phase 1: Enter drain mode - stop sending commands to robot
        # This prevents partial command transmission that can crash daemon
        self._draining_event.set()

        # Give the control loop time to finish any in-flight command
        # 50ms is enough for multiple control cycles at default rates
        time.sleep(0.05)

        # Phase 2: Signal stop
        self._stop_event.set()

        # Phase 3: Wait for thread with reasonable timeout
        self._thread.join(timeout=0.5)
        if self._thread.is_alive():
            logger.warning("Movement manager thread did not stop in time")

        # Reset drain flag for potential restart
        self._draining_event.clear()

        # Skip reset to neutral - let the app manager handle it
        # This speeds up shutdown significantly
        logger.info("Movement manager stopped")

    def _reset_to_neutral_blocking(self) -> None:
        """Reset robot to neutral position (blocking)."""
        try:
            neutral_pose = np.eye(4)
            self.robot.goto_target(
                head=neutral_pose,
                antennas=[0.0, 0.0],
                body_yaw=0.0,
                duration=0.3,  # Faster reset
            )
            logger.info("Robot reset to neutral position")
        except Exception as e:
            logger.error("Failed to reset robot: %s", e)

    @property
    def is_running(self) -> bool:
        """Check if control loop is running."""
        return self._thread is not None and self._thread.is_alive()
