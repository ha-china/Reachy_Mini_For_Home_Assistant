"""Runs mDNS zeroconf services for Home Assistant and Sendspin discovery."""

import asyncio
import logging
import socket
from typing import Callable, Optional, TYPE_CHECKING

from .util import get_mac

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncServiceBrowser

_LOGGER = logging.getLogger(__name__)

try:
    from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf, AsyncServiceBrowser
    ZEROCONF_AVAILABLE = True
except ImportError:
    _LOGGER.fatal("pip install zeroconf")
    raise

MDNS_TARGET_IP = "224.0.0.251"

# Sendspin mDNS service type
SENDSPIN_SERVICE_TYPE = "_sendspin-server._tcp.local."
SENDSPIN_DEFAULT_PATH = "/sendspin"


def get_local_ip() -> str:
    """Get local IP address for mDNS."""
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_sock.setblocking(False)
    try:
        test_sock.connect((MDNS_TARGET_IP, 1))
        return test_sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        test_sock.close()


class HomeAssistantZeroconf:
    """Zeroconf service for Home Assistant discovery."""

    def __init__(
        self, port: int, name: Optional[str] = None, host: Optional[str] = None
    ) -> None:
        self.port = port
        self.name = name or f"reachy-mini-{get_mac()[:6]}"

        if not host:
            host = get_local_ip()
            _LOGGER.debug("Detected IP: %s", host)

        assert host
        self.host = host
        self._aiozc = AsyncZeroconf()

    async def register_server(self) -> None:
        mac_address = get_mac()
        service_info = AsyncServiceInfo(
            "_esphomelib._tcp.local.",
            f"{self.name}._esphomelib._tcp.local.",
            addresses=[socket.inet_aton(self.host)],
            port=self.port,
            properties={
                "version": "2025.9.0",
                "mac": mac_address,
                "board": "reachy_mini",
                "platform": "REACHY_MINI",
                "network": "ethernet",
            },
            server=f"{self.name}.local.",
        )

        await self._aiozc.async_register_service(service_info)
        _LOGGER.debug("Zeroconf discovery enabled: %s", service_info)

    async def unregister_server(self) -> None:
        await self._aiozc.async_close()


class SendspinDiscovery:
    """mDNS discovery for Sendspin servers.
    
    Discovers Sendspin servers on the local network and notifies via callback
    when a server is found.
    """

    def __init__(self, on_server_found: Callable[[str], asyncio.coroutine]) -> None:
        """Initialize Sendspin discovery.
        
        Args:
            on_server_found: Async callback called with server URL when discovered.
        """
        self._on_server_found = on_server_found
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._zeroconf: Optional[AsyncZeroconf] = None
        self._browser: Optional["AsyncServiceBrowser"] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if discovery is running."""
        return self._running

    async def start(self) -> None:
        """Start mDNS discovery for Sendspin servers."""
        if self._running:
            _LOGGER.debug("Sendspin discovery already running")
            return
        
        _LOGGER.info("Starting Sendspin server discovery...")
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._discovery_task = asyncio.create_task(self._discover_loop())

    async def _discover_loop(self) -> None:
        """Background task to discover Sendspin servers."""
        try:
            self._zeroconf = AsyncZeroconf()
            await self._zeroconf.__aenter__()
            
            listener = _SendspinServiceListener(self)
            self._browser = AsyncServiceBrowser(
                self._zeroconf.zeroconf,
                SENDSPIN_SERVICE_TYPE,
                listener,
            )
            
            _LOGGER.info("Sendspin discovery started, waiting for servers...")
            
            # Keep running until stopped
            while self._running:
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            _LOGGER.debug("Sendspin discovery cancelled")
        except Exception as e:
            _LOGGER.error("Sendspin discovery error: %s", e)
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up discovery resources."""
        if self._browser:
            await self._browser.async_cancel()
            self._browser = None
        if self._zeroconf:
            await self._zeroconf.__aexit__(None, None, None)
            self._zeroconf = None
        self._running = False

    async def stop(self) -> None:
        """Stop Sendspin discovery."""
        self._running = False
        if self._discovery_task is not None:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
            self._discovery_task = None
        
        await self._cleanup()
        self._loop = None
        _LOGGER.info("Sendspin discovery stopped")

    async def _handle_service_found(self, url: str) -> None:
        """Handle discovered service."""
        try:
            await self._on_server_found(url)
        except Exception as e:
            _LOGGER.error("Error in Sendspin server callback: %s", e)


class _SendspinServiceListener:
    """Listener for Sendspin server mDNS advertisements."""

    def __init__(self, discovery: SendspinDiscovery) -> None:
        self._discovery = discovery

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
        if self._discovery._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._process_service(zeroconf, service_type, name),
            self._discovery._loop,
        )

    def update_service(self, zeroconf, service_type: str, name: str) -> None:
        """Called when a Sendspin server is updated."""
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type: str, name: str) -> None:
        """Called when a Sendspin server goes offline."""
        _LOGGER.info("Sendspin server removed: %s", name)

    async def _process_service(self, zeroconf, service_type: str, name: str) -> None:
        """Process discovered service and notify callback."""
        try:
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
            
            # Notify via callback
            await self._discovery._handle_service_found(url)
            
        except Exception as e:
            _LOGGER.warning("Error processing Sendspin service %s: %s", name, e)
