"""Face tracking interpolation for smooth transitions.

This module provides smooth interpolation when a tracked face is lost,
allowing the camera/head to gracefully return to neutral position.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial.transform import Rotation as R

# Import SDK interpolation utilities (same as conversation_app)
try:
    from reachy_mini.utils.interpolation import linear_pose_interpolation
    SDK_INTERPOLATION_AVAILABLE = True
except ImportError:
    SDK_INTERPOLATION_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)


@dataclass
class InterpolationConfig:
    """Configuration for face tracking interpolation."""

    face_lost_delay: float = 2.0  # Wait before interpolating back to neutral
    interpolation_duration: float = 1.0  # Duration of return to neutral
    offset_scale: float = 0.6  # Scale factor for tracking offsets
    pitch_offset_deg: float = 9.0  # Pitch compensation (look down)
    yaw_offset_deg: float = -7.0  # Yaw compensation (turn right)


class FaceTrackingInterpolator:
    """Handles smooth interpolation for face tracking transitions.

    When a face is lost, this class manages the smooth transition back
    to a neutral head position using SLERP for rotations.
    """

    def __init__(self, config: Optional[InterpolationConfig] = None):
        """Initialize the interpolator.

        Args:
            config: Configuration for interpolation behavior.
        """
        self.config = config or InterpolationConfig()

        # Interpolation state
        self._last_face_detected_time: Optional[float] = None
        self._interpolation_start_time: Optional[float] = None
        self._interpolation_start_pose: Optional[np.ndarray] = None

        # Current offsets (x, y, z, roll, pitch, yaw)
        self._offsets: List[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def on_face_detected(self, current_time: float) -> None:
        """Call when a face is detected.

        Args:
            current_time: Current time in seconds (from time.time() or similar)
        """
        self._last_face_detected_time = current_time
        self._interpolation_start_time = None  # Stop any interpolation

    def update_offsets(self, translation: np.ndarray, rotation: np.ndarray) -> None:
        """Update the face tracking offsets.

        Args:
            translation: 3D translation vector [x, y, z]
            rotation: Euler rotation vector [roll, pitch, yaw] in radians
        """
        # Scale down for smoother tracking
        scaled_trans = translation * self.config.offset_scale
        scaled_rot = rotation * self.config.offset_scale

        # Apply pitch offset compensation
        pitch_offset_rad = np.radians(self.config.pitch_offset_deg)
        scaled_rot[1] += pitch_offset_rad

        # Apply yaw offset compensation
        yaw_offset_rad = np.radians(self.config.yaw_offset_deg)
        scaled_rot[2] += yaw_offset_rad

        self._offsets = [
            float(scaled_trans[0]),
            float(scaled_trans[1]),
            float(scaled_trans[2]),
            float(scaled_rot[0]),
            float(scaled_rot[1]),
            float(scaled_rot[2]),
        ]

    def process_face_lost(self, current_time: float) -> None:
        """Handle smooth interpolation back to neutral when face is lost.

        Args:
            current_time: Current time in seconds
        """
        if self._last_face_detected_time is None:
            return

        time_since_face_lost = current_time - self._last_face_detected_time

        if time_since_face_lost < self.config.face_lost_delay:
            return  # Still within delay period, keep current offsets

        # Start interpolation if not already started
        if self._interpolation_start_time is None:
            self._interpolation_start_time = current_time
            # Capture current pose as start of interpolation
            current_offsets = self._offsets.copy()

            # Convert to 4x4 pose matrix
            pose_matrix = np.eye(4, dtype=np.float32)
            pose_matrix[:3, 3] = current_offsets[:3]
            pose_matrix[:3, :3] = R.from_euler("xyz", current_offsets[3:]).as_matrix()
            self._interpolation_start_pose = pose_matrix

        # Calculate interpolation progress
        elapsed = current_time - self._interpolation_start_time
        t = min(1.0, elapsed / self.config.interpolation_duration)

        # Interpolate to neutral (identity matrix)
        if self._interpolation_start_pose is not None:
            neutral_pose = np.eye(4, dtype=np.float32)
            interpolated_pose = self._linear_pose_interpolation(
                self._interpolation_start_pose, neutral_pose, t
            )

            # Extract translation and rotation
            translation = interpolated_pose[:3, 3]
            rotation = R.from_matrix(interpolated_pose[:3, :3]).as_euler("xyz", degrees=False)

            self._offsets = [
                float(translation[0]),
                float(translation[1]),
                float(translation[2]),
                float(rotation[0]),
                float(rotation[1]),
                float(rotation[2]),
            ]

        # Reset when interpolation complete
        if t >= 1.0:
            self._last_face_detected_time = None
            self._interpolation_start_time = None
            self._interpolation_start_pose = None

    def _linear_pose_interpolation(
        self, start: np.ndarray, end: np.ndarray, t: float
    ) -> np.ndarray:
        """Linear interpolation between two 4x4 pose matrices.

        Uses SDK's linear_pose_interpolation if available, otherwise falls back
        to manual SLERP implementation.
        """
        if SDK_INTERPOLATION_AVAILABLE:
            return linear_pose_interpolation(start, end, t)

        # Fallback: manual interpolation
        # Interpolate translation
        start_trans = start[:3, 3]
        end_trans = end[:3, 3]
        interp_trans = start_trans * (1 - t) + end_trans * t

        # Interpolate rotation using SLERP
        start_rot = R.from_matrix(start[:3, :3])
        end_rot = R.from_matrix(end[:3, :3])

        # Use scipy's slerp
        from scipy.spatial.transform import Slerp
        key_rots = R.from_quat(np.array([start_rot.as_quat(), end_rot.as_quat()]))
        slerp = Slerp([0, 1], key_rots)
        interp_rot = slerp(t)

        # Build result matrix
        result = np.eye(4, dtype=np.float32)
        result[:3, :3] = interp_rot.as_matrix()
        result[:3, 3] = interp_trans

        return result

    def get_offsets(self) -> Tuple[float, float, float, float, float, float]:
        """Get current face tracking offsets.

        Returns:
            Tuple of (x, y, z, roll, pitch, yaw) offsets
        """
        return tuple(self._offsets)

    def is_face_detected(self) -> bool:
        """Check if a face is currently detected.

        Returns True if face was detected recently (within face_lost_delay period).
        """
        if self._last_face_detected_time is None:
            return False

        time_since_detected = time.time() - self._last_face_detected_time
        return time_since_detected < self.config.face_lost_delay

    def reset_interpolation(self) -> None:
        """Reset interpolation state (e.g., when tracking is disabled)."""
        self._last_face_detected_time = time.time()
        self._interpolation_start_time = None

    def set_raw_offsets(self, offsets: List[float]) -> None:
        """Set offsets directly (thread-safe wrapper use case).

        Args:
            offsets: List of [x, y, z, roll, pitch, yaw]
        """
        self._offsets = offsets.copy()
