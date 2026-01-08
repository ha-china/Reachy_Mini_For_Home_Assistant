"""Audio player using Reachy Mini's media system with automatic Sendspin support.

Sendspin integration allows synchronized multi-room audio playback through
a Sendspin server. Reachy Mini connects as a PLAYER to receive audio streams
from Home Assistant or other Sendspin controllers.

Sendspin is automatically enabled by default - no user configuration needed.
The system uses mDNS to discover Sendspin servers on the local network.
"""

import asyncio
import hashlib
import logging
import socket
import tempfile
import threading
import time
from collections.abc import Callable
from typing import List, Optional, Union

_LOGGER = logging.getLogger(__name__)

# Check if aiosendspin is available
try:
    from aiosendspin.client import SendspinClient, PCMFormat
    from aiosendspin.models.types import Roles, AudioCodec, PlayerCommand
    from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
    from aiosendspin.models.core import StreamStartMessage
    SENDSPIN_AVAILABLE = True
except ImportError:
    SENDSPIN_AVAILABLE = False
    _LOGGER.debug("aiosendspin not installed, Sendspin support disabled")

# Check if zeroconf is available for mDNS discovery
try:
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    _LOGGER.debug("zeroconf not installed, Sendspin auto-discovery disabled")


# Sendspin mDNS service type
SENDSPIN_SERVICE_TYPE = "_sendspin-server._tcp.local."
SENDSPIN_DEFAULT_PATH = "/sendspin"


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
    3. Sounddevice fallback (when Reachy Mini not available)
    
    When connected to Sendspin as a PLAYER, Reachy Mini receives audio streams
    from Home Assistant or other controllers for synchronized playback.
    """

    def __init__(self, reachy_mini=None) -> None:
        """Initialize audio player.
        
        Args:
            reachy_mini: Reachy Mini SDK instance.
        """
        self.reachy_mini = reachy_mini
        self.is_playing = False
        self._playlist: List[str] = []
        self._done_callback: Optional[Callable[[], None]] = None
        self._done_callback_lock = threading.Lock()
        self._duck_volume: float = 0.5
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()
        
        # Sendspin support (auto-enabled via mDNS discovery)
        # Uses stable client_id so HA recognizes the same device after restart
        self._sendspin_client_id = _get_stable_client_id()
        self._sendspin_client: Optional["SendspinClient"] = None
        self._sendspin_enabled = False
        self._sendspin_url: Optional[str] = None
        self._sendspin_loop: Optional[asyncio.AbstractEventLoop] = None
        self._sendspin_discovery_task: Optional[asyncio.Task] = None
        self._sendspin_zeroconf: Optional["AsyncZeroconf"] = None
        self._sendspin_browser: Optional["AsyncServiceBrowser"] = None
        self._sendspin_unsubscribers: List[Callable] = []
        
        # Audio buffer for Sendspin playback
        self._sendspin_audio_format: Optional["PCMFormat"] = None
        self._sendspin_playback_started = False

    def set_reachy_mini(self, reachy_mini) -> None:
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    # ========== Sendspin Integration (Auto-enabled via mDNS) ==========

    @property
    def sendspin_available(self) -> bool:
        """Check if Sendspin library is available."""
        return SENDSPIN_AVAILABLE and ZEROCONF_AVAILABLE

    @property
    def sendspin_enabled(self) -> bool:
        """Check if Sendspin output is enabled and connected."""
        return self._sendspin_enabled and self._sendspin_client is not None

    @property
    def sendspin_url(self) -> Optional[str]:
        """Get current Sendspin server URL."""
        return self._sendspin_url

    async def start_sendspin_discovery(self) -> None:
        """Start mDNS discovery for Sendspin servers.
        
        This runs in the background and automatically connects when a server is found.
        Called automatically during voice assistant startup.
        """
        if not SENDSPIN_AVAILABLE:
            _LOGGER.debug("aiosendspin not installed, skipping Sendspin discovery")
            return
        
        if not ZEROCONF_AVAILABLE:
            _LOGGER.debug("zeroconf not installed, skipping Sendspin discovery")
            return
        
        if self._sendspin_discovery_task is not None:
            _LOGGER.debug("Sendspin discovery already running")
            return
        
        _LOGGER.info("Starting Sendspin server discovery...")
        self._sendspin_loop = asyncio.get_running_loop()
        self._sendspin_discovery_task = asyncio.create_task(self._discover_and_connect())

    async def _discover_and_connect(self) -> None:
        """Background task to discover and connect to Sendspin servers."""
        try:
            self._sendspin_zeroconf = AsyncZeroconf()
            await self._sendspin_zeroconf.__aenter__()
            
            # Create a listener for Sendspin services
            listener = _SendspinServiceListener(self)
            self._sendspin_browser = AsyncServiceBrowser(
                self._sendspin_zeroconf.zeroconf,
                SENDSPIN_SERVICE_TYPE,
                listener,
            )
            
            _LOGGER.info("Sendspin discovery started, waiting for servers...")
            
            # Keep running until stopped
            while True:
                await asyncio.sleep(60)  # Check periodically
                
        except asyncio.CancelledError:
            _LOGGER.debug("Sendspin discovery cancelled")
        except Exception as e:
            _LOGGER.error("Sendspin discovery error: %s", e)
        finally:
            await self._cleanup_discovery()

    async def _cleanup_discovery(self) -> None:
        """Clean up discovery resources."""
        if self._sendspin_browser:
            await self._sendspin_browser.async_cancel()
            self._sendspin_browser = None
        if self._sendspin_zeroconf:
            await self._sendspin_zeroconf.__aexit__(None, None, None)
            self._sendspin_zeroconf = None

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
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=2, sample_rate=16000, bit_depth=16
                    ),
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=1, sample_rate=16000, bit_depth=16
                    ),
                    # Also support higher sample rates (will be resampled to 16kHz)
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=2, sample_rate=48000, bit_depth=16
                    ),
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=2, sample_rate=44100, bit_depth=16
                    ),
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=1, sample_rate=48000, bit_depth=16
                    ),
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM, channels=1, sample_rate=44100, bit_depth=16
                    ),
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
            
            _LOGGER.info("Sendspin connected as PLAYER: %s (client_id=%s)", 
                        server_url, self._sendspin_client_id)
            return True
            
        except Exception as e:
            _LOGGER.warning("Failed to connect to Sendspin server %s: %s", server_url, e)
            self._sendspin_client = None
            self._sendspin_enabled = False
            return False

    def _on_sendspin_audio_chunk(self, server_timestamp_us: int, audio_data: bytes, fmt: "PCMFormat") -> None:
        """Handle incoming audio chunks from Sendspin server.
        
        Plays the audio through Reachy Mini's speaker using push_audio_sample().
        Resamples audio if needed (Reachy Mini uses 16kHz).
        """
        if self.reachy_mini is None:
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
                    if not hasattr(self, '_logged_resample') or not self._logged_resample:
                        _LOGGER.debug("Resampling Sendspin audio: %d Hz -> %d Hz", 
                                     fmt.sample_rate, target_sample_rate)
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
            self.reachy_mini.media.push_audio_sample(audio_float)
            
        except Exception as e:
            _LOGGER.debug("Error playing Sendspin audio: %s", e)

    def _on_sendspin_stream_start(self, message: "StreamStartMessage") -> None:
        """Handle stream start from Sendspin server."""
        _LOGGER.debug("Sendspin stream started")
        # No need to clear buffer - just start fresh

    def _on_sendspin_stream_end(self, roles: Optional[List[Roles]]) -> None:
        """Handle stream end from Sendspin server."""
        if roles is None or Roles.PLAYER in roles:
            _LOGGER.debug("Sendspin stream ended")

    def _on_sendspin_stream_clear(self, roles: Optional[List[Roles]]) -> None:
        """Handle stream clear from Sendspin server."""
        if roles is None or Roles.PLAYER in roles:
            _LOGGER.debug("Sendspin stream cleared")
            if self.reachy_mini is not None:
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
            except Exception:
                pass
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
        # Cancel discovery task
        if self._sendspin_discovery_task is not None:
            self._sendspin_discovery_task.cancel()
            try:
                await self._sendspin_discovery_task
            except asyncio.CancelledError:
                pass
            self._sendspin_discovery_task = None
        
        # Disconnect from server
        await self._disconnect_sendspin()
        self._sendspin_loop = None
        
        _LOGGER.info("Sendspin stopped")


    # ========== Core Playback Methods ==========

    def play(
        self,
        url: Union[str, List[str]],
        done_callback: Optional[Callable[[], None]] = None,
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
        thread = threading.Thread(target=self._play_file, args=(next_url,), daemon=True)
        thread.start()

    def _play_file(self, file_path: str) -> None:
        """Play an audio file."""
        try:
            # Handle URLs - download first
            if file_path.startswith(("http://", "https://")):
                import urllib.request
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    urllib.request.urlretrieve(file_path, tmp.name)
                    file_path = tmp.name

            if self._stop_flag.is_set():
                return

            duration = None

            # Play locally using Reachy Mini's media system
            if self.reachy_mini is not None:
                try:
                    self.reachy_mini.media.play_sound(file_path)

                    # Calculate duration
                    import soundfile as sf
                    data, sample_rate = sf.read(file_path)
                    duration = len(data) / sample_rate

                    # Wait for playback to complete
                    start_time = time.time()
                    while time.time() - start_time < duration:
                        if self._stop_flag.is_set():
                            self.reachy_mini.media.stop_playing()
                            break
                        time.sleep(0.1)

                except Exception as e:
                    _LOGGER.warning("Reachy Mini audio failed, falling back: %s", e)
                    self._play_file_fallback(file_path)
            else:
                self._play_file_fallback(file_path)

        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            self.is_playing = False
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    def _play_file_fallback(self, file_path: str) -> None:
        """Fallback to sounddevice for audio playback."""
        import sounddevice as sd
        import soundfile as sf

        data, samplerate = sf.read(file_path)
        data = data * self._current_volume

        if not self._stop_flag.is_set():
            sd.play(data, samplerate)
            sd.wait()

    def _on_playback_finished(self) -> None:
        """Called when playback is finished."""
        self.is_playing = False
        todo_callback: Optional[Callable[[], None]] = None

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
        """Pause playback."""
        self.is_playing = False

    def resume(self) -> None:
        """Resume playback."""
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        """Stop playback and clear playlist."""
        self._stop_flag.set()
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.stop_playing()
            except Exception:
                pass
        self._playlist.clear()
        self.is_playing = False

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


# ========== Sendspin mDNS Service Listener ==========

class _SendspinServiceListener:
    """Listener for Sendspin server mDNS advertisements."""

    def __init__(self, audio_player: AudioPlayer) -> None:
        self._audio_player = audio_player
        self._loop = audio_player._sendspin_loop

    def _build_url(self, host: str, port: int, properties: dict) -> str:
        """Build WebSocket URL from service info."""
        path_raw = properties.get(b"path")
        path = path_raw.decode("utf-8", "ignore") if isinstance(path_raw, bytes) else SENDSPIN_DEFAULT_PATH
        if not path:
            path = SENDSPIN_DEFAULT_PATH
        if not path.startswith("/"):
            path = "/" + path
        host_fmt = f"[{host}]" if ":" in host else host
        return f"ws://{host_fmt}:{port}{path}"

    def add_service(self, zeroconf, service_type: str, name: str) -> None:
        """Called when a Sendspin server is discovered."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._process_service(zeroconf, service_type, name),
            self._loop,
        )

    def update_service(self, zeroconf, service_type: str, name: str) -> None:
        """Called when a Sendspin server is updated."""
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type: str, name: str) -> None:
        """Called when a Sendspin server goes offline."""
        _LOGGER.info("Sendspin server removed: %s", name)

    async def _process_service(self, zeroconf, service_type: str, name: str) -> None:
        """Process discovered service and connect."""
        try:
            from zeroconf.asyncio import AsyncZeroconf
            
            # Get service info
            azc = AsyncZeroconf(zc=zeroconf)
            info = await azc.async_get_service_info(service_type, name)
            
            if info is None or info.port is None:
                return
            
            addresses = info.parsed_addresses()
            if not addresses:
                return
            
            host = addresses[0]
            url = self._build_url(host, info.port, info.properties)
            
            _LOGGER.info("Discovered Sendspin server: %s at %s", name, url)
            
            # Auto-connect to the server
            await self._audio_player._connect_to_server(url)
            
        except Exception as e:
            _LOGGER.warning("Error processing Sendspin service %s: %s", name, e)
