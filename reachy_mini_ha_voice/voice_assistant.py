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
from dataclasses import dataclass, field
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
from .tap_detector import TapDetector

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_WAKEWORDS_DIR = _MODULE_DIR / "wakewords"
_SOUNDS_DIR = _MODULE_DIR / "sounds"
_LOCAL_DIR = _MODULE_DIR.parent / "local"


@dataclass
class AudioProcessingContext:
    """Context for audio processing, holding mutable state."""
    wake_words: List = field(default_factory=list)
    micro_features: Optional[object] = None
    micro_inputs: List = field(default_factory=list)
    oww_features: Optional[object] = None
    oww_inputs: List = field(default_factory=list)
    has_oww: bool = False
    last_active: Optional[float] = None


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
        self._tap_detector: Optional[TapDetector] = None
        self._last_tap_wakeup: float = 0.0  # For refractory period

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
                # Check if media system is already running to avoid conflicts
                media = self.reachy_mini.media
                if media.audio is not None:
                    # Check recording state
                    is_recording = getattr(media, '_recording', False)
                    if not is_recording:
                        media.start_recording()
                        _LOGGER.info("Started Reachy Mini recording")
                    else:
                        _LOGGER.debug("Reachy Mini recording already active")

                    # Check playback state
                    is_playing = getattr(media, '_playing', False)
                    if not is_playing:
                        media.start_playing()
                        _LOGGER.info("Started Reachy Mini playback")
                    else:
                        _LOGGER.debug("Reachy Mini playback already active")

                    _LOGGER.info("Reachy Mini media system initialized")
                    
                    # Optimize microphone settings for voice recognition
                    self._optimize_microphone_settings()
                else:
                    _LOGGER.warning("Reachy Mini audio system not available")
            except Exception as e:
                _LOGGER.warning("Failed to initialize Reachy Mini media: %s", e)

        # Start motion controller (5Hz control loop)
        if self._motion is not None:
            self._motion.start()

        # Start tap detector for "tap to wake" (Wireless version only)
        if self.reachy_mini is not None:
            from .tap_detector import TAP_THRESHOLD_G_DEFAULT
            # Use saved preference or default
            tap_threshold = preferences.tap_sensitivity if preferences.tap_sensitivity > 0 else TAP_THRESHOLD_G_DEFAULT
            self._tap_detector = TapDetector(
                reachy_mini=self.reachy_mini,
                on_tap_callback=self._on_tap_detected,
                threshold_g=tap_threshold,
                cooldown_seconds=1.0,
            )
            _LOGGER.info("Tap detector started with threshold: %.1fg", tap_threshold)
            self._tap_detector.start()
            # Store tap_detector in state for entity registry access
            self._state.tap_detector = self._tap_detector

        # Start audio processing thread (non-daemon for proper cleanup)
        self._running = True
        self._audio_thread = threading.Thread(
            target=self._process_audio,
            daemon=False,
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
                enable_face_tracking=True,
            )
            await self._camera_server.start()
            
            # Connect camera server to motion controller for face tracking
            if self._motion is not None:
                self._motion.set_camera_server(self._camera_server)

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

        # Start Sendspin auto-discovery (auto-enabled, no user config needed)
        # Sendspin is for music playback, so connect to music_player
        await music_player.start_sendspin_discovery()

        _LOGGER.info("Voice assistant service started on %s:%s", self.host, self.port)

    def _optimize_microphone_settings(self) -> None:
        """Optimize ReSpeaker XVF3800 microphone settings for voice recognition.
        
        This method configures the XMOS XVF3800 audio processor for optimal
        voice command recognition at distances up to 2-3 meters.
        
        Key optimizations:
        1. Enable AGC with higher max gain for distant speech
        2. Reduce noise suppression to preserve quiet speech
        3. Increase base microphone gain
        4. Optimize AGC response times for voice commands
        
        Reference: reachy_mini/src/reachy_mini/media/audio_control_utils.py
        XMOS docs: https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/AA_control_command_appendix.html
        """
        if self.reachy_mini is None:
            return
        
        try:
            # Access ReSpeaker through the media audio system
            audio = self.reachy_mini.media.audio
            if audio is None or not hasattr(audio, '_respeaker'):
                _LOGGER.debug("ReSpeaker not available for optimization")
                return
            
            respeaker = audio._respeaker
            if respeaker is None:
                _LOGGER.debug("ReSpeaker device not found")
                return
            
            # ========== 1. AGC (Automatic Gain Control) Settings ==========
            # Enable AGC for automatic volume normalization
            try:
                respeaker.write("PP_AGCONOFF", [1])
                _LOGGER.info("AGC enabled (PP_AGCONOFF=1)")
            except Exception as e:
                _LOGGER.debug("Could not enable AGC: %s", e)
            
            # Increase AGC max gain for better distant speech pickup
            # Default is ~15dB, increase to 30dB for voice commands at distance
            # Range: 0-40 dB (float)
            try:
                respeaker.write("PP_AGCMAXGAIN", [30.0])
                _LOGGER.info("AGC max gain increased (PP_AGCMAXGAIN=30.0dB)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_AGCMAXGAIN: %s", e)
            
            # Set AGC desired output level (target level after gain)
            # More negative = quieter output, less negative = louder
            # Default is around -25dB, set to -18dB for stronger output
            try:
                respeaker.write("PP_AGCDESIREDLEVEL", [-18.0])
                _LOGGER.info("AGC desired level set (PP_AGCDESIREDLEVEL=-18.0dB)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_AGCDESIREDLEVEL: %s", e)
            
            # Optimize AGC time constants for voice commands
            # Faster attack time helps capture sudden speech onset
            try:
                respeaker.write("PP_AGCTIME", [0.5])  # Main time constant (seconds)
                _LOGGER.debug("AGC time constant set (PP_AGCTIME=0.5s)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_AGCTIME: %s", e)
            
            # ========== 2. Base Microphone Gain ==========
            # Increase base microphone gain for better sensitivity
            # Default is 1.0, increase to 2.0 for distant speech
            # Range: 0.0-4.0 (float, linear gain multiplier)
            try:
                respeaker.write("AUDIO_MGR_MIC_GAIN", [2.0])
                _LOGGER.info("Microphone gain increased (AUDIO_MGR_MIC_GAIN=2.0)")
            except Exception as e:
                _LOGGER.debug("Could not set AUDIO_MGR_MIC_GAIN: %s", e)
            
            # ========== 3. Noise Suppression Settings ==========
            # Reduce noise suppression to preserve quiet speech
            # PP_MIN_NS: minimum noise suppression threshold
            # Higher values = less aggressive suppression = better voice pickup
            # PP_MIN_NS = 0.85 means "keep at least 85% of signal" = 15% max suppression
            # UI shows "noise suppression strength" so 15% = PP_MIN_NS of 0.85
            try:
                respeaker.write("PP_MIN_NS", [0.85])  # 15% noise suppression strength
                _LOGGER.info("Noise suppression set to 15%% strength (PP_MIN_NS=0.85)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_MIN_NS: %s", e)
            
            # PP_MIN_NN: minimum noise floor estimation
            # Higher values = less aggressive noise floor tracking
            try:
                respeaker.write("PP_MIN_NN", [0.85])  # Match PP_MIN_NS
                _LOGGER.info("Noise floor threshold set (PP_MIN_NN=0.85)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_MIN_NN: %s", e)
            
            # ========== 4. Echo Cancellation Settings ==========
            # Ensure echo cancellation is enabled (important for TTS playback)
            try:
                respeaker.write("PP_ECHOONOFF", [1])
                _LOGGER.debug("Echo cancellation enabled (PP_ECHOONOFF=1)")
            except Exception as e:
                _LOGGER.debug("Could not set PP_ECHOONOFF: %s", e)
            
            # ========== 5. High-pass filter (remove low frequency noise) ==========
            try:
                respeaker.write("AEC_HPFONOFF", [1])
                _LOGGER.debug("High-pass filter enabled (AEC_HPFONOFF=1)")
            except Exception as e:
                _LOGGER.debug("Could not set AEC_HPFONOFF: %s", e)
            
            _LOGGER.info("Microphone settings optimized for voice recognition (AGC=ON, MaxGain=30dB, MicGain=2.0x)")
            
        except Exception as e:
            _LOGGER.warning("Failed to optimize microphone settings: %s", e)

    async def stop(self) -> None:
        """Stop the voice assistant service."""
        _LOGGER.info("Stopping voice assistant service...")

        # 1. First stop audio recording to prevent new data from coming in
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.stop_recording()
                _LOGGER.debug("Reachy Mini recording stopped")
            except Exception as e:
                _LOGGER.warning("Error stopping Reachy Mini recording: %s", e)

        # 2. Set stop flag
        self._running = False

        # 3. Wait for audio thread to finish
        if self._audio_thread:
            self._audio_thread.join(timeout=1.0)
            if self._audio_thread.is_alive():
                _LOGGER.warning("Audio thread did not stop in time")

        # 4. Stop playback
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.stop_playing()
                _LOGGER.debug("Reachy Mini playback stopped")
            except Exception as e:
                _LOGGER.warning("Error stopping Reachy Mini playback: %s", e)

        # 5. Stop ESPHome server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # 6. Unregister mDNS
        if self._discovery:
            await self._discovery.unregister_server()

        # 6.5. Stop Sendspin
        if self._state and self._state.music_player:
            await self._state.music_player.stop_sendspin()

        # 7. Stop camera server
        if self._camera_server:
            await self._camera_server.stop()
            self._camera_server = None

        # 8. Stop tap detector
        if self._tap_detector:
            self._tap_detector.stop()
            self._tap_detector = None

        # 9. Shutdown motion executor
        if self._motion:
            self._motion.shutdown()

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
                    loaded_model = wake_word.load()
                    # Set id attribute on the model for later identification
                    setattr(loaded_model, 'id', wake_word_id)
                    wake_models[wake_word_id] = loaded_model
                    active_wake_words.add(wake_word_id)
                except Exception as e:
                    _LOGGER.warning("Failed to load wake model %s: %s", wake_word_id, e)

        # Load default model if none loaded
        if not wake_models:
            wake_word = available_wake_words.get(self.wake_model)
            if wake_word:
                try:
                    _LOGGER.debug("Loading default wake model: %s", self.wake_model)
                    loaded_model = wake_word.load()
                    # Set id attribute on the model for later identification
                    setattr(loaded_model, 'id', self.wake_model)
                    wake_models[self.wake_model] = loaded_model
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
        """Process audio from microphone (Reachy Mini or system fallback)."""
        from pymicro_wakeword import MicroWakeWordFeatures

        ctx = AudioProcessingContext()
        ctx.micro_features = MicroWakeWordFeatures()

        try:
            _LOGGER.info("Starting audio processing...")

            if self.reachy_mini is not None:
                _LOGGER.info("Using Reachy Mini's microphone")
                self._audio_loop_reachy(ctx)
            else:
                _LOGGER.info("Using system microphone (fallback)")
                self._audio_loop_fallback(ctx)

        except Exception:
            _LOGGER.exception("Error processing audio")

    def _audio_loop_reachy(self, ctx: AudioProcessingContext) -> None:
        """Audio loop using Reachy Mini's microphone."""
        while self._running:
            try:
                if not self._wait_for_satellite():
                    continue

                self._update_wake_words_list(ctx)

                # Get audio from Reachy Mini
                audio_chunk = self._get_reachy_audio_chunk()
                if audio_chunk is None:
                    time.sleep(0.01)
                    continue

                self._process_audio_chunk(ctx, audio_chunk)

            except Exception as e:
                _LOGGER.error("Error in Reachy audio processing: %s", e)
                time.sleep(0.1)

    def _audio_loop_fallback(self, ctx: AudioProcessingContext) -> None:
        """Audio loop using system microphone (fallback)."""
        import sounddevice as sd

        block_size = 1024

        with sd.InputStream(
            samplerate=16000,
            channels=1,
            blocksize=block_size,
            dtype="float32",
        ) as stream:
            while self._running:
                if not self._wait_for_satellite():
                    continue

                self._update_wake_words_list(ctx)

                # Get audio from system microphone
                audio_chunk_array, overflowed = stream.read(block_size)
                if overflowed:
                    _LOGGER.warning("Audio buffer overflow")

                audio_chunk_array = audio_chunk_array.reshape(-1)
                audio_chunk = self._convert_to_pcm(audio_chunk_array)

                self._process_audio_chunk(ctx, audio_chunk)

    def _wait_for_satellite(self) -> bool:
        """Wait for satellite connection. Returns True if connected."""
        if self._state is None or self._state.satellite is None:
            time.sleep(0.1)
            return False
        return True

    def _update_wake_words_list(self, ctx: AudioProcessingContext) -> None:
        """Update wake words list if changed."""
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures
        from pymicro_wakeword import MicroWakeWordFeatures

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
                    if not hasattr(ww_model, 'id'):
                        setattr(ww_model, 'id', ww_id)
                    ctx.wake_words.append(ww_model)

            ctx.has_oww = any(isinstance(ww, OpenWakeWord) for ww in ctx.wake_words)
            if ctx.has_oww and ctx.oww_features is None:
                ctx.oww_features = OpenWakeWordFeatures.from_builtin()

            _LOGGER.info("Active wake words updated: %s (features reset)", list(self._state.active_wake_words))

    def _get_reachy_audio_chunk(self) -> Optional[bytes]:
        """Get audio chunk from Reachy Mini's microphone.

        Returns:
            PCM audio bytes, or None if no valid audio available.
        """
        audio_data = self.reachy_mini.media.get_audio_sample()

        # Validate audio data
        if audio_data is None:
            return None
        if not isinstance(audio_data, np.ndarray):
            return None
        if audio_data.size == 0:
            return None

        # Validate and convert dtype
        try:
            if audio_data.dtype.kind in ('S', 'U', 'O', 'V', 'b'):
                return None
            if audio_data.dtype != np.float32:
                audio_data = np.asarray(audio_data, dtype=np.float32)
        except (TypeError, ValueError):
            return None

        # Convert stereo to mono
        try:
            if audio_data.ndim == 2 and audio_data.shape[1] == 2:
                audio_chunk_array = audio_data.mean(axis=1)
            elif audio_data.ndim == 2:
                audio_chunk_array = audio_data[:, 0].copy()
            elif audio_data.ndim == 1:
                audio_chunk_array = audio_data
            else:
                return None
        except Exception:
            return None

        return self._convert_to_pcm(audio_chunk_array)

    def _convert_to_pcm(self, audio_chunk_array: np.ndarray) -> bytes:
        """Convert float32 audio array to 16-bit PCM bytes."""
        return (
            (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
            .astype("<i2")
            .tobytes()
        )

    def _process_audio_chunk(self, ctx: AudioProcessingContext, audio_chunk: bytes) -> None:
        """Process an audio chunk for wake word detection.

        Args:
            ctx: Audio processing context
            audio_chunk: PCM audio bytes
        """
        # Stream audio to Home Assistant
        self._state.satellite.handle_audio(audio_chunk)

        # Skip wake word processing entirely if pipeline is active
        # This prevents model state accumulation during conversation
        if self._state.satellite.is_pipeline_active():
            return

        # Process wake word features
        self._process_features(ctx, audio_chunk)

        # Detect wake words
        self._detect_wake_words(ctx)

        # Detect stop word
        self._detect_stop_word(ctx)

    def _process_features(self, ctx: AudioProcessingContext, audio_chunk: bytes) -> None:
        """Process audio features for wake word detection."""
        ctx.micro_inputs.clear()
        ctx.micro_inputs.extend(ctx.micro_features.process_streaming(audio_chunk))

        if ctx.has_oww and ctx.oww_features is not None:
            ctx.oww_inputs.clear()
            ctx.oww_inputs.extend(ctx.oww_features.process_streaming(audio_chunk))

    def _detect_wake_words(self, ctx: AudioProcessingContext) -> None:
        """Detect wake words in the processed audio features."""
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
            return

        stopped = False
        for micro_input in ctx.micro_inputs:
            if self._state.stop_word.process_streaming(micro_input):
                stopped = True

        if stopped and (self._state.stop_word.id in self._state.active_wake_words):
            _LOGGER.info("Stop word detected")
            self._state.satellite.stop()

    def _on_tap_detected(self) -> None:
        """Callback when tap is detected on the robot.
        
        First tap: Enter continuous conversation mode
        Second tap: Exit continuous conversation mode
        
        NOTE: This is called from the tap_detector background thread.
        We need to be careful about thread safety.
        """
        if self._state is None or self._state.satellite is None:
            return
        
        # Check if we're already in conversation mode (second tap to exit)
        is_in_conversation = self._state.satellite.is_tap_conversation_active()
        
        # Only apply refractory period for ENTERING conversation, not exiting
        # This allows quick exit from conversation mode
        if not is_in_conversation:
            # Check refractory period only when entering conversation
            now = time.monotonic()
            if now - self._last_tap_wakeup < self._state.refractory_seconds:
                _LOGGER.debug("Tap ignored (refractory period)")
                return
            self._last_tap_wakeup = now
        
        try:
            # Trigger tap handling in satellite (handles mode toggle)
            # This sends messages to Home Assistant
            self._state.satellite.wakeup_from_tap()
            
            # Trigger motion feedback (non-blocking)
            if self._motion is not None:
                if is_in_conversation:
                    # Was in conversation, now exiting - return to idle
                    self._motion.on_idle()
                else:
                    # Starting conversation
                    self._motion.on_wakeup()
        except Exception as e:
            _LOGGER.error("Error in tap detection callback: %s", e)
