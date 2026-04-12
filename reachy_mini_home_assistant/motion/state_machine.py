"""Movement state machine and related motion data structures.

This module now also contains idle-behavior data helpers so the control-loop
implementation can stay focused on runtime orchestration.
"""

import json
import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..animations.animation_config import load_animation_config

logger = logging.getLogger(__name__)


class RobotState(Enum):
    """Robot state machine states."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


# State to animation mapping
# SPEAKING uses a dedicated antenna-forward animation while speech_sway
# continues to drive the head motion on top.
STATE_ANIMATION_MAP = {
    "idle": "idle",
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "speaking",
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
    target_antenna_left: float = 0.0
    target_antenna_right: float = 0.0
    duration: float = 0.5
    callback: Callable | None = None


@dataclass
class IdleRestPose:
    """Low-energy rest pose used when idle behavior is disabled."""

    pitch_rad: float
    antenna_left_rad: float
    antenna_right_rad: float


@dataclass
class IdleBehaviorConfig:
    """Parsed idle behavior configuration from the unified JSON file."""

    rest_pose: IdleRestPose
    min_interval_s: float
    max_interval_s: float
    trigger_probability: float
    actions: list[dict[str, Any]]


def parse_numeric_range(value: Any, default_min: float, default_max: float) -> tuple[float, float]:
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


def load_idle_behavior_config(
    *,
    config_path: Path,
    default_rest_pose: dict[str, float],
    default_actions: list[dict[str, Any]],
    default_min_interval_s: float,
    default_max_interval_s: float,
    default_probability: float,
    default_yaw_range_deg: float,
    default_pitch_range_deg: float,
    default_duration_s: float,
) -> IdleBehaviorConfig:
    """Load idle behavior configuration from the unified animation file."""
    actions = list(default_actions)
    rest_pose = IdleRestPose(
        pitch_rad=math.radians(float(default_rest_pose["pitch_deg"])),
        antenna_left_rad=float(default_rest_pose["antenna_left_rad"]),
        antenna_right_rad=float(default_rest_pose["antenna_right_rad"]),
    )
    min_interval_s = default_min_interval_s
    max_interval_s = default_max_interval_s
    trigger_probability = default_probability

    if not config_path.exists():
        logger.debug("Idle behavior config file not found: %s", config_path)
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, actions)

    try:
        config = load_animation_config(config_path)
    except Exception as e:
        logger.warning("Failed to read idle behavior config: %s", e)
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, actions)

    rest_pose_section = config.get("idle_rest_pose")
    if isinstance(rest_pose_section, dict):
        try:
            rest_pose.pitch_rad = math.radians(
                float(rest_pose_section.get("pitch_deg", default_rest_pose["pitch_deg"]))
            )
        except (TypeError, ValueError):
            pass
        try:
            rest_pose.antenna_left_rad = float(
                rest_pose_section.get("antenna_left_rad", default_rest_pose["antenna_left_rad"])
            )
        except (TypeError, ValueError):
            pass
        try:
            rest_pose.antenna_right_rad = float(
                rest_pose_section.get("antenna_right_rad", default_rest_pose["antenna_right_rad"])
            )
        except (TypeError, ValueError):
            pass

    section = config.get("idle_random_actions")
    if not isinstance(section, dict):
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, actions)

    try:
        min_interval = float(section.get("min_interval_s", default_min_interval_s))
        max_interval = float(section.get("max_interval_s", default_max_interval_s))
        if min_interval > max_interval:
            min_interval, max_interval = max_interval, min_interval
        min_interval_s = max(0.5, min_interval)
        max_interval_s = max(min_interval_s, max_interval)
    except (TypeError, ValueError):
        min_interval_s = default_min_interval_s
        max_interval_s = default_max_interval_s

    try:
        probability = float(section.get("trigger_probability", default_probability))
    except (TypeError, ValueError):
        probability = default_probability
    trigger_probability = max(0.0, min(1.0, probability))

    raw_actions = section.get("actions")
    if not isinstance(raw_actions, list):
        return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, actions)

    parsed_actions: list[dict[str, Any]] = []
    for idx, action in enumerate(raw_actions):
        if not isinstance(action, dict):
            continue

        name = str(action.get("name", f"idle_action_{idx + 1}"))
        try:
            weight = float(action.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if weight <= 0.0:
            continue

        try:
            duration_s = max(0.2, float(action.get("duration_s", default_duration_s)))
        except (TypeError, ValueError):
            duration_s = default_duration_s

        yaw_min, yaw_max = parse_numeric_range(
            action.get("yaw_range_deg"), -default_yaw_range_deg, default_yaw_range_deg
        )
        pitch_min, pitch_max = parse_numeric_range(
            action.get("pitch_range_deg"), -default_pitch_range_deg, default_pitch_range_deg
        )
        roll_min, roll_max = parse_numeric_range(action.get("roll_range_deg"), 0.0, 0.0)
        x_min, x_max = parse_numeric_range(action.get("x_range_m"), 0.0, 0.0)
        y_min, y_max = parse_numeric_range(action.get("y_range_m"), 0.0, 0.0)
        z_min, z_max = parse_numeric_range(action.get("z_range_m"), 0.0, 0.0)

        parsed_actions.append(
            {
                "name": name,
                "weight": weight,
                "duration_s": duration_s,
                "yaw_range_deg": (yaw_min, yaw_max),
                "pitch_range_deg": (pitch_min, pitch_max),
                "roll_range_deg": (roll_min, roll_max),
                "x_range_m": (x_min, x_max),
                "y_range_m": (y_min, y_max),
                "z_range_m": (z_min, z_max),
            }
        )

    if parsed_actions:
        actions = parsed_actions

    return IdleBehaviorConfig(rest_pose, min_interval_s, max_interval_s, trigger_probability, actions)


def pick_idle_random_action(actions: list[dict[str, Any]], fallback_actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick one idle random action from weighted definitions."""
    action_pool = actions or fallback_actions
    if not action_pool:
        return {}

    weights = [max(0.0, float(action.get("weight", 1.0))) for action in action_pool]
    total_weight = sum(weights)
    if total_weight <= 0.0:
        return random.choice(action_pool)
    return random.choices(action_pool, weights=weights, k=1)[0]


def build_idle_pending_action(action_config: dict[str, Any], *, default_duration_s: float) -> PendingAction:
    """Convert one idle action config entry into a `PendingAction`."""
    yaw_min, yaw_max = action_config.get("yaw_range_deg", (0.0, 0.0))
    pitch_min, pitch_max = action_config.get("pitch_range_deg", (0.0, 0.0))
    roll_min, roll_max = action_config.get("roll_range_deg", (0.0, 0.0))
    x_min, x_max = action_config.get("x_range_m", (0.0, 0.0))
    y_min, y_max = action_config.get("y_range_m", (0.0, 0.0))
    z_min, z_max = action_config.get("z_range_m", (0.0, 0.0))
    duration = float(action_config.get("duration_s", default_duration_s))

    return PendingAction(
        name=f"idle_action:{action_config.get('name', 'random')}",
        target_yaw=math.radians(random.uniform(float(yaw_min), float(yaw_max))),
        target_pitch=math.radians(random.uniform(float(pitch_min), float(pitch_max))),
        target_roll=math.radians(random.uniform(float(roll_min), float(roll_max))),
        target_x=random.uniform(float(x_min), float(x_max)),
        target_y=random.uniform(float(y_min), float(y_max)),
        target_z=random.uniform(float(z_min), float(z_max)),
        duration=max(0.2, duration),
    )
