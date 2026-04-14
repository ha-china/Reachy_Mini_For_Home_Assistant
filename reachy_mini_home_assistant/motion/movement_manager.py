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

import logging
import math
import threading
import time
from collections import deque
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING, Any

import numpy as np

from ..audio.doa_tracker import DOAConfig, DOATracker
from ..core.config import Config
from .animation_player import AnimationPlayer
from .antenna import AntennaController
from .command_runtime import handle_command, poll_commands, start_action
from .control_runtime import (
    compose_final_pose,
    issue_control_command,
    run_control_loop,
    update_emotion_move,
    update_face_tracking,
)
from .emotion_moves import EmotionMove, is_emotion_available
from .idle_runtime import (
    apply_idle_behavior_enabled,
    apply_idle_rest_pose,
    clear_idle_activity,
    clear_idle_animation,
    schedule_next_idle_action_time,
    transition_or_apply_idle_rest_pose,
    update_idle_look_around,
)
from .state_machine import (
    build_idle_pending_action,
    load_idle_behavior_config,
    MovementState,
    PendingAction,
    pick_idle_random_action,
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
MAX_CONTROL_DT_S = 0.05

# Animation suppression when face detected
FACE_DETECTED_THRESHOLD = 0.001  # Minimum offset magnitude to consider face detected
ANIMATION_BLEND_DURATION = 0.18  # Seconds to blend animation back when face lost
FACE_TRACKING_ANIMATION_BLEND = 0.35
IDLE_ACTION_ANIMATION_BLEND_DURATION = 0.4  # Slightly longer fade avoids visible idle/action handoff steps
IDLE_ACTION_ANTENNA_SUPPRESSION = 0.25  # Keep idle antenna motion mostly continuous during idle actions


def _smoothstep(value: float) -> float:
    """Return a smooth ease-in-out factor in the 0..1 range."""
    clamped = max(0.0, min(1.0, value))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def _smootherstep(value: float) -> float:
    """Return a softer ease-in-out factor with flatter endpoints."""
    clamped = max(0.0, min(1.0, value))
    return clamped * clamped * clamped * (clamped * (clamped * 6.0 - 15.0) + 10.0)


# Pose epsilon constants are kept for compatibility with existing motion logic.
POSE_EPS = 1e-3  # Max element delta in 4x4 pose matrix
ANTENNA_EPS = 0.005  # Radians (~0.29 deg)
BODY_YAW_EPS = 0.005  # Radians (~0.29 deg)
IDLE_POSE_EPS = 0.0018  # Slightly relaxed pose deadband in quiet idle
IDLE_BODY_YAW_EPS = 0.01  # Slightly relaxed body yaw deadband in quiet idle
IDLE_ANTENNA_EPS = 0.012  # Larger idle antenna deadband to reduce tiny updates

# Idle look-around behavior parameters
IDLE_LOOK_AROUND_MIN_INTERVAL = 6.0  # Minimum seconds between look-arounds
IDLE_LOOK_AROUND_MAX_INTERVAL = 14.0  # Maximum seconds between look-arounds
IDLE_LOOK_AROUND_YAW_RANGE = 15.0  # Maximum yaw angle in degrees
IDLE_LOOK_AROUND_PITCH_RANGE = 6.0  # Maximum pitch angle in degrees
IDLE_LOOK_AROUND_DURATION = 2.0  # Duration of look-around action in seconds
IDLE_INACTIVITY_THRESHOLD = 6.0  # Seconds of inactivity before look-around starts
IDLE_LOOK_AROUND_PROBABILITY = 0.8  # Otherwise keep breathing-only cycle
DEFAULT_IDLE_REST_POSE = {
    "pitch_deg": 0.0,
    "antenna_left_rad": 0.0,
    "antenna_right_rad": 0.0,
}

_ANIMATION_CONFIG_FILE = Path(__file__).resolve().parent.parent / "animations" / "conversation_animations.json"
_DEFAULT_IDLE_RANDOM_ACTIONS: list[dict[str, Any]] = [
    {
        "name": "curious_left",
        "weight": 1.0,
        "duration_s": 1.8,
        "yaw_range_deg": [-16.0, -6.0],
        "pitch_range_deg": [-3.0, 4.0],
        "roll_range_deg": [-4.0, 2.0],
    },
    {
        "name": "curious_right",
        "weight": 1.0,
        "duration_s": 1.8,
        "yaw_range_deg": [6.0, 16.0],
        "pitch_range_deg": [-3.0, 4.0],
        "roll_range_deg": [-2.0, 4.0],
    },
    {
        "name": "micro_nod",
        "weight": 0.9,
        "duration_s": 1.3,
        "yaw_range_deg": [-3.0, 3.0],
        "pitch_range_deg": [-10.0, -4.0],
        "roll_range_deg": [-2.0, 2.0],
    },
    {
        "name": "micro_tilt",
        "weight": 0.8,
        "duration_s": 1.6,
        "yaw_range_deg": [-6.0, 6.0],
        "pitch_range_deg": [-2.0, 4.0],
        "roll_range_deg": [-7.0, 7.0],
    },
]


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
        self._idle_rest_head_pitch_rad = math.radians(float(DEFAULT_IDLE_REST_POSE["pitch_deg"]))
        self._idle_rest_antenna_left_rad = float(DEFAULT_IDLE_REST_POSE["antenna_left_rad"])
        self._idle_rest_antenna_right_rad = float(DEFAULT_IDLE_REST_POSE["antenna_right_rad"])
        self._idle_random_actions_probability = IDLE_LOOK_AROUND_PROBABILITY
        self._idle_random_actions_min_interval = IDLE_LOOK_AROUND_MIN_INTERVAL
        self._idle_random_actions_max_interval = IDLE_LOOK_AROUND_MAX_INTERVAL
        self._idle_random_actions: list[dict[str, Any]] = []
        self._load_idle_random_actions_config()

        # Antenna controller (handles freeze/unfreeze for listening mode)
        self._antenna_controller = AntennaController(time_func=self._now)

        logger.info("MovementManager initialized with AnimationPlayer and DOA tracking")

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """Best-effort connection error detection without relying on private SDK state."""
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True

        error_msg = str(exc).lower()
        connection_markers = (
            "lost connection",
            "connection lost",
            "connection refused",
            "connection reset",
            "not connected",
            "timed out",
            "timeout",
            "broken pipe",
            "unavailable",
        )
        return any(marker in error_msg for marker in connection_markers)

    # =========================================================================
    # Thread-safe public API (called from any thread)
    # =========================================================================

    def _enqueue_command(self, command: str, payload: Any, warning_label: str, timeout: float = 0.1) -> bool:
        """Queue a command for the control loop."""
        try:
            self._command_queue.put((command, payload), timeout=timeout)
            return True
        except Exception:
            logger.warning("Command queue full, dropping %s command", warning_label)
            return False

    def set_state(self, new_state: RobotState) -> None:
        """Thread-safe: Set robot state."""
        self._enqueue_command("set_state", new_state, "set_state")

    def set_listening(self, listening: bool) -> None:
        """Thread-safe: Set listening state."""
        state = RobotState.LISTENING if listening else RobotState.IDLE
        self._enqueue_command("set_state", state, "set_listening")

    def set_thinking(self) -> None:
        """Thread-safe: Set thinking state."""
        self._enqueue_command("set_state", RobotState.THINKING, "set_thinking")

    def set_speaking(self, speaking: bool) -> None:
        """Thread-safe: Set speaking state."""
        state = RobotState.SPEAKING if speaking else RobotState.IDLE
        self._enqueue_command("set_state", state, "set_speaking")

    def set_idle(self) -> None:
        """Thread-safe: Return to idle state."""
        self._enqueue_command("set_state", RobotState.IDLE, "set_idle", timeout=0)

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
        """Suspend the movement manager runtime resources.

        This stops the control loop thread to release CPU resources.
        The service can be resumed later with resume().
        """
        if not self.is_running:
            logger.debug("MovementManager not running, nothing to suspend")
            return

        logger.info("Suspending MovementManager resources...")

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
        """Resume the movement manager runtime resources.

        This restarts the control loop thread.
        """
        if self.is_running:
            logger.debug("MovementManager already running")
            return

        logger.info("Resuming MovementManager resources...")

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

        logger.info("MovementManager resumed")

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
        return self._enqueue_command("emotion_move", emotion_name, "emotion_move")

    def queue_action(self, action: PendingAction) -> None:
        """Thread-safe: Queue a motion action."""
        self._enqueue_command("action", action, "action")

    def turn_to_angle(self, yaw_deg: float, duration: float = 0.8) -> None:
        """Thread-safe: Turn head to face a direction."""
        action = PendingAction(
            name="turn_to",
            target_yaw=math.radians(yaw_deg),
            duration=duration,
        )
        self._enqueue_command("action", action, "turn_to")

    def nod(self, amplitude_deg: float = 15, duration: float = 0.5) -> None:
        """Thread-safe: Perform a nod gesture."""
        self._enqueue_command("nod", (amplitude_deg, duration), "nod")

    def shake(self, amplitude_deg: float = 20, duration: float = 0.5) -> None:
        """Thread-safe: Perform a head shake gesture."""
        self._enqueue_command("shake", (amplitude_deg, duration), "shake")

    def set_speech_sway(self, x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> None:
        """Thread-safe: Set speech-driven sway offsets.

        These offsets are applied on top of the current animation
        to create audio-synchronized head motion during TTS playback.

        Args:
            x, y, z: Position offsets in meters
            roll, pitch, yaw: Orientation offsets in radians
        """
        self._enqueue_command("speech_sway", (x, y, z, roll, pitch, yaw), "speech_sway")

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
            target_antenna_left=0.0,
            target_antenna_right=0.0,
            duration=duration,
        )
        self._enqueue_command("action", action, "neutral", timeout=0)

    def transition_to_idle_rest(self, duration: float = 2.0) -> None:
        """Thread-safe: Smoothly move into the configured idle rest pose."""
        action = PendingAction(
            name="idle_rest",
            target_pitch=self._idle_rest_head_pitch_rad,
            target_yaw=0.0,
            target_roll=0.0,
            target_x=0.0,
            target_y=0.0,
            target_z=0.0,
            target_antenna_left=self._idle_rest_antenna_left_rad,
            target_antenna_right=self._idle_rest_antenna_right_rad,
            duration=duration,
        )
        self._enqueue_command("action", action, "idle_rest", timeout=0)

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

    def get_doa_enabled(self) -> bool:
        """Get whether DOA sound tracking is enabled."""
        return self._doa_enabled

    def get_idle_behavior_enabled(self) -> bool:
        """Get whether any idle behavior subsystem is enabled."""
        return self._idle_behavior_enabled()

    def set_idle_behavior_enabled(self, enabled: bool) -> None:
        """Thread-safe: Enable or disable all idle behavior subsystems together."""
        self._enqueue_command("set_idle_behavior", enabled, "set_idle_behavior")

    def _idle_behavior_enabled(self) -> bool:
        """Whether any idle behavior subsystem is currently enabled."""
        return self._idle_motion_enabled or self._idle_antenna_enabled or self._idle_random_actions_enabled

    def _apply_idle_behavior_enabled(self, enabled: bool) -> None:
        apply_idle_behavior_enabled(self, enabled)

    def _apply_idle_rest_pose(self) -> None:
        apply_idle_rest_pose(self)

    def _transition_or_apply_idle_rest_pose(self, duration: float = 2.0) -> None:
        transition_or_apply_idle_rest_pose(self, duration=duration)

    def _clear_idle_activity(self) -> None:
        clear_idle_activity(self)

    def _clear_idle_animation(self) -> None:
        clear_idle_animation(self)

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

    def _schedule_next_idle_action_time(self, now: float) -> None:
        schedule_next_idle_action_time(self, now)

    def _load_idle_random_actions_config(self) -> None:
        """Load idle random action definitions from animation config."""
        config = load_idle_behavior_config(
            config_path=_ANIMATION_CONFIG_FILE,
            default_rest_pose=DEFAULT_IDLE_REST_POSE,
            default_actions=_DEFAULT_IDLE_RANDOM_ACTIONS,
            default_min_interval_s=IDLE_LOOK_AROUND_MIN_INTERVAL,
            default_max_interval_s=IDLE_LOOK_AROUND_MAX_INTERVAL,
            default_probability=IDLE_LOOK_AROUND_PROBABILITY,
            default_yaw_range_deg=IDLE_LOOK_AROUND_YAW_RANGE,
            default_pitch_range_deg=IDLE_LOOK_AROUND_PITCH_RANGE,
            default_duration_s=IDLE_LOOK_AROUND_DURATION,
        )

        self._idle_random_actions = config.actions
        self._idle_rest_head_pitch_rad = config.rest_pose.pitch_rad
        self._idle_rest_antenna_left_rad = config.rest_pose.antenna_left_rad
        self._idle_rest_antenna_right_rad = config.rest_pose.antenna_right_rad
        self._idle_random_actions_min_interval = config.min_interval_s
        self._idle_random_actions_max_interval = config.max_interval_s
        self._idle_random_actions_probability = config.trigger_probability

    def _pick_idle_random_action(self) -> dict[str, Any]:
        """Pick one idle random action from weighted definitions."""
        return pick_idle_random_action(self._idle_random_actions, _DEFAULT_IDLE_RANDOM_ACTIONS)

    def _poll_commands(self) -> None:
        poll_commands(self)

    def _handle_command(self, cmd: str, payload: Any) -> None:
        handle_command(self, cmd, payload)

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
        start_action(self, action)

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

        # Use a softer easing curve so idle actions and micro gestures start/stop less abruptly.
        t = _smootherstep(progress)

        # Interpolate pose
        start = self._action_start_pose
        action = self._pending_action

        self.state.target_pitch = start["pitch"] + t * (action.target_pitch - start["pitch"])
        self.state.target_yaw = start["yaw"] + t * (action.target_yaw - start["yaw"])
        self.state.target_roll = start["roll"] + t * (action.target_roll - start["roll"])
        self.state.target_x = start["x"] + t * (action.target_x - start["x"])
        self.state.target_y = start["y"] + t * (action.target_y - start["y"])
        self.state.target_z = start["z"] + t * (action.target_z - start["z"])
        self.state.target_antenna_left = start["antenna_left"] + t * (
            action.target_antenna_left - start["antenna_left"]
        )
        self.state.target_antenna_right = start["antenna_right"] + t * (
            action.target_antenna_right - start["antenna_right"]
        )

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
        dt_safe = max(0.0, min(dt, MAX_CONTROL_DT_S))
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
        suppression = _smoothstep(self._idle_action_animation_suppression)
        idle_animation_scale = 1.0 - suppression
        antenna_animation_scale = 1.0 - suppression * IDLE_ACTION_ANTENNA_SUPPRESSION

        self.state.anim_pitch = offsets["pitch"] * idle_animation_scale
        self.state.anim_yaw = offsets["yaw"] * idle_animation_scale
        self.state.anim_roll = offsets["roll"] * idle_animation_scale
        self.state.anim_x = offsets["x"] * idle_animation_scale
        self.state.anim_y = offsets["y"] * idle_animation_scale
        self.state.anim_z = offsets["z"] * idle_animation_scale
        if self.state.robot_state != RobotState.IDLE or self._idle_antenna_enabled:
            self.state.anim_antenna_left = offsets["antenna_left"] * antenna_animation_scale
            self.state.anim_antenna_right = offsets["antenna_right"] * antenna_animation_scale
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

        Keep existing idle/speaking features active, but reduce idle animation
        weight while face tracking is actively steering the head.
        """
        target_blend = FACE_TRACKING_ANIMATION_BLEND if self.state.face_detected else 1.0
        current_blend = self.state.animation_blend
        if abs(target_blend - current_blend) < 1e-3:
            self.state.animation_blend = target_blend
            return

        step = self._target_period / max(1e-3, ANIMATION_BLEND_DURATION)
        if target_blend > current_blend:
            self.state.animation_blend = min(target_blend, current_blend + step)
        else:
            self.state.animation_blend = max(target_blend, current_blend - step)

    def _update_face_tracking(self) -> None:
        update_face_tracking(self, FACE_DETECTED_THRESHOLD)

    def _update_idle_look_around(self) -> None:
        update_idle_look_around(
            self,
            inactivity_threshold_s=IDLE_INACTIVITY_THRESHOLD,
            legacy_probability=IDLE_LOOK_AROUND_PROBABILITY,
            yaw_range_deg=IDLE_LOOK_AROUND_YAW_RANGE,
            pitch_range_deg=IDLE_LOOK_AROUND_PITCH_RANGE,
            duration_s=IDLE_LOOK_AROUND_DURATION,
        )

    def _update_emotion_move(self) -> tuple[np.ndarray, tuple[float, float], float] | None:
        return update_emotion_move(self)

    def is_emotion_playing(self) -> bool:
        """Check if an emotion move is currently playing."""
        with self._emotion_move_lock:
            return self._emotion_move is not None

    def _compose_final_pose(self) -> tuple[np.ndarray, tuple[float, float], float]:
        return compose_final_pose(self)

    # =========================================================================
    # Internal: Robot control (runs in control loop)
    # =========================================================================

    def _issue_control_command(self, head_pose: np.ndarray, antennas: tuple[float, float], body_yaw: float) -> None:
        issue_control_command(self, head_pose, antennas, body_yaw)

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
        run_control_loop(self, max_control_dt_s=MAX_CONTROL_DT_S, face_detected_threshold=FACE_DETECTED_THRESHOLD)

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
