"""Reachy Mini Home Assistant Voice Assistant."""

import asyncio
import logging
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union

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

_LOGGER = logging.getLogger(__name__)
_MODULE_DIR = Path(__file__).parent
_WAKEWORDS_DIR = _MODULE_DIR / "wakewords"
_SOUNDS_DIR = _MODULE_DIR / "sounds"


class ReachyMiniHAVoiceApp(ReachyMiniApp):
    """Reachy Mini Apps entry point for the voice assistant app."""

    custom_app_url = "http://0.0.0.0:7860/"
    dont_start_webserver = False

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """Run the Reachy Mini voice assistant app."""
        _LOGGER.info("Reachy Mini HA Voice App: Starting...")
        _LOGGER.info(f"Reachy Mini connected: {reachy_mini is not None}")
        _LOGGER.info(f"Settings app: {self.settings_app is not None}")
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            instance_path = self._get_instance_path().parent
            _LOGGER.info(f"Instance path: {instance_path}")
            
            _run(
                robot=reachy_mini,
                app_stop_event=stop_event,
                settings_app=self.settings_app,
                instance_path=instance_path,
            )
        except Exception as e:
            _LOGGER.error(f"Error in run(): {e}", exc_info=True)
            raise


def _run(
    robot: ReachyMini,
    app_stop_event: threading.Event,
    settings_app=None,
    instance_path: Optional[str] = None,
) -> None:
    """Run the voice assistant."""
    _LOGGER.info("=== Starting Reachy Mini Home Assistant Voice Assistant ===")

    try:
        # Initialize server state
        _LOGGER.info("Initializing server state...")
        state = _init_state(robot)
        _LOGGER.info(f"Server state initialized: {state.name}")

        # Start audio processing thread
        _LOGGER.info("Starting audio processing thread...")
        audio_thread = threading.Thread(
            target=_process_audio,
            args=(state,),
            daemon=True,
            name="AudioProcessor",
        )
        audio_thread.start()
        _LOGGER.info("Audio processing thread started")

        # Start ESPHome server in background thread
        _LOGGER.info("Starting ESPHome server thread...")
        server_thread = threading.Thread(
            target=_run_server,
            args=(state, app_stop_event),
            daemon=True,
            name="ESPServer",
        )
        server_thread.start()
        _LOGGER.info("ESPHome server thread started")

        # Main loop - wait for stop event
        _LOGGER.info("Entering main loop...")
        while not app_stop_event.is_set():
            time.sleep(0.1)

        _LOGGER.info("=== Shutting down voice assistant ===")
    except Exception as e:
        _LOGGER.error(f"Error in _run(): {e}", exc_info=True)
        raise


def _init_state(robot: ReachyMini) -> ServerState:
    """Initialize server state."""
    _LOGGER.info("Loading wake words...")
    available_wake_words = _load_wake_words()
    _LOGGER.info(f"Found {len(available_wake_words)} available wake words")

    # Load active wake words
    active_wake_words = set()
    wake_models: Dict[str, Union[MicroWakeWord, OpenWakeWord]] = {}

    # Use default wake word
    default_wake_word = "okay_nabu"
    _LOGGER.info(f"Loading default wake word: {default_wake_word}")
    if default_wake_word in available_wake_words:
        try:
            wake_word = available_wake_words[default_wake_word]
            wake_models[default_wake_word] = wake_word.load()
            active_wake_words.add(default_wake_word)
            _LOGGER.info("Loaded wake word: %s", default_wake_word)
        except Exception as e:
            _LOGGER.error("Failed to load wake word %s: %s", default_wake_word, e)
    else:
        _LOGGER.warning(f"Wake word {default_wake_word} not found in available wake words")

    # Load stop model
    _LOGGER.info("Loading stop model...")
    stop_model = _load_stop_model()
    _LOGGER.info(f"Stop model loaded: {stop_model is not None}")

    _LOGGER.info("Creating ServerState...")
    return ServerState(
        name="ReachyMini",
        mac_address=get_mac(),
        audio_queue=Queue(),
        entities=[],
        available_wake_words=available_wake_words,
        wake_words=wake_models,
        active_wake_words=active_wake_words,
        stop_word=stop_model,
        music_player=ReachyMiniAudioPlayer(robot),
        tts_player=ReachyMiniAudioPlayer(robot),
        wakeup_sound=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
        timer_finished_sound=str(_SOUNDS_DIR / "timer_finished.flac"),
        preferences=Preferences(),
        preferences_path=_MODULE_DIR / "preferences.json",
        refractory_seconds=2.0,
        download_dir=_MODULE_DIR / "local",
        reachy_integration=None,
        media_player_entity=None,
    )


