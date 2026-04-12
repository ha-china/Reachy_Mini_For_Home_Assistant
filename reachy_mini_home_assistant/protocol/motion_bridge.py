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

if TYPE_CHECKING:
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


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
    if protocol.camera_server is not None:
        try:
            protocol.camera_server.set_conversation_mode(in_conversation)
        except Exception as e:
            _LOGGER.debug("Failed to set conversation mode: %s", e)


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
            else:
                _LOGGER.warning("Failed to queue emotion: %s", emotion_name)
        else:
            _LOGGER.warning("Cannot play emotion: no movement manager available")
    except Exception as e:
        _LOGGER.error("Error playing emotion %s: %s", emotion_name, e)


def set_face_tracking_for_state(protocol: "VoiceSatelliteProtocol", enabled: bool, context: str) -> None:
    if protocol.camera_server is None:
        return
    try:
        protocol.camera_server.set_face_tracking_enabled(enabled)
        _LOGGER.debug("Face tracking %s during %s", "enabled" if enabled else "paused", context)
    except Exception as e:
        _LOGGER.debug("Failed to update face tracking during %s: %s", context, e)


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
