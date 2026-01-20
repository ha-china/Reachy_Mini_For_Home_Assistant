"""Movement state machine and state definitions.

This module contains the state machine for robot movement states
and related data structures.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class RobotState(Enum):
    """Robot state machine states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


# State to animation mapping
# Note: SPEAKING uses idle animation as base, with speech_sway offsets layered on top
STATE_ANIMATION_MAP = {
    "idle": "idle",
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "idle",  # Base animation only; actual motion from speech_sway
}


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

    # Note: Antenna freeze state is now managed by AntennaController (motion/antenna.py)

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
    callback: Callable | None = None
