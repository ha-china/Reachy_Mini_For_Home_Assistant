"""Audio player using Reachy Mini's media system with automatic Sendspin support.

Sendspin integration allows synchronized multi-room audio playback through
a Sendspin server. Reachy Mini connects as a PLAYER to receive audio streams
from Home Assistant or other Sendspin controllers.

Sendspin can be enabled by the runtime integration when a server is discovered.
The system uses mDNS to discover Sendspin servers on the local network.
"""

from __future__ import annotations

import hashlib
import logging
import socket
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiosendspin.models.core import StreamStartMessage

    from ..protocol.zeroconf import SendspinDiscovery

_LOGGER = logging.getLogger(__name__)

# Movement latency to sync head motion with audio playback
# Audio playback has hardware buffer latency, so we delay head motion to match
# Same as reachy_mini_conversation_app's HeadWobbler.MOVEMENT_LATENCY_S
MOVEMENT_LATENCY_S = 0.2  # 200ms latency between audio start and head movement
SWAY_FRAME_DT_S = 0.05
STREAM_FETCH_CHUNK_SIZE = 2048
UNTHROTTLED_PREROLL_S = 0.35

# Check if aiosendspin is available
try:
    from aiosendspin.client import PCMFormat, SendspinClient
    from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
    from aiosendspin.models.types import AudioCodec, PlayerCommand, Roles

    SENDSPIN_AVAILABLE = True
except Exception as e:
    SENDSPIN_AVAILABLE = False
    _LOGGER.warning("Sendspin unavailable, disabling integration: %s", e)
    # Fallback placeholders to keep runtime annotations safe when Sendspin is unavailable.
    PCMFormat = None  # type: ignore[assignment]
    SendspinClient = None  # type: ignore[assignment]
    ClientHelloPlayerSupport = None  # type: ignore[assignment]
    SupportedAudioFormat = None  # type: ignore[assignment]
    AudioCodec = None  # type: ignore[assignment]
    PlayerCommand = None  # type: ignore[assignment]
    Roles = None  # type: ignore[assignment]


def _get_stable_client_id() -> str:
    """Generate a stable client ID based on machine identity.

    Uses hostname and MAC address to create a consistent ID across restarts.
    """
    try:
        hostname = socket.gethostname()
        # Create a hash of hostname for stability
        hash_input = f"reachy-mini-{hostname}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    except Exception:
        return "reachy-mini-default"


