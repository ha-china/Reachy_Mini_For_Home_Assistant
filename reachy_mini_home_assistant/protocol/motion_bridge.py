"""Motion bridge helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from ..entities.event_emotion_mapper import (
    SKILL_PLAY_EMOTION,
    SKILL_TIMER_ALERT,
    VOICE_PHASE_IDLE,
    VOICE_PHASE_LISTENING,
    VOICE_PHASE_SPEAKING,
    VOICE_PHASE_THINKING,
)
from ..motion.state_machine import RobotState

if TYPE_CHECKING:
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Head tracking weight matrix (daemon-side YuNet blend into IK output).
#   0.0 = tracker paused (idle base pose only)
#   1.0 = tracker fully owns the head (ignores our set_target head)
# Values are tuned to keep our idle animation / speaking sway visible while
# the daemon nudges the head toward the tracked face.
# ---------------------------------------------------------------------------
HEAD_TRACKING_WEIGHTS: dict[str, float] = {
    VOICE_PHASE_IDLE: 0.3,
    VOICE_PHASE_LISTENING: 0.3,
    VOICE_PHASE_THINKING: 0.4,
    VOICE_PHASE_SPEAKING: 0.2,
}
# Weight used when an emotion animation is playing — the SDK daemon is told to
# pause the tracker so the emotion pose is not blended toward a face.
HEAD_TRACKING_WEIGHT_EMOTION = 0.0
# Weight used when the user disables face tracking in HA preferences.
HEAD_TRACKING_WEIGHT_DISABLED = 0.0

# Map MovementManager robot states to voice-phase weight keys so we can restore
# the right head-tracking weight after an emotion move without tracking phase
# transitions ourselves.
_ROBOT_STATE_TO_PHASE: dict[RobotState, str] = {
    RobotState.IDLE: VOICE_PHASE_IDLE,
    RobotState.LISTENING: VOICE_PHASE_LISTENING,
    RobotState.THINKING: VOICE_PHASE_THINKING,
    RobotState.SPEAKING: VOICE_PHASE_SPEAKING,
}


def turn_to_sound_source(protocol: "VoiceSatelliteProtocol") -> None:
    if not protocol.state.motion_enabled:
        _LOGGER.info("DOA turn-to-sound: motion disabled")
        return
    try:
        doa = protocol.reachy_controller.get_doa_angle()
        if doa is None:
            _LOGGER.info("DOA not available, skipping turn-to-sound")
            return
        angle_rad, speech_detected = doa
        _LOGGER.debug("DOA raw: angle=%.3f rad (%.1f°), speech=%s", angle_rad, math.degrees(angle_rad), speech_detected)
        dir_x = math.sin(angle_rad)
        dir_y = math.cos(angle_rad)
        yaw_rad = -(angle_rad - math.pi / 2)
        yaw_deg = math.degrees(yaw_rad)
        _LOGGER.debug("DOA direction: x=%.2f, y=%.2f, yaw=%.1f°", dir_x, dir_y, yaw_deg)
        if abs(yaw_deg) < 10.0:
            _LOGGER.debug("DOA angle %.1f° below threshold (%.1f°), skipping turn", yaw_deg, 10.0)
            return
        target_yaw_deg = yaw_deg * 0.8
        _LOGGER.info("Turning toward sound source: DOA=%.1f°, target=%.1f°", yaw_deg, target_yaw_deg)
        if protocol.state.motion and protocol.state.motion.movement_manager:
            protocol.state.motion.movement_manager.turn_to_angle(target_yaw_deg, duration=0.5)
    except Exception as e:
        _LOGGER.error("Error in turn-to-sound: %s", e)


def reachy_on_listening(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._behavior_controller.handle_voice_phase(VOICE_PHASE_LISTENING)


def reachy_on_thinking(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._behavior_controller.handle_voice_phase(VOICE_PHASE_THINKING)


def reachy_on_speaking(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._behavior_controller.handle_voice_phase(VOICE_PHASE_SPEAKING)


def reachy_on_idle(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._behavior_controller.handle_voice_phase(VOICE_PHASE_IDLE)


def set_conversation_mode(protocol: "VoiceSatelliteProtocol", in_conversation: bool) -> None:
    """Conversation mode affects DOA suppression; no longer wired to the camera server."""
    # The camera_server's adaptive frame rate no longer keys off conversation
    # state, so we intentionally do nothing here. Kept for compatibility with
    # the behavior controller which still calls this hook.
    _LOGGER.debug("Conversation mode set to %s", in_conversation)


def reachy_on_timer_finished(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._behavior_controller.execute_skill(SKILL_TIMER_ALERT, context="timer_finished")


def play_emotion(protocol: "VoiceSatelliteProtocol", emotion_name: str) -> None:
    protocol._behavior_controller.execute_skill(SKILL_PLAY_EMOTION, emotion_name=emotion_name, context="emotion")


def queue_emotion_move(protocol: "VoiceSatelliteProtocol", emotion_name: str) -> None:
    try:
        if protocol.state.motion and protocol.state.motion.movement_manager:
            movement_manager = protocol.state.motion.movement_manager
            if movement_manager.queue_emotion_move(emotion_name):
                _LOGGER.info("Queued emotion move: %s", emotion_name)
                # Pause daemon-side face tracking so the emotion pose is not
                # blended toward the tracked face. Restored when the emotion
                # move finishes (see _restore_head_tracking_after_emotion).
                apply_head_tracking_weight(protocol, HEAD_TRACKING_WEIGHT_EMOTION, context=f"emotion:{emotion_name}")
            else:
                _LOGGER.warning("Failed to queue emotion: %s", emotion_name)
        else:
            _LOGGER.warning("Cannot play emotion: no movement manager available")
    except Exception as e:
        _LOGGER.error("Error playing emotion %s: %s", emotion_name, e)


def apply_head_tracking_weight(protocol: "VoiceSatelliteProtocol", weight: float, *, context: str) -> None:
    """Push a face tracking weight to the SDK daemon.

    The SDK's ``start_head_tracking(weight)``:
      - Creates/pauses the YuNet tracker thread on the daemon side
      - ``weight=0`` pauses detection (worker kept warm) and clears the aim
      - ``weight>0`` starts detection and blends ``aim`` into IK output

    The user can globally disable face tracking via HA preferences; in that
    case every call collapses to weight=0 (tracker kept paused).
    """
    reachy_mini = protocol.state.reachy_mini
    if reachy_mini is None:
        return
    prefs = protocol.state.preferences
    if prefs is not None and not bool(getattr(prefs, "face_tracking_enabled", False)):
        weight = HEAD_TRACKING_WEIGHT_DISABLED
    try:
        reachy_mini.start_head_tracking(weight=float(weight))
        _LOGGER.debug("Head tracking weight=%.2f (%s)", weight, context)
    except Exception as e:
        _LOGGER.debug("Failed to apply head tracking weight %.2f (%s): %s", weight, context, e)


def _restore_head_tracking_after_emotion(protocol: "VoiceSatelliteProtocol") -> None:
    """Re-apply the current voice-phase weight after an emotion move ends."""
    mm = protocol.state.motion.movement_manager if protocol.state.motion else None
    robot_state = mm.state.robot_state if mm is not None else RobotState.IDLE
    phase = _ROBOT_STATE_TO_PHASE.get(robot_state, VOICE_PHASE_IDLE)
    weight = HEAD_TRACKING_WEIGHTS.get(phase, HEAD_TRACKING_WEIGHTS[VOICE_PHASE_IDLE])
    apply_head_tracking_weight(protocol, weight, context="after_emotion")


def set_face_tracking_for_state(protocol: "VoiceSatelliteProtocol", enabled: bool, context: str) -> None:
    """Apply a face tracking weight for a voice phase.

    Maps the legacy boolean ``face_tracking`` flag from ``enter_motion_state``
    onto a dynamic weight matrix:
      - For most phases ``face_tracking=True`` and we use the per-phase weight
        from HEAD_TRACKING_WEIGHTS (0.3 idle/listening, 0.4 thinking).
      - For speaking we pass ``face_tracking=False`` to flag "lower" intensity;
        we still want some head tracking so we use the speaking weight (0.2)
        rather than fully pausing.
      - ``enabled=False`` with an unrecognized context fully pauses the tracker.
    """
    phase_key = context.lower()
    phase_weight = HEAD_TRACKING_WEIGHTS.get(phase_key)
    if phase_weight is not None:
        weight = phase_weight
    elif enabled:
        weight = HEAD_TRACKING_WEIGHTS[VOICE_PHASE_IDLE]
    else:
        weight = HEAD_TRACKING_WEIGHT_EMOTION
    apply_head_tracking_weight(protocol, weight, context=context)


def enter_motion_state(
    protocol: "VoiceSatelliteProtocol", context: str, callback_name: str, *, face_tracking: bool | None = None
) -> None:
    protocol._cancel_delayed_idle_return()
    if face_tracking is not None:
        set_face_tracking_for_state(protocol, face_tracking, context)
    run_motion_state(protocol, context, callback_name)


def run_motion_state(protocol: "VoiceSatelliteProtocol", context: str, callback_name: str) -> None:
    if not protocol.state.motion_enabled:
        if context == "speaking":
            _LOGGER.warning("Motion disabled, skipping speaking animation")
        return
    if context in {"thinking", "idle"} and not protocol.state.reachy_mini:
        return
    motion = protocol.state.motion
    if motion is None:
        if context == "speaking":
            _LOGGER.warning("No motion controller, skipping speaking animation")
        return
    try:
        _LOGGER.debug("Reachy Mini: %s animation", context.capitalize())
        getattr(motion, callback_name)()
    except Exception as e:
        _LOGGER.error("Reachy Mini motion error: %s", e)
