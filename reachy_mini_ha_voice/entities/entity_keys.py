"""Entity key definitions for ESPHome entities.

This module provides consistent entity key mappings for all HA entities.
Keys are fixed to ensure consistency across restarts.
"""

import logging

logger = logging.getLogger(__name__)


# Fixed entity key mapping - ensures consistent keys across restarts
# Keys are based on phase/category organization
ENTITY_KEYS: dict[str, int] = {
    # Media player (key 0 reserved)
    "reachy_mini_media_player": 0,
    # Phase 1: Basic status and volume (100-199)
    "daemon_state": 100,
    "backend_ready": 101,
    "speaker_volume": 103,
    # Phase 2: Motor control (200-299)
    "motors_enabled": 200,
    "motor_mode": 201,
    "wake_up": 202,
    "go_to_sleep": 203,
    # Phase 3: Pose control (300-399)
    "head_x": 300,
    "head_y": 301,
    "head_z": 302,
    "head_roll": 303,
    "head_pitch": 304,
    "head_yaw": 305,
    "body_yaw": 306,
    "antenna_left": 307,
    "antenna_right": 308,
    # Phase 4: Look at control (400-499)
    "look_at_x": 400,
    "look_at_y": 401,
    "look_at_z": 402,
    # Phase 5: DOA - Direction of Arrival (500-599)
    "doa_angle": 500,
    "speech_detected": 501,
    # Phase 6: Diagnostic information (600-699)
    "control_loop_frequency": 600,
    "sdk_version": 601,
    "robot_name": 602,
    "wireless_version": 603,
    "simulation_mode": 604,
    "wlan_ip": 605,
    "error_message": 606,
    # Phase 7: IMU sensors (700-799)
    "imu_accel_x": 700,
    "imu_accel_y": 701,
    "imu_accel_z": 702,
    "imu_gyro_x": 703,
    "imu_gyro_y": 704,
    "imu_gyro_z": 705,
    "imu_temperature": 706,
    # Phase 8: Emotion selector (800-899)
    "emotion": 800,
    # Phase 9: Audio controls (900-999)
    "microphone_volume": 900,
    # Phase 10: Camera (1000-1099)
    "camera_url": 1000,
    "camera": 1001,
    # Phase 12: Audio processing (1200-1299)
    "agc_enabled": 1200,
    "agc_max_gain": 1201,
    "noise_suppression": 1202,
    "echo_cancellation_converged": 1203,
    # Phase 21: Continuous conversation (1500-1599)
    "continuous_conversation": 1500,
    # Phase 22: Gesture detection (1600-1699)
    "gesture_detected": 1600,
    "gesture_confidence": 1601,
    # Phase 23: Face detection (1700-1799)
    "face_detected": 1700,
    # Phase 24: System diagnostics (1800-1899)
    "sys_cpu_percent": 1800,
    "sys_cpu_temperature": 1801,
    "sys_memory_percent": 1802,
    "sys_memory_used": 1803,
    "sys_disk_percent": 1804,
    "sys_disk_free": 1805,
    "sys_uptime": 1806,
    "sys_process_cpu": 1807,
    "sys_process_memory": 1808,
    # Phase 25: Sleep state (1900-1999)
    "sleep_mode": 1900,
    "services_suspended": 1901,
    # Phase 26: DOA tracking control (2000+)
    "doa_tracking_enabled": 2000,
}


def get_entity_key(object_id: str) -> int:
    """Get a consistent entity key for the given object_id.

    Args:
        object_id: The entity's object ID

    Returns:
        Integer key for the entity
    """
    if object_id in ENTITY_KEYS:
        return ENTITY_KEYS[object_id]

    # Fallback: generate key from hash (should not happen if all entities are registered)
    logger.warning("Entity key not found for %s, generating from hash", object_id)
    return abs(hash(object_id)) % 10000 + 2000


def register_entity_key(object_id: str, key: int) -> None:
    """Register a new entity key.

    Args:
        object_id: The entity's object ID
        key: The key to assign
    """
    if object_id in ENTITY_KEYS:
        logger.warning("Overwriting existing key for %s", object_id)
    ENTITY_KEYS[object_id] = key


def get_next_available_key(phase: int = 2000) -> int:
    """Get the next available key in a phase range.

    Args:
        phase: The phase base (e.g., 2000 for phase 26+)

    Returns:
        Next available key in the range
    """
    phase_keys = [k for k in ENTITY_KEYS.values() if phase <= k < phase + 100]
    if not phase_keys:
        return phase
    return max(phase_keys) + 1
