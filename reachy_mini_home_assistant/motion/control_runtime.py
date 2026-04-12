"""Pose and control loop helpers for `MovementManager`."""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

import numpy as np

from ..core.config import Config
from .pose_composer import clamp_body_yaw, compose_poses, create_head_pose_matrix, extract_yaw_from_pose
from .state_machine import RobotState

if TYPE_CHECKING:
    from .movement_manager import MovementManager

logger = logging.getLogger(__name__)


def update_face_tracking(manager: "MovementManager", face_detected_threshold: float) -> None:
    if manager._camera_server is None:
        return
    try:
        raw_offsets = manager._camera_server.get_face_tracking_offsets()
        offsets_for_motion = raw_offsets
        if manager.state.robot_state == RobotState.IDLE and not manager._idle_motion_enabled:
            offsets_for_motion = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        with manager._face_tracking_lock:
            manager._face_tracking_offsets = offsets_for_motion
        offset_magnitude = sum(abs(o) for o in raw_offsets)
        face_now_detected = offset_magnitude > face_detected_threshold
        if face_now_detected:
            if not manager.state.face_detected:
                logger.debug("Face detected")
            manager.state.face_detected = True
        else:
            if manager.state.face_detected:
                logger.debug("Face lost")
            manager.state.face_detected = False
    except Exception as e:
        logger.debug("Error getting face tracking offsets: %s", e)


def update_emotion_move(manager: "MovementManager") -> tuple[np.ndarray, tuple[float, float], float] | None:
    with manager._emotion_move_lock:
        if manager._emotion_move is None:
            return None
        elapsed = manager._now() - manager._emotion_start_time
        if elapsed >= manager._emotion_move.duration:
            emotion_name = manager._emotion_move.emotion_name
            manager._emotion_move = None
            logger.info("Emotion move complete: %s", emotion_name)
            return None
        try:
            head_pose, antennas, body_yaw = manager._emotion_move.evaluate(elapsed)
            antenna_tuple = (float(antennas[0]), float(antennas[1]))
            clamped_body_yaw = clamp_body_yaw(float(body_yaw))
            return (head_pose, antenna_tuple, clamped_body_yaw)
        except Exception as e:
            logger.error("Error sampling emotion pose: %s", e)
            manager._emotion_move = None
            return None


def compose_final_pose(manager: "MovementManager") -> tuple[np.ndarray, tuple[float, float], float]:
    primary_head = create_head_pose_matrix(
        x=manager.state.target_x,
        y=manager.state.target_y,
        z=manager.state.target_z,
        roll=manager.state.target_roll,
        pitch=manager.state.target_pitch,
        yaw=manager.state.target_yaw,
    )
    with manager._face_tracking_lock:
        face_offsets = manager._face_tracking_offsets
    anim_blend = manager.state.animation_blend
    secondary_head = create_head_pose_matrix(
        x=manager.state.anim_x * anim_blend + manager.state.sway_x + face_offsets[0],
        y=manager.state.anim_y * anim_blend + manager.state.sway_y + face_offsets[1],
        z=manager.state.anim_z * anim_blend + manager.state.sway_z + face_offsets[2],
        roll=manager.state.anim_roll * anim_blend + manager.state.sway_roll + face_offsets[3],
        pitch=manager.state.anim_pitch * anim_blend + manager.state.sway_pitch + face_offsets[4],
        yaw=manager.state.anim_yaw * anim_blend + manager.state.sway_yaw + face_offsets[5],
    )
    final_head = compose_poses(primary_head, secondary_head)

    anim_antenna_left = manager.state.anim_antenna_left * anim_blend
    anim_antenna_right = manager.state.anim_antenna_right * anim_blend
    target_antenna_left = manager.state.target_antenna_left + anim_antenna_left
    target_antenna_right = manager.state.target_antenna_right + anim_antenna_right
    antenna_left, antenna_right = manager._antenna_controller.get_blended_positions(target_antenna_left, target_antenna_right)

    if manager.state.robot_state != RobotState.IDLE:
        manager._idle_antenna_smoothed = None
        manager._last_idle_antenna_update = 0.0

    final_head_yaw = extract_yaw_from_pose(final_head)
    target_body_yaw = clamp_body_yaw(final_head_yaw)
    if manager.state.robot_state == RobotState.IDLE and not manager.state.face_detected:
        target_body_yaw = 0.0

    now = manager._now()
    if manager._body_yaw_smoothed is None:
        manager._body_yaw_smoothed = target_body_yaw
        manager._last_body_yaw_update = now
    else:
        dt = max(1e-6, now - manager._last_body_yaw_update)
        max_rate_rad_s = math.radians(Config.motion.body_yaw_max_rate_deg_s)
        if manager.state.face_detected or manager.state.robot_state != RobotState.IDLE:
            max_rate_rad_s *= 1.15
        max_step = max_rate_rad_s * dt
        delta = target_body_yaw - manager._body_yaw_smoothed
        if abs(delta) <= Config.motion.body_yaw_deadband_rad:
            manager._body_yaw_smoothed = target_body_yaw
        else:
            step = max(-max_step, min(max_step, delta))
            manager._body_yaw_smoothed = clamp_body_yaw(manager._body_yaw_smoothed + step)
        manager._last_body_yaw_update = now

    return final_head, (antenna_right, antenna_left), manager._body_yaw_smoothed