def _load_wake_words() -> Dict[str, AvailableWakeWord]:
    """Load available wake words."""
    available_wake_words: Dict[str, AvailableWakeWord] = {}

    _LOGGER.info(f"Loading wake words from: {_WAKEWORDS_DIR}")
    
    for wake_word_dir in [_WAKEWORDS_DIR]:
        if not wake_word_dir.exists():
            _LOGGER.warning(f"Wake word directory not found: {wake_word_dir}")
            continue

        _LOGGER.info(f"Scanning wake word directory: {wake_word_dir}")
        
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
                    _LOGGER.debug(f"Loaded wake word config: {model_id}")
            except Exception as e:
                _LOGGER.error("Error loading wake word config %s: %s", model_config_path, e)

    _LOGGER.info(f"Loaded {len(available_wake_words)} wake word configurations")
    return available_wake_words


def _load_stop_model() -> Optional[MicroWakeWord]:
    """Load stop word model."""
    stop_config_path = _WAKEWORDS_DIR / "stop.json"
    _LOGGER.info(f"Loading stop model from: {stop_config_path}")
    
    if not stop_config_path.exists():
        _LOGGER.warning(f"Stop model config not found: {stop_config_path}")
        return None

    try:
        model = MicroWakeWord.from_config(stop_config_path)
        _LOGGER.info("Stop model loaded successfully")
        return model
    except Exception as e:
        _LOGGER.error("Failed to load stop model: %s", e, exc_info=True)
        return None


def _run_server(state: ServerState, stop_event: threading.Event):
    """Run ESPHome server in a separate thread."""
    _LOGGER.info("ESPHome server thread: Starting...")
    
    async def server_loop():
        _LOGGER.info("ESPHome server: Creating event loop...")
        loop = asyncio.get_running_loop()
        
        _LOGGER.info("ESPHome server: Creating server on port 6053...")
        server = await loop.create_server(
            lambda: VoiceSatelliteProtocol(state), host="0.0.0.0", port=6053
        )
        _LOGGER.info("ESPHome server: Server created successfully")

        # Auto discovery (zeroconf, mDNS)
        _LOGGER.info("ESPHome server: Registering mDNS service...")
        discovery = HomeAssistantZeroconf(port=6053, name="ReachyMini")
        await discovery.register_server()
        _LOGGER.info("ESPHome server: mDNS service registered")

        try:
            async with server:
                _LOGGER.info("ESPHome server: Server started on port 6053")
                _LOGGER.info("ESPHome server: mDNS service registered for auto-discovery")
                
                while not stop_event.is_set():
                    await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.error(f"ESPHome server: Error in server loop: {e}", exc_info=True)
        finally:
            _LOGGER.info("ESPHome server: Unregistering mDNS service...")
            await discovery.unregister_server()
            _LOGGER.info("ESPHome server: Stopped")

    try:
        asyncio.run(server_loop())
    except Exception as e:
        _LOGGER.error(f"ESPHome server thread: Fatal error: {e}", exc_info=True)


def _process_audio(state: ServerState):
    """Process audio from microphone."""
    _LOGGER.info("Audio processor thread: Starting...")
    
    try:
        # Start media
        _LOGGER.info("Audio processor: Starting media recording...")
        state.music_player._robot.media.start_recording()
        _LOGGER.info("Audio processor: Starting media playback...")
        state.music_player._robot.media.start_playing()
        _LOGGER.info("Audio processor: Media started, waiting 1 second...")
        time.sleep(1)

        wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
        micro_features: Optional[MicroWakeWordFeatures] = None
        micro_inputs: List[np.ndarray] = []

        oww_features: Optional[OpenWakeWordFeatures] = None
        oww_inputs: List[np.ndarray] = []
        has_oww = False

        last_active: Optional[float] = None

        _LOGGER.info("Audio processor: Audio processing loop started")

        while True:
            try:
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
            except Exception as e:
                _LOGGER.error(f"Audio processor: Error in processing loop: {e}", exc_info=True)
                time.sleep(0.1)
    except Exception as e:
        _LOGGER.error(f"Audio processor thread: Fatal error: {e}", exc_info=True)


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
                    # For URLs, use Reachy Mini's play_sound method
                    self._robot.media.play_sound(audio_source)
                else:
                    # Load audio file using soundfile
                    import soundfile as sf
                    data, sr = sf.read(audio_source, dtype='float32')
                    
                    # Resample if needed
                    output_sr = self._robot.media.get_output_audio_samplerate()
                    if sr != output_sr:
                        from scipy.signal import resample
                        data = resample(data, int(len(data) * output_sr / sr))
                    
                    # Ensure correct shape for output channels
                    output_channels = self._robot.media.get_output_channels()
                    if data.ndim == 1 and output_channels > 1:
                        data = np.tile(data[:, None], (1, output_channels))
                    elif data.ndim == 2 and data.shape[1] < output_channels:
                        data = np.tile(data[:, [0]], (1, output_channels))
                    elif data.ndim == 2 and data.shape[1] > output_channels:
                        data = data[:, :output_channels]
                    
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