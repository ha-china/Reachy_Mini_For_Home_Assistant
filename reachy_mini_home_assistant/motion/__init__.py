"""Motion control module for Reachy Mini.

This module handles all motion-related functionality:
- MovementManager: Core control loop composing target + animation + sway
- ReachyMiniMotion: High-level motion API
- StateMachine: Movement state management (RobotState, MovementState)
- Antenna: Antenna freeze/unfreeze control
- PoseComposer: Pose composition utilities (delegates to SDK)
- EmotionMoves: Emotion animation playback (via SDK RecordedMoves)
- AnimationPlayer: JSON-driven idle/speaking oscillators
"""

from .animation_player import AnimationPlayer
from .antenna import (
    ANTENNA_BLEND_DURATION,
    AntennaController,
    AntennaState,
    calculate_antenna_blend,
)
from .emotion_moves import EmotionMove, is_emotion_available, list_available_emotions
from .movement_manager import MovementManager
from .pose_composer import (
    clamp_body_yaw,
    compose_poses,
    create_head_pose_matrix,
    extract_yaw_from_pose,
)
from .reachy_motion import ReachyMiniMotion
from .state_machine import STATE_ANIMATION_MAP, MovementState, PendingAction, RobotState

__all__ = [
    "ANTENNA_BLEND_DURATION",
    "STATE_ANIMATION_MAP",
    "AnimationPlayer",
    "AntennaController",
    "AntennaState",
    "EmotionMove",
    "MovementManager",
    "MovementState",
    "PendingAction",
    "ReachyMiniMotion",
    "RobotState",
    "calculate_antenna_blend",
    "clamp_body_yaw",
    "compose_poses",
    "create_head_pose_matrix",
    "extract_yaw_from_pose",
    "is_emotion_available",
    "list_available_emotions",
]
