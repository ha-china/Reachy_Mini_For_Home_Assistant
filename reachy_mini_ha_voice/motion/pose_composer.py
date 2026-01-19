"""Pose composition module for Reachy Mini.

This module provides utilities for composing robot head poses from
multiple sources (target, animation, face tracking, speech sway).

The composition logic follows the reachy_mini_conversation_app approach:
1. Build primary pose from target state
2. Build secondary pose from animation + face tracking + speech sway
3. Compose using SDK's compose_world_offset for proper rotation composition
"""

import logging
import math
from dataclasses import dataclass
from typing import Tuple, Optional, List

import numpy as np

logger = logging.getLogger(__name__)

# Try to import SDK utilities
try:
    from reachy_mini.utils import create_head_pose
    from reachy_mini.utils.interpolation import compose_world_offset
    SDK_UTILS_AVAILABLE = True
except ImportError:
    SDK_UTILS_AVAILABLE = False
    logger.debug("SDK utils not available, using fallback pose composition")

# Try to import scipy for rotation handling
try:
    from scipy.spatial.transform import Rotation as R
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available, some pose functions may not work")


# Body yaw safety limits (matches SDK's inverse_kinematics_safe constraints)
MAX_BODY_YAW_RAD = math.radians(160.0)
MIN_BODY_YAW_RAD = math.radians(-160.0)


@dataclass
class PoseComponents:
    """Container for pose components.

    All angles are in radians, positions in meters.
    """

    # Translation
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    # Rotation (euler xyz)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@dataclass
class AntennaComponents:
    """Container for antenna components."""

    target_left: float = 0.0
    target_right: float = 0.0
    anim_left: float = 0.0
    anim_right: float = 0.0


def create_head_pose_matrix(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    roll: float = 0.0,
    pitch: float = 0.0,
    yaw: float = 0.0,
) -> np.ndarray:
    """Create a 4x4 head pose matrix from position and rotation.

    Uses SDK's create_head_pose if available, otherwise builds manually.

    Args:
        x, y, z: Position in meters
        roll, pitch, yaw: Rotation in radians (euler xyz)

    Returns:
        4x4 numpy array representing the pose
    """
    if SDK_UTILS_AVAILABLE:
        return create_head_pose(
            x=x, y=y, z=z,
            roll=roll, pitch=pitch, yaw=yaw,
            degrees=False, mm=False,
        )

    # Fallback: build matrix manually
    if SCIPY_AVAILABLE:
        rotation = R.from_euler('xyz', [roll, pitch, yaw])
        pose = np.eye(4, dtype=np.float64)
        pose[:3, :3] = rotation.as_matrix()
        pose[0, 3] = x
        pose[1, 3] = y
        pose[2, 3] = z
        return pose
    else:
        # Basic fallback without scipy
        pose = np.eye(4, dtype=np.float64)
        pose[0, 3] = x
        pose[1, 3] = y
        pose[2, 3] = z
        # Note: rotation is ignored without scipy
        logger.warning("Cannot create rotation matrix without scipy")
        return pose


def compose_poses(
    primary: np.ndarray,
    secondary: np.ndarray,
    reorthonormalize: bool = True,
) -> np.ndarray:
    """Compose two pose matrices.

    Uses SDK's compose_world_offset if available, otherwise does simple composition.

    Args:
        primary: Primary pose matrix (target)
        secondary: Secondary pose matrix (offsets)
        reorthonormalize: Whether to normalize the rotation matrix

    Returns:
        Composed 4x4 pose matrix
    """
    if SDK_UTILS_AVAILABLE:
        return compose_world_offset(primary, secondary, reorthonormalize=reorthonormalize)

    # Fallback: simple composition
    # R_final = R_secondary @ R_primary, t_final = t_primary + t_secondary
    if SCIPY_AVAILABLE:
        final = np.eye(4, dtype=np.float64)
        final[:3, :3] = secondary[:3, :3] @ primary[:3, :3]
        final[:3, 3] = primary[:3, 3] + secondary[:3, 3]
        return final
    else:
        # Without scipy, just add translations
        final = primary.copy()
        final[:3, 3] = primary[:3, 3] + secondary[:3, 3]
        return final


