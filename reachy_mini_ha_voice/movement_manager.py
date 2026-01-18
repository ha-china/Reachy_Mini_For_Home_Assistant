"""
Unified Movement Manager for Reachy Mini.

This module provides a centralized control system for robot movements,
inspired by the reachy_mini_conversation_app architecture.

Key features:
- Single 100Hz control loop (same as reachy_mini_conversation_app)
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
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
from scipy.spatial.transform import Rotation as R

from .animation_player import AnimationPlayer
from .emotion_moves import EmotionMove, is_emotion_available

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)

# Import SDK utilities for pose composition (same as conversation_app)
try:
    from reachy_mini.utils import create_head_pose
    from reachy_mini.utils.interpolation import compose_world_offset
    SDK_UTILS_AVAILABLE = True
except ImportError:
    SDK_UTILS_AVAILABLE = False
    logger.warning("SDK utils not available, using fallback pose composition")


# =============================================================================
# Constants
# =============================================================================

# Control loop frequency - daemon now supports higher rates
CONTROL_LOOP_FREQUENCY_HZ = 100  # 100Hz control loop (same as conversation_app)
TARGET_PERIOD = 1.0 / CONTROL_LOOP_FREQUENCY_HZ

# Body yaw safety limits (matches SDK's inverse_kinematics_safe constraints)
# SDK limits body_yaw to ±160° and head-body relative angle to ±65°
MAX_BODY_YAW_RAD = math.radians(160.0)
MIN_BODY_YAW_RAD = math.radians(-160.0)

# Antenna freeze parameters (listening mode)
ANTENNA_BLEND_DURATION = 0.5  # Seconds to blend back from frozen state

# Animation suppression when face detected
FACE_DETECTED_THRESHOLD = 0.001  # Minimum offset magnitude to consider face detected
ANIMATION_BLEND_DURATION = 0.5  # Seconds to blend animation back when face lost

# Idle look-around behavior parameters
IDLE_LOOK_AROUND_MIN_INTERVAL = 8.0   # Minimum seconds between look-arounds
IDLE_LOOK_AROUND_MAX_INTERVAL = 20.0  # Maximum seconds between look-arounds
IDLE_LOOK_AROUND_YAW_RANGE = 25.0     # Maximum yaw angle in degrees
IDLE_LOOK_AROUND_PITCH_RANGE = 10.0   # Maximum pitch angle in degrees
IDLE_LOOK_AROUND_DURATION = 1.2       # Duration of look-around action in seconds
IDLE_INACTIVITY_THRESHOLD = 5.0       # Seconds of inactivity before look-around starts

# State to animation mapping
# Note: SPEAKING uses idle animation as base, with speech_sway offsets layered on top
STATE_ANIMATION_MAP = {
    "idle": "idle",
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "idle",  # Base animation only; actual motion from speech_sway
}


class RobotState(Enum):
    """Robot state machine states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class MovementState:
    """Internal movement state (only modified by control loop)."""
    # Current robot state
    robot_state: RobotState = RobotState.IDLE

    # Animation offsets (from AnimationPlayer)
    anim_pitch: float = 0.0
    anim_yaw: float = 0.0
    anim_roll: float = 0.0
    anim_x: float = 0.0
    anim_y: float = 0.0
    anim_z: float = 0.0
    anim_antenna_left: float = 0.0
    anim_antenna_right: float = 0.0

    # Speech sway offsets (from audio analysis)
    sway_pitch: float = 0.0
    sway_yaw: float = 0.0
    sway_roll: float = 0.0
    sway_x: float = 0.0
    sway_y: float = 0.0
    sway_z: float = 0.0

    # Target pose (from actions)
    target_pitch: float = 0.0
    target_yaw: float = 0.0
    target_roll: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    target_antenna_left: float = 0.0
    target_antenna_right: float = 0.0

    # Timing
    last_activity_time: float = 0.0
    idle_start_time: float = 0.0

    # Antenna freeze state (listening mode)
    antenna_frozen: bool = False
    frozen_antenna_left: float = 0.0
    frozen_antenna_right: float = 0.0
    antenna_blend: float = 1.0  # 0=frozen, 1=normal
    antenna_blend_start_time: float = 0.0

    # Idle look-around behavior
    next_look_around_time: float = 0.0
    look_around_in_progress: bool = False

    # Face tracking animation suppression
    face_detected: bool = False
    face_lost_time: float = 0.0
    animation_blend: float = 1.0  # 0=suppressed (face tracking), 1=full animation


