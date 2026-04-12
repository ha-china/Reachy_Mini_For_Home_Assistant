"""Command queue helpers for `MovementManager`."""

from __future__ import annotations

import logging
import math
from queue import Empty
from typing import TYPE_CHECKING, Any

from .emotion_moves import EmotionMove, is_emotion_available
from .state_machine import STATE_ANIMATION_MAP, PendingAction, RobotState

if TYPE_CHECKING:
    from .movement_manager import MovementManager

logger = logging.getLogger(__name__)


def poll_commands(manager: "MovementManager") -> None:
    while True:
        try:
            cmd, payload = manager._command_queue.get_nowait()
        except Empty:
            break

        if cmd == "set_state":
            while True:
                try:
                    next_cmd, next_payload = manager._command_queue.get_nowait()
                except Empty:
                    break
                if next_cmd == "set_state":
                    payload = next_payload
                    continue
                handle_command(manager, next_cmd, next_payload)

        handle_command(manager, cmd, payload)


def handle_command(manager: "MovementManager", cmd: str, payload: Any) -> None:
    if cmd == "set_state":
        old_state = manager.state.robot_state
        manager.state.robot_state = payload
        manager.state.last_activity_time = manager._now()

        if payload == RobotState.IDLE and not manager._idle_behavior_enabled():
            animation_name = "none"
            manager._animation_player.stop()
        else:
            animation_name = STATE_ANIMATION_MAP.get(payload.value, "idle")
            manager._animation_player.set_animation(animation_name)

        if payload == RobotState.IDLE and old_state != RobotState.IDLE:
            manager.state.idle_start_time = manager._now()
            manager._start_antenna_unfreeze()
            manager._idle_antenna_smoothed = None
            manager._last_idle_antenna_update = 0.0

        if payload != RobotState.IDLE:
            # Preserve the current pose anchor during an active conversation.
            # This keeps wakeup turn-to-sound orientation until the session
            # actually ends and `on_idle()` decides how to settle the robot.
            manager._idle_antenna_smoothed = None
            manager._last_idle_antenna_update = 0.0

        logger.debug("State changed: %s -> %s, animation: %s", old_state.value, payload.value, animation_name)
        return

    if cmd == "action":
        start_action(manager, payload)
        return

    if cmd == "nod":
        amplitude_deg, duration = payload
        do_nod(manager, amplitude_deg, duration)
        return

    if cmd == "shake":
        amplitude_deg, duration = payload
        do_shake(manager, amplitude_deg, duration)
        return

    if cmd == "set_pose":
        if payload.get("x") is not None:
            manager.state.target_x = payload["x"]
        if payload.get("y") is not None:
            manager.state.target_y = payload["y"]
        if payload.get("z") is not None:
            manager.state.target_z = payload["z"]
        if payload.get("roll") is not None:
            manager.state.target_roll = payload["roll"]
        if payload.get("pitch") is not None:
            manager.state.target_pitch = payload["pitch"]
        if payload.get("yaw") is not None:
            manager.state.target_yaw = payload["yaw"]
        if payload.get("antenna_left") is not None:
            manager.state.target_antenna_left = payload["antenna_left"]
        if payload.get("antenna_right") is not None:
            manager.state.target_antenna_right = payload["antenna_right"]
        logger.debug("External pose update: %s", payload)
        return

    if cmd == "speech_sway":
        x, y, z, roll, pitch, yaw = payload
        manager.state.sway_x = x
        manager.state.sway_y = y
        manager.state.sway_z = z
        manager.state.sway_roll = roll
        manager.state.sway_pitch = pitch
        manager.state.sway_yaw = yaw
        return

    if cmd == "emotion_move":
        start_emotion_move(manager, payload)
        return

    if cmd == "set_idle_behavior":
        manager._apply_idle_behavior_enabled(bool(payload))


def start_emotion_move(manager: "MovementManager", emotion_name: str) -> None:
    if not is_emotion_available():
        logger.warning("Cannot play emotion '%s': emotion library not available", emotion_name)
        return

    try:
        emotion_move = EmotionMove(emotion_name)
        with manager._emotion_move_lock:
            manager._emotion_move = emotion_move
            manager._emotion_start_time = manager._now()
        logger.info("Started emotion move: %s (duration=%.2fs)", emotion_name, emotion_move.duration)
    except Exception as e:
        logger.error("Failed to start emotion '%s': %s", emotion_name, e)


def start_action(manager: "MovementManager", action: PendingAction) -> None:
    manager._pending_action = action
    manager._action_start_time = manager._now()
    manager._action_start_pose = {
        "pitch": manager.state.target_pitch,
        "yaw": manager.state.target_yaw,
        "roll": manager.state.target_roll,
        "x": manager.state.target_x,
        "y": manager.state.target_y,
        "z": manager.state.target_z,
        "antenna_left": manager.state.target_antenna_left,
        "antenna_right": manager.state.target_antenna_right,
    }
    logger.debug("Starting action: %s", action.name)


def do_nod(manager: "MovementManager", amplitude_deg: float, duration: float) -> None:
    amplitude_rad = math.radians(amplitude_deg)
    half_duration = duration / 2
    action_down = PendingAction(name="nod_down", target_pitch=amplitude_rad, duration=half_duration)
    start_action(manager, action_down)


def do_shake(manager: "MovementManager", amplitude_deg: float, duration: float) -> None:
    amplitude_rad = math.radians(amplitude_deg)
    half_duration = duration / 2
    action_left = PendingAction(name="shake_left", target_yaw=-amplitude_rad, duration=half_duration)
    start_action(manager, action_left)
