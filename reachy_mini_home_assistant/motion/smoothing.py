"""Pose smoothing and interpolation utilities.

This module provides functions for smooth pose transitions,
interpolation, and easing.
"""

import math

import numpy as np


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out function for smooth transitions.

    Args:
        t: Progress value between 0 and 1

    Returns:
        Eased value between 0 and 1
    """
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out function for smooth deceleration.

    Args:
        t: Progress value between 0 and 1

    Returns:
        Eased value between 0 and 1
    """
    return 1 - pow(1 - t, 3)


def lerp(start: float, end: float, t: float) -> float:
    """Linear interpolation between two values.

    Args:
        start: Start value
        end: End value
        t: Progress value between 0 and 1

    Returns:
        Interpolated value
    """
    return start + (end - start) * t


def lerp_angle(start: float, end: float, t: float) -> float:
    """Linear interpolation between two angles (handles wraparound).

    Args:
        start: Start angle in radians
        end: End angle in radians
        t: Progress value between 0 and 1

    Returns:
        Interpolated angle in radians
    """
    # Normalize the difference to [-pi, pi]
    diff = end - start
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi

    return start + diff * t


def interpolate_pose(
    start_pose: dict[str, float], end_pose: dict[str, float], t: float, use_easing: bool = True
) -> dict[str, float]:
    """Interpolate between two pose dictionaries.

    Args:
        start_pose: Starting pose dictionary with keys like 'pitch', 'yaw', etc.
        end_pose: Ending pose dictionary
        t: Progress value between 0 and 1
        use_easing: Whether to apply cubic easing

    Returns:
        Interpolated pose dictionary
    """
    if use_easing:
        t = ease_in_out_cubic(t)

    result = {}
    for key, start_value in start_pose.items():
        if key in end_pose:
            if key in ("pitch", "yaw", "roll"):
                result[key] = lerp_angle(start_value, end_pose[key], t)
            else:
                result[key] = lerp(start_value, end_pose[key], t)
        else:
            result[key] = start_value

    return result


def smooth_value(current: float, target: float, smoothing_factor: float, dt: float) -> float:
    """Exponentially smooth a value towards a target.

    Args:
        current: Current value
        target: Target value
        smoothing_factor: Smoothing factor (higher = faster)
        dt: Delta time in seconds

    Returns:
        Smoothed value
    """
    alpha = 1 - math.exp(-smoothing_factor * dt)
    return current + (target - current) * alpha


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to a range.

    Args:
        value: Value to clamp
        min_val: Minimum value
        max_val: Maximum value

    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def normalize_angle(angle: float) -> float:
    """Normalize an angle to [-pi, pi].

    Args:
        angle: Angle in radians

    Returns:
        Normalized angle in radians
    """
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def pose_distance(pose1: np.ndarray, pose2: np.ndarray) -> float:
    """Calculate the distance between two poses.

    Args:
        pose1: First pose as 4x4 transformation matrix
        pose2: Second pose as 4x4 transformation matrix

    Returns:
        Distance metric (position + rotation)
    """
    # Position distance
    pos1 = pose1[:3, 3]
    pos2 = pose2[:3, 3]
    pos_dist = np.linalg.norm(pos1 - pos2)

    # Rotation distance (Frobenius norm of rotation difference)
    rot1 = pose1[:3, :3]
    rot2 = pose2[:3, :3]
    rot_dist = np.linalg.norm(rot1 - rot2)

    return pos_dist + rot_dist * 0.1  # Scale rotation to be comparable


def blend_poses(pose1: np.ndarray, pose2: np.ndarray, weight: float) -> np.ndarray:
    """Blend two pose matrices.

    Args:
        pose1: First pose as 4x4 transformation matrix
        pose2: Second pose as 4x4 transformation matrix
        weight: Blend weight (0 = pose1, 1 = pose2)

    Returns:
        Blended pose as 4x4 transformation matrix
    """
    # Simple linear blend (good enough for small differences)
    return pose1 * (1 - weight) + pose2 * weight
