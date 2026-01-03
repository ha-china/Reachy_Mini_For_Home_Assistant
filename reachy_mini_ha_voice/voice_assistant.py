"""
Voice Assistant Service for Reachy Mini.

This module provides the main voice assistant service that integrates
with Home Assistant via ESPHome protocol.
"""

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union

import numpy as np

from reachy_mini import ReachyMini

from .models import AvailableWakeWord, Preferences, ServerState, WakeWordType
from .audio_player import AudioPlayer
from .satellite import VoiceSatelliteProtocol
from .util import get_mac
from .zeroconf import HomeAssistantZeroconf
from .motion import ReachyMiniMotion
from .camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_WAKEWORDS_DIR = _MODULE_DIR / "wakewords"
_SOUNDS_DIR = _MODULE_DIR / "sounds"
_LOCAL_DIR = _MODULE_DIR.parent / "local"


class VoiceAssistantService:
    """Voice assistant service that runs ESPHome protocol server."""

    def __init__(
        self,
        reachy_mini: Optional[ReachyMini] = None,
        name: str = "Reachy Mini",
        host: str = "0.0.0.0",
        port: int = 6053,
        wake_model: str = "okay_nabu",
        camera_port: int = 8081,
        camera_enabled: bool = True,
    ):
        self.reachy_mini = reachy_mini
        self.name = name
        self.host = host
        self.port = port
        self.wake_model = wake_model
        self.camera_port = camera_port
        self.camera_enabled = camera_enabled

        self._server = None
        self._discovery = None
        self._audio_thread = None
        self._running = False
        self._state: Optional[ServerState] = None
        self._motion = ReachyMiniMotion(reachy_mini)
        self._camera_server: Optional[MJPEGCameraServer] = None

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
        available_wake_words = self._load_available_wake_words()
        _LOGGER.debug("Available wake words: %s", list(available_wake_words.keys()))

        # Load preferences
        preferences_path = _LOCAL_DIR / "preferences.json"
        preferences = self._load_preferences(preferences_path)

        # Load wake word models
        wake_models, active_wake_words = self._load_wake_models(
            available_wake_words, preferences
        )

        # Load stop model
        stop_model = self._load_stop_model()

        # Create audio players with Reachy Mini reference
        music_player = AudioPlayer(self.reachy_mini)
        tts_player = AudioPlayer(self.reachy_mini)

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
            motion_enabled=self.reachy_mini is not None,
        )

        # Set motion controller reference in state
        self._state.motion = self._motion

        # Start Reachy Mini media system if available
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.start_recording()
                self.reachy_mini.media.start_playing()
                _LOGGER.info("Reachy Mini media system initialized")
            except Exception as e:
                _LOGGER.warning("Failed to initialize Reachy Mini media: %s", e)

        # Start audio processing thread
        self._running = True
        self._audio_thread = threading.Thread(
            target=self._process_audio,
            daemon=True,
        )
        self._audio_thread.start()

        # Start camera server if enabled (must be before ESPHome server)
        if self.camera_enabled:
            self._camera_server = MJPEGCameraServer(
                reachy_mini=self.reachy_mini,
                host=self.host,
                port=self.camera_port,
                fps=15,
                quality=80,
            )
            await self._camera_server.start()

        # Create ESPHome server (pass camera_server for camera entity)
        loop = asyncio.get_running_loop()
        camera_server = self._camera_server  # Capture for lambda
        self._server = await loop.create_server(
            lambda: VoiceSatelliteProtocol(self._state, camera_server=camera_server),
            host=self.host,
            port=self.port,
        )

        # Start mDNS discovery
        self._discovery = HomeAssistantZeroconf(port=self.port, name=self.name)
        await self._discovery.register_server()

        _LOGGER.info("Voice assistant service started on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        """Stop the voice assistant service."""
        _LOGGER.info("Stopping voice assistant service...")

        self._running = False

        if self._audio_thread:
            self._audio_thread.join(timeout=2.0)

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        if self._discovery:
            await self._discovery.unregister_server()

        # Stop camera server
        if self._camera_server:
            await self._camera_server.stop()
            self._camera_server = None

        # Stop Reachy Mini media system
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.stop_recording()
                self.reachy_mini.media.stop_playing()
            except Exception as e:
                _LOGGER.warning("Error stopping Reachy Mini media: %s", e)

        _LOGGER.info("Voice assistant service stopped.")

    async def _verify_required_files(self) -> None:
        """Verify required model and sound files exist (bundled with package)."""
        # Required wake word files (bundled in wakewords/ directory)
        required_wakewords = [
            "okay_nabu.tflite",
            "okay_nabu.json",
            "hey_jarvis.tflite",
            "hey_jarvis.json",
            "stop.tflite",
            "stop.json",
        ]

        # Required sound files (bundled in sounds/ directory)
        required_sounds = [
            "wake_word_triggered.flac",
            "timer_finished.flac",
        ]

        # Verify wake word files
        missing_wakewords = []
        for filename in required_wakewords:
            filepath = _WAKEWORDS_DIR / filename
            if not filepath.exists():
                missing_wakewords.append(filename)

        if missing_wakewords:
            _LOGGER.warning(
                "Missing wake word files: %s. These should be bundled with the package.",
                missing_wakewords
            )

        # Verify sound files
        missing_sounds = []
        for filename in required_sounds:
            filepath = _SOUNDS_DIR / filename
            if not filepath.exists():
                missing_sounds.append(filename)

        if missing_sounds:
            _LOGGER.warning(
                "Missing sound files: %s. These should be bundled with the package.",
                missing_sounds
            )

        if not missing_wakewords and not missing_sounds:
            _LOGGER.info("All required files verified successfully.")

    def _load_available_wake_words(self) -> Dict[str, AvailableWakeWord]:
        """Load available wake word configurations."""
        available_wake_words: Dict[str, AvailableWakeWord] = {}

        wake_word_dirs = [_WAKEWORDS_DIR, _LOCAL_DIR / "external_wake_words"]

        for wake_word_dir in wake_word_dirs:
            if not wake_word_dir.exists():
                continue

            for config_path in wake_word_dir.glob("*.json"):
                model_id = config_path.stem
                if model_id == "stop":
                    continue

                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)

                    model_type = WakeWordType(config.get("type", "micro"))

                    if model_type == WakeWordType.OPEN_WAKE_WORD:
                        wake_word_path = config_path.parent / config["model"]
                    else:
                        wake_word_path = config_path

                    available_wake_words[model_id] = AvailableWakeWord(
                        id=model_id,
                        type=model_type,
                        wake_word=config.get("wake_word", model_id),
                        trained_languages=config.get("trained_languages", []),
                        wake_word_path=wake_word_path,
                    )
                except Exception as e:
                    _LOGGER.warning("Failed to load wake word %s: %s", config_path, e)

        return available_wake_words

    def _load_preferences(self, preferences_path: Path) -> Preferences:
        """Load user preferences."""
        if preferences_path.exists():
            try:
                with open(preferences_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Preferences(**data)
            except Exception as e:
                _LOGGER.warning("Failed to load preferences: %s", e)

        return Preferences()

    def _load_wake_models(
        self,
        available_wake_words: Dict[str, AvailableWakeWord],
        preferences: Preferences,
    ):
        """Load wake word models."""
        from pymicro_wakeword import MicroWakeWord
        from pyopen_wakeword import OpenWakeWord

        wake_models: Dict[str, Union[MicroWakeWord, OpenWakeWord]] = {}
        active_wake_words: Set[str] = set()

        # Try to load preferred models
        if preferences.active_wake_words:
            for wake_word_id in preferences.active_wake_words:
                wake_word = available_wake_words.get(wake_word_id)
                if wake_word is None:
                    _LOGGER.warning("Unknown wake word: %s", wake_word_id)
                    continue

                try:
                    _LOGGER.debug("Loading wake model: %s", wake_word_id)
                    wake_models[wake_word_id] = wake_word.load()
                    active_wake_words.add(wake_word_id)
                except Exception as e:
                    _LOGGER.warning("Failed to load wake model %s: %s", wake_word_id, e)

        # Load default model if none loaded
        if not wake_models:
            wake_word = available_wake_words.get(self.wake_model)
            if wake_word:
                try:
                    _LOGGER.debug("Loading default wake model: %s", self.wake_model)
                    wake_models[self.wake_model] = wake_word.load()
                    active_wake_words.add(self.wake_model)
                except Exception as e:
                    _LOGGER.error("Failed to load default wake model: %s", e)

        return wake_models, active_wake_words

    def _load_stop_model(self):
        """Load the stop word model."""
        from pymicro_wakeword import MicroWakeWord

        stop_config = _WAKEWORDS_DIR / "stop.json"
        if stop_config.exists():
            try:
                return MicroWakeWord.from_config(stop_config)
            except Exception as e:
                _LOGGER.warning("Failed to load stop model: %s", e)

        # Return a dummy model if stop model not available
        _LOGGER.warning("Stop model not available, using fallback")
        okay_nabu_config = _WAKEWORDS_DIR / "okay_nabu.json"
        if okay_nabu_config.exists():
            return MicroWakeWord.from_config(okay_nabu_config)

        return None

    def _process_audio(self) -> None:
        """Process audio from Reachy Mini's microphone."""
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

        wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
        micro_features: Optional[MicroWakeWordFeatures] = None
        micro_inputs: List[np.ndarray] = []
        oww_features: Optional[OpenWakeWordFeatures] = None
        oww_inputs: List[np.ndarray] = []
        has_oww = False
        last_active: Optional[float] = None

        try:
            _LOGGER.info("Starting audio processing...")

            # Use Reachy Mini's microphone if available
            use_reachy_audio = self.reachy_mini is not None

            if use_reachy_audio:
                _LOGGER.info("Using Reachy Mini's microphone")
                self._process_audio_reachy(
                    wake_words, micro_features, micro_inputs,
                    oww_features, oww_inputs, has_oww, last_active
                )
            else:
                _LOGGER.info("Using system microphone (fallback)")
                self._process_audio_fallback(
                    wake_words, micro_features, micro_inputs,
                    oww_features, oww_inputs, has_oww, last_active
                )

        except Exception:
            _LOGGER.exception("Error processing audio")

    def _process_audio_reachy(
        self,
        wake_words, micro_features, micro_inputs,
        oww_features, oww_inputs, has_oww, last_active
    ) -> None:
        """Process audio using Reachy Mini's microphone.

        Based on official SDK examples (sound_record.py):
        - get_audio_sample() returns np.ndarray with dtype=float32, shape=(samples, 2)
        - Data is already normalized to [-1.0, 1.0] range
        """
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

        # Initialize features once
        micro_features = MicroWakeWordFeatures()

        while self._running:
            try:
                # Skip if no satellite connection
                if self._state is None or self._state.satellite is None:
                    time.sleep(0.1)
                    continue

                # Update wake words list if changed
                if (not wake_words) or (self._state.wake_words_changed and self._state.wake_words):
                    self._state.wake_words_changed = False
                    wake_words.clear()
                    wake_words.extend([
                        ww for ww in self._state.wake_words.values()
                        if ww.id in self._state.active_wake_words
                    ])

                    has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)
                    if has_oww and oww_features is None:
                        oww_features = OpenWakeWordFeatures.from_builtin()

                    _LOGGER.debug("Wake words updated: %s", [ww.id for ww in wake_words])

                # Get audio from Reachy Mini
                audio_data = self.reachy_mini.media.get_audio_sample()

                # Skip if no data
                if audio_data is None:
                    time.sleep(0.01)
                    continue

                # Validate data type
                if not isinstance(audio_data, np.ndarray):
                    time.sleep(0.01)
                    continue

                # Skip empty arrays
                if audio_data.size == 0:
                    time.sleep(0.01)
                    continue

                # Validate and convert dtype
                try:
                    if audio_data.dtype.kind in ('S', 'U', 'O', 'V', 'b'):
                        time.sleep(0.01)
                        continue
                    if audio_data.dtype != np.float32:
                        audio_data = np.asarray(audio_data, dtype=np.float32)
                except (TypeError, ValueError):
                    time.sleep(0.01)
                    continue

                # Convert stereo to mono
                try:
                    if audio_data.ndim == 2 and audio_data.shape[1] == 2:
                        audio_chunk_array = audio_data.mean(axis=1)
                    elif audio_data.ndim == 2:
                        audio_chunk_array = audio_data[:, 0].copy()
                    elif audio_data.ndim == 1:
                        audio_chunk_array = audio_data
                    else:
                        time.sleep(0.01)
                        continue
                except Exception:
                    time.sleep(0.01)
                    continue

                # Convert to 16-bit PCM bytes
                audio_chunk = (
                    (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
                    .astype("<i2")
                    .tobytes()
                )

                # Stream audio to Home Assistant
                self._state.satellite.handle_audio(audio_chunk)

                # Process wake word features
                micro_inputs.clear()
                micro_inputs.extend(micro_features.process_streaming(audio_chunk))

                if has_oww and oww_features is not None:
                    oww_inputs.clear()
                    oww_inputs.extend(oww_features.process_streaming(audio_chunk))

                # Check each wake word
                for wake_word in wake_words:
                    activated = False

                    if isinstance(wake_word, MicroWakeWord):
                        for micro_input in micro_inputs:
                            if wake_word.process_streaming(micro_input):
                                activated = True
                    elif isinstance(wake_word, OpenWakeWord):
                        for oww_input in oww_inputs:
                            for prob in wake_word.process_streaming(oww_input):
                                if prob > 0.5:
                                    activated = True

                    if activated:
                        now = time.monotonic()
                        if (last_active is None) or ((now - last_active) > self._state.refractory_seconds):
                            _LOGGER.info("Wake word detected: %s", wake_word.id)
                            self._state.satellite.wakeup(wake_word)
                            # Get DOA angle and turn to sound source
                            doa_angle_deg = self._get_doa_angle_deg()
                            self._motion.on_wakeup(doa_angle_deg)
                            last_active = now

                # Process stop word
                if self._state.stop_word:
                    stopped = False
                    for micro_input in micro_inputs:
                        if self._state.stop_word.process_streaming(micro_input):
                            stopped = True

                    if stopped and (self._state.stop_word.id in self._state.active_wake_words):
                        _LOGGER.info("Stop word detected")
                        self._state.satellite.stop()

            except Exception as e:
                _LOGGER.error("Error in Reachy audio processing: %s", e)
                time.sleep(0.1)

    def _process_audio_fallback(
        self,
        wake_words, micro_features, micro_inputs,
        oww_features, oww_inputs, has_oww, last_active
    ) -> None:
        """Process audio using system microphone (fallback)."""
        import sounddevice as sd
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

        block_size = 1024
        micro_features = MicroWakeWordFeatures()

        with sd.InputStream(
            samplerate=16000,
            channels=1,
            blocksize=block_size,
            dtype="float32",
        ) as stream:
            while self._running:
                # Skip if no satellite connection
                if self._state is None or self._state.satellite is None:
                    time.sleep(0.1)
                    continue

                # Update wake words list if changed
                if (not wake_words) or (self._state.wake_words_changed and self._state.wake_words):
                    self._state.wake_words_changed = False
                    wake_words.clear()
                    wake_words.extend([
                        ww for ww in self._state.wake_words.values()
                        if ww.id in self._state.active_wake_words
                    ])

                    has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)
                    if has_oww and oww_features is None:
                        oww_features = OpenWakeWordFeatures.from_builtin()

                audio_chunk_array, overflowed = stream.read(block_size)
                if overflowed:
                    _LOGGER.warning("Audio buffer overflow")

                audio_chunk_array = audio_chunk_array.reshape(-1)

                # Convert to 16-bit PCM bytes
                audio_chunk = (
                    (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
                    .astype("<i2")
                    .tobytes()
                )

                # Stream audio to Home Assistant
                self._state.satellite.handle_audio(audio_chunk)

                # Process wake word features
                micro_inputs.clear()
                micro_inputs.extend(micro_features.process_streaming(audio_chunk))

                if has_oww and oww_features is not None:
                    oww_inputs.clear()
                    oww_inputs.extend(oww_features.process_streaming(audio_chunk))

                # Check each wake word
                for wake_word in wake_words:
                    activated = False

                    if isinstance(wake_word, MicroWakeWord):
                        for micro_input in micro_inputs:
                            if wake_word.process_streaming(micro_input):
                                activated = True
                    elif isinstance(wake_word, OpenWakeWord):
                        for oww_input in oww_inputs:
                            for prob in wake_word.process_streaming(oww_input):
                                if prob > 0.5:
                                    activated = True

                    if activated:
                        now = time.monotonic()
                        if (last_active is None) or ((now - last_active) > self._state.refractory_seconds):
                            _LOGGER.info("Wake word detected: %s", wake_word.id)
                            self._state.satellite.wakeup(wake_word)
                            # Get DOA angle and turn to sound source
                            doa_angle_deg = self._get_doa_angle_deg()
                            self._motion.on_wakeup(doa_angle_deg)
                            last_active = now

                # Process stop word
                if self._state.stop_word:
                    stopped = False
                    for micro_input in micro_inputs:
                        if self._state.stop_word.process_streaming(micro_input):
                            stopped = True

                    if stopped and (self._state.stop_word.id in self._state.active_wake_words):
                        _LOGGER.info("Stop word detected")
                        self._state.satellite.stop()

    def _get_doa_angle_deg(self) -> Optional[float]:
        """Get DOA angle in degrees from Reachy Mini's microphone array.

        The ReSpeaker DOA returns angle in radians where:
        - 0 radians = left
        - π/2 radians = front/back
        - π radians = right

        We convert this to head yaw degrees where:
        - 0 = front
        - positive = right
        - negative = left

        Returns:
            DOA angle in degrees suitable for head yaw, or None if unavailable.
        """
        if self.reachy_mini is None:
            return None

        try:
            import math
            doa_result = self.reachy_mini.media.get_DoA()
            if doa_result is None:
                _LOGGER.debug("DOA not available")
                return None

            doa_radians, speech_detected = doa_result

            # Note: We don't check speech_detected here because we already know
            # speech was detected (wake word triggered this call).
            # The DOA value should still be valid from the recent speech.

            # Convert ReSpeaker DOA to head yaw angle
            # ReSpeaker: 0=left, π/2=front, π=right
            # Head yaw: 0=front, positive=right, negative=left
            # Formula: yaw = (doa - π/2) converted to degrees
            yaw_radians = doa_radians - (math.pi / 2)
            yaw_degrees = math.degrees(yaw_radians)

            _LOGGER.info("DOA detected: %.1f rad -> yaw %.1f deg (speech=%s)",
                        doa_radians, yaw_degrees, speech_detected)

            return yaw_degrees

        except Exception as e:
            _LOGGER.error("Error getting DOA angle: %s", e)
            return None
