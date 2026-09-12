"""Service lifecycle orchestration for `VoiceAssistantService`.

Suspend/resume coordination across the ESPHome satellite, audio players,
camera server and the SDK media pipelines, plus the media (re)start logic.
Moved verbatim from `voice_assistant` to keep that module focused on the
audio processing loop and wake word pipeline.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import requests

from .config import Config

_LOGGER = logging.getLogger(__name__)


class ServiceLifecycleMixin:
    """Mixin: suspend/resume + media lifecycle hooks for the voice service."""

    def _get_daemon_status(self) -> Any:
        """Return the current daemon status via the public REST API, or None if unavailable."""
        try:
            resp = requests.get(
                f"{Config.daemon.url.rstrip('/')}/api/daemon/status",
                timeout=Config.daemon.check_interval_active,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def _probe_audio_capture_ready(self, media, timeout_s: float = 1.5) -> bool:
        """Check whether microphone samples become available shortly after startup."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                sample = media.get_audio_sample()
                if sample is not None and isinstance(sample, np.ndarray) and sample.size > 0:
                    return True
            except Exception:
                pass
            time.sleep(0.05)
        return False

    def _suspend_voice_services(self, reason: str) -> None:
        """Suspend only voice-related services."""
        _LOGGER.warning("Suspending voice services (%s)", reason)
        self._robot_services_paused.set()
        self._robot_services_resumed.clear()
        self._set_services_state(suspended=True)
        self._audio_buffer.clear()
        self._suspend_satellite()
        self._set_audio_players_suspended(True)
        self._stop_media_system()

        _LOGGER.info("Voice services suspended - camera and motion remain active")

    def _resume_voice_services(self, reason: str) -> None:
        """Resume only voice-related services."""
        _LOGGER.info("Resuming voice services (%s)", reason)
        self._robot_services_paused.clear()
        self._set_services_state(suspended=False)
        self._start_media_system()
        self._resume_satellite()
        self._set_audio_players_suspended(False)
        self._robot_services_resumed.set()

        _LOGGER.info("Voice services resumed - camera and motion remained active")

    def _suspend_non_esphome_services(self, reason: str) -> None:
        """Suspend all non-ESPHome services."""
        _LOGGER.warning("Suspending non-ESPHome services (%s)", reason)
        self._robot_services_paused.set()
        self._robot_services_resumed.clear()
        self._set_services_state(suspended=True)
        self._audio_buffer.clear()

        if self._camera_server is not None and self._state.camera_enabled:
            try:
                self._camera_server.suspend()
                _LOGGER.debug("Camera server suspended")
            except Exception as e:
                _LOGGER.warning("Error suspending camera: %s", e)

        if self._motion is not None and self._motion._movement_manager is not None:
            try:
                self._motion._movement_manager.suspend()
                _LOGGER.debug("Motion controller suspended")
            except Exception as e:
                _LOGGER.warning("Error suspending motion: %s", e)

        self._suspend_satellite()
        self._set_audio_players_suspended(True)
        self._stop_media_system()

        _LOGGER.info("Services suspended - ESPHome only")

    def _resume_non_esphome_services(self, reason: str) -> None:
        """Resume all non-ESPHome services after runtime suspension."""
        _LOGGER.info("Resuming non-ESPHome services (%s)", reason)
        self._robot_services_paused.clear()
        self._set_services_state(suspended=False)
        self._start_media_system()

        if self._camera_server is not None and self._state.camera_enabled:
            try:
                self._camera_server.resume_from_suspend()
                _LOGGER.debug("Camera server resumed from suspend")
            except Exception as e:
                _LOGGER.warning("Error resuming camera: %s", e)

        if self._motion is not None and self._motion._movement_manager is not None:
            try:
                self._motion._movement_manager.resume_from_suspend()
                _LOGGER.debug("Motion controller resumed from suspend")
            except Exception as e:
                _LOGGER.warning("Error resuming motion: %s", e)

        self._resume_satellite()
        self._set_audio_players_suspended(False)
        self._robot_services_resumed.set()

        _LOGGER.info("All services resumed - system fully operational")

    def _set_services_state(self, *, suspended: bool) -> None:
        if self._state is None:
            return
        self._state.services_suspended = suspended

    def _suspend_satellite(self) -> None:
        if self._state is None or self._state.satellite is None:
            return
        try:
            self._state.satellite.suspend()
            _LOGGER.debug("Satellite suspended")
        except Exception as e:
            _LOGGER.warning("Error suspending satellite: %s", e)

    def _resume_satellite(self) -> None:
        if self._state is None or self._state.satellite is None:
            return
        try:
            self._state.satellite.resume()
            _LOGGER.debug("Satellite resumed")
        except Exception as e:
            _LOGGER.warning("Error resuming satellite: %s", e)

    def _set_audio_players_suspended(self, suspended: bool) -> None:
        if self._state is None:
            return
        action = "suspend" if suspended else "resume"
        verb = "suspending" if suspended else "resuming"
        for player_name, label in (("tts_player", "TTS player"), ("music_player", "music player")):
            player = getattr(self._state, player_name)
            if player is None:
                continue
            try:
                getattr(player, action)()
            except Exception as e:
                _LOGGER.warning("Error %s %s: %s", verb, label, e)

    def _stop_media_system(self) -> None:
        media = self.reachy_mini.media
        try:
            media.stop_recording()
        except Exception as e:
            _LOGGER.warning("Error stopping recording: %s", e)
        try:
            media.stop_playing()
        except Exception as e:
            _LOGGER.warning("Error stopping playback: %s", e)
        _LOGGER.debug("Media system stopped")

    def _start_media_system(self) -> None:
        try:
            media = self.reachy_mini.media
            if media.audio is not None:
                try:
                    media.stop_recording()
                except Exception:
                    pass
                try:
                    media.stop_playing()
                except Exception:
                    pass
                time.sleep(0.2)
                media.start_recording()
                media.start_playing()
                if not self._probe_audio_capture_ready(media, timeout_s=1.5):
                    raise RuntimeError("Audio capture probe failed after media restart")
                _LOGGER.info("Media system restarted")
        except Exception as e:
            _LOGGER.warning("Failed to restart media: %s", e)

    def _on_robot_disconnected(self) -> None:
        """Called when robot connection is lost."""
        self._suspend_non_esphome_services(reason="robot_disconnected")

    def _on_robot_connected(self) -> None:
        """Called when robot connection is restored."""
        self._resume_non_esphome_services(reason="robot_connected")

    async def _on_ha_connected(self) -> None:
        """Called when Home Assistant connects."""
        _LOGGER.info("Home Assistant connected - initializing camera and voice services")
        self._ha_connected = True
        self._ha_connection_established = True

        try:
            await self._reconcile_camera_runtime(reason="ha_connected")
        except Exception as e:
            _LOGGER.error("Failed to reconcile camera runtime: %s", e)

        # Resume services if they were suspended due to HA disconnection
        if self._state.services_suspended:
            self._resume_non_esphome_services(reason="ha_connected")

    def _on_ha_disconnected(self) -> None:
        """Called when Home Assistant disconnects."""
        _LOGGER.warning("Home Assistant disconnected - suspending camera and voice services")
        self._ha_connected = False

        self._suspend_non_esphome_services(reason="ha_disconnected")