def issue_control_command(manager: "MovementManager", head_pose: np.ndarray, antennas: tuple[float, float], body_yaw: float) -> None:
    if manager._draining_event.is_set() or manager._emotion_playing_event.is_set() or manager._robot_paused_event.is_set():
        return
    now = manager._now()
    if manager._connection_lost:
        if now - manager._last_reconnect_attempt < manager._reconnect_attempt_interval:
            return
        manager._last_reconnect_attempt = now
        logger.debug("Attempting to send command after connection loss...")
    try:
        manager.robot.set_target(head=head_pose, antennas=list(antennas), body_yaw=body_yaw)
        manager._last_successful_command = now
        manager._consecutive_errors = 0
        manager._last_sent_head_pose = head_pose.copy()
        manager._last_sent_antennas = antennas
        manager._last_sent_body_yaw = body_yaw
        manager._last_send_time = now
        if manager._connection_lost:
            logger.info("✓ Connection to robot restored")
            manager._connection_lost = False
            manager._reconnect_attempt_interval = manager._reconnect_backoff_initial
            manager._suppressed_errors = 0
    except Exception as e:
        error_msg = str(e)
        manager._consecutive_errors += 1
        is_connection_error = manager._is_connection_error(e)
        if is_connection_error:
            if not manager._connection_lost:
                if manager._consecutive_errors >= manager._max_consecutive_errors:
                    logger.warning(f"Connection unstable after {manager._consecutive_errors} errors: {error_msg}")
                    logger.warning("  Will retry connection every %.1fs...", manager._reconnect_attempt_interval)
                    manager._connection_lost = True
                    manager._last_reconnect_attempt = now
                else:
                    manager._log_error_throttled(
                        f"Transient connection error ({manager._consecutive_errors}/{manager._max_consecutive_errors}): {error_msg}"
                    )
            else:
                manager._log_error_throttled(f"Connection still lost: {error_msg}")
                manager._reconnect_attempt_interval = min(
                    manager._reconnect_backoff_max,
                    manager._reconnect_attempt_interval * manager._reconnect_backoff_multiplier,
                )
        else:
            manager._log_error_throttled(f"Failed to set robot target: {error_msg}")


def run_control_loop(manager: "MovementManager", *, max_control_dt_s: float, face_detected_threshold: float) -> None:
    logger.info("Movement manager control loop started (%.1f Hz)", manager._control_loop_hz)
    last_time = manager._now()
    while not manager._stop_event.is_set():
        loop_start = manager._now()
        dt = min(max(0.0, loop_start - last_time), max_control_dt_s)
        last_time = loop_start
        try:
            manager._poll_commands()
            if manager._robot_paused_event.is_set():
                manager._robot_resumed_event.wait(timeout=0.5)
                continue
            emotion_pose = manager._update_emotion_move()
            if emotion_pose is not None:
                head_pose, antennas, body_yaw = emotion_pose
                manager._issue_control_command(head_pose, antennas, body_yaw)
            else:
                manager._update_action(dt)
                manager._update_animation(dt)
                manager._update_antenna_blend(dt)
                manager._update_face_tracking()
                manager._update_animation_blend()
                manager._update_idle_look_around()
                head_pose, antennas, body_yaw = manager._compose_final_pose()
                manager._issue_control_command(head_pose, antennas, body_yaw)
        except Exception as e:
            manager._log_error_throttled(f"Control loop error: {e}")
        sleep_time = max(0.0, manager._target_period - (manager._now() - loop_start))
        if sleep_time > 0:
            time.sleep(sleep_time)
    logger.info("Movement manager control loop stopped")