@dataclass
class PendingAction:
    """A pending motion action."""
    name: str
    target_pitch: float = 0.0
    target_yaw: float = 0.0
    target_roll: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    duration: float = 0.5
    callback: Optional[Callable] = None


class MovementManager:
    """
    Unified movement manager with 100Hz control loop.

    All external interactions go through the command queue,
    ensuring thread safety and preventing race conditions.
    """

    def __init__(self, reachy_mini: Optional["ReachyMini"] = None):
        self.robot = reachy_mini
        self._now = time.monotonic

        # Command queue - all external threads communicate through this
        self._command_queue: Queue[Tuple[str, Any]] = Queue()

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
        self._thread: Optional[threading.Thread] = None

        # Error throttling
        self._last_error_time = 0.0
        self._error_interval = 2.0  # Log at most once per 2 seconds in error mode
        self._suppressed_errors = 0

        # Connection health tracking
        self._connection_lost = False
        self._last_successful_command = self._now()
        self._connection_timeout = 3.0
        self._reconnect_attempt_interval = 2.0
        self._last_reconnect_attempt = 0.0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

        # Pending action
        self._pending_action: Optional[PendingAction] = None
        self._action_start_time: float = 0.0
        self._action_start_pose: Dict[str, float] = {}

        # Face tracking offsets (from camera worker)
        self._face_tracking_offsets: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self._face_tracking_lock = threading.Lock()

        # Camera server reference for face tracking
        self._camera_server = None

        # Face tracking smoothing - DISABLED to match reference project
        # Reference project applies face tracking offsets directly without smoothing
        # Smoothing causes "lag" and "trailing" that looks unnatural
        # Only smooth interpolation when face is lost (handled in camera_server.py)
        self._smoothed_face_offsets: List[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        # self._face_smoothing_factor = 0.3  # DISABLED - direct application instead

        # Emotion move playback state
        self._emotion_move: Optional[EmotionMove] = None
        self._emotion_start_time: float = 0.0
        self._emotion_move_lock = threading.Lock()

        logger.info("MovementManager initialized with AnimationPlayer")

    # =========================================================================
    # Thread-safe public API (called from any thread)
    # =========================================================================

    def set_state(self, new_state: RobotState) -> None:
        """Thread-safe: Set robot state."""
        self._command_queue.put(("set_state", new_state))

    def set_listening(self, listening: bool) -> None:
        """Thread-safe: Set listening state."""
        state = RobotState.LISTENING if listening else RobotState.IDLE
        self._command_queue.put(("set_state", state))

    def set_thinking(self) -> None:
        """Thread-safe: Set thinking state."""
        self._command_queue.put(("set_state", RobotState.THINKING))

    def set_speaking(self, speaking: bool) -> None:
        """Thread-safe: Set speaking state."""
        state = RobotState.SPEAKING if speaking else RobotState.IDLE
        self._command_queue.put(("set_state", state))

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
            self._last_successful_command = self._now()
            logger.info("MovementManager resumed - robot reconnected")

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
        self._command_queue.put(("emotion_move", emotion_name))
        return True

    def queue_action(self, action: PendingAction) -> None:
        """Thread-safe: Queue a motion action."""
        self._command_queue.put(("action", action))

    def turn_to_angle(self, yaw_deg: float, duration: float = 0.8) -> None:
        """Thread-safe: Turn head to face a direction."""
        action = PendingAction(
            name="turn_to",
            target_yaw=math.radians(yaw_deg),
            duration=duration,
        )
        self._command_queue.put(("action", action))

    def nod(self, amplitude_deg: float = 15, duration: float = 0.5) -> None:
        """Thread-safe: Perform a nod gesture."""
        self._command_queue.put(("nod", (amplitude_deg, duration)))

    def shake(self, amplitude_deg: float = 20, duration: float = 0.5) -> None:
        """Thread-safe: Perform a head shake gesture."""
        self._command_queue.put(("shake", (amplitude_deg, duration)))

    def set_speech_sway(
        self, x: float, y: float, z: float,
        roll: float, pitch: float, yaw: float
    ) -> None:
        """Thread-safe: Set speech-driven sway offsets.

        These offsets are applied on top of the current animation
        to create audio-synchronized head motion during TTS playback.

        Args:
            x, y, z: Position offsets in meters
            roll, pitch, yaw: Orientation offsets in radians
        """
        self._command_queue.put(("speech_sway", (x, y, z, roll, pitch, yaw)))

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

    def set_face_tracking_offsets(self, offsets: Tuple[float, float, float, float, float, float]) -> None:
        """Thread-safe: Update face tracking offsets manually.

        Args:
            offsets: Tuple of (x, y, z, roll, pitch, yaw) in meters/radians
        """
        with self._face_tracking_lock:
            self._face_tracking_offsets = offsets

    def set_target_pose(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        roll: Optional[float] = None,
        pitch: Optional[float] = None,
        yaw: Optional[float] = None,
        antenna_left: Optional[float] = None,
        antenna_right: Optional[float] = None,
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
        self._command_queue.put(("set_pose", {
            "x": x,
            "y": y,
            "z": z,
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
            "antenna_left": antenna_left,
            "antenna_right": antenna_right,
        }))

    # =========================================================================
    # Internal: Command processing (runs in control loop)
    # =========================================================================

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
            animation_name = STATE_ANIMATION_MAP.get(payload.value, "idle")
            self._animation_player.set_animation(animation_name)

            # State transition logic
            if payload == RobotState.IDLE and old_state != RobotState.IDLE:
                self.state.idle_start_time = self._now()
                # Unfreeze antennas when returning to idle
                self._start_antenna_unfreeze()

            # Freeze antennas when entering listening mode
            if payload == RobotState.LISTENING:
                self._freeze_antennas()
            elif old_state == RobotState.LISTENING and payload != RobotState.LISTENING:
                # Start unfreezing when leaving listening mode
                self._start_antenna_unfreeze()

            logger.debug("State changed: %s -> %s, animation: %s",
                         old_state.value, payload.value, animation_name)

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

    def _start_emotion_move(self, emotion_name: str) -> None:
        """Start playing an emotion move.

        Creates an EmotionMove and sets it as the active emotion, which will
        be sampled in the control loop via _update_emotion_move().
        """
        if not is_emotion_available():
            logger.warning("Cannot play emotion '%s': emotion library not available",
                           emotion_name)
            return

        try:
            emotion_move = EmotionMove(emotion_name)
            with self._emotion_move_lock:
                self._emotion_move = emotion_move
                self._emotion_start_time = self._now()
            logger.info("Started emotion move: %s (duration=%.2fs)",
                        emotion_name, emotion_move.duration)
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
            return

        elapsed = self._now() - self._action_start_time
        progress = min(1.0, elapsed / self._pending_action.duration)

        # Smooth interpolation (ease in-out)
        t = progress * progress * (3 - 2 * progress)

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
            if self._pending_action.callback:
                try:
                    self._pending_action.callback()
                except Exception as e:
                    logger.error("Action callback error: %s", e)
            # Reset look-around state if this was a look-around action
            if self._pending_action.name == "look_around":
                self.state.look_around_in_progress = False
            self._pending_action = None

    def _update_animation(self, dt: float) -> None:
        """Update animation offsets from AnimationPlayer."""
        offsets = self._animation_player.get_offsets(dt)

        self.state.anim_pitch = offsets["pitch"]
        self.state.anim_yaw = offsets["yaw"]
        self.state.anim_roll = offsets["roll"]
        self.state.anim_x = offsets["x"]
        self.state.anim_y = offsets["y"]
        self.state.anim_z = offsets["z"]
        self.state.anim_antenna_left = offsets["antenna_left"]
        self.state.anim_antenna_right = offsets["antenna_right"]

    def _freeze_antennas(self) -> None:
        """Freeze antennas at current position (for listening mode)."""
        # Capture current antenna positions
        current_left = self.state.target_antenna_left + self.state.anim_antenna_left
        current_right = self.state.target_antenna_right + self.state.anim_antenna_right

        self.state.antenna_frozen = True
        self.state.frozen_antenna_left = current_left
        self.state.frozen_antenna_right = current_right
        self.state.antenna_blend = 0.0  # Fully frozen
        logger.debug("Antennas frozen at left=%.2f, right=%.2f",
                     math.degrees(current_left), math.degrees(current_right))

    def _start_antenna_unfreeze(self) -> None:
        """Start unfreezing antennas (smooth blend back to normal)."""
        if not self.state.antenna_frozen:
            return

        self.state.antenna_blend_start_time = self._now()
        logger.debug("Starting antenna unfreeze")

    def _update_antenna_blend(self, dt: float) -> None:
        """Update antenna blend state for smooth unfreezing."""
        if not self.state.antenna_frozen:
            return

        if self.state.antenna_blend >= 1.0:
            # Fully unfrozen
            self.state.antenna_frozen = False
            return

        # Calculate blend progress
        elapsed = self._now() - self.state.antenna_blend_start_time
        if elapsed > 0:
            self.state.antenna_blend = min(1.0, elapsed / ANTENNA_BLEND_DURATION)

            if self.state.antenna_blend >= 1.0:
                self.state.antenna_frozen = False
                logger.debug("Antennas unfrozen")

    def _update_animation_blend(self) -> None:
        """Update animation blend factor when face is lost.

        When face is detected, animation_blend is set to 0 immediately.
        When face is lost, we smoothly blend animation back to 1.0.
        """
        if self.state.face_detected:
            # Face is detected, keep animation suppressed
            return

        if self.state.animation_blend >= 1.0:
            # Already fully blended, nothing to do
            return

        # Calculate blend progress since face was lost
        elapsed = self._now() - self.state.face_lost_time
        if elapsed > 0:
            self.state.animation_blend = min(1.0, elapsed / ANIMATION_BLEND_DURATION)

            if self.state.animation_blend >= 1.0:
                logger.debug("Animation fully restored")

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

                with self._face_tracking_lock:
                    self._face_tracking_offsets = raw_offsets

                # Check if face is detected (any offset is non-zero)
                offset_magnitude = sum(abs(o) for o in raw_offsets)
                face_now_detected = offset_magnitude > FACE_DETECTED_THRESHOLD

                # Update face detection state
                if face_now_detected:
                    if not self.state.face_detected:
                        logger.debug("Face detected - suppressing breathing animation")
                    self.state.face_detected = True
                    self.state.animation_blend = 0.0  # Immediately suppress animation
                else:
                    if self.state.face_detected:
                        # Face just lost - start blend timer
                        self.state.face_lost_time = self._now()
                        logger.debug("Face lost - will restore animation after blend")
                    self.state.face_detected = False

            except Exception as e:
                logger.debug("Error getting face tracking offsets: %s", e)

    def _update_idle_look_around(self) -> None:
        """Trigger random look-around behavior when idle for a while.

        This adds life-like behavior to the robot by occasionally looking around
        when not engaged in conversation. Similar to conversation_app's idle behaviors.
        """
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
            interval = random.uniform(
                IDLE_LOOK_AROUND_MIN_INTERVAL,
                IDLE_LOOK_AROUND_MAX_INTERVAL
            )
            self.state.next_look_around_time = now + interval
            logger.debug("Scheduled next look-around in %.1fs", interval)
            return

        # Check if it's time for look-around
        if now >= self.state.next_look_around_time and not self.state.look_around_in_progress:
            # Generate random look direction
            target_yaw = random.uniform(
                -IDLE_LOOK_AROUND_YAW_RANGE,
                IDLE_LOOK_AROUND_YAW_RANGE
            )
            target_pitch = random.uniform(
                -IDLE_LOOK_AROUND_PITCH_RANGE,
                IDLE_LOOK_AROUND_PITCH_RANGE
            )

            # Create look-around action
            action = PendingAction(
                name="look_around",
                target_yaw=math.radians(target_yaw),
                target_pitch=math.radians(target_pitch),
                duration=IDLE_LOOK_AROUND_DURATION,
            )

            # Start the action
            self._start_action(action)
            self.state.look_around_in_progress = True

            # Schedule return to center and next look-around
            interval = random.uniform(
                IDLE_LOOK_AROUND_MIN_INTERVAL,
                IDLE_LOOK_AROUND_MAX_INTERVAL
            )
            self.state.next_look_around_time = now + IDLE_LOOK_AROUND_DURATION * 2 + interval

            logger.debug("Starting look-around: yaw=%.1f°, pitch=%.1f°",
                         target_yaw, target_pitch)

    def _update_emotion_move(self) -> Optional[Tuple[np.ndarray, Tuple[float, float], float]]:
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
                clamped_body_yaw = max(MIN_BODY_YAW_RAD, min(MAX_BODY_YAW_RAD, float(body_yaw)))

                return (head_pose, antenna_tuple, clamped_body_yaw)

            except Exception as e:
                logger.error("Error sampling emotion pose: %s", e)
                self._emotion_move = None
                return None

    def is_emotion_playing(self) -> bool:
        """Check if an emotion move is currently playing."""
        with self._emotion_move_lock:
            return self._emotion_move is not None

    def _compose_final_pose(self) -> Tuple[np.ndarray, Tuple[float, float], float]:
        """Compose final pose from all sources using SDK's compose_world_offset.

        Body yaw follows head yaw to enable natural head tracking with body rotation.
        When head turns beyond a threshold, body rotates to follow it, similar to
        how the reference project's sweep_look tool synchronizes body_yaw with head_yaw.

        Returns:
            Tuple of (head_pose_4x4, (antenna_right, antenna_left), body_yaw)
        """
        # Build primary head pose from target state
        if SDK_UTILS_AVAILABLE:
            primary_head = create_head_pose(
                x=self.state.target_x,
                y=self.state.target_y,
                z=self.state.target_z,
                roll=self.state.target_roll,
                pitch=self.state.target_pitch,
                yaw=self.state.target_yaw,
                degrees=False,
                mm=False,
            )
        else:
            # Fallback: build matrix manually
            rotation = R.from_euler('xyz', [
                self.state.target_roll,
                self.state.target_pitch,
                self.state.target_yaw,
            ])
            primary_head = np.eye(4)
            primary_head[:3, :3] = rotation.as_matrix()
            primary_head[0, 3] = self.state.target_x
            primary_head[1, 3] = self.state.target_y
            primary_head[2, 3] = self.state.target_z

        # Build secondary pose from animation + face tracking + speech sway
        with self._face_tracking_lock:
            face_offsets = self._face_tracking_offsets

        # Apply animation blend factor (0 when face detected, 1 when no face)
        # This suppresses breathing animation during face tracking
        anim_blend = self.state.animation_blend
        anim_x = self.state.anim_x * anim_blend
        anim_y = self.state.anim_y * anim_blend
        anim_z = self.state.anim_z * anim_blend
        anim_roll = self.state.anim_roll * anim_blend
        anim_pitch = self.state.anim_pitch * anim_blend
        anim_yaw = self.state.anim_yaw * anim_blend

        secondary_x = anim_x + self.state.sway_x + face_offsets[0]
        secondary_y = anim_y + self.state.sway_y + face_offsets[1]
        secondary_z = anim_z + self.state.sway_z + face_offsets[2]
        secondary_roll = anim_roll + self.state.sway_roll + face_offsets[3]
        secondary_pitch = anim_pitch + self.state.sway_pitch + face_offsets[4]
        secondary_yaw = anim_yaw + self.state.sway_yaw + face_offsets[5]

        if SDK_UTILS_AVAILABLE:
            secondary_head = create_head_pose(
                x=secondary_x,
                y=secondary_y,
                z=secondary_z,
                roll=secondary_roll,
                pitch=secondary_pitch,
                yaw=secondary_yaw,
                degrees=False,
                mm=False,
            )
            # Compose using SDK's compose_world_offset (same as conversation_app)
            final_head = compose_world_offset(primary_head, secondary_head, reorthonormalize=True)
        else:
            # Fallback: simple addition (less accurate but works)
            secondary_rotation = R.from_euler('xyz', [secondary_roll, secondary_pitch, secondary_yaw])
            secondary_head = np.eye(4)
            secondary_head[:3, :3] = secondary_rotation.as_matrix()
            secondary_head[0, 3] = secondary_x
            secondary_head[1, 3] = secondary_y
            secondary_head[2, 3] = secondary_z

            # Simple composition: R_final = R_secondary @ R_primary, t_final = t_primary + t_secondary
            final_head = np.eye(4)
            final_head[:3, :3] = secondary_head[:3, :3] @ primary_head[:3, :3]
            final_head[:3, 3] = primary_head[:3, 3] + secondary_head[:3, 3]

        # Antenna pose with freeze blending
        # Apply animation blend to antenna as well (suppress when face detected)
        anim_antenna_left = self.state.anim_antenna_left * anim_blend
        anim_antenna_right = self.state.anim_antenna_right * anim_blend

        target_antenna_left = self.state.target_antenna_left + anim_antenna_left
        target_antenna_right = self.state.target_antenna_right + anim_antenna_right

        # Apply antenna freeze blending (listening mode)
        blend = self.state.antenna_blend
        if blend < 1.0:
            # Blend between frozen position and target position
            antenna_left = (self.state.frozen_antenna_left * (1.0 - blend) +
                            target_antenna_left * blend)
            antenna_right = (self.state.frozen_antenna_right * (1.0 - blend) +
                             target_antenna_right * blend)
        else:
            antenna_left = target_antenna_left
            antenna_right = target_antenna_right

        # Calculate body_yaw to follow head yaw
        # Extract yaw from the final head pose rotation matrix
        # The rotation matrix uses xyz euler convention
        final_rotation = R.from_matrix(final_head[:3, :3])
        _, _, final_head_yaw = final_rotation.as_euler('xyz')

        # Body follows head yaw directly, clamped to safe range
        # SDK's inverse_kinematics_safe limits body_yaw to ±160°
        body_yaw = max(MIN_BODY_YAW_RAD, min(MAX_BODY_YAW_RAD, final_head_yaw))

        return final_head, (antenna_right, antenna_left), body_yaw

    # =========================================================================
    # Internal: Robot control (runs in control loop)
    # =========================================================================

    def _issue_control_command(self, head_pose: np.ndarray, antennas: Tuple[float, float], body_yaw: float) -> None:
        """Send control command to robot with error throttling and connection health tracking.

        Body yaw follows head yaw for natural tracking. The SDK's automatic_body_yaw
        mechanism (inverse_kinematics_safe) handles collision prevention.

        Args:
            head_pose: 4x4 head pose matrix
            antennas: Tuple of (right_angle, left_angle) in radians
            body_yaw: Body yaw angle (follows head yaw for natural tracking)
        """
        if self.robot is None:
            return

        # Skip sending commands during graceful shutdown drain phase
        # This prevents partial command transmission that can crash daemon
        if self._draining_event.is_set():
            return

        # Skip sending commands while emotion animation is playing
        # This prevents "a move is currently running" warning spam
        if self._emotion_playing_event.is_set():
            return

        now = self._now()

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

            if self._connection_lost:
                logger.info("✓ Connection to robot restored")
                self._connection_lost = False
                self._suppressed_errors = 0

        except Exception as e:
            error_msg = str(e)
            self._consecutive_errors += 1

            # Check if this is a connection error
            is_connection_error = "Lost connection" in error_msg or "ZError" in error_msg

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
                        self._log_error_throttled(
                            f"Transient connection error ({err_cnt}/{max_err}): {error_msg}")
                else:
                    # Already in lost state, use throttled logging
                    self._log_error_throttled(f"Connection still lost: {error_msg}")
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
        """Main 100Hz control loop."""
        logger.info("Movement manager control loop started (%.0f Hz)", CONTROL_LOOP_FREQUENCY_HZ)

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
                    # Just wait and check again
                    time.sleep(0.1)
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
            sleep_time = max(0.0, TARGET_PERIOD - elapsed)
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
        # At 100Hz, one cycle is 10ms, so 50ms (5 cycles) is plenty
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
        if self.robot is None:
            return

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
