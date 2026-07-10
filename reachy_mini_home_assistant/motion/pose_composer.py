"""Pose composition module for Reachy Mini.

All pose math delegates to the SDK's utilities:
- ``create_head_pose`` from ``reachy_mini.utils``
- ``compose_world_offset`` from ``reachy_mini.utils.interpolation``

The only project-specific helpers retained here are body-yaw clamping
(mirrors the daemon-side IK safety limits so our local smoothing math
stays in range) and yaw extraction from a pose matrix.
"""

import logging
import math

import numpy as np
from reachy_mini.utils import create_head_pose
from reachy_mini.utils.interpolation import compose_world_offset
from scipy.spatial.transform import Rotation as R

logger = logging.getLogger(__name__)

# Body yaw safety limits (mirror SDK's inverse_kinematics_safe constraints).
MAX_BODY_YAW_RAD = math.radians(160.0)
MIN_BODY_YAW_RAD = math.radians(-160.0)


def create_head_pose_matrix(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    roll: float = 0.0,
    pitch: float = 0.0,
    yaw: float = 0.0,
) -> np.ndarray:
    """Create a 4x4 head pose matrix (radians, meters)."""
    return create_head_pose(
        x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw, degrees=False, mm=False
    )


def compose_poses(
    primary: np.ndarray,
    secondary: np.ndarray,
    reorthonormalize: bool = True,
) -> np.ndarray:
    """Compose two pose matrices via the SDK's world-offset composition."""
    return compose_world_offset(primary, secondary, reorthonormalize=reorthonormalize)


def extract_yaw_from_pose(pose: np.ndarray) -> float:
    """Extract the xyz-euler yaw component from a 4x4 pose matrix."""
    rotation = R.from_matrix(pose[:3, :3])
    _, _, yaw = rotation.as_euler("xyz")
    return yaw


def clamp_body_yaw(yaw: float) -> float:
    """Clamp body yaw to the SDK's safe range (±160°)."""
    return max(MIN_BODY_YAW_RAD, min(MAX_BODY_YAW_RAD, yaw))
