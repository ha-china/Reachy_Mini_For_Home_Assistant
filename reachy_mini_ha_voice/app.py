"""Reachy Mini Home Assistant Voice Assistant."""

import time
import threading
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union
from pydantic import BaseModel

import numpy as np
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

_LOGGER = __import__('logging').getLogger(__name__)
_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"


class ReachyMiniHAVoiceApp(ReachyMiniApp):
    """Home Assistant Voice Assistant for Reachy Mini."""

    custom_app_url: str = "http://0.0.0.0:8042"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """Run the voice assistant."""
        _LOGGER.info("Starting Reachy Mini Home Assistant Voice Assistant")

        # Initialize server state
        state = self._init_state(reachy_mini)

        # Start audio processing thread
        audio_thread = threading.Thread(
            target=self._process_audio,
            args=(state,),
            daemon=True,
        )
        audio_thread.start()

        # Start ESPHome server in background thread
        server_thread = threading.Thread(
            target=self._run_server,
            args=(state, stop_event),
            daemon=True,
        )
        server_thread.start()

        # Main loop - wait for stop event
        while not stop_event.is_set():
            time.sleep(0.1)

        _LOGGER.info("Shutting down voice assistant")

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

        return ServerState(
            name="ReachyMini",
            mac_address=get_mac(),
            audio_queue=Queue(),
            entities=[],
            available_wake_words=available_wake_words,
            wake_words=wake_models,
            active_wake_words=active_wake_words,
            stop_word=stop_model,
            music_player=ReachyMiniAudioPlayer(reachy_mini),
            tts_player=ReachyMiniAudioPlayer(reachy_mini),
            wakeup_sound=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
            timer_finished_sound=str(_SOUNDS_DIR / "timer_finished.flac"),
            preferences=Preferences(),
            preferences_path=_REPO_DIR / "preferences.json",
            refractory_seconds=2.0,
            download_dir=_REPO_DIR / "local",
            reachy_integration=None,
            media_player_entity=None,
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
                        model_type = WakeWordType(model_config.get("type", "microWakeWord"))
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
                    _LOGGER.error("Error loading wake word config %s: %s", model_config_path, e)

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

    def _run_server(self, state: ServerState, stop_event: threading.Event):
        """Run ESPHome server in a separate thread."""
        import asyncio

        async def server_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            server = await loop.create_server(
                lambda: VoiceSatelliteProtocol(state), host="0.0.0.0", port=6053
            )

            # Auto discovery (zeroconf, mDNS)
            discovery = HomeAssistantZeroconf(port=6053, name="ReachyMini")
            await discovery.register_server()

            try:
                async with server:
                    _LOGGER.info("ESPHome server started on port 6053")
                    _LOGGER.info("mDNS service registered for auto-discovery")
                    
                    while not stop_event.is_set():
                        await asyncio.sleep(0.1)
            finally:
                await discovery.unregister_server()
                _LOGGER.info("ESPHome server stopped")

        asyncio.run(server_loop())

    def _process_audio(self, state: ServerState):
        """Process audio from microphone."""
        # Start media
        state.music_player._robot.media.start_recording()
        state.music_player._robot.media.start_playing()
        time.sleep(1)

        wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
        micro_features: Optional[MicroWakeWordFeatures] = None
        micro_inputs: List[np.ndarray] = []

        oww_features: Optional[OpenWakeWordFeatures] = None
        oww_inputs: List[np.ndarray] = []
        has_oww = False

        last_active: Optional[float] = None

        _LOGGER.info("Audio processing started")

        while True:
            # Get audio sample from Reachy Mini
            audio_frame = state.music_player._robot.media.get_audio_sample()
            
            if audio_frame is not None:
                # Send to satellite if connected
                if state.satellite is not None:
                    # Convert to bytes for satellite
                    audio_bytes = (audio_frame * 32767.0).astype(np.int16).tobytes()
                    state.satellite.handle_audio(audio_bytes)

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
                    # Convert float32 audio to int16 for microWakeWord
                    audio_int16 = (audio_frame * 32767.0).astype(np.int16)
                    micro_inputs.extend(micro_features.process_streaming(audio_int16))

                    if has_oww:
                        assert oww_features is not None
                        oww_inputs.clear()
                        oww_inputs.extend(oww_features.process_streaming(audio_frame))

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

            time.sleep(0.001)


class ReachyMiniAudioPlayer:
    """Audio player using Reachy Mini's media system."""
    
    def __init__(self, robot: ReachyMini):
        self._robot = robot
        
    def play(self, audio_source, done_callback=None):
        """Play audio from file or URL."""
        try:
            if isinstance(audio_source, str):
                # Check if it's a URL or file path
                if audio_source.startswith(('http://', 'https://')):
                    _LOGGER.info(f"Playing audio from URL: {audio_source}")
                else:
                    # Load audio file
                    import soundfile as sf
                    data, sr = sf.read(audio_source)
                    if len(data.shape) > 1:
                        data = data[:, 0]
                    # Convert to float32
                    data = data.astype(np.float32)
                    # Resample if needed
                    output_sr = self._robot.media.get_output_audio_samplerate()
                    if sr != output_sr:
                        from scipy.signal import resample
                        data = resample(data, int(len(data) * output_sr / sr))
                    # Push to player
                    self._robot.media.push_audio_sample(data)
                    
            if done_callback:
                done_callback()
        except Exception as e:
            _LOGGER.error(f"Error playing audio: {e}")
    
    def stop(self):
        """Stop playback."""
        pass
    
    def duck(self):
        """Duck volume."""
        pass
    
    def unduck(self):
        """Unduck volume."""
        pass
    
    def close(self):
        """Close player."""
        pass