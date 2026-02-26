"""Motion control module for Reachy Mini.

This module handles all motion-related functionality:
- MovementManager: Core 100Hz motion control loop
- ReachyMiniMotion: High-level motion API
- StateMachine: Movement state management (RobotState, MovementState)
- Smoothing: Interpolation and transition algorithms
- GestureActions: Gesture-to-action mapping
- Antenna: Antenna freeze/unfreeze control
- PoseComposer: Pose composition utilities
- EmotionMoves: Emotion animation playback
- SpeechSway: Speech-driven head motion
- AnimationPlayer: Animation playback system
"""

from .animation_player import AnimationPlayer
from .antenna import (
    ANTENNA_BLEND_DURATION,
    AntennaController,
    AntennaState,
    calculate_antenna_blend,
)
from .emotion_moves import EmotionMove, is_emotion_available, list_available_emotions
from .gesture_actions import (
    DEFAULT_GESTURE_MAPPINGS,
    GestureAction,
    GestureActionMapper,
    GestureMapping,
    load_gesture_mappings,
)
from .movement_manager import MovementManager
from .pose_composer import (
    AntennaComponents,
    PoseComponents,
    clamp_body_yaw,
    compose_full_pose,
    compose_poses,
    compute_antenna_positions,
    create_head_pose_matrix,
    extract_yaw_from_pose,
)
from .reachy_motion import ReachyMiniMotion
from .smoothing import (
    blend_poses,
    clamp,
    ease_in_out_cubic,
    ease_out_cubic,
    interpolate_pose,
    lerp,
    lerp_angle,
    normalize_angle,
    pose_distance,
    smooth_value,
)
from .speech_sway import SpeechSwayRT, analyze_audio_for_sway
from .state_machine import STATE_ANIMATION_MAP, MovementState, PendingAction, RobotState

__all__ = [
    "ANTENNA_BLEND_DURATION",
    "DEFAULT_GESTURE_MAPPINGS",
    "STATE_ANIMATION_MAP",
    # Animation
    "AnimationPlayer",
    "AntennaComponents",
    # Antenna control
    "AntennaController",
    "AntennaState",
    # Emotion moves
    "EmotionMove",
    # Gesture actions
    "GestureAction",
    "GestureActionMapper",
    "GestureMapping",
    # Core motion control
    "MovementManager",
    "MovementState",
    "PendingAction",
    # Pose composition
    "PoseComponents",
    "ReachyMiniMotion",
    # State machine
    "RobotState",
    # Speech sway
    "SpeechSwayRT",
    "analyze_audio_for_sway",
    "blend_poses",
    "calculate_antenna_blend",
    "clamp",
    "clamp_body_yaw",
    "compose_full_pose",
    "compose_poses",
    "compute_antenna_positions",
    "create_head_pose_matrix",
    # Smoothing
    "ease_in_out_cubic",
    "ease_out_cubic",
    "extract_yaw_from_pose",
    "interpolate_pose",
    "is_emotion_available",
    "lerp",
    "lerp_angle",
    "list_available_emotions",
    "load_gesture_mappings",
    "normalize_angle",
    "pose_distance",
    "smooth_value",
]
