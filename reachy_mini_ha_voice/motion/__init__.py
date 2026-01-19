"""Motion control module for Reachy Mini.

This module handles all motion-related functionality:
- StateMachine: Movement state management (RobotState, MovementState)
- Smoothing: Interpolation and transition algorithms
- GestureActions: Gesture-to-action mapping
- Antenna: Antenna freeze/unfreeze control
- PoseComposer: Pose composition utilities

Note: MovementManager is in the parent module to avoid circular imports.
Import it directly: from reachy_mini_ha_voice.movement_manager import MovementManager
"""

from .state_machine import RobotState, MovementState, PendingAction, STATE_ANIMATION_MAP
from .smoothing import (
    ease_in_out_cubic,
    ease_out_cubic,
    lerp,
    lerp_angle,
    interpolate_pose,
    smooth_value,
    clamp,
    normalize_angle,
    pose_distance,
    blend_poses,
)
from .gesture_actions import (
    GestureAction,
    GestureMapping,
    GestureActionMapper,
    DEFAULT_GESTURE_MAPPINGS,
    load_gesture_mappings,
)
from .antenna import (
    AntennaController,
    AntennaState,
    ANTENNA_BLEND_DURATION,
    calculate_antenna_blend,
)
from .pose_composer import (
    PoseComponents,
    AntennaComponents,
    create_head_pose_matrix,
    compose_poses,
    extract_yaw_from_pose,
    clamp_body_yaw,
    compose_full_pose,
    compute_antenna_positions,
)

__all__ = [
    # State machine
    "RobotState",
    "MovementState",
    "PendingAction",
    "STATE_ANIMATION_MAP",
    # Smoothing
    "ease_in_out_cubic",
    "ease_out_cubic",
    "lerp",
    "lerp_angle",
    "interpolate_pose",
    "smooth_value",
    "clamp",
    "normalize_angle",
    "pose_distance",
    "blend_poses",
    # Gesture actions
    "GestureAction",
    "GestureMapping",
    "GestureActionMapper",
    "DEFAULT_GESTURE_MAPPINGS",
    "load_gesture_mappings",
    # Antenna control
    "AntennaController",
    "AntennaState",
    "ANTENNA_BLEND_DURATION",
    "calculate_antenna_blend",
    # Pose composition
    "PoseComponents",
    "AntennaComponents",
    "create_head_pose_matrix",
    "compose_poses",
    "extract_yaw_from_pose",
    "clamp_body_yaw",
    "compose_full_pose",
    "compute_antenna_positions",
]
