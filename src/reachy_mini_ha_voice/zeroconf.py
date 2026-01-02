"""Runs mDNS zeroconf service for Home Assistant discovery."""

import logging
import socket
from typing import Optional

_LOGGER = logging.getLogger(__name__)

try:
    from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf
except ImportError:
    _LOGGER.fatal("pip install zeroconf")
    raise

MDNS_TARGET_IP = "224.0.0.251"


class HomeAssistantZeroconf:
    """Zeroconf service for Home Assistant discovery."""

    def __init__(
        self, port: int, name: Optional[str] = None, host: Optional[str] = None
    ) -> None:
        self.port = port
        self.name = name or _get_mac_address()

        if not host:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_sock.setblocking(False)
            try:
                test_sock.connect((MDNS_TARGET_IP, 1))
                host = test_sock.getsockname()[0]
            except Exception:
                host = "127.0.0.1"
            finally:
                test_sock.close()
            _LOGGER.debug("Detected IP: %s", host)

        assert host
        self.host = host
        self._aiozc = AsyncZeroconf()

    async def register_server(self) -> None:
        service_info = AsyncServiceInfo(
            "_esphomelib._tcp.local.",
            f"{self.name}._esphomelib._tcp.local.",
            addresses=[socket.inet_aton(self.host)],
            port=self.port,
            properties={
                "version": "2025.9.0",
                "mac": _get_mac_address(),
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


def _get_mac_address() -> str:
    """Return MAC address formatted as hex with no colons."""
    import uuid
    return "".join(
        ["{:02x}".format((uuid.getnode() >> ele) & 0xFF) for ele in range(0, 8 * 6, 8)][
            ::-1
        ]
    )
