from __future__ import annotations

"""
Voice Assistant Service for Reachy Mini.

This module provides the main voice assistant service that integrates
with Home Assistant via ESPHome protocol.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, fields
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING

import numpy as np
import requests
from reachy_mini import ReachyMini

from .audio.audio_player import AudioPlayer
from .audio.local_audio_player import LocalAudioPlayer
from .core import Config
from .core.util import get_mac
from .models import Preferences, ServerState
from .motion.reachy_motion import ReachyMiniMotion
from .protocol.satellite import VoiceSatelliteProtocol
from .protocol.wakeword_assets import find_available_wake_words, get_wake_word_dirs, load_stop_model, load_wake_models
from .protocol.zeroconf import HomeAssistantZeroconf, get_default_friendly_name
from .vision.camera_server import MJPEGCameraServer

if TYPE_CHECKING:
    from pymicro_wakeword import MicroWakeWord
    from pyopen_wakeword import OpenWakeWord

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_WAKEWORDS_DIR = _MODULE_DIR / "wakewords"
_SOUNDS_DIR = _MODULE_DIR / "sounds"
_LOCAL_DIR = _MODULE_DIR.parent / "local"


@dataclass
class AudioProcessingContext:
    """Context for audio processing, holding mutable state."""

    wake_words: list = field(default_factory=list)
    micro_features: object | None = None
    micro_inputs: list = field(default_factory=list)
    oww_features: object | None = None
    oww_inputs: list = field(default_factory=list)
    has_oww: bool = False
    last_active: float | None = None


# Audio chunk size for consistent streaming
# Smaller chunks = faster VAD response
# ESPHome typical range: 256-512 samples
# Going smaller improves latency but increases CPU/network overhead
AUDIO_BLOCK_SIZE = 512  # samples at 16kHz = 32ms (lower CPU while keeping wake latency reasonable)
MAX_AUDIO_BUFFER_SIZE = AUDIO_BLOCK_SIZE * 40  # Max 40 chunks (~640ms) to prevent memory leak


class VoiceAssistantService:
    """Voice assistant service that runs ESPHome protocol server."""

    def __init__(
        self,
        reachy_mini: ReachyMini,
        name: str | None = None,
        host: str = "0.0.0.0",
        port: int = 6053,
        wake_model: str = "okay_nabu",
        camera_port: int = 8081,
        camera_enabled: bool = True,
    ):
        self.reachy_mini = reachy_mini
        self.name = name or get_default_friendly_name()
        self.host = host
        self.port = port
        self.wake_model = wake_model
        self.camera_port = camera_port
        self.camera_enabled = camera_enabled

        self._server = None
        self._discovery = None
        self._audio_thread = None
        self._running = False
        self._state: ServerState | None = None
        self._motion = ReachyMiniMotion(reachy_mini)
        self._camera_server: MJPEGCameraServer | None = None

        # Audio buffer for fixed-size chunk output
        # Use deque with maxlen to avoid creating new arrays on every operation
        # This prevents memory leak from repeated array creation (2-3 arrays per chunk)
        self._audio_buffer: deque[float] = deque(maxlen=MAX_AUDIO_BUFFER_SIZE)

        # Audio overflow log throttling
        self._last_audio_overflow_log = 0.0
        self._suppressed_audio_overflows = 0

        # Robot services pause/resume tracking (without RobotStateMonitor)
        self._robot_services_paused = threading.Event()  # Set when services should pause
        self._robot_services_resumed = threading.Event()  # Event-driven resume signaling
        self._robot_services_resumed.set()  # Start in resumed state

        # GStreamer access lock - prevents concurrent access to media pipeline
        # This prevents crashes when multiple threads access get_audio_sample(), push_audio_sample(), get_frame()
        self._gstreamer_lock = threading.Lock()

        self._event_loop: asyncio.AbstractEventLoop | None = None

        # Home Assistant connection state
        self._ha_connected = False  # Track whether HA is connected
        self._ha_connection_established = False  # Track if HA connection was ever established

    async def start(self) -> None:
        """Start the voice assistant service."""
        _LOGGER.info("Initializing voice assistant service...")

        # Ensure directories exist
        _WAKEWORDS_DIR.mkdir(parents=True, exist_ok=True)
        _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        _LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        # Verify required files (bundled with package)
        await self._verify_required_files()

        # Load wake words
        wake_word_dirs = get_wake_word_dirs(_WAKEWORDS_DIR, _LOCAL_DIR)
        available_wake_words = find_available_wake_words(wake_word_dirs, stop_model_id="stop")
        _LOGGER.debug("Available wake words: %s", list(available_wake_words.keys()))

        # Load preferences
        preferences_path = _LOCAL_DIR / "preferences.json"
        preferences = self._load_preferences(preferences_path)

        # Load wake word models
        wake_models, active_wake_words = load_wake_models(
            available_wake_words,
            preferences.active_wake_words,
            self.wake_model,
        )

        # Load stop model
        stop_model = load_stop_model(wake_word_dirs, stop_model_id="stop")

        # Create audio players with Reachy Mini reference and GStreamer lock
        music_player = AudioPlayer(self.reachy_mini, gstreamer_lock=self._gstreamer_lock)
        tts_player = LocalAudioPlayer(self.reachy_mini, gstreamer_lock=self._gstreamer_lock)

        # Create server state
        self._state = ServerState(
            name=self.name,
            mac_address=get_mac(),
            audio_queue=Queue(),
            entities=[],
            available_wake_words=available_wake_words,
            wake_words=wake_models,
            active_wake_words=active_wake_words,
            stop_word=stop_model,
            music_player=music_player,
            tts_player=tts_player,
            wakeup_sound=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
            timer_finished_sound=str(_SOUNDS_DIR / "timer_finished.flac"),
            preferences=preferences,
            preferences_path=preferences_path,
            refractory_seconds=2.0,
            download_dir=_LOCAL_DIR,
            reachy_mini=self.reachy_mini,
            motion_enabled=True,
        )

        # Log stop word status
        if self._state.stop_word:
            _LOGGER.info("Stop word initialized with ID: %s", self._state.stop_word.id)
        else:
            _LOGGER.error("Stop word is None! Stop command will not work")

        # Set motion controller reference in state
        self._state.motion = self._motion
        if self._motion and self._motion.movement_manager:
            idle_enabled = preferences.idle_behavior_enabled
            self._motion.movement_manager.set_idle_behavior_enabled(idle_enabled)
            _LOGGER.info("Idle behavior restored from preferences: %s", idle_enabled)

        # Start Reachy Mini media system
        try:
            media = self.reachy_mini.media
            daemon_status = self.reachy_mini.client.get_status()

            if getattr(self.reachy_mini, "media_released", False):
                raise RuntimeError("Reachy Mini media has been released externally; this app requires SDK-owned media")

            if getattr(daemon_status, "no_media", False):
                raise RuntimeError("Reachy Mini daemon is running with no_media=True; this app requires SDK media")

            if media.audio is None:
                raise RuntimeError("Reachy Mini audio backend is unavailable")

            if self.camera_enabled and getattr(self._state, "camera_enabled", True) and media.camera is None:
                raise RuntimeError("Reachy Mini camera backend is unavailable while camera runtime is enabled")

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
            _LOGGER.info("Started Reachy Mini recording")
            media.start_playing()
            _LOGGER.info("Started Reachy Mini playback")

            if not self._probe_audio_capture_ready(media, timeout_s=1.5):
                raise RuntimeError("Audio capture probe failed after media startup")

            _LOGGER.info("Reachy Mini media system initialized")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Reachy Mini media: {e}") from e

        # Start motion controller (5Hz control loop)
        self._motion.start()

        # Start audio processing thread (non-daemon for proper cleanup)
        self._running = True
        self._audio_thread = threading.Thread(
            target=self._process_audio,
            daemon=False,
        )
        self._audio_thread.start()

        # Create ESPHome server (pass camera_server for camera entity)
        loop = asyncio.get_running_loop()
        camera_server = self._camera_server  # Capture for lambda

        def protocol_factory():
            try:
                protocol = VoiceSatelliteProtocol(
                    self._state, camera_server=camera_server, voice_assistant_service=self
                )
                protocol.set_ha_connection_callbacks(
                    on_connected=self._on_ha_connected, on_disconnected=self._on_ha_disconnected
                )
                return protocol
            except Exception:
                _LOGGER.exception("Failed to initialize ESPHome protocol connection")
                raise

        self._server = await loop.create_server(
            protocol_factory,
            host=self.host,
            port=self.port,
        )

        # Start mDNS discovery
        self._discovery = HomeAssistantZeroconf(port=self.port, name=self.name)
        await self._discovery.register_server()

        # Store service event loop for cross-thread async toggles
        self._event_loop = asyncio.get_running_loop()

        # Start Sendspin discovery only when enabled in preferences (default OFF)
        if preferences.sendspin_enabled:
            await music_player.start_sendspin_discovery()
            _LOGGER.info("Sendspin discovery enabled from preferences")
        else:
            _LOGGER.info("Sendspin discovery disabled by default")

        _LOGGER.info("Voice assistant service started on %s:%s", self.host, self.port)

    def set_sendspin_enabled(self, enabled: bool) -> None:
        """Enable or disable Sendspin discovery and connection at runtime."""
        if self._state is None or self._state.music_player is None:
            return

        if self._state.preferences.sendspin_enabled != enabled:
            self._state.preferences.sendspin_enabled = enabled
            self._state.save_preferences()

        async def _apply() -> None:
            if self._state is None or self._state.music_player is None:
                return
            if enabled:
                await self._state.music_player.start_sendspin_discovery()
            else:
                await self._state.music_player.stop_sendspin()

        try:
            loop = self._event_loop
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(_apply(), loop)
            else:
                task = asyncio.create_task(_apply())
                task.add_done_callback(lambda _task: None)
        except Exception as e:
            _LOGGER.warning("Failed to apply Sendspin toggle (%s): %s", enabled, e)

    def set_idle_behavior_enabled(self, enabled: bool) -> None:
        """Apply idle behavior runtime changes that affect camera services."""
        if self._state is None:
            return

        self._state.preferences.idle_behavior_enabled = bool(enabled)

        async def _apply() -> None:
            await self._reconcile_camera_runtime(reason="idle_behavior_toggle")

        try:
            loop = self._event_loop
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(_apply(), loop)
            else:
                task = asyncio.create_task(_apply())
                task.add_done_callback(lambda _task: None)
        except Exception as e:
            _LOGGER.warning("Failed to apply idle behavior toggle (%s): %s", enabled, e)

    async def _start_camera_server_if_needed(self) -> None:
        if self._state is None:
            return
        if not self.camera_enabled or not self._state.camera_enabled:
            return
        if not bool(self._state.preferences.idle_behavior_enabled):
            return
        if self._camera_server is not None:
            prefs = self._state.preferences
            self._camera_server.apply_runtime_vision_state(
                face_requested=bool(prefs.face_tracking_enabled),
                gesture_requested=bool(prefs.gesture_detection_enabled),
                models_allowed=True,
            )
            self._camera_server.set_face_confidence_threshold(float(prefs.face_confidence_threshold))
            return

        self._camera_server = MJPEGCameraServer(
            reachy_mini=self.reachy_mini,
            host=self.host,
            port=self.camera_port,
            fps=15,
            quality=80,
            enable_face_tracking=bool(self._state.preferences.face_tracking_enabled),
            enable_gesture_detection=bool(self._state.preferences.gesture_detection_enabled),
            gstreamer_lock=self._gstreamer_lock,
        )

        prefs = self._state.preferences
        self._camera_server.apply_runtime_vision_state(
            face_requested=bool(prefs.face_tracking_enabled),
            gesture_requested=bool(prefs.gesture_detection_enabled),
            models_allowed=True,
        )
        self._camera_server.set_face_confidence_threshold(float(prefs.face_confidence_threshold))
        await self._camera_server.start()

        self._state._camera_server = self._camera_server
        if self._state.satellite:
            self._state.satellite.update_camera_server(self._camera_server)
        if self._motion is not None:
            self._motion.set_camera_server(self._camera_server)
        _LOGGER.info("Camera server started on %s:%s", self.host, self.camera_port)

    async def _stop_camera_server_if_running(self, *, reason: str) -> None:
        if self._camera_server is None:
            return
        await self._camera_server.stop(join_timeout=Config.shutdown.camera_stop_timeout)
        self._camera_server = None
        if self._state is not None:
            self._state._camera_server = None
            if self._state.satellite:
                self._state.satellite.update_camera_server(None)
        if self._motion is not None:
            self._motion.set_camera_server(None)
        _LOGGER.info("Camera server stopped (%s)", reason)

    async def _reconcile_camera_runtime(self, *, reason: str) -> None:
        if self._state is None:
            return
        should_run_camera = self.camera_enabled and self._state.camera_enabled and self._ha_connected
        should_run_camera = should_run_camera and bool(self._state.preferences.idle_behavior_enabled)

        if should_run_camera:
            await self._start_camera_server_if_needed()
            return

        await self._stop_camera_server_if_running(reason=reason)

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
        self._set_service_state(suspended=True)
        self._audio_buffer.clear()
        self._suspend_satellite()
        self._set_audio_players_suspended(True)
        self._stop_media_system()

        _LOGGER.info("Voice services suspended - camera and motion remain active")

    def _resume_voice_services(self, reason: str) -> None:
        """Resume only voice-related services."""
        _LOGGER.info("Resuming voice services (%s)", reason)
        self._robot_services_paused.clear()
        self._set_service_state(suspended=False)
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
        self._set_service_state(suspended=True)
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
        self._set_service_state(suspended=False)
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

    def _set_service_state(self, *, suspended: bool) -> None:
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

    async def stop(self) -> None:
        """Stop the voice assistant service."""
        _LOGGER.info("Stopping voice assistant service...")

        # 1. First stop audio recording to prevent new data from coming in
        try:
            self.reachy_mini.media.stop_recording()
            _LOGGER.debug("Reachy Mini recording stopped")
        except Exception as e:
            _LOGGER.warning("Error stopping Reachy Mini recording: %s", e)

        # 2. Set stop flag
        self._running = False
        # Wake any threads blocked on resume signal
        self._robot_services_resumed.set()

        # 3. Wait for audio thread to finish
        if self._audio_thread:
            self._audio_thread.join(timeout=Config.shutdown.audio_thread_join_timeout)
            if self._audio_thread.is_alive():
                _LOGGER.warning("Audio thread did not stop in time")

        # 4. Stop playback
        try:
            self.reachy_mini.media.stop_playing()
            _LOGGER.debug("Reachy Mini playback stopped")
        except Exception as e:
            _LOGGER.warning("Error stopping Reachy Mini playback: %s", e)

        # 5. Stop ESPHome server
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(
                    self._server.wait_closed(),
                    timeout=Config.shutdown.server_close_timeout,
                )
            except TimeoutError:
                _LOGGER.warning("ESPHome server did not close in time")

        # 6. Unregister mDNS
        if self._discovery:
            try:
                await asyncio.wait_for(
                    self._discovery.unregister_server(),
                    timeout=Config.shutdown.server_close_timeout,
                )
            except TimeoutError:
                _LOGGER.warning("mDNS unregister did not finish in time")

        # 6.5. Stop Sendspin
        if self._state and self._state.music_player:
            try:
                await asyncio.wait_for(
                    self._state.music_player.stop_sendspin(),
                    timeout=Config.shutdown.sendspin_stop_timeout,
                )
            except TimeoutError:
                _LOGGER.warning("Sendspin stop did not finish in time")

        # 7. Stop camera server
        # Only stop if camera is NOT disabled (user has not manually disabled it)
        if self._camera_server and self._state.camera_enabled:
            await self._camera_server.stop(join_timeout=Config.shutdown.camera_stop_timeout)
            self._camera_server = None
        # Close SDK media resources to prevent memory leaks (even if camera is disabled)
        try:
            self.reachy_mini.media.close()
            _LOGGER.info("SDK media resources closed")
        except Exception as e:
            _LOGGER.debug("Failed to close SDK media: %s", e)

        # 8. Shutdown motion executor
        if self._motion:
            self._motion.shutdown()

        _LOGGER.info("Voice assistant service stopped.")

    async def _verify_required_files(self) -> None:
        """Verify required model and sound files exist (bundled with package)."""
        # Required wake word files (bundled in wakewords/ directory)
        # Note: hey_jarvis is in openWakeWord/ with version suffix, so not required here
        required_wakewords = [
            "okay_nabu.tflite",
            "okay_nabu.json",
            "stop.tflite",
            "stop.json",
        ]

        # Required sound files (bundled in sounds/ directory)
        required_sounds = [
            "wake_word_triggered.flac",
            "timer_finished.flac",
        ]

        missing_wakewords = self._find_missing_files(_WAKEWORDS_DIR, required_wakewords)

        if missing_wakewords:
            _LOGGER.warning("Missing wake word files: %s. These should be bundled with the package.", missing_wakewords)

        missing_sounds = self._find_missing_files(_SOUNDS_DIR, required_sounds)

        if missing_sounds:
            _LOGGER.warning("Missing sound files: %s. These should be bundled with the package.", missing_sounds)

        if not missing_wakewords and not missing_sounds:
            _LOGGER.info("All required files verified successfully.")

    @staticmethod
    def _find_missing_files(base_dir: Path, filenames: list[str]) -> list[str]:
        return [filename for filename in filenames if not (base_dir / filename).exists()]

    def _load_preferences(self, preferences_path: Path) -> Preferences:
        """Load user preferences."""
        if preferences_path.exists():
            try:
                with open(preferences_path, encoding="utf-8") as f:
                    data = json.load(f)

                valid_fields = {field.name for field in fields(Preferences)}
                filtered = {key: value for key, value in data.items() if key in valid_fields}
                return Preferences(**filtered)
            except Exception as e:
                _LOGGER.warning("Failed to load preferences: %s", e)

        return Preferences()

    def _process_audio(self) -> None:
        """Process audio from Reachy Mini's microphone."""
        from pymicro_wakeword import MicroWakeWordFeatures

        ctx = AudioProcessingContext()
        ctx.micro_features = MicroWakeWordFeatures()

        try:
            _LOGGER.info("Starting audio processing using Reachy Mini's microphone...")
            self._audio_loop_reachy(ctx)

        except Exception:
            _LOGGER.exception("Error processing audio")

    def _audio_loop_reachy(self, ctx: AudioProcessingContext) -> None:
        """Audio loop using Reachy Mini's microphone.

        This loop checks the robot connection state before attempting to
        read audio. When the robot is disconnected (e.g., sleep mode),
        the loop waits for reconnection without generating errors.
        """
        consecutive_audio_errors = 0
        max_consecutive_errors = 3  # Pause after 3 consecutive errors

        while self._running:
            try:
                # Check if robot services are paused (sleep mode / disconnected / muted)
                if self._robot_services_paused.is_set():
                    # Wait for resume signal (event-driven, wakes immediately on resume)
                    consecutive_audio_errors = 0  # Reset on pause
                    self._robot_services_resumed.wait(timeout=1.0)
                    continue

                if not self._wait_for_satellite():
                    continue

                # Update wake words list
                self._update_wake_words_list(ctx)

                # Get audio from Reachy Mini
                audio_chunk = self._get_reachy_audio_chunk()
                if audio_chunk is None:
                    idle_sleep = (
                        Config.audio.idle_sleep_sleeping
                        if self._robot_services_paused.is_set()
                        else Config.audio.idle_sleep_active
                    )
                    time.sleep(idle_sleep)
                    continue

                # Audio successfully obtained, reset error counter
                consecutive_audio_errors = 0
                self._process_audio_chunk(ctx, audio_chunk)

            except Exception as e:
                error_msg = str(e)

                # Check for audio processing errors that indicate sleep mode
                if "can only convert" in error_msg or "scalar" in error_msg:
                    consecutive_audio_errors += 1
                    if consecutive_audio_errors >= max_consecutive_errors:
                        if not self._robot_services_paused.is_set():
                            _LOGGER.warning("Audio errors indicate robot may be asleep - pausing audio processing")
                            self._robot_services_paused.set()
                            self._robot_services_resumed.clear()
                            # Clear audio buffer
                            self._audio_buffer.clear()
                    # Wait for resume signal instead of polling
                    self._robot_services_resumed.wait(timeout=0.5)
                    continue

                # Check if this is a connection error
                if "Lost connection" in error_msg:
                    # Don't log - the state monitor will handle this
                    if not self._robot_services_paused.is_set():
                        _LOGGER.debug("Connection error detected, waiting for state monitor")
                    # Wait for resume signal instead of polling
                    self._robot_services_resumed.wait(timeout=1.0)
                else:
                    # Log unexpected errors (but limit frequency)
                    consecutive_audio_errors += 1
                    if consecutive_audio_errors <= 3:
                        _LOGGER.error("Error in Reachy audio processing: %s", e)
                    time.sleep(Config.audio.idle_sleep_sleeping)

    def _wait_for_satellite(self) -> bool:
        """Wait for satellite connection. Returns True if connected."""
        if self._state is None or self._state.satellite is None:
            time.sleep(0.1)
            return False
        return True

    def _update_wake_words_list(self, ctx: AudioProcessingContext) -> None:
        """Update wake words list if changed."""
        from pymicro_wakeword import MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

        if (not ctx.wake_words) or (self._state.wake_words_changed and self._state.wake_words):
            self._state.wake_words_changed = False
            ctx.wake_words.clear()

            # Reset feature extractors to clear any residual audio data
            # This prevents false triggers when switching wake words
            ctx.micro_features = MicroWakeWordFeatures()
            ctx.micro_inputs.clear()
            if ctx.oww_features is not None:
                ctx.oww_features = OpenWakeWordFeatures.from_builtin()
            ctx.oww_inputs.clear()

            # Also reset the refractory period to prevent immediate trigger
            ctx.last_active = time.monotonic()

            # state.wake_words is Dict[str, MicroWakeWord/OpenWakeWord]
            # We need to filter by active_wake_words (which contains the IDs/keys)
            for ww_id, ww_model in self._state.wake_words.items():
                if ww_id in self._state.active_wake_words:
                    # Ensure the model has an 'id' attribute for later use
                    if not hasattr(ww_model, "id"):
                        ww_model.id = ww_id
                    ctx.wake_words.append(ww_model)

            ctx.has_oww = any(isinstance(ww, OpenWakeWord) for ww in ctx.wake_words)
            if ctx.has_oww and ctx.oww_features is None:
                ctx.oww_features = OpenWakeWordFeatures.from_builtin()

            _LOGGER.info("Active wake words updated: %s (features reset)", list(self._state.active_wake_words))

    def _get_reachy_audio_chunk(self) -> bytes | None:
        """Get fixed-size audio chunk from Reachy Mini's microphone.

        Returns exactly AUDIO_BLOCK_SIZE samples each time, buffering
        internally to ensure consistent chunk sizes for streaming.

        Returns:
            PCM audio bytes of fixed size, or None if not enough data.
        """
        # Check if services are paused (e.g., during sleep/disconnect)
        if self._robot_services_paused.is_set():
            return None

        # Get new audio data from SDK
        audio_data = self.reachy_mini.media.get_audio_sample()

        # Debug: Log SDK audio data statistics and sample rate (once at startup)
        if audio_data is not None and isinstance(audio_data, np.ndarray) and audio_data.size > 0:
            if not hasattr(self, "_audio_sample_rate_logged"):
                self._audio_sample_rate_logged = True
                try:
                    input_rate = self.reachy_mini.media.get_input_audio_samplerate()
                    _LOGGER.info(
                        "Audio input: sample_rate=%d Hz, shape=%s, dtype=%s (expected 16000 Hz)",
                        input_rate,
                        audio_data.shape,
                        audio_data.dtype,
                    )
                    if input_rate != 16000:
                        _LOGGER.warning(
                            "Audio sample rate mismatch! Got %d Hz, expected 16000 Hz. "
                            "STT may be slow or inaccurate. Consider resampling.",
                            input_rate,
                        )
                except Exception as e:
                    _LOGGER.warning("Could not get audio sample rate: %s", e)

        # Append new data to buffer if valid
        if audio_data is not None and isinstance(audio_data, np.ndarray) and audio_data.size > 0:
            try:
                if audio_data.dtype.kind not in ("S", "U", "O", "V", "b"):
                    # Convert to float32 only if needed (SDK already returns float32)
                    if audio_data.dtype != np.float32:
                        audio_data = audio_data.astype(np.float32, copy=False)

                    # Clean NaN/Inf values early to prevent downstream errors
                    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=1.0, neginf=-1.0)

                    # Convert stereo to mono (use first channel for better quality)
                    if audio_data.ndim == 2 and audio_data.shape[1] >= 2:
                        # Use first channel instead of mean - cleaner signal
                        # Remove .copy() to avoid unnecessary array duplication
                        audio_data = audio_data[:, 0]
                    elif audio_data.ndim == 2:
                        # Remove .copy() to avoid unnecessary array duplication
                        audio_data = audio_data[:, 0]

                    # Resample if needed (SDK may return non-16kHz audio)
                    if audio_data.ndim == 1:
                        # Initialize sample rate once (not every chunk)
                        if not hasattr(self, "_input_sample_rate_fixed"):
                            try:
                                self._input_sample_rate = self.reachy_mini.media.get_input_audio_samplerate()
                                if self._input_sample_rate != 16000:
                                    _LOGGER.warning(
                                        f"Sample rate {self._input_sample_rate} != 16000 Hz. "
                                        "Performance may be degraded. "
                                        "Consider forcing 16kHz in hardware config."
                                    )
                            except Exception:
                                self._input_sample_rate = 16000

                            self._input_sample_rate_fixed = True  # Mark as fixed

                        # Resample to 16kHz if needed
                        if self._input_sample_rate != 16000 and self._input_sample_rate > 0:
                            from scipy.signal import resample

                            new_length = int(len(audio_data) * 16000 / self._input_sample_rate)
                            if new_length > 0:
                                audio_data = resample(audio_data, new_length)
                                audio_data = np.nan_to_num(
                                    audio_data,
                                    nan=0.0,
                                    posinf=1.0,
                                    neginf=-1.0,
                                ).astype(np.float32, copy=False)

                        # Extend deque (deque automatically handles overflow with maxlen)
                        # This avoids creating new arrays like np.concatenate does
                        self._audio_buffer.extend(audio_data)

            except (TypeError, ValueError):
                pass

        # Return fixed-size chunk if we have enough data
        if len(self._audio_buffer) >= AUDIO_BLOCK_SIZE:
            # Extract chunk and remove from buffer
            chunk = [self._audio_buffer.popleft() for _ in range(AUDIO_BLOCK_SIZE)]

            # Convert to PCM bytes (16-bit signed, little-endian)
            chunk_array = np.array(chunk, dtype=np.float32)
            pcm_bytes = (np.clip(chunk_array, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            return pcm_bytes

        return None

    def _convert_to_pcm(self, audio_chunk_array: np.ndarray) -> bytes:
        """Convert float32 audio array to 16-bit PCM bytes."""
        # Replace NaN/Inf with 0 to avoid casting errors
        audio_clean = np.nan_to_num(audio_chunk_array, nan=0.0, posinf=1.0, neginf=-1.0)
        return (np.clip(audio_clean, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def _process_audio_chunk(self, ctx: AudioProcessingContext, audio_chunk: bytes) -> None:
        """Process an audio chunk for wake word detection.

        Following reference project pattern: always process wake words.
        Refractory period prevents duplicate triggers.

        Args:
            ctx: Audio processing context
            audio_chunk: PCM audio bytes
        """
        # Stream audio to Home Assistant only after wake (privacy: no pre-wake upload)
        if self._state.satellite.is_streaming_audio:
            self._state.satellite.handle_audio(audio_chunk)

        # Process wake word features
        self._process_features(ctx, audio_chunk)

        # Detect wake words
        self._detect_wake_words(ctx)

        stop_context_active = (
            self._state.tts_player.is_playing
            or self._state.satellite._pipeline_active
            or self._state.satellite._timer_finished
        )

        # Stop-word inference is only useful while there is active playback or
        # a live voice pipeline/timer to interrupt.
        if stop_context_active:
            self._detect_stop_word(ctx)

    def _process_features(self, ctx: AudioProcessingContext, audio_chunk: bytes) -> None:
        """Process audio features for wake word detection."""
        ctx.micro_inputs.clear()
        ctx.micro_inputs.extend(ctx.micro_features.process_streaming(audio_chunk))

        if ctx.has_oww and ctx.oww_features is not None:
            ctx.oww_inputs.clear()
            ctx.oww_inputs.extend(ctx.oww_features.process_streaming(audio_chunk))

    def _detect_wake_words(self, ctx: AudioProcessingContext) -> None:
        """Detect wake words in the processed audio features.

        Uses refractory period to prevent duplicate triggers.
        Following reference project pattern.
        """
        from pymicro_wakeword import MicroWakeWord
        from pyopen_wakeword import OpenWakeWord

        for wake_word in ctx.wake_words:
            activated = False

            if isinstance(wake_word, MicroWakeWord):
                for micro_input in ctx.micro_inputs:
                    if wake_word.process_streaming(micro_input):
                        activated = True
            elif isinstance(wake_word, OpenWakeWord):
                for oww_input in ctx.oww_inputs:
                    for prob in wake_word.process_streaming(oww_input):
                        if prob > 0.5:
                            activated = True

            if activated:
                # Check refractory period to prevent duplicate triggers
                now = time.monotonic()
                if (ctx.last_active is None) or ((now - ctx.last_active) > self._state.refractory_seconds):
                    _LOGGER.info("Wake word detected: %s", wake_word.id)
                    self._state.satellite.wakeup(wake_word)
                    # Face tracking will handle looking at user automatically
                    self._motion.on_wakeup()
                    ctx.last_active = now

    def _detect_stop_word(self, ctx: AudioProcessingContext) -> None:
        """Detect stop word in the processed audio features."""
        if not self._state.stop_word:
            _LOGGER.warning("Stop word model not loaded")
            return

        stop_context_active = (
            self._state.tts_player.is_playing
            or self._state.satellite._pipeline_active
            or self._state.satellite._timer_finished
        )

        # Keep the stop model armed whenever playback/pipeline interruption is
        # meaningful. The active wake-word membership and model activation can
        # drift apart across HA event transitions, so re-arm both here.
        if stop_context_active:
            self._state.active_wake_words.add(self._state.stop_word.id)
            try:
                self._state.stop_word.is_active = True
            except Exception:
                pass

        stopped = False
        for micro_input in ctx.micro_inputs:
            if self._state.stop_word.process_streaming(micro_input):
                stopped = True
                break  # Stop at first detection

        if stopped and stop_context_active and (not self._state.is_muted):
            _LOGGER.info("Stop word detected - stopping playback")
            self._state.satellite.stop()
