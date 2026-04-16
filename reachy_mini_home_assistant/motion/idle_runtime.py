"""Idle runtime helpers for `MovementManager`."""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from .state_machine import PendingAction, RobotState, build_idle_pending_action

if TYPE_CHECKING:
    from .movement_manager import MovementManager

logger = logging.getLogger(__name__)


def apply_idle_behavior_enabled(manager: "MovementManager", enabled: bool) -> None:
    manager._idle_motion_enabled = enabled
    manager._idle_antenna_enabled = enabled
    manager._idle_random_actions_enabled = enabled

    if not enabled:
        clear_idle_activity(manager)
        clear_idle_animation(manager)
        manager.state.anim_antenna_left = 0.0
        manager.state.anim_antenna_right = 0.0
        manager._idle_antenna_smoothed = None
        manager._last_idle_antenna_update = 0.0
        if manager.state.robot_state == RobotState.IDLE:
            transition_or_apply_idle_rest_pose(manager)
    elif manager.state.robot_state == RobotState.IDLE:
        manager._animation_player.set_animation("idle")
        manager.state.target_pitch = 0.0
        manager.state.target_antenna_left = 0.0
        manager.state.target_antenna_right = 0.0

    logger.info("Idle behavior %s", "enabled" if enabled else "disabled")


def apply_idle_rest_pose(manager: "MovementManager") -> None:
    manager.state.target_pitch = manager._idle_rest_head_pitch_rad
    manager.state.target_yaw = manager._idle_rest_head_yaw_rad
    manager.state.target_roll = manager._idle_rest_head_roll_rad
    manager.state.target_x = manager._idle_rest_x_m
    manager.state.target_y = manager._idle_rest_y_m
    manager.state.target_z = manager._idle_rest_z_m
    manager.state.target_antenna_left = manager._idle_rest_antenna_left_rad
    manager.state.target_antenna_right = manager._idle_rest_antenna_right_rad
    manager.state.anim_antenna_left = 0.0
    manager.state.anim_antenna_right = 0.0
    manager._antenna_controller.reset()


def transition_or_apply_idle_rest_pose(manager: "MovementManager", duration: float = 2.0) -> None:
    if manager.state.robot_state == RobotState.IDLE:
        manager.transition_to_idle_rest(duration=duration)
    else:
        apply_idle_rest_pose(manager)


def clear_idle_activity(manager: "MovementManager") -> None:
    manager.state.next_look_around_time = 0.0
    manager.state.look_around_in_progress = False
    manager._idle_action_queue.clear()
    if manager._pending_action and manager._pending_action.name.startswith("idle_action"):
        manager._pending_action = None


def clear_idle_animation(manager: "MovementManager") -> None:
    manager._animation_player.stop()
    manager.state.anim_pitch = 0.0
    manager.state.anim_yaw = 0.0
    manager.state.anim_roll = 0.0
    manager.state.anim_x = 0.0
    manager.state.anim_y = 0.0
    manager.state.anim_z = 0.0
    manager.state.anim_antenna_left = 0.0
    manager.state.anim_antenna_right = 0.0


def schedule_next_idle_action_time(manager: "MovementManager", now: float) -> None:
    interval = random.uniform(manager._idle_random_actions_min_interval, manager._idle_random_actions_max_interval)
    manager.state.next_look_around_time = now + interval


def update_idle_look_around(
    manager: "MovementManager",
    *,
    inactivity_threshold_s: float,
    legacy_probability: float,
    yaw_range_deg: float,
    pitch_range_deg: float,
    duration_s: float,
) -> None:
    if not manager._idle_motion_enabled and not manager._idle_random_actions_enabled:
        manager.state.next_look_around_time = 0.0
        manager.state.look_around_in_progress = False
        return

    if manager.state.robot_state != RobotState.IDLE:
        manager.state.next_look_around_time = 0.0
        manager.state.look_around_in_progress = False
        return

    if manager._pending_action is not None:
        return

    now = manager._now()
    idle_duration = now - manager.state.idle_start_time
    if idle_duration < inactivity_threshold_s:
        return

    if manager.state.next_look_around_time == 0.0:
        schedule_next_idle_action_time(manager, now)
        return

    if now < manager.state.next_look_around_time or manager.state.look_around_in_progress:
        return

    if manager._idle_random_actions_enabled:
        if random.random() > manager._idle_random_actions_probability:
            schedule_next_idle_action_time(manager, now)
            return

        action_config = manager._pick_idle_random_action()
        idle_action = build_idle_pending_action(action_config, default_duration_s=duration_s)
        manager._idle_action_queue.append(idle_action)
        manager.state.look_around_in_progress = True
        queued_duration = sum(max(0.0, float(item.duration)) for item in manager._idle_action_queue)
        manager.state.next_look_around_time = now + queued_duration
        schedule_next_idle_action_time(manager, manager.state.next_look_around_time)
        return

    if not manager._idle_motion_enabled:
        schedule_next_idle_action_time(manager, now)
        return

    if random.random() > legacy_probability:
        schedule_next_idle_action_time(manager, now)
        return

    target_yaw = random.uniform(-yaw_range_deg, yaw_range_deg)
    target_pitch = random.uniform(-pitch_range_deg, pitch_range_deg)
    action = PendingAction(
        name="look_around",
        target_yaw=math.radians(target_yaw),
        target_pitch=math.radians(target_pitch),
        duration=duration_s,
    )
    manager._idle_action_queue.append(action)
    manager.state.look_around_in_progress = True
    queued_duration = sum(max(0.0, float(item.duration)) for item in manager._idle_action_queue)
    manager.state.next_look_around_time = now + queued_duration
    schedule_next_idle_action_time(manager, manager.state.next_look_around_time)
    logger.debug("Starting look-around: yaw=%.1f°, pitch=%.1f°", target_yaw, target_pitch)
