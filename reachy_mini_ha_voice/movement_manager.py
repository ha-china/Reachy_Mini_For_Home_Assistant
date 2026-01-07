"""
Unified Movement Manager for Reachy Mini.

This module provides a centralized control system for robot movements,
inspired by the reachy_mini_conversation_app architecture.

Key features:
- Single 20Hz control loop (balanced between responsiveness and stability)
- Command queue pattern (thread-safe external API)
- Error throttling (prevents log explosion)
- Speech-driven head sway (based on conversation_app's SwayRollRT)
- Breathing animation during idle (based on conversation_app's BreathingMove)
- Graceful shutdown
- Pose change detection (skip sending if no significant change)
- Robust connection recovery (faster reconnection attempts)
- Proper pose composition using SDK's compose_world_offset (same as conversation_app)
- Antenna freeze during listening mode with smooth blend back

SDK Analysis Notes:
- get_current_head_pose() and get_current_joint_positions() are non-blocking
  (they return cached Zenoh data from subscriptions)
- set_target() is the only method that sends Zenoh messages
- get_status() may trigger I/O, so it's cached in reachy_controller.py

Reference: reachy_mini_conversation_app/src/reachy_mini_conversation_app/moves.py
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
from scipy.spatial.transform import Rotation as R

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
# Constants (borrowed from conversation_app)
# =============================================================================

# Control loop frequency - CRITICAL for daemon stability
# The daemon's internal control loop runs at 50Hz.
# We use 10Hz to stay well below daemon capacity while maintaining smooth motion.
# Each set_target() call sends 3 Zenoh messages (head, antennas, body_yaw).
# At 10Hz × 3 = 30 messages/second, well within daemon's 50Hz capacity.
CONTROL_LOOP_FREQUENCY_HZ = 10  # 10Hz control loop (reduced from 20Hz for stability)
# SDK's get_current_head_pose() and get_current_joint_positions() are non-blocking
# (they return cached Zenoh data), so higher frequency is safe.
# Using 20Hz as a balance between responsiveness and stability.
TARGET_PERIOD = 1.0 / CONTROL_LOOP_FREQUENCY_HZ

# Speech sway parameters (from conversation_app SwayRollRT)
# Rotation amplitudes
SWAY_A_PITCH_DEG = 4.5   # Pitch amplitude (degrees)
SWAY_A_YAW_DEG = 7.5     # Yaw amplitude
SWAY_A_ROLL_DEG = 2.25   # Roll amplitude
# Rotation frequencies
SWAY_F_PITCH = 2.2       # Pitch frequency Hz
SWAY_F_YAW = 0.6         # Yaw frequency
SWAY_F_ROLL = 1.3        # Roll frequency
# Translation amplitudes (mm -> m)
SWAY_A_X_MM = 4.5        # X amplitude (mm)
SWAY_A_Y_MM = 3.75       # Y amplitude (mm)
SWAY_A_Z_MM = 2.25       # Z amplitude (mm)
# Translation frequencies
SWAY_F_X = 0.35          # X frequency Hz
SWAY_F_Y = 0.45          # Y frequency Hz
SWAY_F_Z = 0.25          # Z frequency Hz
# Master scale
SWAY_MASTER = 1.5        # Overall sway intensity multiplier

# Breathing parameters
BREATHING_Z_AMPLITUDE = 0.005  # 5mm
BREATHING_FREQUENCY = 0.1     # 0.1Hz (6 breaths per minute)
ANTENNA_SWAY_AMPLITUDE_DEG = 15.0  # 15 degrees
ANTENNA_FREQUENCY = 0.5       # 0.5Hz

# VAD parameters for speech detection
VAD_DB_ON = -35   # Start detection threshold
VAD_DB_OFF = -45  # Stop detection threshold

# Antenna freeze parameters (listening mode)
ANTENNA_BLEND_DURATION = 0.5  # Seconds to blend back from frozen state


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

    # Speech sway offsets (radians for rotation, meters for translation)
    speech_pitch: float = 0.0
    speech_yaw: float = 0.0
    speech_roll: float = 0.0
    speech_x: float = 0.0
    speech_y: float = 0.0
    speech_z: float = 0.0

    # Breathing offsets
    breathing_z: float = 0.0
    breathing_antenna_left: float = 0.0
    breathing_antenna_right: float = 0.0

    # Target pose (from actions)
    target_pitch: float = 0.0
    target_yaw: float = 0.0
    target_roll: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    target_antenna_left: float = 0.0
    target_antenna_right: float = 0.0
    target_body_yaw: float = 0.0

    # Timing
    last_activity_time: float = 0.0
    idle_start_time: float = 0.0

    # Speech sway state
    sway_time: float = 0.0
    sway_envelope: float = 0.0  # 0-1, smoothed VAD
    sway_phase_pitch: float = 0.0
    sway_phase_yaw: float = 0.0
    sway_phase_roll: float = 0.0
    sway_phase_x: float = 0.0
    sway_phase_y: float = 0.0
    sway_phase_z: float = 0.0

    # Breathing state
    breathing_time: float = 0.0
    breathing_active: bool = False

    # Antenna freeze state (listening mode)
    antenna_frozen: bool = False
    frozen_antenna_left: float = 0.0
    frozen_antenna_right: float = 0.0
    antenna_blend: float = 1.0  # 0=frozen, 1=normal
    antenna_blend_start_time: float = 0.0


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


class SpeechSwayGenerator:
    """
    Generates speech-driven head sway based on audio loudness.

    Uses multiple sine wave oscillators at different frequencies
    to create natural-looking "Lissajous" motion.
    Includes both rotation (pitch/yaw/roll) and translation (x/y/z).
    """

    def __init__(self, seed: int = 7):
        # Random initial phases (avoid mechanical feel)
        rng = np.random.default_rng(seed)
        self.phase_pitch = float(rng.random() * 2 * math.pi)
        self.phase_yaw = float(rng.random() * 2 * math.pi)
        self.phase_roll = float(rng.random() * 2 * math.pi)
        self.phase_x = float(rng.random() * 2 * math.pi)
        self.phase_y = float(rng.random() * 2 * math.pi)
        self.phase_z = float(rng.random() * 2 * math.pi)

        # State
        self.t = 0.0
        self.vad_on = False
        self.envelope = 0.0  # Smoothed VAD [0, 1]
        self.last_db = -100.0

    def reset(self):
        """Reset state."""
        self.t = 0.0
        self.vad_on = False
        self.envelope = 0.0
        self.last_db = -100.0

    def update(self, dt: float, loudness_db: float) -> Tuple[float, float, float, float, float, float]:
        """
        Update sway based on audio loudness.

        Args:
            dt: Time delta in seconds
            loudness_db: Audio loudness in dBFS

        Returns:
            Tuple of (pitch_rad, yaw_rad, roll_rad, x_m, y_m, z_m) offsets
        """
        self.t += dt
        self.last_db = loudness_db

        # VAD detection with hysteresis
        if loudness_db >= VAD_DB_ON:
            self.vad_on = True
        elif loudness_db <= VAD_DB_OFF:
            self.vad_on = False

        # Smooth envelope
        target = 1.0 if self.vad_on else 0.0
        self.envelope += 0.1 * (target - self.envelope)
        self.envelope = max(0.0, min(1.0, self.envelope))

        # Loudness mapping: -50dB -> 0, -20dB -> 1
        loud = max(0.0, min(1.0, (loudness_db + 50) / 30))

        # Apply master scale
        env = self.envelope * SWAY_MASTER

        # Generate rotation sway
        pitch = (math.radians(SWAY_A_PITCH_DEG) * loud * env *
                math.sin(2 * math.pi * SWAY_F_PITCH * self.t + self.phase_pitch))
        yaw = (math.radians(SWAY_A_YAW_DEG) * loud * env *
              math.sin(2 * math.pi * SWAY_F_YAW * self.t + self.phase_yaw))
        roll = (math.radians(SWAY_A_ROLL_DEG) * loud * env *
               math.sin(2 * math.pi * SWAY_F_ROLL * self.t + self.phase_roll))

        # Generate translation sway (mm -> m)
        x = (SWAY_A_X_MM / 1000.0 * loud * env *
             math.sin(2 * math.pi * SWAY_F_X * self.t + self.phase_x))
        y = (SWAY_A_Y_MM / 1000.0 * loud * env *
             math.sin(2 * math.pi * SWAY_F_Y * self.t + self.phase_y))
        z = (SWAY_A_Z_MM / 1000.0 * loud * env *
             math.sin(2 * math.pi * SWAY_F_Z * self.t + self.phase_z))

        return pitch, yaw, roll, x, y, z


class BreathingAnimation:
    """
    Generates idle breathing animation.

    Creates subtle Z-axis movement and antenna sway to make
    the robot appear more alive when idle.
    """

    def __init__(self):
        self.t = 0.0
        self.active = False
        self.blend = 0.0  # Blend factor for smooth transitions

    def reset(self):
        """Reset animation."""
        self.t = 0.0
        self.blend = 0.0

    def set_active(self, active: bool):
        """Set whether breathing is active."""
        self.active = active

    def update(self, dt: float) -> Tuple[float, float, float]:
        """
        Update breathing animation.

        Args:
            dt: Time delta in seconds

        Returns:
            Tuple of (z_offset_m, antenna_left_rad, antenna_right_rad)
        """
        self.t += dt

        # Smooth blend in/out
        target_blend = 1.0 if self.active else 0.0
        blend_speed = 0.5  # Blend over ~2 seconds
        self.blend += blend_speed * dt * (target_blend - self.blend)
        self.blend = max(0.0, min(1.0, self.blend))

        if self.blend < 0.001:
            return 0.0, 0.0, 0.0

        # Z breathing
        z_offset = (BREATHING_Z_AMPLITUDE * self.blend *
                   math.sin(2 * math.pi * BREATHING_FREQUENCY * self.t))

        # Antenna sway (opposite directions for natural look)
        antenna_angle = (math.radians(ANTENNA_SWAY_AMPLITUDE_DEG) * self.blend *
                        math.sin(2 * math.pi * ANTENNA_FREQUENCY * self.t))

        return z_offset, antenna_angle, -antenna_angle


class MovementManager:
    """
    Unified movement manager with 10Hz control loop.

    All external interactions go through the command queue,
    ensuring thread safety and preventing race conditions.
    
    Note: Frequency reduced from 100Hz to 10Hz to prevent daemon crashes
    caused by excessive Zenoh message traffic.
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

        # Initialize random phases for sway
        rng = np.random.default_rng(42)
        self.state.sway_phase_pitch = float(rng.random() * 2 * math.pi)
        self.state.sway_phase_yaw = float(rng.random() * 2 * math.pi)
        self.state.sway_phase_roll = float(rng.random() * 2 * math.pi)

        # Sub-modules
        self._speech_sway = SpeechSwayGenerator()
        self._breathing = BreathingAnimation()

        # Thread control
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Error throttling
        self._last_error_time = 0.0
        self._error_interval = 1.0  # Log at most once per second
        self._suppressed_errors = 0

        # Connection health tracking
        self._connection_lost = False
        self._last_successful_command = self._now()
        self._connection_timeout = 3.0  # 3 seconds without success = connection lost
        self._reconnect_attempt_interval = 2.0  # Try reconnecting every 2 seconds (faster recovery)
        self._last_reconnect_attempt = 0.0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # Reset connection state after 5 consecutive errors

        # Pending action
        self._pending_action: Optional[PendingAction] = None
        self._action_start_time: float = 0.0
        self._action_start_pose: Dict[str, float] = {}

        # Audio loudness (updated externally)
        self._audio_loudness_db: float = -100.0
        self._audio_lock = threading.Lock()

        # Pose change detection threshold
        # Increased from 0.002 to 0.005 to reduce unnecessary set_target() calls
        # 0.005 rad ≈ 0.29 degrees - still smooth enough for natural motion
        # This helps reduce Zenoh message traffic to the daemon
        self._last_sent_pose: Optional[Dict[str, float]] = None
        self._pose_change_threshold = 0.005
        
        # Face tracking offsets (from camera worker)
        self._face_tracking_offsets: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self._face_tracking_lock = threading.Lock()
        
        # Camera server reference for face tracking
        self._camera_server = None

        logger.info("MovementManager initialized")

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

    def update_audio_loudness(self, loudness_db: float) -> None:
        """Thread-safe: Update audio loudness for speech sway."""
        with self._audio_lock:
            self._audio_loudness_db = loudness_db

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

            # State transition logic
            if payload == RobotState.IDLE and old_state != RobotState.IDLE:
                self.state.idle_start_time = self._now()
                self._breathing.set_active(True)
                self._speech_sway.reset()
                # Unfreeze antennas when returning to idle
                self._start_antenna_unfreeze()
            elif payload != RobotState.IDLE:
                self._breathing.set_active(False)

            if payload == RobotState.SPEAKING:
                self._speech_sway.reset()

            # Freeze antennas when entering listening mode
            if payload == RobotState.LISTENING:
                self._freeze_antennas()
            elif old_state == RobotState.LISTENING and payload != RobotState.LISTENING:
                # Start unfreezing when leaving listening mode
                self._start_antenna_unfreeze()

            logger.debug("State changed: %s -> %s", old_state.value, payload.value)

        elif cmd == "action":
            self._start_action(payload)

        elif cmd == "nod":
            amplitude_deg, duration = payload
            self._do_nod(amplitude_deg, duration)

        elif cmd == "shake":
            amplitude_deg, duration = payload
            self._do_shake(amplitude_deg, duration)

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
            self._pending_action = None

    def _update_speech_sway(self, dt: float) -> None:
        """Update speech-driven head sway."""
        if self.state.robot_state != RobotState.SPEAKING:
            # Decay sway when not speaking
            self.state.speech_pitch *= 0.9
            self.state.speech_yaw *= 0.9
            self.state.speech_roll *= 0.9
            self.state.speech_x *= 0.9
            self.state.speech_y *= 0.9
            self.state.speech_z *= 0.9
            return

        # Get current audio loudness
        with self._audio_lock:
            loudness_db = self._audio_loudness_db

        # Update sway generator
        pitch, yaw, roll, x, y, z = self._speech_sway.update(dt, loudness_db)

        self.state.speech_pitch = pitch
        self.state.speech_yaw = yaw
        self.state.speech_roll = roll
        self.state.speech_x = x
        self.state.speech_y = y
        self.state.speech_z = z

    def _update_breathing(self, dt: float) -> None:
        """Update breathing animation."""
        z_offset, antenna_left, antenna_right = self._breathing.update(dt)

        self.state.breathing_z = z_offset
        self.state.breathing_antenna_left = antenna_left
        self.state.breathing_antenna_right = antenna_right

    def _freeze_antennas(self) -> None:
        """Freeze antennas at current position (for listening mode)."""
        # Capture current antenna positions
        current_left = self.state.target_antenna_left + self.state.breathing_antenna_left
        current_right = self.state.target_antenna_right + self.state.breathing_antenna_right

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

    def _update_face_tracking(self) -> None:
        """Get face tracking offsets from camera server."""
        if self._camera_server is not None:
            try:
                offsets = self._camera_server.get_face_tracking_offsets()
                with self._face_tracking_lock:
                    self._face_tracking_offsets = offsets
            except Exception as e:
                logger.debug("Error getting face tracking offsets: %s", e)

    def _compose_final_pose(self) -> Dict[str, float]:
        """Compose final pose from all sources.
        
        Uses SDK's compose_world_offset for proper pose composition (same as conversation_app).
        Primary pose comes from actions, secondary offsets come from speech sway and face tracking.
        """
        # Build primary head pose matrix (from actions)
        if SDK_UTILS_AVAILABLE:
            primary_head = create_head_pose(
                x=self.state.target_x,
                y=self.state.target_y,
                z=self.state.target_z,
                roll=self.state.target_roll,
                pitch=self.state.target_pitch,
                yaw=self.state.target_yaw,
                degrees=False,  # Our state is in radians
                mm=False,       # Our state is in meters
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

        # Build secondary offset pose (speech sway + face tracking + breathing)
        # Get face tracking offsets
        with self._face_tracking_lock:
            face_offsets = self._face_tracking_offsets
        
        # Combine all secondary offsets
        secondary_x = self.state.speech_x + face_offsets[0]
        secondary_y = self.state.speech_y + face_offsets[1]
        secondary_z = self.state.speech_z + self.state.breathing_z + face_offsets[2]
        secondary_roll = self.state.speech_roll + face_offsets[3]
        secondary_pitch = self.state.speech_pitch + face_offsets[4]
        secondary_yaw = self.state.speech_yaw + face_offsets[5]

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
            # Compose using SDK utility (same as conversation_app)
            combined_head = compose_world_offset(primary_head, secondary_head, reorthonormalize=True)
        else:
            # Fallback: simple addition (less accurate but works)
            secondary_rotation = R.from_euler('xyz', [secondary_roll, secondary_pitch, secondary_yaw])
            secondary_head = np.eye(4)
            secondary_head[:3, :3] = secondary_rotation.as_matrix()
            secondary_head[0, 3] = secondary_x
            secondary_head[1, 3] = secondary_y
            secondary_head[2, 3] = secondary_z
            
            # Simple composition: R_final = R_secondary @ R_primary, t_final = t_primary + t_secondary
            combined_head = np.eye(4)
            combined_head[:3, :3] = secondary_head[:3, :3] @ primary_head[:3, :3]
            combined_head[:3, 3] = primary_head[:3, 3] + secondary_head[:3, 3]

        # Extract final pose values from combined matrix
        final_rotation = R.from_matrix(combined_head[:3, :3])
        final_roll, final_pitch, final_yaw = final_rotation.as_euler('xyz')
        final_x = combined_head[0, 3]
        final_y = combined_head[1, 3]
        final_z = combined_head[2, 3]

        # Antenna pose with freeze blending
        target_antenna_left = self.state.target_antenna_left + self.state.breathing_antenna_left
        target_antenna_right = self.state.target_antenna_right + self.state.breathing_antenna_right

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

        return {
            "pitch": final_pitch,
            "yaw": final_yaw,
            "roll": final_roll,
            "x": final_x,
            "y": final_y,
            "z": final_z,
            "antenna_left": antenna_left,
            "antenna_right": antenna_right,
            "body_yaw": self.state.target_body_yaw,
        }

    # =========================================================================
    # Internal: Robot control (runs in control loop)
    # =========================================================================

    def _issue_control_command(self, pose: Dict[str, float]) -> None:
        """Send control command to robot with error throttling and connection health tracking."""
        if self.robot is None:
            return

        # Check if pose changed significantly (prevent unnecessary commands)
        if self._last_sent_pose is not None:
            max_diff = max(
                abs(pose[k] - self._last_sent_pose.get(k, 0.0))
                for k in pose.keys()
            )
            if max_diff < self._pose_change_threshold:
                # No significant change, skip sending command
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
            # Build head pose matrix
            # SDK uses 'xyz' euler order with [roll, pitch, yaw]
            rotation = R.from_euler('xyz', [
                pose["roll"],
                pose["pitch"],
                pose["yaw"],
            ])

            head_pose = np.eye(4)
            head_pose[:3, :3] = rotation.as_matrix()
            head_pose[0, 3] = pose["x"]
            head_pose[1, 3] = pose["y"]
            head_pose[2, 3] = pose["z"]

            # Send to robot (single control point!)
            self.robot.set_target(
                head=head_pose,
                antennas=[pose["antenna_right"], pose["antenna_left"]],
                body_yaw=pose["body_yaw"],
            )

            # Command succeeded - update connection health and cache
            self._last_successful_command = now
            self._last_sent_pose = pose.copy()  # Cache sent pose
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
                        self._log_error_throttled(f"Transient connection error ({self._consecutive_errors}/{self._max_consecutive_errors}): {error_msg}")
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
        """Main 5Hz control loop."""
        logger.info("Movement manager control loop started (%.0f Hz)", CONTROL_LOOP_FREQUENCY_HZ)

        last_time = self._now()

        while not self._stop_event.is_set():
            loop_start = self._now()
            dt = loop_start - last_time
            last_time = loop_start

            try:
                # 1. Process commands from queue
                self._poll_commands()

                # 2. Update action interpolation
                self._update_action(dt)

                # 3. Update speech sway
                self._update_speech_sway(dt)

                # 4. Update breathing animation
                self._update_breathing(dt)

                # 5. Update antenna blend (listening mode freeze/unfreeze)
                self._update_antenna_blend(dt)
                
                # 6. Update face tracking offsets from camera server
                self._update_face_tracking()

                # 7. Compose final pose
                pose = self._compose_final_pose()

                # 8. Send to robot (single control point!)
                self._issue_control_command(pose)

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
        self._thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name="MovementManager",
        )
        self._thread.start()
        logger.info("Movement manager started")

    def stop(self) -> None:
        """Stop the control loop and reset robot."""
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping movement manager...")

        # Signal stop
        self._stop_event.set()

        # Wait for thread
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("Movement manager thread did not stop in time")

        # Reset robot to neutral
        self._reset_to_neutral_blocking()

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
                duration=1.0,
            )
            logger.info("Robot reset to neutral position")
        except Exception as e:
            logger.error("Failed to reset robot: %s", e)

    @property
    def is_running(self) -> bool:
        """Check if control loop is running."""
        return self._thread is not None and self._thread.is_alive()
