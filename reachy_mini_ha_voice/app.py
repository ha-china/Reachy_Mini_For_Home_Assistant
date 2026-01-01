"""Reachy Mini Home Assistant Voice Assistant App."""

import asyncio
import logging
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union

import numpy as np
import pyaudio
from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

from reachy_mini import ReachyMini, ReachyMiniApp

from .models import (
    AvailableWakeWord,
    Preferences,
    ServerState,
    WakeWordType,
    AudioPlayer,
)
from .satellite import VoiceSatelliteProtocol
from .util import get_mac
from .zeroconf import HomeAssistantZeroconf

_LOGGER = logging.getLogger(__name__)
_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"


class ReachyMiniHAVoiceApp(ReachyMiniApp):
    """Home Assistant Voice Assistant for Reachy Mini."""

    custom_app_url: Optional[str] = None

    def __init__(self):
        """Initialize the app."""
        self._state: Optional[ServerState] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio_thread: Optional[threading.Thread] = None
        self._server_task: Optional[asyncio.Task] = None

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """Run the voice assistant."""
        _LOGGER.info("Starting Reachy Mini Home Assistant Voice Assistant")

        try:
            # Create event loop
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)

            # Initialize server state
            self._state = self._init_state(reachy_mini)

            # Start audio processing thread
            self._audio_thread = threading.Thread(
                target=self._process_audio,
                args=(self._state,),
                daemon=True,
            )
            self._audio_thread.start()

            # Start ESPHome server
            self._server_task = self._event_loop.create_task(
                self._run_server(self._state)
            )
            self._event_loop.run_until_complete(self._server_task)

        except Exception as e:
            _LOGGER.error("Error running voice assistant: %s", e)
        finally:
            _LOGGER.info("Shutting down voice assistant")
            if self._audio_thread:
                self._audio_thread.join(timeout=5)
            if self._event_loop:
                self._event_loop.close()

    def _init_state(self, reachy_mini: ReachyMini) -> ServerState:
        """Initialize server state."""
        # Load wake words
        available_wake_words = self._load_wake_words()

        # Load active wake words
        active_wake_words = set()
        wake_models: Dict[str, Union[MicroWakeWord, OpenWakeWord]] = {}

        # Use default wake word
        default_wake_word = "okay_nabu"
        if default_wake_word in available_wake_words:
            try:
                wake_word = available_wake_words[default_wake_word]
                wake_models[default_wake_word] = wake_word.load()
                active_wake_words.add(default_wake_word)
                _LOGGER.info("Loaded wake word: %s", default_wake_word)
            except Exception as e:
                _LOGGER.error("Failed to load wake word %s: %s", default_wake_word, e)

        # Load stop model
        stop_model = self._load_stop_model()

        # Create audio players
        tts_player = AudioPlayer()

        return ServerState(
            name="ReachyMini",
            mac_address=get_mac(),
            audio_queue=Queue(),
            entities=[],
            available_wake_words=available_wake_words,
            wake_words=wake_models,
            active_wake_words=active_wake_words,
            stop_word=stop_model,
            music_player=AudioPlayer(),
            tts_player=tts_player,
            wakeup_sound=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
            timer_finished_sound=str(_SOUNDS_DIR / "timer_finished.flac"),
            preferences=Preferences(),
            preferences_path=_REPO_DIR / "preferences.json",
            refractory_seconds=2.0,
            download_dir=_REPO_DIR / "local",
            reachy_integration=None,  # Not using Reachy integration for now
        )

    def _load_wake_words(self) -> Dict[str, AvailableWakeWord]:
        """Load available wake words."""
        available_wake_words: Dict[str, AvailableWakeWord] = {}

        for wake_word_dir in [_WAKEWORDS_DIR]:
            if not wake_word_dir.exists():
                continue

            for model_config_path in wake_word_dir.glob("*.json"):
                model_id = model_config_path.stem
                if model_id == "stop":
                    continue

                try:
                    import json

                    with open(model_config_path, "r", encoding="utf-8") as f:
                        model_config = json.load(f)
                        model_type = WakeWordType(
                            model_config.get("type", "microWakeWord")
                        )
                        if model_type == WakeWordType.OPEN_WAKE_WORD:
                            wake_word_path = model_config_path.parent / model_config["model"]
                        else:
                            wake_word_path = model_config_path

                        available_wake_words[model_id] = AvailableWakeWord(
                            id=model_id,
                            type=model_type,
                            wake_word=model_config["wake_word"],
                            trained_languages=model_config.get("trained_languages", []),
                            wake_word_path=wake_word_path,
                        )
                except Exception as e:
                    _LOGGER.error(
                        "Error loading wake word config %s: %s", model_config_path, e
                    )

        return available_wake_words

    def _load_stop_model(self) -> Optional[MicroWakeWord]:
        """Load stop word model."""
        stop_config_path = _WAKEWORDS_DIR / "stop.json"
        if not stop_config_path.exists():
            return None

        try:
            return MicroWakeWord.from_config(stop_config_path)
        except Exception as e:
            _LOGGER.error("Failed to load stop model: %s", e)
            return None

    async def _run_server(self, state: ServerState) -> None:
        """Run ESPHome server."""
        # Start ESPHome server
        loop = asyncio.get_running_loop()
        server = await loop.create_server(
            lambda: VoiceSatelliteProtocol(state), host="0.0.0.0", port=6053
        )

        # Auto discovery (zeroconf, mDNS)
        discovery = HomeAssistantZeroconf(port=6053, name="ReachyMini")
        await discovery.register_server()

        try:
            async with server:
                _LOGGER.info("ESPHome server started on port 6053")
                await server.serve_forever()
        finally:
            await discovery.unregister_server()

    def _process_audio(self, state: ServerState) -> None:
        """Process audio from microphone."""
        import pyaudio

        p = pyaudio.PyAudio()

        # Get input device
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                device_index = i
                break

        if device_index is None:
            _LOGGER.error("No audio input device found")
            return

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        try:
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK,
            )

            wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
            micro_features: Optional[MicroWakeWordFeatures] = None
            micro_inputs: List[np.ndarray] = []

            oww_features: Optional[OpenWakeWordFeatures] = None
            oww_inputs: List[np.ndarray] = []
            has_oww = False

            last_active: Optional[float] = None

            _LOGGER.info("Audio processing started")

            while True:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    audio_array = (
                        np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    )

                    # Send to satellite if connected
                    if state.satellite is not None:
                        state.satellite.handle_audio(data)

                    # Update wake word models
                    if (not wake_words) or (state.wake_words_changed and state.wake_words):
                        state.wake_words_changed = False
                        wake_words = [
                            ww
                            for ww in state.wake_words.values()
                            if ww.id in state.active_wake_words
                        ]

                        has_oww = False
                        for wake_word in wake_words:
                            if isinstance(wake_word, OpenWakeWord):
                                has_oww = True

                        if micro_features is None:
                            micro_features = MicroWakeWordFeatures()

                        if has_oww and (oww_features is None):
                            oww_features = OpenWakeWordFeatures.from_builtin()

                    # Process wake words
                    if wake_words:
                        assert micro_features is not None
                        micro_inputs.clear()
                        micro_inputs.extend(micro_features.process_streaming(data))

                        if has_oww:
                            assert oww_features is not None
                            oww_inputs.clear()
                            oww_inputs.extend(oww_features.process_streaming(data))

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
                                if (last_active is None) or (
                                    (now - last_active) > state.refractory_seconds
                                ):
                                    if state.satellite:
                                        state.satellite.wakeup(wake_word)
                                    last_active = now

                        # Process stop word
                        if state.stop_word is not None:
                            stopped = False
                            for micro_input in micro_inputs:
                                if state.stop_word.process_streaming(micro_input):
                                    stopped = True

                            if stopped and (state.stop_word.id in state.active_wake_words):
                                if state.satellite:
                                    state.satellite.stop()

                except Exception as e:
                    _LOGGER.error("Error processing audio: %s", e)
                    time.sleep(0.1)

        except Exception as e:
            _LOGGER.error("Error opening audio stream: %s", e)
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
            _LOGGER.info("Audio processing stopped")