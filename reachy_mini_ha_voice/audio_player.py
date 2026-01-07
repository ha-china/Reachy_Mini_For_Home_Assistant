"""Audio player using Reachy Mini's media system with automatic Sendspin support.

Sendspin integration allows synchronized multi-room audio playback through
a Sendspin server. When a Sendspin server is discovered via mDNS, TTS and 
media audio will be automatically sent to the server for distribution to 
all connected players.

Sendspin is automatically enabled by default - no user configuration needed.
The system uses mDNS to discover Sendspin servers on the local network.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import List, Optional, Union

_LOGGER = logging.getLogger(__name__)

# Check if aiosendspin is available
try:
    from aiosendspin.client import SendspinClient
    from aiosendspin.models.types import Roles
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


class AudioPlayer:
    """Audio player using Reachy Mini's media system with automatic Sendspin output.
    
    Supports three audio output modes:
    1. Reachy Mini's built-in media system (default)
    2. Sendspin synchronized multi-room playback (auto-enabled via mDNS discovery)
    3. Sounddevice fallback (when Reachy Mini not available)
    
    Sendspin is automatically enabled when a server is discovered on the network.
    Audio is sent to both the local speaker AND the Sendspin server for 
    synchronized playback across multiple devices.
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
        self._sendspin_client: Optional["SendspinClient"] = None
        self._sendspin_enabled = False
        self._sendspin_url: Optional[str] = None
        self._sendspin_loop: Optional[asyncio.AbstractEventLoop] = None
        self._sendspin_discovery_task: Optional[asyncio.Task] = None
        self._sendspin_zeroconf: Optional["AsyncZeroconf"] = None
        self._sendspin_browser: Optional["AsyncServiceBrowser"] = None

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
        """Connect to a discovered Sendspin server.
        
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
            import uuid
            client_id = str(uuid.uuid4())
            
            self._sendspin_client = SendspinClient(
                client_id=client_id,
                client_name="Reachy Mini",
                roles=[Roles.CONTROLLER],
            )
            
            await self._sendspin_client.connect(server_url)
            
            self._sendspin_url = server_url
            self._sendspin_enabled = True
            
            _LOGGER.info("Sendspin connected: %s", server_url)
            return True
            
        except Exception as e:
            _LOGGER.warning("Failed to connect to Sendspin server %s: %s", server_url, e)
            self._sendspin_client = None
            self._sendspin_enabled = False
            return False

    async def _disconnect_sendspin(self) -> None:
        """Disconnect from current Sendspin server."""
        if self._sendspin_client is not None:
            try:
                await self._sendspin_client.disconnect()
            except Exception as e:
                _LOGGER.debug("Error disconnecting from Sendspin: %s", e)
            self._sendspin_client = None
        
        self._sendspin_enabled = False
        self._sendspin_url = None

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

    def _send_audio_to_sendspin(self, audio_data: bytes, sample_rate: int, channels: int) -> bool:
        """Send audio data to Sendspin server (thread-safe).
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed).
            sample_rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            
        Returns:
            True if audio was sent successfully.
        """
        if not self._sendspin_enabled or self._sendspin_client is None:
            return False
        
        if self._sendspin_loop is None:
            return False

        try:
            # Send audio chunk to Sendspin server
            # The server will distribute to all connected players
            future = asyncio.run_coroutine_threadsafe(
                self._sendspin_client.send_audio(
                    audio_data,
                    sample_rate=sample_rate,
                    channels=channels,
                    bit_depth=16,
                ),
                self._sendspin_loop,
            )
            future.result(timeout=5.0)
            return True
        except Exception as e:
            _LOGGER.warning("Failed to send audio to Sendspin: %s", e)
            return False

    def _clear_sendspin_stream(self) -> None:
        """Clear Sendspin audio stream (thread-safe)."""
        if not self._sendspin_enabled or self._sendspin_client is None:
            return
        
        if self._sendspin_loop is None:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._sendspin_client.clear_stream(),
                self._sendspin_loop,
            )
        except Exception as e:
            _LOGGER.debug("Error clearing Sendspin stream: %s", e)


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

            # Read audio file for Sendspin (if enabled)
            audio_data = None
            sample_rate = None
            duration = None
            
            if self._sendspin_enabled:
                try:
                    import soundfile as sf
                    import numpy as np
                    
                    data, sample_rate = sf.read(file_path, dtype='int16')
                    
                    # Convert to mono if stereo
                    if len(data.shape) > 1:
                        data = np.mean(data, axis=1).astype(np.int16)
                    
                    # Apply volume
                    data = (data * self._current_volume).astype(np.int16)
                    audio_data = data.tobytes()
                    duration = len(data) / sample_rate
                    
                    # Send to Sendspin server
                    self._send_audio_to_sendspin(audio_data, sample_rate, channels=1)
                except Exception as e:
                    _LOGGER.warning("Failed to send audio to Sendspin: %s", e)

            # Play locally using Reachy Mini's media system
            if self.reachy_mini is not None:
                try:
                    self.reachy_mini.media.play_sound(file_path)

                    # Calculate duration if not already done
                    if duration is None:
                        import soundfile as sf
                        data, sample_rate = sf.read(file_path)
                        duration = len(data) / sample_rate

                    # Wait for playback to complete
                    start_time = time.time()
                    while time.time() - start_time < duration:
                        if self._stop_flag.is_set():
                            self.reachy_mini.media.clear_output_buffer()
                            self._clear_sendspin_stream()
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
                self.reachy_mini.media.clear_output_buffer()
            except Exception:
                pass
        self._clear_sendspin_stream()
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