class AudioPlayer:
    """Audio player using Reachy Mini's media system with automatic Sendspin support.

    Supports audio playback modes:
    1. Reachy Mini's built-in media system (default)
    2. Sendspin synchronized multi-room playback (as PLAYER - receives audio)

    When connected to Sendspin as a PLAYER, Reachy Mini receives audio streams
    from Home Assistant or other controllers for synchronized playback.
    """

    def __init__(self, reachy_mini=None, gstreamer_lock=None) -> None:
        """Initialize audio player.

        Args:
            reachy_mini: Reachy Mini SDK instance.
            gstreamer_lock: Threading lock for GStreamer media access (shared across all media operations).
        """
        self.reachy_mini = reachy_mini
        self._gstreamer_lock = gstreamer_lock if gstreamer_lock is not None else threading.Lock()
        self.is_playing = False
        self._playlist: list[str] = []
        self._done_callback: Callable[[], None] | None = None
        self._done_callback_lock = threading.Lock()
        self._duck_volume: float = 0.5
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()
        self._playback_thread: threading.Thread | None = None  # Track active playback thread

        # Speech sway callback for audio-driven head motion
        self._sway_callback: Callable[[dict], None] | None = None

        # Sendspin support (auto-enabled via mDNS discovery)
        # Uses stable client_id so HA recognizes the same device after restart
        self._sendspin_client_id = _get_stable_client_id()
        self._sendspin_client: SendspinClient | None = None
        self._sendspin_enabled = False
        self._sendspin_url: str | None = None
        self._sendspin_discovery: SendspinDiscovery | None = None
        self._sendspin_unsubscribers: list[Callable] = []

        # Audio buffer for Sendspin playback
        self._sendspin_audio_format: PCMFormat | None = None
        self._sendspin_playback_started = False
        self._sendspin_paused = False  # Pause Sendspin when voice assistant is active

    def set_sway_callback(self, callback: Callable[[dict], None] | None) -> None:
        """Set callback for speech-driven sway animation.

        Args:
            callback: Function called with sway dict containing
                      pitch_rad, yaw_rad, roll_rad, x_m, y_m, z_m
        """
        self._sway_callback = callback

    def set_reachy_mini(self, reachy_mini) -> None:
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    # ========== Sendspin Integration (Auto-enabled via mDNS) ==========

    @property
    def sendspin_available(self) -> bool:
        """Check if Sendspin library is available."""
        return SENDSPIN_AVAILABLE

    @property
    def sendspin_enabled(self) -> bool:
        """Check if Sendspin output is enabled and connected."""
        return self._sendspin_enabled and self._sendspin_client is not None

    @property
    def sendspin_url(self) -> str | None:
        """Get current Sendspin server URL."""
        return self._sendspin_url

    def pause_sendspin(self) -> None:
        """Pause Sendspin audio playback.

        Called when voice assistant is activated to prevent audio conflicts.
        Incoming Sendspin audio chunks will be dropped until resumed.
        """
        if self._sendspin_paused:
            return
        self._sendspin_paused = True
        _LOGGER.debug("Sendspin audio paused (voice assistant active)")

    def resume_sendspin(self) -> None:
        """Resume Sendspin audio playback.

        Called when voice assistant returns to idle state.
        """
        if not self._sendspin_paused:
            return
        self._sendspin_paused = False
        self._logged_resample = False  # Reset resample log flag for new stream
        _LOGGER.debug("Sendspin audio resumed")

    async def start_sendspin_discovery(self) -> None:
        """Start mDNS discovery for Sendspin servers.

        This runs in the background and automatically connects when a server is found.
        Called automatically during voice assistant startup.
        """
        if not SENDSPIN_AVAILABLE:
            _LOGGER.debug("aiosendspin not installed, skipping Sendspin discovery")
            return

        if self._sendspin_discovery is not None and self._sendspin_discovery.is_running:
            _LOGGER.debug("Sendspin discovery already running")
            return

        # Import here to avoid circular imports
        from ..protocol.zeroconf import SendspinDiscovery

        _LOGGER.info("Starting Sendspin server discovery...")
        self._sendspin_discovery = SendspinDiscovery(self._on_sendspin_server_found)
        await self._sendspin_discovery.start()

    async def _on_sendspin_server_found(self, server_url: str) -> None:
        """Callback when a Sendspin server is discovered via mDNS.

        Args:
            server_url: WebSocket URL of the discovered server.
        """
        await self._connect_to_server(server_url)

    async def _connect_to_server(self, server_url: str) -> bool:
        """Connect to a discovered Sendspin server as PLAYER.

        Args:
            server_url: WebSocket URL of the Sendspin server.

        Returns:
            True if connected successfully.
        """
        if not SENDSPIN_AVAILABLE:
            return False

        # Already connected to this server
        if self._sendspin_enabled and self._sendspin_url == server_url:
            return True

        # Disconnect from previous server if any
        if self._sendspin_client is not None:
            await self._disconnect_sendspin()

        try:
            # Use stable client_id so HA recognizes the same device after restart
            # Configure player support with audio formats
            # Prioritize 16kHz since ReSpeaker hardware only supports 16kHz output
            # Higher sample rates will be resampled down, causing quality loss
            player_support = ClientHelloPlayerSupport(
                supported_formats=[
                    # Prefer 16kHz (native ReSpeaker sample rate - no resampling needed)
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=16000, bit_depth=16),
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=16000, bit_depth=16),
                    # Also support higher sample rates (will be resampled to 16kHz)
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=48000, bit_depth=16),
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=44100, bit_depth=16),
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=48000, bit_depth=16),
                    SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=44100, bit_depth=16),
                ],
                buffer_capacity=32_000_000,
                supported_commands=[PlayerCommand.VOLUME, PlayerCommand.MUTE],
            )

            self._sendspin_client = SendspinClient(
                client_id=self._sendspin_client_id,
                client_name="Reachy Mini",
                roles=[Roles.PLAYER],  # PLAYER role to receive audio
                player_support=player_support,
            )

            await self._sendspin_client.connect(server_url)

            # Register audio listeners
            self._sendspin_unsubscribers = [
                self._sendspin_client.add_audio_chunk_listener(self._on_sendspin_audio_chunk),
                self._sendspin_client.add_stream_start_listener(self._on_sendspin_stream_start),
                self._sendspin_client.add_stream_end_listener(self._on_sendspin_stream_end),
                self._sendspin_client.add_stream_clear_listener(self._on_sendspin_stream_clear),
            ]

            self._sendspin_url = server_url
            self._sendspin_enabled = True

            _LOGGER.info("Sendspin connected as PLAYER: %s (client_id=%s)", server_url, self._sendspin_client_id)
            return True

        except Exception as e:
            _LOGGER.warning("Failed to connect to Sendspin server %s: %s", server_url, e)
            self._sendspin_client = None
            self._sendspin_enabled = False
            return False

    def _on_sendspin_audio_chunk(self, server_timestamp_us: int, audio_data: bytes, fmt: PCMFormat) -> None:
        """Handle incoming audio chunks from Sendspin server.

        Plays the audio through Reachy Mini's speaker using push_audio_sample().
        Resamples audio if needed (Reachy Mini uses 16kHz).

        Note: Audio is dropped when Sendspin is paused (e.g., during voice assistant interaction).
        """
        # Drop audio when paused (voice assistant is active)
        if self._sendspin_paused:
            return

        try:
            # Store format for potential use
            self._sendspin_audio_format = fmt

            import numpy as np

            # Convert bytes to numpy array based on format
            if fmt.bit_depth == 16:
                dtype = np.int16
                max_val = 32768.0
            elif fmt.bit_depth == 32:
                dtype = np.int32
                max_val = 2147483648.0
            else:
                dtype = np.int16
                max_val = 32768.0

            audio_array = np.frombuffer(audio_data, dtype=dtype)

            # Convert to float32 for playback (SDK expects float32)
            audio_float = audio_array.astype(np.float32) / max_val

            # Clamp values to valid range [-1.0, 1.0] to prevent invalid values
            audio_float = np.clip(audio_float, -1.0, 1.0)

            # Reshape for channels if needed
            if fmt.channels > 1:
                # Reshape to (samples, channels)
                audio_float = audio_float.reshape(-1, fmt.channels)
            else:
                # Mono: reshape to (samples, 1)
                audio_float = audio_float.reshape(-1, 1)

            # Resample if needed (ReSpeaker hardware only supports 16kHz)
            target_sample_rate = self.reachy_mini.media.get_output_audio_samplerate()
            if fmt.sample_rate != target_sample_rate and target_sample_rate > 0:
                import scipy.signal

                # Calculate new length
                new_length = int(len(audio_float) * target_sample_rate / fmt.sample_rate)
                if new_length > 0:
                    audio_float = scipy.signal.resample(audio_float, new_length, axis=0)
                    # Log resampling only once per stream
                    if not hasattr(self, "_logged_resample") or not self._logged_resample:
                        _LOGGER.debug("Resampling Sendspin audio: %d Hz -> %d Hz", fmt.sample_rate, target_sample_rate)
                        self._logged_resample = True

            # Apply volume
            audio_float = audio_float * self._current_volume

            # Ensure media playback is started
            if not self._sendspin_playback_started:
                try:
                    self.reachy_mini.media.start_playing()
                    self._sendspin_playback_started = True
                    _LOGGER.info("Started media playback for Sendspin audio (target: %d Hz)", target_sample_rate)
                except Exception as e:
                    _LOGGER.warning("Failed to start media playback: %s", e)

            # Play through Reachy Mini's media system using push_audio_sample
            # Use GStreamer lock to prevent concurrent access conflicts
            acquired = self._gstreamer_lock.acquire(timeout=0.05)
            if acquired:
                try:
                    self.reachy_mini.media.push_audio_sample(audio_float)
                finally:
                    self._gstreamer_lock.release()
            else:
                _LOGGER.debug("GStreamer lock busy, skipping audio sample")
                audio_backend = getattr(self.reachy_mini.media, "audio", None)
                if audio_backend is not None and hasattr(audio_backend, "clear_output_buffer"):
                    try:
                        audio_backend.clear_output_buffer()
                    except Exception:
                        pass

        except Exception as e:
            _LOGGER.debug("Error playing Sendspin audio: %s", e)

    def _on_sendspin_stream_start(self, message: StreamStartMessage) -> None:
        """Handle stream start from Sendspin server."""
        _LOGGER.debug("Sendspin stream started")
        # No need to clear buffer - just start fresh

    def _on_sendspin_stream_end(self, roles: list[Roles] | None) -> None:
        """Handle stream end from Sendspin server."""
        if roles is None or Roles.PLAYER in roles:
            _LOGGER.debug("Sendspin stream ended")

    def _on_sendspin_stream_clear(self, roles: list[Roles] | None) -> None:
        """Handle stream clear from Sendspin server."""
        if roles is None or Roles.PLAYER in roles:
            _LOGGER.debug("Sendspin stream cleared")
            try:
                self.reachy_mini.media.stop_playing()
                self._sendspin_playback_started = False
            except Exception:
                pass

    async def _disconnect_sendspin(self) -> None:
        """Disconnect from current Sendspin server."""
        # Unsubscribe from listeners
        for unsub in self._sendspin_unsubscribers:
            try:
                unsub()
            except Exception as e:
                _LOGGER.debug("Error during Sendspin unsubscribe: %s", e)
        self._sendspin_unsubscribers.clear()

        if self._sendspin_client is not None:
            try:
                await self._sendspin_client.disconnect()
            except Exception as e:
                _LOGGER.debug("Error disconnecting from Sendspin: %s", e)
            self._sendspin_client = None

        self._sendspin_enabled = False
        self._sendspin_url = None
        self._sendspin_audio_format = None

    async def stop_sendspin(self) -> None:
        """Stop Sendspin discovery and disconnect from server."""
        # Stop discovery
        if self._sendspin_discovery is not None:
            await self._sendspin_discovery.stop()
            self._sendspin_discovery = None

        # Disconnect from server
        await self._disconnect_sendspin()

        # Clear all references to prevent memory leaks
        self._sendspin_client = None
        self._sendspin_url = None
        self._sendspin_audio_format = None
        self._sendspin_enabled = False

        _LOGGER.info("Sendspin stopped")

    # ========== Core Playback Methods ==========

    def play(
        self,
        url: str | list[str],
        done_callback: Callable[[], None] | None = None,
        stop_first: bool = True,
    ) -> None:
        """Play audio from URL(s).

        Args:
            url: Single URL or list of URLs to play.
            done_callback: Called when playback finishes.
            stop_first: Stop current playback before starting new.
        """
        if stop_first:
            self.stop()

        if isinstance(url, str):
            self._playlist = [url]
        else:
            self._playlist = list(url)

        self._done_callback = done_callback
        self._stop_flag.clear()

        # Limit active playback threads to prevent resource exhaustion
        if hasattr(self, "_playback_thread") and self._playback_thread and self._playback_thread.is_alive():
            _LOGGER.warning("Previous playback still active, stopping it")
            self.stop()

        self._play_next()

    def _play_next(self) -> None:
        """Play next item in playlist."""
        if not self._playlist or self._stop_flag.is_set():
            self._on_playback_finished()
            return

        next_url = self._playlist.pop(0)
        _LOGGER.debug("Playing %s", next_url)
        self.is_playing = True

        # Start playback in a thread
        self._playback_thread = threading.Thread(target=self._play_file, args=(next_url,), daemon=True)
        self._playback_thread.start()

    def _play_file(self, file_path: str) -> None:
        """Play an audio file with optional speech-driven sway animation."""
        try:
            # Handle URLs - download first
            if file_path.startswith(("http://", "https://")):
                import requests

                source_url = file_path
                streamed = False
                cached_audio = bytearray()
                content_type = ""

                try:
                    with requests.get(source_url, stream=True, timeout=(5.0, 30.0)) as response:
                        response.raise_for_status()
                        content_type = (response.headers.get("Content-Type") or "").lower()

                        stream_iter = response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE)

                        def caching_iter_content(chunk_size: int = STREAM_FETCH_CHUNK_SIZE):
                            del chunk_size
                            for chunk in stream_iter:
                                if chunk:
                                    cached_audio.extend(chunk)
                                    yield chunk

                        adapted_response = self._iterator_response_adapter(caching_iter_content())

                        # Try true streaming on this single HTTP request.
                        if self._is_pcm_content_type(content_type):
                            _LOGGER.info("TTS playback mode: streaming_pcm")
                            streamed = self._stream_pcm_response(adapted_response, content_type)
                        else:
                            _LOGGER.info("TTS playback mode: streaming_decoded")
                            streamed = self._stream_decoded_response(adapted_response, source_url, content_type)

                        if not streamed:
                            # Keep draining remaining bytes from the SAME request
                            # so one-time URLs are still playable via fallback.
                            for chunk in stream_iter:
                                if chunk:
                                    cached_audio.extend(chunk)

                except Exception as e:
                    _LOGGER.debug("Streaming TTS failed, fallback to memory playback: %s", e)

                if streamed:
                    return

                _LOGGER.info("TTS playback mode: fallback_memory")
                played = self._play_cached_audio(cached_audio, content_type)
                if played:
                    return

                _LOGGER.error("Failed to play cached TTS audio from memory")
                return

            if self._stop_flag.is_set():
                return

            # Play locally using Reachy Mini's media system
            try:
                duration: float | None = None
                sway_frames: list[dict] = []

                # Fast metadata path first to avoid long pre-read latency.
                try:
                    import soundfile as sf

                    info = sf.info(file_path)
                    if info.samplerate > 0 and info.frames > 0:
                        duration = float(info.frames) / float(info.samplerate)
                except Exception:
                    duration = None

                # Optional sway pre-analysis (best effort). If decode/read is expensive
                # or unsupported, keep playback path working without blocking startup.
                if self._sway_callback is not None:
                    try:
                        import soundfile as sf

                        data, sample_rate = sf.read(file_path)
                        if duration is None and sample_rate > 0:
                            duration = len(data) / sample_rate

                        from ..motion.speech_sway import SpeechSwayRT

                        sway = SpeechSwayRT()
                        sway_frames = sway.feed(data, sample_rate)
                    except Exception:
                        sway_frames = []

                # Start playback
                self.reachy_mini.media.play_sound(file_path)

                # Playback loop with sway animation
                # Apply MOVEMENT_LATENCY_S delay to sync head motion with audio
                # (audio playback has hardware buffer latency)
                start_time = time.time()
                frame_duration = 0.05  # 50ms per sway frame (HOP_MS)
                frame_idx = 0

                # Playback loop with sway animation and timeout protection
                # Apply MOVEMENT_LATENCY_S delay to sync head motion with audio
                # (audio playback has hardware buffer latency)
                start_time = time.time()
                frame_duration = 0.05  # 50ms per sway frame (HOP_MS)
                frame_idx = 0
                # If duration unknown, poll SDK playback state when available.
                has_duration = (duration is not None) and (duration > 0)
                duration_s = duration if has_duration else 0.0
                max_duration = (duration_s * 1.5) if has_duration else 60.0
                playback_timeout = start_time + max_duration

                is_playing_fn = getattr(self.reachy_mini.media, "is_playing", None)

                while True:
                    # Check for timeout (safety guard)
                    if time.time() > playback_timeout:
                        _LOGGER.warning("Audio playback timeout (%.1fs), stopping", max_duration)
                        self.reachy_mini.media.stop_playing()
                        break

                    if self._stop_flag.is_set():
                        self.reachy_mini.media.stop_playing()
                        break

                    if has_duration:
                        if (time.time() - start_time) >= duration_s:
                            break
                    elif callable(is_playing_fn):
                        try:
                            if not bool(is_playing_fn()):
                                break
                        except Exception:
                            pass

                    # Apply sway frame if available, with 200ms delay
                    if self._sway_callback and frame_idx < len(sway_frames):
                        elapsed = time.time() - start_time
                        # Apply latency: head motion starts MOVEMENT_LATENCY_S after audio
                        effective_elapsed = max(0, elapsed - MOVEMENT_LATENCY_S)
                        target_frame = int(effective_elapsed / frame_duration)

                        # Skip frames if falling behind (lag compensation)
                        while frame_idx <= target_frame and frame_idx < len(sway_frames):
                            self._sway_callback(sway_frames[frame_idx])
                            frame_idx += 1

                    time.sleep(0.02)  # 20ms sleep for responsive sway

                # Reset sway to zero when done
                if self._sway_callback:
                    self._sway_callback(
                        {
                            "pitch_rad": 0.0,
                            "yaw_rad": 0.0,
                            "roll_rad": 0.0,
                            "x_m": 0.0,
                            "y_m": 0.0,
                            "z_m": 0.0,
                        }
                    )

            except Exception as e:
                _LOGGER.error("Reachy Mini audio failed: %s", e)
                raise

        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            self.is_playing = False
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    @staticmethod
    def _iterator_response_adapter(iterator):
        class _ResponseAdapter:
            def __init__(self, iter_obj) -> None:
                self._iter_obj = iter_obj

            def iter_content(self, chunk_size: int = 8192):
                del chunk_size
                return self._iter_obj

        return _ResponseAdapter(iterator)

    def _play_cached_audio(self, audio_bytes: bytes | bytearray, content_type: str) -> bool:
        if not audio_bytes:
            return False

        audio_data = bytes(audio_bytes)
        mem_iter = (
            audio_data[i : i + STREAM_FETCH_CHUNK_SIZE] for i in range(0, len(audio_data), STREAM_FETCH_CHUNK_SIZE)
        )
        adapted_response = self._iterator_response_adapter(mem_iter)

        if self._is_pcm_content_type(content_type):
            return self._stream_pcm_response(adapted_response, content_type)

        return self._stream_decoded_response(adapted_response, "memory-cache", content_type)

    @staticmethod
    def _is_pcm_content_type(content_type: str) -> bool:
        return ("audio/l16" in content_type) or ("audio/pcm" in content_type) or ("audio/raw" in content_type)

    @staticmethod
    def _parse_pcm_format(content_type: str) -> tuple[int, int]:
        channels = 1
        sample_rate = 16000
        if ";" in content_type:
            for part in content_type.split(";"):
                token = part.strip()
                if token.startswith("channels="):
                    try:
                        channels = max(1, int(token.split("=", 1)[1]))
                    except Exception:
                        pass
                elif token.startswith("rate="):
                    try:
                        sample_rate = max(8000, int(token.split("=", 1)[1]))
                    except Exception:
                        pass
        return channels, sample_rate

    @staticmethod
    def _guess_gst_input_caps(content_type: str) -> str | None:
        ct = (content_type or "").split(";", 1)[0].strip().lower()
        mapping = {
            "audio/mpeg": "audio/mpeg,mpegversion=(int)1",
            "audio/mp3": "audio/mpeg,mpegversion=(int)1",
            "audio/aac": "audio/mpeg,mpegversion=(int)4,stream-format=(string)raw",
            "audio/mp4": "audio/mpeg,mpegversion=(int)4,stream-format=(string)raw",
            "audio/ogg": "application/ogg",
            "application/ogg": "application/ogg",
            "audio/opus": "audio/x-opus",
            "audio/webm": "video/webm",
            "audio/wav": "audio/x-wav",
            "audio/wave": "audio/x-wav",
            "audio/x-wav": "audio/x-wav",
            "audio/flac": "audio/x-flac",
            "audio/x-flac": "audio/x-flac",
        }
        return mapping.get(ct)

    def _ensure_media_playback_started(self) -> bool:
        acquired = self._gstreamer_lock.acquire(timeout=0.3)
        if not acquired:
            return False
        try:
            self.reachy_mini.media.start_playing()
            return True
        except Exception:
            return False
        finally:
            self._gstreamer_lock.release()

    def _push_audio_float(self, audio_float: np.ndarray, max_wait_s: float = 1.0) -> bool:
        deadline = time.monotonic() + max(0.05, max_wait_s)
        while time.monotonic() < deadline:
            if self._stop_flag.is_set():
                return False

            acquired = self._gstreamer_lock.acquire(timeout=0.1)
            if not acquired:
                continue
            try:
                self.reachy_mini.media.push_audio_sample(audio_float)
                return True
            finally:
                self._gstreamer_lock.release()

        return False

    def _stream_pcm_response(self, response, content_type: str) -> bool:
        channels, sample_rate = self._parse_pcm_format(content_type)
        target_sr = self.reachy_mini.media.get_output_audio_samplerate()
        if target_sr <= 0:
            target_sr = 16000

        if not self._ensure_media_playback_started():
            return False

        remainder = b""
        pushed_any = False
        played_frames = 0
        stream_start = time.monotonic()
        sway_ctx = self._init_stream_sway_context()
        bytes_per_frame = 2 * channels

        for chunk in response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE):
            if self._stop_flag.is_set():
                break
            if not chunk:
                continue

            data = remainder + chunk
            usable_len = (len(data) // bytes_per_frame) * bytes_per_frame
            remainder = data[usable_len:]
            if usable_len == 0:
                continue

            pcm = np.frombuffer(data[:usable_len], dtype=np.int16).astype(np.float32) / 32768.0
            pcm = np.clip(pcm * self._current_volume, -1.0, 1.0).reshape(-1, channels)

            if sample_rate != target_sr and target_sr > 0:
                import scipy.signal

                new_len = int(len(pcm) * target_sr / sample_rate)
                if new_len > 0:
                    pcm = scipy.signal.resample(pcm, new_len, axis=0).astype(np.float32, copy=False)

            target_elapsed = played_frames / float(target_sr)
            actual_elapsed = time.monotonic() - stream_start
            if target_elapsed > UNTHROTTLED_PREROLL_S and target_elapsed > actual_elapsed:
                time.sleep(min(0.05, target_elapsed - actual_elapsed))

            if not self._push_audio_float(pcm):
                continue

            pushed_any = True
            played_frames += int(pcm.shape[0])
            self._feed_stream_sway(sway_ctx, pcm, target_sr)

        self._finalize_stream_sway(sway_ctx)
        return pushed_any

    def _stream_decoded_response(self, response, source_url: str, content_type: str) -> bool:
        try:
            import gi

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
        except Exception:
            return False

        try:
            Gst.init(None)
        except Exception:
            pass

        target_sr = self.reachy_mini.media.get_output_audio_samplerate()
        if target_sr <= 0:
            target_sr = 16000

        target_channels = 1
        if not self._ensure_media_playback_started():
            return False

        pipeline = Gst.Pipeline.new("tts_stream_decode")
        appsrc = Gst.ElementFactory.make("appsrc", "src")
        decodebin = Gst.ElementFactory.make("decodebin", "decode")
        audioconvert = Gst.ElementFactory.make("audioconvert", "conv")
        audioresample = Gst.ElementFactory.make("audioresample", "resample")
        capsfilter = Gst.ElementFactory.make("capsfilter", "caps")
        appsink = Gst.ElementFactory.make("appsink", "sink")

        if not all((pipeline, appsrc, decodebin, audioconvert, audioresample, capsfilter, appsink)):
            return False

        target_caps = Gst.Caps.from_string(f"audio/x-raw,format=S16LE,channels={target_channels},rate={target_sr}")
        capsfilter.set_property("caps", target_caps)

        appsrc.set_property("is-live", True)
        appsrc.set_property("format", Gst.Format.BYTES)
        appsrc.set_property("block", False)
        appsrc.set_property("do-timestamp", True)

        src_caps = self._guess_gst_input_caps(content_type)
        if src_caps:
            try:
                appsrc.set_property("caps", Gst.Caps.from_string(src_caps))
            except Exception:
                pass

        try:
            decodebin.set_property("caps", Gst.Caps.from_string("audio/x-raw"))
        except Exception:
            pass

        appsink.set_property("emit-signals", False)
        appsink.set_property("sync", False)
        # Keep all decoded audio for TTS completion. Dropping buffers can cause
        # a short "blip" then silence on fast decoders.
        appsink.set_property("max-buffers", 0)
        appsink.set_property("drop", False)

        pipeline.add(appsrc)
        pipeline.add(decodebin)
        pipeline.add(audioconvert)
        pipeline.add(audioresample)
        pipeline.add(capsfilter)
        pipeline.add(appsink)

        if not appsrc.link(decodebin):
            return False
        if not audioconvert.link(audioresample):
            return False
        if not audioresample.link(capsfilter):
            return False
        if not capsfilter.link(appsink):
            return False

        audio_state = {"linked": False}

        def on_pad_added(_decodebin, pad) -> None:
            sink_pad = audioconvert.get_static_pad("sink")
            if sink_pad is None or sink_pad.is_linked():
                return

            caps_obj = pad.get_current_caps() or pad.query_caps(None)
            if caps_obj is None:
                return
            if caps_obj.to_string().startswith("audio/"):
                try:
                    result = pad.link(sink_pad)
                    if result == Gst.PadLinkReturn.OK:
                        audio_state["linked"] = True
                except Exception:
                    pass

        decodebin.connect("pad-added", on_pad_added)

        pushed_any = False
        played_frames = 0
        stream_start = time.monotonic()
        sway_ctx = self._init_stream_sway_context()
        bytes_per_frame = 2 * target_channels
        feed_done = threading.Event()
        decode_error = False

        def writer() -> None:
            try:
                for chunk in response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE):
                    if self._stop_flag.is_set():
                        break
                    if not chunk:
                        continue
                    gst_buffer = Gst.Buffer.new_allocate(None, len(chunk), None)
                    if gst_buffer is None:
                        continue
                    gst_buffer.fill(0, chunk)
                    ret = appsrc.emit("push-buffer", gst_buffer)
                    if ret not in (Gst.FlowReturn.OK, Gst.FlowReturn.FLUSHING):
                        _LOGGER.debug("appsrc push-buffer returned %s", ret)
                        break
            except Exception:
                pass
            finally:
                feed_done.set()
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass

        try:
            state_ret = pipeline.set_state(Gst.State.PLAYING)
            if state_ret == Gst.StateChangeReturn.FAILURE:
                _LOGGER.debug("Failed to set GStreamer decode pipeline PLAYING for URL=%s", source_url)
                return False

            writer_thread = threading.Thread(target=writer, daemon=True)
            writer_thread.start()

            remainder = b""
            timeout_ns = 20_000_000  # 20ms
            bus = pipeline.get_bus()
            eos_seen = False
            eos_drain_empty_polls = 0

            while True:
                sample = appsink.emit("try-pull-sample", timeout_ns)
                if sample is not None:
                    eos_drain_empty_polls = 0
                    try:
                        gst_buffer = sample.get_buffer()
                        if gst_buffer is None:
                            continue
                        ok, map_info = gst_buffer.map(Gst.MapFlags.READ)
                        if not ok:
                            continue
                        try:
                            raw = bytes(map_info.data)
                        finally:
                            gst_buffer.unmap(map_info)

                        data = remainder + raw
                        usable_len = (len(data) // bytes_per_frame) * bytes_per_frame
                        remainder = data[usable_len:]
                        if usable_len == 0:
                            continue

                        pcm = np.frombuffer(data[:usable_len], dtype=np.int16).astype(np.float32) / 32768.0
                        pcm = np.clip(pcm * self._current_volume, -1.0, 1.0).reshape(-1, target_channels)

                        target_elapsed = played_frames / float(target_sr)
                        actual_elapsed = time.monotonic() - stream_start
                        if target_elapsed > UNTHROTTLED_PREROLL_S and target_elapsed > actual_elapsed:
                            time.sleep(min(0.05, target_elapsed - actual_elapsed))

                        if not self._push_audio_float(pcm):
                            continue

                        pushed_any = True
                        played_frames += int(pcm.shape[0])
                        self._feed_stream_sway(sway_ctx, pcm, target_sr)
                    finally:
                        sample = None
                elif eos_seen and feed_done.is_set():
                    eos_drain_empty_polls += 1

                msg = bus.timed_pop_filtered(
                    0,
                    Gst.MessageType.ERROR | Gst.MessageType.EOS,
                )
                if msg is not None:
                    if msg.type == Gst.MessageType.EOS:
                        eos_seen = True
                    elif msg.type == Gst.MessageType.ERROR:
                        err, debug = msg.parse_error()
                        err_text = str(err).lower()
                        debug_text = str(debug).lower() if debug is not None else ""

                        # Some demuxers report non-audio not-linked warnings as ERROR.
                        # If audio pad is already linked, keep streaming instead of aborting.
                        if audio_state["linked"] and (
                            "not-linked" in err_text
                            or "not-linked" in debug_text
                            or "streaming stopped, reason not-linked" in debug_text
                        ):
                            continue

                        decode_error = True
                        _LOGGER.debug(
                            "GStreamer decode error content-type=%s url=%s err=%s debug=%s",
                            content_type or "unknown",
                            source_url,
                            err,
                            debug,
                        )
                        break

                if feed_done.is_set() and eos_seen:
                    sink_eos = False
                    try:
                        sink_eos_fn = getattr(appsink, "is_eos", None)
                        if callable(sink_eos_fn):
                            sink_eos = bool(sink_eos_fn())
                    except Exception:
                        sink_eos = False

                    # End playback only after upstream finished feeding and
                    # appsink has drained decoded buffers.
                    if sink_eos and eos_drain_empty_polls >= 2:
                        break

                    # Fallback guard in case is_eos is unavailable.
                    if eos_drain_empty_polls >= 100:
                        break

                if self._stop_flag.is_set():
                    break

            writer_thread.join(timeout=1.0)

            # Streaming is successful only if it reached a clean EOS without decode error.
            # If decode failed (typically unsupported stream format), force fallback.
            if self._stop_flag.is_set():
                return True

            completed_cleanly = feed_done.is_set() and eos_seen and (not decode_error)
            if not completed_cleanly:
                return False

        except Exception as e:
            _LOGGER.debug("Error during GStreamer stream decode: %s", e)
            pushed_any = False
        finally:
            self._finalize_stream_sway(sway_ctx)
            try:
                pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass

        return pushed_any

    def _init_stream_sway_context(self) -> dict | None:
        if self._sway_callback is None:
            return None
        try:
            from ..motion.speech_sway import SpeechSwayRT

            return {
                "sway": SpeechSwayRT(),
                "base_ts": time.monotonic(),
                "frames_done": 0,
            }
        except Exception:
            return None

    def _feed_stream_sway(self, ctx: dict | None, pcm: np.ndarray, sample_rate: int) -> None:
        if ctx is None or self._sway_callback is None:
            return
        try:
            sway = ctx["sway"]
            results = sway.feed(pcm, sample_rate)
            if not results:
                return

            base_ts = float(ctx["base_ts"])
            for item in results:
                target = base_ts + MOVEMENT_LATENCY_S + ctx["frames_done"] * SWAY_FRAME_DT_S
                now = time.monotonic()
                if target > now:
                    time.sleep(min(0.02, target - now))

                self._sway_callback(item)
                ctx["frames_done"] += 1
        except Exception:
            pass

    def _finalize_stream_sway(self, ctx: dict | None) -> None:
        if ctx is None or self._sway_callback is None:
            return
        try:
            self._sway_callback(
                {
                    "pitch_rad": 0.0,
                    "yaw_rad": 0.0,
                    "roll_rad": 0.0,
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "z_m": 0.0,
                }
            )
        except Exception:
            pass

    def _on_playback_finished(self) -> None:
        """Called when playback is finished."""
        self.is_playing = False
        todo_callback: Callable[[], None] | None = None

        with self._done_callback_lock:
            if self._done_callback:
                todo_callback = self._done_callback
                self._done_callback = None

        if todo_callback:
            try:
                todo_callback()
            except Exception:
                _LOGGER.exception("Unexpected error running done callback")

    def pause(self) -> None:
        """Pause playback.

        Stops current audio output but preserves playlist for resume.
        """
        self._stop_flag.set()
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass
        self.is_playing = False

    def resume_playback(self) -> None:
        """Resume playback from where it was paused."""
        self._stop_flag.clear()
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        """Stop playback and clear playlist."""
        self._stop_flag.set()

        # Stop Reachy Mini playback
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass

        # Wait for playback thread to finish (with timeout)
        if self._playback_thread and self._playback_thread.is_alive():
            try:
                self._playback_thread.join(timeout=2.0)
                if self._playback_thread.is_alive():
                    _LOGGER.warning("Playback thread did not stop in time")
            except Exception:
                pass
            self._playback_thread = None

        self._playlist.clear()
        self.is_playing = False

    def __del__(self) -> None:
        """Cleanup on garbage collection to prevent listener leaks."""
        try:
            # Force cleanup of Sendspin listeners to prevent memory leaks
            for unsub in self._sendspin_unsubscribers:
                try:
                    unsub()
                except Exception:
                    pass
            self._sendspin_unsubscribers.clear()
            self._sendspin_client = None
        except Exception:
            pass

    def duck(self) -> None:
        """Reduce volume for announcements."""
        self._current_volume = self._duck_volume

    def unduck(self) -> None:
        """Restore normal volume."""
        self._current_volume = self._unduck_volume

    def set_volume(self, volume: int) -> None:
        """Set volume level (0-100)."""
        volume = max(0, min(100, volume))
        self._unduck_volume = volume / 100.0
        self._duck_volume = self._unduck_volume / 2
        self._current_volume = self._unduck_volume

    def suspend(self) -> None:
        """Suspend the audio player for sleep mode.

        Stops any current playback and clears the playlist.
        """
        _LOGGER.info("Suspending AudioPlayer for sleep...")

        # Stop any current playback
        self.stop()

        # Clear sway callback to release reference
        self._sway_callback = None

        _LOGGER.info("AudioPlayer suspended")

    def resume(self) -> None:
        """Resume the audio player after sleep."""
        _LOGGER.info("Resuming AudioPlayer from sleep...")

        # Nothing specific to restore - audio player is stateless
        # Just ensure flags are reset
        self._stop_flag.clear()

        _LOGGER.info("AudioPlayer resumed")