def extract_yaw_from_pose(pose: np.ndarray) -> float:
    """Extract yaw angle from a 4x4 pose matrix.

    Args:
        pose: 4x4 pose matrix

    Returns:
        Yaw angle in radians
    """
    if not SCIPY_AVAILABLE:
        return 0.0

    rotation = R.from_matrix(pose[:3, :3])
    _, _, yaw = rotation.as_euler('xyz')
    return yaw


def clamp_body_yaw(yaw: float) -> float:
    """Clamp body yaw to safe range.

    SDK's inverse_kinematics_safe limits body_yaw to ±160°.

    Args:
        yaw: Yaw angle in radians

    Returns:
        Clamped yaw angle in radians
    """
    return max(MIN_BODY_YAW_RAD, min(MAX_BODY_YAW_RAD, yaw))


def compose_full_pose(
    target: PoseComponents,
    animation: PoseComponents,
    face_offsets: Tuple[float, float, float, float, float, float],
    sway: PoseComponents,
    animation_blend: float = 1.0,
) -> Tuple[np.ndarray, float]:
    """Compose full head pose from all sources.

    Args:
        target: Target pose components
        animation: Animation pose components
        face_offsets: Face tracking offsets (x, y, z, roll, pitch, yaw)
        sway: Speech sway pose components
        animation_blend: Blend factor for animation (0=suppressed, 1=full)

    Returns:
        Tuple of (head_pose_4x4, head_yaw)
    """
    # Build primary head pose from target
    primary_head = create_head_pose_matrix(
        x=target.x, y=target.y, z=target.z,
        roll=target.roll, pitch=target.pitch, yaw=target.yaw,
    )

    # Apply animation blend factor
    anim_x = animation.x * animation_blend
    anim_y = animation.y * animation_blend
    anim_z = animation.z * animation_blend
    anim_roll = animation.roll * animation_blend
    anim_pitch = animation.pitch * animation_blend
    anim_yaw = animation.yaw * animation_blend

    # Combine secondary sources
    secondary_x = anim_x + sway.x + face_offsets[0]
    secondary_y = anim_y + sway.y + face_offsets[1]
    secondary_z = anim_z + sway.z + face_offsets[2]
    secondary_roll = anim_roll + sway.roll + face_offsets[3]
    secondary_pitch = anim_pitch + sway.pitch + face_offsets[4]
    secondary_yaw = anim_yaw + sway.yaw + face_offsets[5]

    # Build secondary head pose
    secondary_head = create_head_pose_matrix(
        x=secondary_x, y=secondary_y, z=secondary_z,
        roll=secondary_roll, pitch=secondary_pitch, yaw=secondary_yaw,
    )

    # Compose poses
    final_head = compose_poses(primary_head, secondary_head)

    # Extract yaw for body following
    head_yaw = extract_yaw_from_pose(final_head)

    return final_head, head_yaw


def compute_antenna_positions(
    antenna: AntennaComponents,
    animation_blend: float = 1.0,
    freeze_blend: float = 1.0,
    frozen_left: float = 0.0,
    frozen_right: float = 0.0,
) -> Tuple[float, float]:
    """Compute final antenna positions with blending.

    Args:
        antenna: Antenna target and animation components
        animation_blend: Blend factor for animation (0=suppressed, 1=full)
        freeze_blend: Freeze blend factor (0=frozen, 1=unfrozen)
        frozen_left: Frozen left antenna position
        frozen_right: Frozen right antenna position

    Returns:
        Tuple of (left_position, right_position)
    """
    # Apply animation blend
    anim_left = antenna.anim_left * animation_blend
    anim_right = antenna.anim_right * animation_blend

    target_left = antenna.target_left + anim_left
    target_right = antenna.target_right + anim_right

    # Apply freeze blending
    if freeze_blend < 1.0:
        left = frozen_left * (1.0 - freeze_blend) + target_left * freeze_blend
        right = frozen_right * (1.0 - freeze_blend) + target_right * freeze_blend
    else:
        left = target_left
        right = target_right

    return left, right
