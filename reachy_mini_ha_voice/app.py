"""Reachy Mini Home Assistant Voice Assistant App."""

import asyncio
import logging
import sys
import threading
import time
import traceback
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

try:
    from fastapi import FastAPI, Response
    from fastapi.responses import FileResponse, JSONResponse
    from starlette.staticfiles import StaticFiles
except Exception:
    FastAPI = object
    FileResponse = object
    JSONResponse = object
    StaticFiles = object

# Configure root logger to ensure logs are visible
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

_LOGGER = logging.getLogger(__name__)
_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"

# Log when module is loaded
print("=" * 80)
print("Reachy Mini Home Assistant Voice Assistant module loaded")
print("=" * 80)


class ReachyMiniHAVoiceApp(ReachyMiniApp):
    """Home Assistant Voice Assistant for Reachy Mini."""

    custom_app_url: Optional[str] = "http://0.0.0.0:7860"

    def __init__(self):
        """Initialize the app."""
        print("ReachyMiniHAVoiceApp.__init__() called")
        self._state: Optional[ServerState] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio_thread: Optional[threading.Thread] = None
        self._server: Optional[asyncio.Server] = None
        self._discovery: Optional[HomeAssistantZeroconf] = None
        self._robot: Optional[ReachyMini] = None
        self._stop_event: Optional[threading.Event] = None
        self._settings_initialized = False

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """Run the voice assistant."""
        print("=" * 80)
        print("ReachyMiniHAVoiceApp.run() called")
        print("=" * 80)
        _LOGGER.info("=" * 80)
        _LOGGER.info("Starting Reachy Mini Home Assistant Voice Assistant")
        _LOGGER.info("=" * 80)
        
        self._robot = reachy_mini
        self._stop_event = stop_event

        # Setup settings API
        try:
            self._init_settings_ui_if_needed()
            _LOGGER.info("Settings UI initialized")
        except Exception as e:
            _LOGGER.error(f"Failed to initialize settings UI: {e}")
            traceback.print_exc()

        try:
            # Create event loop
            _LOGGER.info("Creating event loop...")
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            _LOGGER.info("Event loop created")

            # Initialize server state
            _LOGGER.info("Initializing server state...")
            self._state = self._init_state(reachy_mini)
            _LOGGER.info("Server state initialized")

            # Start media recording and playing
            _LOGGER.info("Starting media recording and playing...")
            reachy_mini.media.start_recording()
            reachy_mini.media.start_playing()
            time.sleep(1)  # Give time for pipelines to start
            _LOGGER.info("Media started")

            # Start audio processing loop
            _LOGGER.info("Starting audio processing loop...")
            self._event_loop.run_until_complete(self._run_audio_loop(self._state, stop_event))

        except Exception as e:
            _LOGGER.error("=" * 80)
            _LOGGER.error(f"Error running voice assistant: {e}")
            _LOGGER.error("=" * 80)
            traceback.print_exc()
        finally:
            _LOGGER.info("Shutting down voice assistant")
            self._cleanup()

    def _init_settings_ui_if_needed(self) -> None:
        """Attach settings UI to the settings app."""
        if self._settings_initialized:
            return
        if not hasattr(self, 'settings_app') or self.settings_app is None:
            _LOGGER.warning("settings_app not available, skipping settings UI")
            return

        static_dir = _MODULE_DIR / "static"
        index_file = static_dir / "index.html"

        if hasattr(self.settings_app, "mount"):
            try:
                self.settings_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
                _LOGGER.info(f"Mounted static files from {static_dir}")
            except Exception as e:
                _LOGGER.warning(f"Failed to mount static files: {e}")
                pass

        class AppStatus(BaseModel):
            running: bool
            connected: bool = False

        @self.settings_app.get("/")
        def _root() -> FileResponse:
            return FileResponse(str(index_file))

        @self.settings_app.get("/favicon.ico")
        def _favicon() -> Response:
            return Response(status_code=204)

        @self.settings_app.get("/status")
        def _status() -> JSONResponse:
            return JSONResponse({
                "running": self._state is not None,
                "connected": self._state.satellite is not None if self._state else False
            })

        self._settings_initialized = True
        _LOGGER.info("Settings UI routes registered")

    def _init_state(self, reachy_mini: ReachyMini) -> ServerState:
        """Initialize server state."""
        # Load wake words
        _LOGGER.info("Loading wake words...")
        available_wake_words = self._load_wake_words()
        _LOGGER.info(f"Loaded {len(available_wake_words)} wake words")

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
        _LOGGER.info("Loading stop model...")
        stop_model = self._load_stop_model()
        if stop_model:
            _LOGGER.info("Stop model loaded")

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
                _LOGGER.warning(f"Wake word directory not found: {wake_word_dir}")
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
            _LOGGER.warning(f"Stop model config not found: {stop_config_path}")
            return None

        try:
            return MicroWakeWord.from_config(stop_config_path)
        except Exception as e:
            _LOGGER.error("Failed to load stop model: %s", e)
            return None

    async def _run_audio_loop(self, state: ServerState, stop_event: threading.Event) -> None:
        """Run audio processing loop and ESPHome server."""
        _LOGGER.info("Starting ESPHome server...")
        # Start ESPHome server
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(
            lambda: VoiceSatelliteProtocol(state), host="0.0.0.0", port=6053
        )
        _LOGGER.info("ESPHome server created")

        # Auto discovery (zeroconf, mDNS)
        _LOGGER.info("Registering mDNS service...")
        self._discovery = HomeAssistantZeroconf(port=6053, name="ReachyMini")
        await self._discovery.register_server()
        _LOGGER.info("mDNS service registered")

        try:
            async with self._server:
                _LOGGER.info("=" * 80)
                _LOGGER.info("ESPHome server started on port 6053")
                _LOGGER.info("mDNS service registered for auto-discovery")
                _LOGGER.info("=" * 80)
                
                # Audio processing loop
                input_sample_rate = self._robot.media.get_input_audio_samplerate()
                _LOGGER.info(f"Audio input sample rate: {input_sample_rate} Hz")
                
                wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
                micro_features: Optional[MicroWakeWordFeatures] = None
                micro_inputs: List[np.ndarray] = []

                oww_features: Optional[OpenWakeWordFeatures] = None
                oww_inputs: List[np.ndarray] = []
                has_oww = False

                last_active: Optional[float] = None

                _LOGGER.info("Audio processing loop started")

                while not stop_event.is_set():
                    # Get audio sample from Reachy Mini
                    audio_frame = self._robot.media.get_audio_sample()
                    
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

                                if stopped and (self._stop_word.id in state.active_wake_words):
                                    if state.satellite:
                                        state.satellite.stop()

                    await asyncio.sleep(0.001)  # Small sleep to avoid busy loop
                
                _LOGGER.info("Stop event received, shutting down...")
                
        finally:
            if self._discovery:
                _LOGGER.info("Unregistering mDNS service...")
                await self._discovery.unregister_server()
            _LOGGER.info("ESPHome server stopped")

    def _cleanup(self) -> None:
        """Clean up resources."""
        _LOGGER.info("Cleaning up resources...")
        if self._robot:
            try:
                self._robot.media.stop_recording()
                _LOGGER.info("Recording stopped")
            except Exception as e:
                _LOGGER.error(f"Error stopping recording: {e}")
            try:
                self._robot.media.stop_playing()
                _LOGGER.info("Playing stopped")
            except Exception as e:
                _LOGGER.error(f"Error stopping playing: {e}")
        if self._event_loop and not self._event_loop.is_closed():
            self._event_loop.close()
            _LOGGER.info("Event loop closed")
        _LOGGER.info("Cleanup complete")


class ReachyMiniAudioPlayer:
    """Audio player using Reachy Mini's media system."""
    
    def __init__(self, robot: ReachyMini):
        self._robot = robot
        self._playing = False
        
    def play(self, audio_source, done_callback=None):
        """Play audio from file or URL."""
        try:
            if isinstance(audio_source, str):
                # Check if it's a URL or file path
                if audio_source.startswith(('http://', 'https://')):
                    _LOGGER.info(f"Playing audio from URL: {audio_source}")
                    # For URLs, we would need to download and play
                    # For now, just log
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