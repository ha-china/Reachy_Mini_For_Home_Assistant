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

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"
_LOCAL_DIR = _REPO_DIR / "local"


class VoiceAssistantService:
    """Voice assistant service that runs ESPHome protocol server."""

    def __init__(
        self,
        reachy_mini: Optional[ReachyMini] = None,
        name: str = "Reachy Mini",
        host: str = "0.0.0.0",
        port: int = 6053,
        wake_model: str = "okay_nabu",
    ):
        self.reachy_mini = reachy_mini
        self.name = name
        self.host = host
        self.port = port
        self.wake_model = wake_model

        self._server = None
        self._discovery = None
        self._audio_thread = None
        self._running = False
        self._state: Optional[ServerState] = None
        self._motion = ReachyMiniMotion(reachy_mini)

    async def start(self) -> None:
        """Start the voice assistant service."""
        _LOGGER.info("Initializing voice assistant service...")

        # Ensure directories exist
        _WAKEWORDS_DIR.mkdir(parents=True, exist_ok=True)
        _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        _LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        # Download required files
        await self._download_required_files()

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

        # Create ESPHome server
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(
            lambda: VoiceSatelliteProtocol(self._state),
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

        # Stop Reachy Mini media system
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.stop_recording()
                self.reachy_mini.media.stop_playing()
            except Exception as e:
                _LOGGER.warning("Error stopping Reachy Mini media: %s", e)

        _LOGGER.info("Voice assistant service stopped.")

    async def _download_required_files(self) -> None:
        """Download required model and sound files if missing."""
        import urllib.request

        # Wake word models - use OHF-Voice/linux-voice-assistant as source
        wakeword_files = {
            "okay_nabu.tflite": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/okay_nabu.tflite",
            "okay_nabu.json": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/okay_nabu.json",
            "hey_jarvis.tflite": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/hey_jarvis.tflite",
            "hey_jarvis.json": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/hey_jarvis.json",
            "stop.tflite": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/stop.tflite",
            "stop.json": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/wakewords/stop.json",
        }

        # Sound files
        sound_files = {
            "wake_word_triggered.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/wake_word_triggered.flac",
            "timer_finished.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/timer_finished.flac",
        }

        for filename, url in wakeword_files.items():
            dest = _WAKEWORDS_DIR / filename
            if not dest.exists():
                _LOGGER.info("Downloading %s...", filename)
                try:
                    urllib.request.urlretrieve(url, dest)
                    _LOGGER.info("Downloaded %s", filename)
                except Exception as e:
                    _LOGGER.warning("Failed to download %s: %s", filename, e)

        for filename, url in sound_files.items():
            dest = _SOUNDS_DIR / filename
            if not dest.exists():
                _LOGGER.info("Downloading %s...", filename)
                try:
                    urllib.request.urlretrieve(url, dest)
                    _LOGGER.info("Downloaded %s", filename)
                except Exception as e:
                    _LOGGER.warning("Failed to download %s: %s", filename, e)

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
        """Process audio using Reachy Mini's microphone."""
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures
        from scipy.signal import resample

        # Get sample rate from Reachy Mini
        try:
            input_sample_rate = self.reachy_mini.media.get_input_audio_samplerate()
        except Exception:
            input_sample_rate = 16000  # Default fallback

        target_sample_rate = 16000  # Wake word models expect 16kHz

        while self._running:
            try:
                # Get audio from Reachy Mini (returns numpy array)
                audio_data = self.reachy_mini.media.get_audio_sample()

                if audio_data is None:
                    time.sleep(0.01)
                    continue

                # Handle bytes data - convert to numpy array first
                if isinstance(audio_data, bytes):
                    audio_data = np.frombuffer(audio_data, dtype=np.int16)
                elif isinstance(audio_data, (list, tuple)):
                    audio_data = np.array(audio_data)

                # Ensure it's a numpy array
                if not isinstance(audio_data, np.ndarray):
                    audio_data = np.asarray(audio_data)

                if audio_data.size == 0:
                    time.sleep(0.01)
                    continue

                # Handle string dtype (S1) - this is the actual error case
                if audio_data.dtype.kind in ('S', 'U', 'O'):  # bytes, unicode, object
                    # Convert bytes array to int16
                    audio_data = np.frombuffer(audio_data.tobytes(), dtype=np.int16)

                # Handle multi-dimensional arrays (stereo/multi-channel)
                if audio_data.ndim == 2:
                    if audio_data.shape[0] <= 8 and audio_data.shape[0] <= audio_data.shape[1]:
                        audio_data = audio_data.mean(axis=0)
                    else:
                        audio_data = audio_data.mean(axis=1)
                elif audio_data.ndim > 2:
                    audio_data = audio_data.reshape(-1)

                # Convert to float32 normalized to [-1.0, 1.0]
                if audio_data.dtype == np.int16:
                    audio_chunk_array = audio_data.astype(np.float32) / 32768.0
                elif audio_data.dtype == np.float32:
                    audio_chunk_array = audio_data
                elif audio_data.dtype == np.float64:
                    audio_chunk_array = audio_data.astype(np.float32)
                elif np.issubdtype(audio_data.dtype, np.integer):
                    # Other integer types
                    info = np.iinfo(audio_data.dtype)
                    scale = float(max(-info.min, info.max))
                    audio_chunk_array = audio_data.astype(np.float32) / scale
                else:
                    # Try to convert to float32
                    audio_chunk_array = audio_data.astype(np.float32)

                # Ensure 1D array
                audio_chunk_array = audio_chunk_array.reshape(-1)

                # Resample if needed
                if input_sample_rate != target_sample_rate and len(audio_chunk_array) > 0:
                    num_samples = int(len(audio_chunk_array) * target_sample_rate / input_sample_rate)
                    if num_samples > 0:
                        audio_chunk_array = resample(audio_chunk_array, num_samples).astype(np.float32)

                # Convert to 16-bit PCM for streaming to Home Assistant
                audio_chunk = (
                    (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
                    .astype("<i2")
                    .tobytes()
                )

                # Stream audio to Home Assistant
                if self._state and self._state.satellite:
                    self._state.satellite.handle_audio(audio_chunk)

                # Process wake words
                self._process_wake_words(
                    audio_chunk_array, wake_words, micro_features, micro_inputs,
                    oww_features, oww_inputs, has_oww, last_active
                )

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

        with sd.InputStream(
            samplerate=16000,
            channels=1,
            blocksize=block_size,
            dtype="float32",
        ) as stream:
            while self._running:
                audio_chunk_array, overflowed = stream.read(block_size)
                if overflowed:
                    _LOGGER.warning("Audio buffer overflow")

                audio_chunk_array = audio_chunk_array.reshape(-1)

                # Convert to 16-bit PCM for streaming
                audio_chunk = (
                    (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
                    .astype("<i2")
                    .tobytes()
                )

                # Stream audio to Home Assistant
                if self._state and self._state.satellite:
                    self._state.satellite.handle_audio(audio_chunk)

                # Process wake words
                self._process_wake_words(
                    audio_chunk_array, wake_words, micro_features, micro_inputs,
                    oww_features, oww_inputs, has_oww, last_active
                )

    def _process_wake_words(
        self,
        audio_chunk_array: np.ndarray,
        wake_words, micro_features, micro_inputs,
        oww_features, oww_inputs, has_oww, last_active
    ) -> None:
        """Process wake word detection."""
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

        # Check if wake words changed
        if self._state and self._state.wake_words_changed:
            self._state.wake_words_changed = False
            wake_words.clear()
            wake_words.extend(self._state.wake_words.values())
            has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)

            if any(isinstance(ww, MicroWakeWord) for ww in wake_words):
                micro_features = MicroWakeWordFeatures()
            else:
                micro_features = None

            if has_oww:
                oww_features = OpenWakeWordFeatures.from_builtin()
            else:
                oww_features = None

        # Initialize features if needed
        if not wake_words and self._state:
            wake_words.extend(self._state.wake_words.values())
            has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)

            if any(isinstance(ww, MicroWakeWord) for ww in wake_words):
                micro_features = MicroWakeWordFeatures()

            if has_oww:
                oww_features = OpenWakeWordFeatures.from_builtin()

        # Extract features - ensure audio is float32
        audio_chunk_array = audio_chunk_array.astype(np.float32)
        
        micro_inputs.clear()
        oww_inputs.clear()

        if micro_features:
            features = micro_features.process_streaming(audio_chunk_array)
            if features:
                micro_inputs.extend(features)

        if oww_features:
            features = oww_features.process_streaming(audio_chunk_array)
            if features:
                oww_inputs.extend(features)

        # Process wake words
        if self._state:
            for wake_word in wake_words:
                if wake_word.id not in self._state.active_wake_words:
                    continue

                activated = False

                if isinstance(wake_word, MicroWakeWord):
                    for micro_input in micro_inputs:
                        if wake_word.process_streaming(micro_input):
                            activated = True
                elif isinstance(wake_word, OpenWakeWord):
                    for oww_input in oww_inputs:
                        scores = wake_word.process_streaming(oww_input)
                        if any(s > 0.5 for s in scores):
                            activated = True

                if activated:
                    now = time.monotonic()
                    if (last_active is None) or (
                        (now - last_active) > self._state.refractory_seconds
                    ):
                        if self._state.satellite:
                            self._state.satellite.wakeup(wake_word)
                            # Trigger motion
                            if self._motion:
                                self._motion.on_wakeup()
                        last_active = now

            # Process stop word
            if self._state.stop_word:
                stopped = False
                for micro_input in micro_inputs:
                    if self._state.stop_word.process_streaming(micro_input):
                        stopped = True

                if stopped and (self._state.stop_word.id in self._state.active_wake_words):
                    if self._state.satellite:
                        self._state.satellite.stop()
